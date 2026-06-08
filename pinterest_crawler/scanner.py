"""Board scanning and manifest checkpoint creation."""

from __future__ import annotations

import logging
from dataclasses import replace
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse

from pinterest_crawler.board_feed import (
    data_from_resource_response,
    filter_board_pins,
    next_bookmarks_from_resource,
)
from pinterest_crawler.config import RuntimeConfig
from pinterest_crawler.http_client import PinterestHttpClient
from pinterest_crawler.images import extract_image_candidates
from pinterest_crawler.manifest import load_board_manifest, save_board_manifest
from pinterest_crawler.models import BoardManifest, JsonObject, PinDownload
from pinterest_crawler.pin_detail import PinDetailParseError, extract_pin_detail_metadata
from pinterest_crawler.playwright_bootstrap import bootstrap_board_page
from pinterest_crawler.ssr import (
    SsrParseError,
    extract_initial_state,
    find_board_feed_resource,
    resolve_board,
)


LOGGER = logging.getLogger(__name__)


class BoardScanClient(Protocol):
    """HTTP behavior required by the board scanner."""

    def fetch_board_html(self, board_url: str) -> str:
        """Fetch a board page."""

    def fetch_pin_html(self, pin_id: str) -> str:
        """Fetch a public Pinterest pin detail page."""

    def fetch_board_feed(
        self,
        *,
        board_url: str,
        board_id: str,
        source_url: str,
        bookmarks: list[str],
        page_size: int,
    ) -> JsonObject:
        """Fetch one `BoardFeedResource` page."""

    def apply_cookies(self, cookies: dict[str, str]) -> None:
        """Apply cookies captured by Playwright."""


def scan_board(
    board_url: str,
    output_dir: Path,
    config: RuntimeConfig,
    *,
    use_playwright: bool = True,
    client: BoardScanClient | None = None,
    bootstrap: object | None = None,
) -> BoardManifest:
    """Scan a board and update its manifest checkpoint.

    Args:
        board_url: Public Pinterest board URL.
        output_dir: Directory containing `manifest.json`.
        config: Runtime crawl configuration.
        use_playwright: Whether to use Playwright if SSR HTML is missing.
        client: Optional client for tests.
        bootstrap: Optional bootstrap function for tests.

    Returns:
        Updated board manifest.
    """

    manifest_path = output_dir / "manifest.json"
    if manifest_path.exists():
        manifest = load_board_manifest(manifest_path)
        if manifest.scan_status == "complete":
            return manifest
        if _should_rebuild_manifest(manifest):
            manifest = _create_manifest_from_ssr(
                board_url,
                output_dir,
                config,
                use_playwright=use_playwright,
                client=client,
                bootstrap=bootstrap,
            )
            if manifest.scan_status == "complete":
                return manifest
    else:
        manifest = _create_manifest_from_ssr(
            board_url,
            output_dir,
            config,
            use_playwright=use_playwright,
            client=client,
            bootstrap=bootstrap,
        )
        if manifest.scan_status == "complete":
            return manifest

    owns_client = client is None
    http_client = client or PinterestHttpClient(config=config)
    try:
        return _scan_remaining_pages(http_client, manifest_path, manifest, config)
    except Exception as exc:
        failed = replace(manifest, scan_status="failed", error=str(exc))
        save_board_manifest(manifest_path, failed)
        return failed
    finally:
        if owns_client and isinstance(http_client, PinterestHttpClient):
            http_client.close()


def _create_manifest_from_ssr(
    board_url: str,
    output_dir: Path,
    config: RuntimeConfig,
    *,
    use_playwright: bool,
    client: BoardScanClient | None,
    bootstrap: object | None,
) -> BoardManifest:
    owns_client = client is None
    http_client = client or PinterestHttpClient(config=config)
    bootstrap_func = bootstrap_board_page if bootstrap is None else bootstrap
    manifest_path = output_dir / "manifest.json"

    try:
        html = http_client.fetch_board_html(board_url)
        try:
            state = extract_initial_state(html)
        except SsrParseError:
            if not use_playwright:
                raise
            bootstrapped_html, cookies = _call_bootstrap(bootstrap_func, board_url)
            http_client.apply_cookies(cookies)
            state = extract_initial_state(bootstrapped_html)

        board = resolve_board(state, board_url)
        initial_page = find_board_feed_resource(state, board.id)
        pins = filter_board_pins(initial_page.items, board.id)
        records = _records_from_pins(
            pins,
            existing_pin_ids=set(),
            limit=config.limit,
            client=http_client,
        )
        reached_end = initial_page.bookmarks == ["-end-"]
        scan_complete = reached_end or len(records) >= config.limit
        manifest = BoardManifest(
            board_id=board.id,
            board_url=board_url,
            board_name=board.name,
            board_slug=board.slug,
            scan_status="complete" if scan_complete else "in_progress",
            download_status="not_started",
            next_bookmark=None if reached_end else _first_bookmark(initial_page.bookmarks),
            pages_done=0,
            accepted_pins=len(records),
            reached_end=reached_end,
            error=None,
            records=records,
        )
        save_board_manifest(manifest_path, manifest)
        return manifest
    except Exception as exc:
        placeholder = BoardManifest(
            board_id="",
            board_url=board_url,
            board_name="",
            board_slug=_slug_from_url(board_url),
            scan_status="failed",
            download_status="not_started",
            next_bookmark=None,
            pages_done=0,
            accepted_pins=0,
            reached_end=False,
            error=str(exc),
            records=[],
        )
        save_board_manifest(manifest_path, placeholder)
        return placeholder
    finally:
        if owns_client and isinstance(http_client, PinterestHttpClient):
            http_client.close()


