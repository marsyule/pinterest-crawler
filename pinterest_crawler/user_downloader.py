"""Batch orchestration for downloading a user's created feed and saved boards."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Protocol

from pinterest_crawler.config import RuntimeConfig
from pinterest_crawler.created_downloader import crawl_created_feed
from pinterest_crawler.downloader import crawl_board
from pinterest_crawler.http_client import PinterestHttpClient
from pinterest_crawler.manifest import load_board_manifest, load_user_manifest, save_user_manifest
from pinterest_crawler.models import (
    BoardManifest,
    CrawlStatus,
    UserTargetManifestEntry,
    UserBoardStatus,
    UserManifest,
)
from pinterest_crawler.user_boards import discover_user_boards, normalize_user_url


class UserProfileClient(Protocol):
    """HTTP behavior needed to fetch a Pinterest user profile page."""

    def fetch_user_html(self, user_url: str) -> str:
        """Fetch user profile HTML."""


class CreatedCrawler(Protocol):
    """Callable contract for created-feed downloads."""

    def __call__(
        self,
        created_url: str,
        output_dir: Path,
        config: RuntimeConfig,
        *,
        dry_run: bool,
        use_playwright: bool,
        client: PinterestHttpClient | None = None,
    ) -> BoardManifest:
        """Download one created feed."""


class SavedBoardCrawler(Protocol):
    """Callable contract for saved-board downloads."""

    def __call__(
        self,
        board_url: str,
        output_dir: Path,
        config: RuntimeConfig,
        *,
        dry_run: bool,
        use_playwright: bool,
        client: PinterestHttpClient | None = None,
    ) -> BoardManifest:
        """Download one saved board."""


def crawl_user_boards(
    user_url: str,
    output_dir: Path,
    config: RuntimeConfig,
    *,
    dry_run: bool = False,
    use_playwright: bool = True,
    client: UserProfileClient | PinterestHttpClient | None = None,
    created_crawler: CreatedCrawler | None = None,
    board_crawler: SavedBoardCrawler | None = None,
) -> UserManifest:
    """Download a user's created feed and public saved boards.

    Args:
        user_url: Pinterest user profile URL.
        output_dir: Root directory for user output directories.
        config: Runtime crawl configuration.
        dry_run: Scan only when true.
        use_playwright: Whether saved-board scans may use Playwright fallback.
        client: Optional HTTP client for tests.
        created_crawler: Optional callable replacing `crawl_created_feed` in tests.
        board_crawler: Optional callable replacing `crawl_board` in tests.

    Returns:
        Updated user manifest.
    """

    manifest_path = output_dir / "user_manifest.json"
    owns_client = client is None
    profile_client = client or PinterestHttpClient(config=config)
    created_func: CreatedCrawler = (
        crawl_created_feed if created_crawler is None else created_crawler
    )
    board_func: SavedBoardCrawler = crawl_board if board_crawler is None else board_crawler

    try:
        if manifest_path.exists():
            load_user_manifest(manifest_path)

        user_manifest = _discover_targets(user_url, output_dir, profile_client)
        save_user_manifest(manifest_path, user_manifest)

        targets: list[UserTargetManifestEntry] = []
        for entry in user_manifest.targets:
            updated = _process_target_entry(
                entry,
                output_dir,
                config,
                dry_run=dry_run,
                use_playwright=use_playwright,
                client=client if isinstance(client, PinterestHttpClient) else None,
                created_crawler=created_func,
                board_crawler=board_func,
            )
            targets.append(updated)
            user_manifest = replace(
                user_manifest,
                targets=targets + user_manifest.targets[len(targets) :],
                status=_user_status(
                    targets + user_manifest.targets[len(targets) :],
                    dry_run=dry_run,
                ),
                error=None,
            )
            save_user_manifest(manifest_path, user_manifest)

        final = replace(
            user_manifest,
            targets=targets,
            status=_user_status(targets, dry_run=dry_run),
            error=None,
        )
        save_user_manifest(manifest_path, final)
        return final
    except Exception as exc:
        failed = UserManifest(
            user_url=user_url,
            username=_username_from_url(user_url),
            discovery_status="failed",
            status="failed",
            error=str(exc),
            targets=[],
        )
        save_user_manifest(manifest_path, failed)
        return failed
    finally:
        if owns_client and isinstance(profile_client, PinterestHttpClient):
            profile_client.close()


def _discover_targets(
    user_url: str,
    output_dir: Path,
    client: UserProfileClient,
) -> UserManifest:
    output_dir.mkdir(parents=True, exist_ok=True)
    normalized = normalize_user_url(user_url)
    user_html = client.fetch_user_html(normalized.user_url)
    profile = discover_user_boards(user_html, normalized.user_url)
    entries = [_created_entry(normalized.created_url)] + [
        _entry_for_board(board) for board in profile.boards
    ]
    return UserManifest(
        user_url=normalized.user_url,
        username=profile.username,
        discovery_status="complete",
        status="not_started" if entries else "complete",
        error=None,
        targets=entries,
        pinterest_metadata=profile.pinterest_metadata,
    )


def _process_target_entry(
    entry: UserTargetManifestEntry,
    output_dir: Path,
    config: RuntimeConfig,
    *,
    dry_run: bool,
    use_playwright: bool,
    client: PinterestHttpClient | None,
    created_crawler: CreatedCrawler,
    board_crawler: SavedBoardCrawler,
) -> UserTargetManifestEntry:
    manifest_path = _resolve_manifest_path(output_dir, entry.manifest_path)

    expected_manifest_id = entry.target_id if entry.kind == "saved_board" else None
    existing = _load_matching_board_manifest(manifest_path, expected_manifest_id)
    if existing is not None and _target_entry_status(existing, dry_run=dry_run) == "complete":
        return replace(entry, status="complete", error=None)

    result = _crawl_target(
        entry,
        manifest_path.parent,
        config,
        dry_run=dry_run,
        use_playwright=use_playwright,
        client=client,
        created_crawler=created_crawler,
        board_crawler=board_crawler,
    )
    if not isinstance(result, BoardManifest):
        raise ValueError("target crawler must return a BoardManifest")
    if entry.kind == "saved_board" and result.board_id != entry.target_id:
        return replace(entry, status="failed", error="Board manifest ID mismatch")
    return replace(entry, status=_target_entry_status(result, dry_run=dry_run), error=result.error)


def _crawl_target(
    entry: UserTargetManifestEntry,
    output_dir: Path,
    config: RuntimeConfig,
    *,
    dry_run: bool,
    use_playwright: bool,
    client: PinterestHttpClient | None,
    created_crawler: CreatedCrawler,
    board_crawler: SavedBoardCrawler,
) -> BoardManifest:
    if entry.kind == "created":
        return created_crawler(
            entry.target_url,
            output_dir,
            config,
            dry_run=dry_run,
            use_playwright=use_playwright,
            client=client,
        )

    return board_crawler(
        entry.target_url,
        output_dir,
        config,
        dry_run=dry_run,
        use_playwright=use_playwright,
        client=client,
    )


def _load_matching_board_manifest(path: Path, board_id: str | None) -> BoardManifest | None:
    if not path.exists():
        return None
    try:
        manifest = load_board_manifest(path)
    except (OSError, ValueError, KeyError):
        return None
    if board_id is not None and manifest.board_id != board_id:
        return None
    return manifest


def _created_entry(created_url: str) -> UserTargetManifestEntry:
    return UserTargetManifestEntry(
        kind="created",
        target_id="created",
        target_url=created_url,
        target_slug="created",
        manifest_path=str(Path("created") / "manifest.json"),
        status="pending",
        error=None,
    )


def _entry_for_board(board: object) -> UserTargetManifestEntry:
    board_id = getattr(board, "id")
    board_url = getattr(board, "url")
    board_slug = getattr(board, "slug")
    return UserTargetManifestEntry(
        kind="saved_board",
        target_id=board_id,
        target_url=board_url,
        target_slug=board_slug,
        manifest_path=str(Path("saved") / board_slug / "manifest.json"),
        status="pending",
        error=None,
    )


def _resolve_manifest_path(output_dir: Path, manifest_path: str) -> Path:
    path = Path(manifest_path)
    if path.is_absolute():
        return path

    output_parts = output_dir.parts
    if output_parts and path.parts[: len(output_parts)] == output_parts:
        return path
    return output_dir / path


def _target_entry_status(manifest: BoardManifest, *, dry_run: bool) -> UserBoardStatus:
    if manifest.scan_status == "failed" or manifest.download_status == "failed":
        return "failed"
    if dry_run:
        return "complete" if manifest.scan_status == "complete" else "in_progress"
    if manifest.scan_status == "complete" and manifest.download_status == "complete":
        return "complete"
    return "in_progress"


def _user_status(targets: list[UserTargetManifestEntry], *, dry_run: bool) -> CrawlStatus:
    if not targets:
        return "complete"
    if any(target.status == "failed" for target in targets):
        return "failed"
    if dry_run:
        return (
            "complete" if all(target.status == "complete" for target in targets) else "in_progress"
        )
    if all(target.status == "complete" for target in targets):
        return "complete"
    return "in_progress"


def _username_from_url(user_url: str) -> str:
    return user_url.rstrip("/").split("/")[-1] or "user"
