"""Tests for Pinterest board feed helpers."""

from pinterest_crawler.board_feed import (
    build_board_feed_params,
    build_board_feed_headers,
    filter_board_pins,
    next_bookmarks_from_resource,
)
from pinterest_crawler.models import JsonObject


def test_filter_board_pins_keeps_only_target_board_pin_items() -> None:
    items: list[JsonObject] = [
        {"id": "pin-1", "type": "pin", "board": {"id": "104"}},
        {"id": "pin-2", "type": "pin", "board": {"id": "999"}},
        {"id": "interest-1", "type": "interest", "board": {"id": "104"}},
        {"id": "pin-3", "type": "pin", "board": None},
    ]

    pins = filter_board_pins(items, "104")

    assert [pin["id"] for pin in pins] == ["pin-1"]


def test_build_board_feed_params_encodes_resource_options() -> None:
    params = build_board_feed_params(
        board_id="104",
        source_url="/adryanlong/golden-hour/",
        bookmarks=["bookmark-1"],
        page_size=15,
    )

    assert params["source_url"] == "/adryanlong/golden-hour/"
    assert '"board_id":"104"' in params["data"]
    assert '"bookmarks":["bookmark-1"]' in params["data"]
    assert '"page_size":15' in params["data"]


def test_build_board_feed_headers_sets_required_xhr_headers() -> None:
    headers = build_board_feed_headers("https://www.pinterest.com/adryanlong/golden-hour/")

    assert headers["X-Requested-With"] == "XMLHttpRequest"
    assert headers["X-Pinterest-AppState"] == "active"
    assert headers["X-Pinterest-PWS-Handler"] == "www/adryanlong/golden-hour.js"
    assert headers["Referer"] == "https://www.pinterest.com/adryanlong/golden-hour/"


def test_next_bookmarks_from_resource_detects_end_marker() -> None:
    resource: JsonObject = {"resource": {"options": {"bookmarks": ["-end-"]}}}

    assert next_bookmarks_from_resource(resource) == ["-end-"]
