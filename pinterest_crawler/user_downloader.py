"""Batch orchestration for downloading all public boards from a Pinterest user."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Protocol

from pinterest_crawler.config import RuntimeConfig
from pinterest_crawler.downloader import crawl_board
from pinterest_crawler.http_client import PinterestHttpClient
from pinterest_crawler.manifest import load_board_manifest, load_user_manifest, save_user_manifest
from pinterest_crawler.models import (
    Board,
    BoardManifest,
    CrawlStatus,
    UserBoardManifestEntry,
    UserBoardStatus,
    UserManifest,
)
from pinterest_crawler.user_boards import discover_user_boards


class UserProfileClient(Protocol):
    """HTTP behavior needed to fetch a Pinterest user profile page."""

    def fetch_user_html(self, user_url: str) -> str:
        """Fetch user profile HTML."""


def crawl_user_boards(
    user_url: str,
    output_dir: Path,
    config: RuntimeConfig,
    *,
    dry_run: bool = False,
    use_playwright: bool = True,
    client: UserProfileClient | PinterestHttpClient | None = None,
    board_crawler: object | None = None,
) -> UserManifest:
    """Download all public boards discovered from a Pinterest user page.

    Args:
        user_url: Pinterest user profile URL.
        output_dir: Root directory for per-board output directories.
        config: Runtime crawl configuration.
        dry_run: Scan only when true.
        use_playwright: Whether board scans may use Playwright fallback.
        client: Optional profile/board client for tests.
        board_crawler: Optional callable replacing `crawl_board` in tests.

    Returns:
        Updated user manifest.
    """

    manifest_path = output_dir / "user_manifest.json"
    owns_client = client is None
    profile_client = client or PinterestHttpClient(config=config)
    crawl_func = crawl_board if board_crawler is None else board_crawler

    try:
        if manifest_path.exists():
            user_manifest = load_user_manifest(manifest_path)
        else:
            user_manifest = _discover_boards(user_url, output_dir, profile_client)
            save_user_manifest(manifest_path, user_manifest)

        if user_manifest.discovery_status != "complete":
            user_manifest = _discover_boards(user_url, output_dir, profile_client)
            save_user_manifest(manifest_path, user_manifest)

        boards: list[UserBoardManifestEntry] = []
        for entry in user_manifest.boards:
            updated = _process_board_entry(
                entry,
                output_dir,
                config,
                dry_run=dry_run,
                use_playwright=use_playwright,
                client=client if isinstance(client, PinterestHttpClient) else None,
                board_crawler=crawl_func,
            )
            boards.append(updated)
            user_manifest = replace(
                user_manifest,
                boards=boards + user_manifest.boards[len(boards) :],
                status=_user_status(boards + user_manifest.boards[len(boards) :], dry_run=dry_run),
                error=None,
            )
            save_user_manifest(manifest_path, user_manifest)

        final = replace(
            user_manifest,
            boards=boards,
            status=_user_status(boards, dry_run=dry_run),
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
            boards=[],
        )
        save_user_manifest(manifest_path, failed)
        return failed
    finally:
        if owns_client and isinstance(profile_client, PinterestHttpClient):
            profile_client.close()


def _discover_boards(
    user_url: str,
    output_dir: Path,
    client: UserProfileClient,
) -> UserManifest:
    output_dir.mkdir(parents=True, exist_ok=True)
    html = client.fetch_user_html(user_url)
    profile = discover_user_boards(html, user_url)
    entries = [_entry_for_board(output_dir, board) for board in profile.boards]
    return UserManifest(
        user_url=profile.user_url,
        username=profile.username,
        discovery_status="complete",
        status="not_started" if entries else "complete",
        error=None,
        boards=entries,
    )


def _process_board_entry(
    entry: UserBoardManifestEntry,
    output_dir: Path,
    config: RuntimeConfig,
    *,
    dry_run: bool,
    use_playwright: bool,
    client: PinterestHttpClient | None,
    board_crawler: object,
) -> UserBoardManifestEntry:
    manifest_path = _resolve_manifest_path(output_dir, entry.manifest_path)

    existing = _load_matching_board_manifest(manifest_path, entry.board_id)
    if existing is not None and _board_entry_status(existing, dry_run=dry_run) == "complete":
        return replace(entry, status="complete", error=None)

    if not callable(board_crawler):
        raise TypeError("board_crawler must be callable")
    result = board_crawler(
        entry.board_url,
        manifest_path.parent,
        config,
        dry_run=dry_run,
        use_playwright=use_playwright,
        client=client,
    )
    if not isinstance(result, BoardManifest):
        raise ValueError("board_crawler must return a BoardManifest")
    if result.board_id != entry.board_id:
        return replace(entry, status="failed", error="Board manifest ID mismatch")
    return replace(entry, status=_board_entry_status(result, dry_run=dry_run), error=result.error)


def _load_matching_board_manifest(path: Path, board_id: str) -> BoardManifest | None:
    if not path.exists():
        return None
    try:
        manifest = load_board_manifest(path)
    except (OSError, ValueError, KeyError):
        return None
    if manifest.board_id != board_id:
        return None
    return manifest


def _entry_for_board(output_dir: Path, board: Board) -> UserBoardManifestEntry:
    return UserBoardManifestEntry(
        board_id=board.id,
        board_url=board.url,
        board_slug=board.slug,
        manifest_path=str(Path(board.slug) / "manifest.json"),
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


def _board_entry_status(manifest: BoardManifest, *, dry_run: bool) -> UserBoardStatus:
    if manifest.scan_status == "failed" or manifest.download_status == "failed":
        return "failed"
    if dry_run:
        return "complete" if manifest.scan_status == "complete" else "in_progress"
    if manifest.scan_status == "complete" and manifest.download_status == "complete":
        return "complete"
    return "in_progress"


def _user_status(boards: list[UserBoardManifestEntry], *, dry_run: bool) -> CrawlStatus:
    if not boards:
        return "complete"
    if any(board.status == "failed" for board in boards):
        return "failed"
    if dry_run:
        return "complete" if all(board.status == "complete" for board in boards) else "in_progress"
    if all(board.status == "complete" for board in boards):
        return "complete"
    return "in_progress"


def _username_from_url(user_url: str) -> str:
    return user_url.rstrip("/").split("/")[-1] or "user"