def _scan_remaining_pages(
    client: BoardScanClient,
    manifest_path: Path,
    manifest: BoardManifest,
    config: RuntimeConfig,
) -> BoardManifest:
    current = manifest
    seen = {record.pin_id for record in current.records}

    while (
        current.next_bookmark is not None
        and not current.reached_end
        and current.pages_done < config.max_pages
        and current.accepted_pins < config.limit
    ):
        response = client.fetch_board_feed(
            board_url=current.board_url,
            board_id=current.board_id,
            source_url=_source_url(current.board_url),
            bookmarks=[current.next_bookmark],
            page_size=config.page_size,
        )
        page_pins = filter_board_pins(data_from_resource_response(response), current.board_id)
        remaining = config.limit - current.accepted_pins
        new_records = _records_from_pins(
            page_pins,
            existing_pin_ids=seen,
            limit=remaining,
            client=client,
        )
        seen.update(record.pin_id for record in new_records)

        bookmarks = next_bookmarks_from_resource(response)
        reached_end = bookmarks == ["-end-"]
        pages_done = current.pages_done + 1
        accepted_pins = current.accepted_pins + len(new_records)
        scan_complete = (
            reached_end or pages_done >= config.max_pages or accepted_pins >= config.limit
        )
        current = replace(
            current,
            records=[*current.records, *new_records],
            next_bookmark=None if reached_end else _first_bookmark(bookmarks),
            pages_done=pages_done,
            accepted_pins=accepted_pins,
            reached_end=reached_end,
            scan_status="complete" if scan_complete else "in_progress",
            error=None,
        )
        save_board_manifest(manifest_path, current)

    return current


def _should_rebuild_manifest(manifest: BoardManifest) -> bool:
    return (
        manifest.scan_status == "failed"
        and not manifest.board_id
        and not manifest.records
        and manifest.next_bookmark is None
    )


def _records_from_pins(
    pins: list[JsonObject],
    *,
    existing_pin_ids: set[str],
    limit: int,
    client: BoardScanClient,
) -> list[PinDownload]:
    records: list[PinDownload] = []
    for pin in pins:
        raw_id = pin.get("id")
        if not isinstance(raw_id, str | int):
            continue
        pin_id = str(raw_id)
        if pin_id in existing_pin_ids:
            continue

        pin_detail = _fetch_pin_detail_metadata(client, pin_id)
        if pin_detail is None:
            existing_pin_ids.add(pin_id)
            continue

        existing_pin_ids.add(pin_id)
        records.append(
            PinDownload(
                pin_id=pin_id,
                source_url=_pin_source_url(pin, pin_id),
                image_candidates=extract_image_candidates(pin),
                selected_image_url=None,
                attempted_urls=[],
                local_path=None,
                status="planned",
                error=None,
                pinterest_metadata={
                    "board_feed": pin,
                    "pin_detail": pin_detail,
                },
            )
        )
        if len(records) >= limit:
            break
    return records


def _fetch_pin_detail_metadata(client: BoardScanClient, pin_id: str) -> JsonObject | None:
    try:
        html = client.fetch_pin_html(pin_id)
    except Exception as exc:
        LOGGER.warning("Skipping pin %s because detail metadata fetch failed: %s", pin_id, exc)
        return None

    try:
        return extract_pin_detail_metadata(html)
    except PinDetailParseError as exc:
        LOGGER.warning("Skipping pin %s because detail metadata could not be parsed: %s", pin_id, exc)
        return None


def _call_bootstrap(bootstrap: object, board_url: str) -> tuple[str, dict[str, str]]:
    if not callable(bootstrap):
        raise TypeError("bootstrap must be callable")
    result = bootstrap(board_url)
    if (
        not isinstance(result, tuple)
        or len(result) != 2
        or not isinstance(result[0], str)
        or not isinstance(result[1], dict)
    ):
        raise ValueError("bootstrap must return (html, cookies)")
    cookies = {str(name): str(value) for name, value in result[1].items()}
    return result[0], cookies


def _pin_source_url(pin: JsonObject, pin_id: str) -> str:
    raw_url = pin.get("link") or pin.get("url")
    if isinstance(raw_url, str) and raw_url.startswith("http"):
        return raw_url
    return f"https://www.pinterest.com/pin/{pin_id}/"


def _source_url(board_url: str) -> str:
    parsed = urlparse(board_url)
    return f"/{parsed.path.strip('/')}/"


def _slug_from_url(url: str) -> str:
    parts = [part for part in urlparse(url).path.split("/") if part]
    return parts[-1] if parts else "board"


def _first_bookmark(bookmarks: list[str]) -> str | None:
    if not bookmarks:
        return None
    return bookmarks[0]
