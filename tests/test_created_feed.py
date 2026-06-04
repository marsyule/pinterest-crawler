"""Tests for Pinterest created-feed helpers."""

import json

from pinterest_crawler.created_feed import (
    build_created_feed_headers,
    build_created_feed_params,
    discover_created_profile,
    filter_created_pins,
    normalize_created_url,
)
from pinterest_crawler.models import JsonObject


def test_normalize_created_url_accepts_canonical_created_path() -> None:
    normalized = normalize_created_url("https://www.pinterest.com/rileyaussies/_created/?foo=bar")

    assert normalized.username == "rileyaussies"
    assert normalized.url == "https://www.pinterest.com/rileyaussies/_created/"
    assert normalized.slug == "rileyaussies-created"


def test_discover_created_profile_reads_user_resource_payload() -> None:
    profile = discover_created_profile(
        {
            "resource_response": {
                "data": {
                    "id": "1103945064818071965",
                    "username": "rileyaussies",
                    "full_name": "Riley A",
                    "pin_count": 22,
                    "eligible_profile_tabs": [
                        {"name": "Created", "tab_type": 1},
                        {"name": "Saved", "tab_type": 0},
                    ],
                }
            }
        },
        "https://www.pinterest.com/rileyaussies/_created/",
    )

    assert profile.user_id == "1103945064818071965"
    assert profile.username == "rileyaussies"
    assert profile.display_name == "Riley A"
    assert profile.created_url == "https://www.pinterest.com/rileyaussies/_created/"
    assert profile.pin_count == 22


def test_filter_created_pins_keeps_only_target_user_created_pins() -> None:
    items: list[JsonObject] = [
        {
            "id": "pin-1",
            "type": "pin",
            "pinner": {"id": "1103945064818071965"},
            "images": {"orig": {"url": "https://i.pinimg.com/originals/pin-1.jpg"}},
        },
        {
            "id": "pin-2",
            "type": "pin",
            "native_creator": {"id": "1103945064818071965"},
            "images": {"orig": {"url": "https://i.pinimg.com/originals/pin-2.jpg"}},
        },
        {
            "id": "pin-3",
            "type": "pin",
            "pinner": {"id": "someone-else"},
            "images": {"orig": {"url": "https://i.pinimg.com/originals/pin-3.jpg"}},
        },
        {"id": "card-1", "type": "profiletab"},
    ]

    filtered = filter_created_pins(items, user_id="1103945064818071965")

    assert [item["id"] for item in filtered] == ["pin-1", "pin-2"]


def test_build_created_feed_params_includes_bookmarks_only_when_present() -> None:
    params = build_created_feed_params(
        user_id="1103945064818071965",
        username="rileyaussies",
        source_url="/rileyaussies/_created/",
        bookmarks=["bookmark-1"],
    )

    payload = json.loads(params["data"])

    assert params["source_url"] == "/rileyaussies/_created/"
    assert payload["options"]["field_set_key"] == "profile_created_grid_item"
    assert payload["options"]["bookmarks"] == ["bookmark-1"]


def test_build_created_feed_headers_matches_verified_created_page_handler() -> None:
    headers = build_created_feed_headers("https://www.pinterest.com/rileyaussies/_created/")

    assert headers["Referer"] == "https://www.pinterest.com/"
    assert headers["X-Pinterest-PWS-Handler"] == "www/[username]/_created.js"
    assert headers["X-Pinterest-Source-Url"] == "/rileyaussies/_created/"
