"""Tests for board scanning checkpoints."""

import json
from pathlib import Path

from pinterest_crawler.config import RuntimeConfig
from pinterest_crawler.manifest import load_board_manifest, save_board_manifest
from pinterest_crawler.models import BoardManifest, JsonObject
from pinterest_crawler.scanner import scan_board


class FakeScanClient:
    """In-memory scanner client."""

    def __init__(
        self,
        html: str,
        pages: list[JsonObject] | None = None,
        pin_html_by_id: dict[str, str] | None = None,
    ) -> None:
        self.html = html
        self.pages = pages or []
        self.pin_html_by_id = pin_html_by_id or {}
        self.pin_html_requests: list[str] = []
        self.page_sizes: list[int] = []
        self.bookmarks: list[list[str]] = []
        self.bootstrap_called = False

    def fetch_board_html(self, board_url: str) -> str:
        return self.html

    def fetch_pin_html(self, pin_id: str) -> str:
        self.pin_html_requests.append(pin_id)
        html = self.pin_html_by_id.get(pin_id)
        if html is None:
            raise RuntimeError(f"missing detail html for {pin_id}")
        return html

    def fetch_board_feed(
        self,
        *,
        board_url: str,
        board_id: str,
        source_url: str,
        bookmarks: list[str],
        page_size: int,
    ) -> JsonObject:
        self.bookmarks.append(bookmarks)
        self.page_sizes.append(page_size)
        return self.pages.pop(0)

    def apply_cookies(self, cookies: dict[str, str]) -> None:
        self.bootstrap_called = True


def test_scan_board_writes_planned_records_from_ssr(tmp_path: Path) -> None:
    pin = _pin("pin-1")
    client = FakeScanClient(
        _board_html([pin], next_bookmark="-end-"),
        pin_html_by_id={"pin-1": _pin_detail_html("pin-1")},
    )

    manifest = scan_board(
        "https://www.pinterest.com/adryanlong/golden-hour/",
        tmp_path,
        RuntimeConfig(),
        client=client,
    )

    assert manifest.scan_status == "complete"
    assert manifest.records[0].status == "planned"
    assert manifest.records[0].image_candidates == [
        "https://i.pinimg.com/originals/aa/bb/pin-1.jpg"
    ]
    assert manifest.records[0].pinterest_metadata == {
        "board_feed": pin,
        "pin_detail": {
            "id": "pin-1",
            "closeup_description": "Detail for pin-1",
        },
    }
    assert manifest.pinterest_metadata == {
        "board": {
            "id": "104",
            "name": "Golden Hour",
            "url": "/adryanlong/golden-hour/",
            "pin_count": 1,
            "privacy": "public",
            "created_at": "Fri, 05 Jun 2026 08:10:52 +0000",
            "board_order_modified_at": "Fri, 05 Jun 2026 08:11:04 +0000",
            "cover_pin": {
                "pin_id": "pin-1",
                "image_signature": "aa-bb",
                "timestamp": 1780647060,
            },
        }
    }
    assert load_board_manifest(tmp_path / "manifest.json").accepted_pins == 1


