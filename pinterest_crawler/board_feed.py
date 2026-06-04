"""Helpers for Pinterest `BoardFeedResource` pagination."""

from __future__ import annotations

import json
from urllib.parse import urlparse

from pinterest_crawler.models import JsonObject, JsonValue


def filter_board_pins(items: list[JsonObject], board_id: str) -> list[JsonObject]:
    """Return only pin items that belong to the target board.

    Args:
        items: Raw Pinterest feed items.
        board_id: Target board ID.

    Returns:
        Filtered pin items.
    """

    return [
        item for item in items if item.get("type") == "pin" and _item_board_id(item) == board_id
    ]


def build_board_feed_params(
    *,
    board_id: str,
    source_url: str,
    bookmarks: list[str],
    page_size: int,
) -> dict[str, str]:
    """Build query parameters for `BoardFeedResource`.

    Args:
        board_id: Target board ID.
        source_url: Board path used by Pinterest as request source.
        bookmarks: Pagination bookmarks.
        page_size: Page size requested from Pinterest.

    Returns:
        Query parameters for `httpx`.
    """

    payload = {
        "options": {
            "add_vase": True,
            "board_id": board_id,
            "field_set_key": "react_grid_pin",
            "filter_section_pins": False,
            "is_react": True,
            "page_size": page_size,
            "prepend": False,
            "bookmarks": bookmarks,
        }
    }
    return {"source_url": source_url, "data": json.dumps(payload, separators=(",", ":"))}


def build_board_feed_headers(board_url: str) -> dict[str, str]:
    """Build required XHR headers for `BoardFeedResource`.

    Args:
        board_url: Full board URL.

    Returns:
        Headers accepted by Pinterest's internal resource endpoint.
    """

    parsed = urlparse(board_url)
    path = parsed.path.strip("/")
    return {
        "Accept": "application/json, text/javascript, */*, q=0.01",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": board_url,
        "X-Requested-With": "XMLHttpRequest",
        "X-Pinterest-AppState": "active",
        "X-Pinterest-PWS-Handler": f"www/{path}.js",
    }


def next_bookmarks_from_resource(response: JsonObject) -> list[str]:
    """Read pagination bookmarks from a Pinterest resource response.

    Args:
        response: Decoded JSON response from Pinterest.

    Returns:
        Bookmark strings, including `["-end-"]` when the feed is complete.
    """

    options = _nested_options(response)
    raw_bookmarks = options.get("bookmarks")
    if isinstance(raw_bookmarks, list):
        return [bookmark for bookmark in raw_bookmarks if isinstance(bookmark, str)]
    return []


def data_from_resource_response(response: JsonObject) -> list[JsonObject]:
    """Extract feed item data from a Pinterest resource response."""

    raw_data = response.get("resource_response")
    if isinstance(raw_data, dict):
        data = raw_data.get("data")
    else:
        data = response.get("data")
    if not isinstance(data, list):
        return []
    return [dict(item) for item in data if isinstance(item, dict)]


def _item_board_id(item: JsonObject) -> str | None:
    board = item.get("board")
    if not isinstance(board, dict):
        return None
    raw_id = board.get("id")
    if isinstance(raw_id, str | int):
        return str(raw_id)
    return None


def _nested_options(response: JsonObject) -> dict[str, JsonValue]:
    resource = response.get("resource")
    if isinstance(resource, dict):
        options = resource.get("options")
        if isinstance(options, dict):
            return options

    options = response.get("options")
    if isinstance(options, dict):
        return options

    return {}
