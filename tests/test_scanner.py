"""Tests for board scanning checkpoints."""

import json
from pathlib import Path

from pinterest_crawler.config import RuntimeConfig
from pinterest_crawler.manifest import load_board_manifest, save_board_manifest
from pinterest_crawler.models import BoardManifest, JsonObject
from pinterest_crawler.scanner import scan_board


class FakeScanClient:
    """In-memory scanner client."""

    def __init__(self, html: str, pages: list[JsonObject] | None = None) -> None:
        self.html = html
        self.pages = pages or []
        self.page_sizes: list[int] = []
        self.bookmarks: list[list[str]] = []
        self.bootstrap_called = False

    def fetch_board_html(self, board_url: str) -> str:
        return self.html

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
    client = FakeScanClient(_board_html([_pin("pin-1")], next_bookmark="-end-"))

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
    client = FakeScanClient(_board_html([_pin("pin-1")], next_bookmark="-end-"))

    manifest = scan_board(
        "https://www.pinterest.com/adryanlong/golden-hour/",
        tmp_path,
        RuntimeConfig(),
        client=client,
    )

    assert manifest.scan_status == "complete"
    assert manifest.board_id == "104"
    assert [record.pin_id for record in manifest.records] == ["pin-1"]


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
        "images": {"orig": {"url": f"https://i.pinimg.com/originals/aa/bb/{pin_id}.jpg"}},
    }
