"""Tests for Pinterest SSR parsing."""

import json

import pytest

from pinterest_crawler.models import JsonObject
from pinterest_crawler.ssr import (
    SsrParseError,
    extract_initial_state,
    find_board_feed_resource,
    resolve_board,
)


def _html_with_state(state: dict[str, object]) -> str:
    props = {"initialReduxState": state}
    return (
        "<html><body>"
        f'<script id="__PWS_INITIAL_PROPS__" type="application/json">'
        f"{json.dumps(props)}"
        "</script>"
        "</body></html>"
    )


def _html_with_pws_data(state: dict[str, object]) -> str:
    props = {"initialReduxState": state}
    return (
        "<html><body>"
        f'<script id="__PWS_DATA__" type="application/json">{json.dumps(props)}</script>'
        "</body></html>"
    )


def test_extract_initial_state_reads_pws_initial_props() -> None:
    html = _html_with_state({"boards": {"1": {"id": "1", "name": "Board"}}})

    state = extract_initial_state(html)
    boards = state["boards"]
    assert isinstance(boards, dict)
    board = boards["1"]
    assert isinstance(board, dict)

    assert board["name"] == "Board"


def test_extract_initial_state_reads_pws_data_fallback() -> None:
    html = _html_with_pws_data({"boards": {"2": {"id": "2", "name": "Fallback Board"}}})

    state = extract_initial_state(html)
    boards = state["boards"]
    assert isinstance(boards, dict)
    board = boards["2"]
    assert isinstance(board, dict)

    assert board["name"] == "Fallback Board"


def test_extract_initial_state_raises_when_script_missing() -> None:
    with pytest.raises(SsrParseError, match="__PWS_INITIAL_PROPS__|__PWS_DATA__"):
        extract_initial_state("<html></html>")


def test_resolve_board_matches_board_url() -> None:
    state: JsonObject = {
        "boards": {
            "104": {
                "id": "104",
                "name": "Golden Hour",
                "url": "/adryanlong/golden-hour/",
                "pin_count": 20,
                "privacy": "public",
            }
        }
    }

    board = resolve_board(state, "https://www.pinterest.com/adryanlong/golden-hour/")

    assert board.id == "104"
    assert board.name == "Golden Hour"
    assert board.url == "/adryanlong/golden-hour/"
    assert board.pin_count == 20


def test_find_board_feed_resource_returns_matching_feed_and_bookmark() -> None:
    feed: JsonObject = {
        "data": [{"id": "pin-1", "type": "pin", "board": {"id": "104"}}],
        "nextBookmark": "bookmark-1",
    }
    state: JsonObject = {
        "resources": {
            "BoardFeedResource": {
                json.dumps([["board_id", "104"], ["page_size", 15]]): feed,
                json.dumps([["board_id", "999"], ["page_size", 15]]): {"data": []},
            }
        }
    }

    resource = find_board_feed_resource(state, "104")

    assert resource.items == feed["data"]
    assert resource.bookmarks == ["bookmark-1"]
