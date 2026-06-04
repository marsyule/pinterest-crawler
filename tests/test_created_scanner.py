"""Tests for created-feed scanning checkpoints."""

from pathlib import Path

from pinterest_crawler.config import RuntimeConfig
from pinterest_crawler.manifest import load_board_manifest, save_board_manifest
from typing import cast

from pinterest_crawler.models import BoardManifest, JsonObject, JsonValue
from pinterest_crawler.created_scanner import scan_created_feed


class FakeCreatedScanClient:
    """In-memory client for created-feed scanning."""

    def __init__(
        self,
        user_resource: JsonObject,
        initial_page: JsonObject,
        pages: list[JsonObject] | None = None,
    ) -> None:
        self.user_resource = user_resource
        self.initial_page = initial_page
        self.pages = pages or []
        self.page_bookmarks: list[list[str]] = []

    def fetch_user_resource(self, created_url: str, username: str) -> JsonObject:
        return self.user_resource

    def fetch_user_activity_pins(
        self,
        *,
        created_url: str,
        username: str,
        user_id: str,
        bookmarks: list[str],
    ) -> JsonObject:
        self.page_bookmarks.append(bookmarks)
        if not bookmarks:
            return self.initial_page
        return self.pages.pop(0)


def test_scan_created_feed_writes_planned_records_from_initial_page(tmp_path: Path) -> None:
    client = FakeCreatedScanClient(
        _user_resource(),
        _created_page([_created_pin("pin-1")], next_bookmark="-end-"),
    )

    manifest = scan_created_feed(
        "https://www.pinterest.com/rileyaussies/_created/",
        tmp_path,
        RuntimeConfig(),
        client=client,
    )

    assert manifest.board_id == "1103945064818071965"
    assert manifest.board_slug == "rileyaussies-created"
    assert manifest.board_name == "Riley A Created"
    assert manifest.scan_status == "complete"
    assert [record.pin_id for record in manifest.records] == ["pin-1"]
    assert load_board_manifest(tmp_path / "manifest.json").accepted_pins == 1


def test_scan_created_feed_resumes_from_bookmark(tmp_path: Path) -> None:
    save_board_manifest(
        tmp_path / "manifest.json",
        BoardManifest(
            board_id="1103945064818071965",
            board_url="https://www.pinterest.com/rileyaussies/_created/",
            board_name="Riley A Created",
            board_slug="rileyaussies-created",
            scan_status="in_progress",
            download_status="not_started",
            next_bookmark="bookmark-1",
            pages_done=0,
            accepted_pins=1,
            reached_end=False,
            error=None,
            records=[],
        ),
    )
    client = FakeCreatedScanClient(
        _user_resource(),
        _created_page([], next_bookmark="unused"),
        pages=[_created_page([_created_pin("pin-2")], next_bookmark="-end-")],
    )

    manifest = scan_created_feed(
        "https://www.pinterest.com/rileyaussies/_created/",
        tmp_path,
        RuntimeConfig(),
        client=client,
    )

    assert client.page_bookmarks == [["bookmark-1"]]
    assert [record.pin_id for record in manifest.records] == ["pin-2"]
    assert manifest.pages_done == 1
    assert manifest.scan_status == "complete"


def test_scan_created_feed_retries_after_failed_placeholder_manifest(tmp_path: Path) -> None:
    save_board_manifest(
        tmp_path / "manifest.json",
        BoardManifest(
            board_id="",
            board_url="https://www.pinterest.com/rileyaussies/_created/",
            board_name="",
            board_slug="rileyaussies-created",
            scan_status="failed",
            download_status="not_started",
            next_bookmark=None,
            pages_done=0,
            accepted_pins=0,
            reached_end=False,
            error="temporary socket error",
            records=[],
        ),
    )
    client = FakeCreatedScanClient(
        _user_resource(),
        _created_page([_created_pin("pin-1")], next_bookmark="-end-"),
    )

    manifest = scan_created_feed(
        "https://www.pinterest.com/rileyaussies/_created/",
        tmp_path,
        RuntimeConfig(),
        client=client,
    )

    assert manifest.scan_status == "complete"
    assert manifest.board_id == "1103945064818071965"
    assert [record.pin_id for record in manifest.records] == ["pin-1"]


def _user_resource() -> JsonObject:
    return {
        "resource_response": {
            "data": {
                "id": "1103945064818071965",
                "username": "rileyaussies",
                "full_name": "Riley A",
                "pin_count": 22,
                "eligible_profile_tabs": [{"name": "Created", "tab_type": 1}],
            }
        }
    }


def _created_page(pins: list[JsonObject], *, next_bookmark: str) -> JsonObject:
    options: JsonObject = {"bookmarks": [next_bookmark]}
    resource_response: JsonObject = {"data": cast(JsonValue, pins)}
    return {
        "resource_response": resource_response,
        "resource": {"options": options},
    }


def _created_pin(pin_id: str) -> JsonObject:
    return {
        "id": pin_id,
        "type": "pin",
        "pinner": {"id": "1103945064818071965"},
        "images": {"orig": {"url": f"https://i.pinimg.com/originals/{pin_id}.jpg"}},
    }
