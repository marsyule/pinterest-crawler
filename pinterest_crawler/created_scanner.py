"""Scanning support for Pinterest user `Created` feeds."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Protocol

from pinterest_crawler.board_feed import data_from_resource_response, next_bookmarks_from_resource
from pinterest_crawler.config import RuntimeConfig
from pinterest_crawler.created_feed import (
    discover_created_profile,
    filter_created_pins,
    normalize_created_url,
)
from pinterest_crawler.http_client import PinterestHttpClient
from pinterest_crawler.images import extract_image_candidates
from pinterest_crawler.manifest import load_board_manifest, save_board_manifest
from pinterest_crawler.models import BoardManifest, JsonObject, PinDownload


class CreatedScanClient(Protocol):
    """HTTP behavior required by the created-feed scanner."""

    def fetch_user_resource(self, created_url: str, username: str) -> JsonObject:
        """Fetch the created-page user metadata resource."""

    def fetch_user_activity_pins(
        self,
        *,
        created_url: str,
        username: str,
        user_id: str,
        bookmarks: list[str],
    ) -> JsonObject:
        """Fetch one `UserActivityPinsResource` page."""


def scan_created_feed(
    created_url: str,
    output_dir: Path,
    config: RuntimeConfig,
    *,
    client: CreatedScanClient | None = None,
) -> BoardManifest:
    """Scan a public Pinterest created feed and persist a checkpoint manifest."""

    manifest_path = output_dir / "manifest.json"
    if manifest_path.exists():
        manifest = load_board_manifest(manifest_path)
        if manifest.scan_status == "complete":
            return manifest
        if _should_rebuild_manifest(manifest):
            manifest = _create_manifest(created_url, output_dir, config, client=client)
            if manifest.scan_status == "complete":
                return manifest
    else:
        manifest = _create_manifest(created_url, output_dir, config, client=client)
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


def _create_manifest(
    created_url: str,
    output_dir: Path,
    config: RuntimeConfig,
    *,
    client: CreatedScanClient | None,
) -> BoardManifest:
    normalized = normalize_created_url(created_url)
    manifest_path = output_dir / "manifest.json"
    owns_client = client is None
    http_client = client or PinterestHttpClient(config=config)

    try:
        profile = discover_created_profile(
            http_client.fetch_user_resource(normalized.url, normalized.username),
            normalized.url,
        )
        initial_page = http_client.fetch_user_activity_pins(
            created_url=normalized.url,
            username=profile.username,
            user_id=profile.user_id,
            bookmarks=[],
        )
        pins = filter_created_pins(
            data_from_resource_response(initial_page),
            user_id=profile.user_id,
        )
        records = _records_from_pins(pins, existing_pin_ids=set(), limit=config.limit)
        bookmarks = next_bookmarks_from_resource(initial_page)
        reached_end = bookmarks == ["-end-"]
        scan_complete = reached_end or len(records) >= config.limit
        manifest = BoardManifest(
            board_id=profile.user_id,
            board_url=profile.created_url,
            board_name=f"{profile.display_name} Created",
            board_slug=profile.slug,
            scan_status="complete" if scan_complete else "in_progress",
            download_status="not_started",
            next_bookmark=None if reached_end else _first_bookmark(bookmarks),
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
            board_url=normalized.url,
            board_name="",
            board_slug=normalized.slug,
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
    client: CreatedScanClient,
    manifest_path: Path,
    manifest: BoardManifest,
    config: RuntimeConfig,
) -> BoardManifest:
    current = manifest
    seen = {record.pin_id for record in current.records}
    username = normalize_created_url(current.board_url).username

    while (
        current.next_bookmark is not None
        and not current.reached_end
        and current.pages_done < config.max_pages
        and current.accepted_pins < config.limit
    ):
        response = client.fetch_user_activity_pins(
            created_url=current.board_url,
            username=username,
            user_id=current.board_id,
            bookmarks=[current.next_bookmark],
        )
        page_pins = filter_created_pins(
            data_from_resource_response(response),
            user_id=current.board_id,
        )
        remaining = config.limit - current.accepted_pins
        new_records = _records_from_pins(page_pins, existing_pin_ids=seen, limit=remaining)
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


def _records_from_pins(
    pins: list[JsonObject],
    *,
    existing_pin_ids: set[str],
    limit: int,
) -> list[PinDownload]:
    records: list[PinDownload] = []
    for pin in pins:
        raw_id = pin.get("id")
        if not isinstance(raw_id, str | int):
            continue
        pin_id = str(raw_id)
        if pin_id in existing_pin_ids:
            continue
        existing_pin_ids.add(pin_id)
        records.append(
            PinDownload(
                pin_id=pin_id,
                source_url=f"https://www.pinterest.com/pin/{pin_id}/",
                image_candidates=extract_image_candidates(pin),
                selected_image_url=None,
                attempted_urls=[],
                local_path=None,
                status="planned",
                error=None,
            )
        )
        if len(records) >= limit:
            break
    return records


def _first_bookmark(bookmarks: list[str]) -> str | None:
    if not bookmarks:
        return None
    return bookmarks[0]


def _should_rebuild_manifest(manifest: BoardManifest) -> bool:
    return (
        manifest.scan_status == "failed"
        and not manifest.board_id
        and not manifest.records
        and manifest.next_bookmark is None
    )