def test_scan_board_resumes_from_checkpoint_and_uses_page_size(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    save_board_manifest(
        manifest_path,
        BoardManifest(
            board_id="104",
            board_url="https://www.pinterest.com/adryanlong/golden-hour/",
            board_name="Golden Hour",
            board_slug="golden-hour",
            scan_status="in_progress",
            download_status="not_started",
            next_bookmark="bookmark-1",
            pages_done=0,
            accepted_pins=0,
            reached_end=False,
            error=None,
            records=[],
        ),
    )
    client = FakeScanClient(
        "",
        pages=[
            {
                "resource": {"options": {"bookmarks": ["-end-"]}},
                "data": [_pin("pin-1"), _pin("pin-1"), _pin("pin-2")],
            }
        ],
        pin_html_by_id={
            "pin-1": _pin_detail_html("pin-1"),
            "pin-2": _pin_detail_html("pin-2"),
        },
    )

    manifest = scan_board(
        "https://www.pinterest.com/adryanlong/golden-hour/",
        tmp_path,
        RuntimeConfig(page_size=25),
        client=client,
    )

    assert client.bookmarks == [["bookmark-1"]]
    assert client.page_sizes == [25]
    assert [record.pin_id for record in manifest.records] == ["pin-1", "pin-2"]
    assert manifest.pages_done == 1
    assert manifest.scan_status == "complete"


def test_scan_board_enforces_limit_and_max_pages(tmp_path: Path) -> None:
    client = FakeScanClient(
        _board_html([], next_bookmark="bookmark-1"),
        pages=[
            {
                "resource": {"options": {"bookmarks": ["bookmark-2"]}},
                "data": [_pin("pin-1"), _pin("pin-2")],
            }
        ],
        pin_html_by_id={
            "pin-1": _pin_detail_html("pin-1"),
            "pin-2": _pin_detail_html("pin-2"),
        },
    )

    manifest = scan_board(
        "https://www.pinterest.com/adryanlong/golden-hour/",
        tmp_path,
        RuntimeConfig(limit=1, max_pages=1),
        client=client,
    )

    assert [record.pin_id for record in manifest.records] == ["pin-1"]
    assert manifest.pages_done == 1
    assert manifest.scan_status == "complete"


def test_scan_board_retries_after_failed_placeholder_manifest(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    save_board_manifest(
        manifest_path,
        BoardManifest(
            board_id="",
            board_url="https://www.pinterest.com/adryanlong/golden-hour/",
            board_name="",
            board_slug="golden-hour",
            scan_status="failed",
            download_status="not_started",
            next_bookmark=None,
            pages_done=0,
            accepted_pins=0,
            reached_end=False,
            error="temporary ssl error",
            records=[],
        ),
    )
    client = FakeScanClient(
        _board_html([_pin("pin-1")], next_bookmark="-end-"),
        pin_html_by_id={"pin-1": _pin_detail_html("pin-1")},
    )

    manifest = scan_board(
        "https://www.pinterest.com/adryanlong/golden-hour/",
        tmp_path,
        RuntimeConfig(),
        client=client,
    )

    assert manifest.scan_status == "complete"
    assert manifest.board_id == "104"
    assert [record.pin_id for record in manifest.records] == ["pin-1"]


def test_scan_board_skips_pin_when_detail_metadata_cannot_be_parsed(
    tmp_path: Path,
) -> None:
    client = FakeScanClient(
        _board_html([_pin("pin-1"), _pin("pin-2")], next_bookmark="-end-"),
        pin_html_by_id={
            "pin-1": "<html>no relay payload</html>",
            "pin-2": _pin_detail_html("pin-2"),
        },
    )

    manifest = scan_board(
        "https://www.pinterest.com/adryanlong/golden-hour/",
        tmp_path,
        RuntimeConfig(limit=2),
        client=client,
    )

    assert [record.pin_id for record in manifest.records] == ["pin-2"]
    assert manifest.accepted_pins == 1
    assert client.pin_html_requests == ["pin-1", "pin-2"]


def test_scan_board_skipped_pins_do_not_count_toward_limit(tmp_path: Path) -> None:
    client = FakeScanClient(
        _board_html([_pin("pin-1")], next_bookmark="bookmark-1"),
        pages=[
            {
                "resource": {"options": {"bookmarks": ["-end-"]}},
                "data": [_pin("pin-2")],
            }
        ],
        pin_html_by_id={
            "pin-1": "<html>no detail</html>",
            "pin-2": _pin_detail_html("pin-2"),
        },
    )

    manifest = scan_board(
        "https://www.pinterest.com/adryanlong/golden-hour/",
        tmp_path,
        RuntimeConfig(limit=1, max_pages=1),
        client=client,
    )

    assert [record.pin_id for record in manifest.records] == ["pin-2"]
    assert manifest.accepted_pins == 1
    assert manifest.pages_done == 1
    assert client.bookmarks == [["bookmark-1"]]


def _board_html(pins: list[JsonObject], *, next_bookmark: str) -> str:
    state = {
        "initialReduxState": {
            "boards": {
                "104": {
                    "data": {
                        "id": "104",
                        "name": "Golden Hour",
                        "url": "/adryanlong/golden-hour/",
                        "pin_count": len(pins),
                        "privacy": "public",
                        "created_at": "Fri, 05 Jun 2026 08:10:52 +0000",
                        "board_order_modified_at": "Fri, 05 Jun 2026 08:11:04 +0000",
                        "cover_pin": {
                            "pin_id": "pin-1",
                            "image_signature": "aa-bb",
                            "timestamp": 1780647060,
                        },
                    }
                }
            },
            "resources": {
                "BoardFeedResource": {
                    json.dumps([["board_id", "104"]]): {
                        "data": pins,
                        "nextBookmark": next_bookmark,
                    }
                }
            },
        }
    }
    return f'<script id="__PWS_INITIAL_PROPS__">{json.dumps(state)}</script>'


def _pin(pin_id: str) -> JsonObject:
    return {
        "id": pin_id,
        "type": "pin",
        "board": {"id": "104"},
        "grid_title": "Golden pin",
        "description": "A saved Pinterest pin.",
        "reaction_counts": {"1": 3},
        "images": {"orig": {"url": f"https://i.pinimg.com/originals/aa/bb/{pin_id}.jpg"}},
    }


def _pin_detail_html(pin_id: str) -> str:
    payload = {
        "data": {
            "v3GetPinQueryv2": {
                "data": {
                    "id": pin_id,
                    "closeup_description": f"Detail for {pin_id}",
                }
            }
        }
    }
    return (
        "<script>"
        "window.__PWS_RELAY_REGISTER_COMPLETED_REQUEST__("
        '"request-id",'
        f"{json.dumps(payload)}"
        ");"
        "</script>"
    )
