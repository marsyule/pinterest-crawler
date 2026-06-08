"""Parse Pinterest SSR state from board HTML."""

from __future__ import annotations

import json
from html import unescape
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Tag

from pinterest_crawler.models import Board, BoardFeedPage, JsonObject, JsonValue


class SsrParseError(ValueError):
    """Raised when Pinterest SSR state cannot be extracted."""


def extract_initial_state(html: str) -> JsonObject:
    """Extract `initialReduxState` from Pinterest SSR HTML.

    Args:
        html: Raw Pinterest board HTML.

    Returns:
        The `initialReduxState` JSON object.

    Raises:
        SsrParseError: If the script or expected JSON state is missing.
    """

    soup = BeautifulSoup(html, "html.parser")
    script = _find_state_script(soup)
    if script is None:
        raise SsrParseError("Missing __PWS_INITIAL_PROPS__ or __PWS_DATA__ script")

    raw = script.string or script.get_text()
    if not raw:
        raise SsrParseError("Empty __PWS_INITIAL_PROPS__ script")

    try:
        props = json.loads(unescape(raw))
    except json.JSONDecodeError as exc:
        raise SsrParseError("Invalid __PWS_INITIAL_PROPS__ JSON") from exc

    if not isinstance(props, dict):
        raise SsrParseError("__PWS_INITIAL_PROPS__ is not a JSON object")

    state = props.get("initialReduxState")
    if not isinstance(state, dict):
        raise SsrParseError("Missing initialReduxState")

    return dict(state)


def _find_state_script(soup: BeautifulSoup) -> Tag | None:
    for script_id in ("__PWS_INITIAL_PROPS__", "__PWS_DATA__"):
        script = soup.find("script", id=script_id)
        if script is not None:
            return script
    return None


def resolve_board(state: JsonObject, board_url: str) -> Board:
    """Resolve the target board from SSR state.

    Args:
        state: Pinterest `initialReduxState`.
        board_url: Requested board URL.

    Returns:
        Board metadata.

    Raises:
        ValueError: If no board in state matches the requested URL.
    """

    requested_path = _normalize_path(urlparse(board_url).path)
    boards = state.get("boards")
    if not isinstance(boards, dict):
        raise ValueError("Board metadata not found in SSR state")

    for raw_board in boards.values():
        if not isinstance(raw_board, dict):
            continue
        board_data = _unwrap_data(raw_board)
        raw_url = board_data.get("url")
        if not isinstance(raw_url, str):
            continue
        if _normalize_path(raw_url) != requested_path:
            continue

        raw_id = board_data.get("id")
        raw_name = board_data.get("name")
        if not isinstance(raw_id, str | int) or not isinstance(raw_name, str):
            raise ValueError("Board metadata is incomplete")

        return Board(
            id=str(raw_id),
            name=raw_name,
            url=raw_url,
            slug=_slug_from_path(raw_url),
            pin_count=_optional_int(board_data.get("pin_count")),
            privacy=_optional_str(board_data.get("privacy")),
            pinterest_metadata={"board": board_data},
        )

    raise ValueError("Board metadata not found for requested URL")


def find_board_feed_resource(state: JsonObject, board_id: str) -> BoardFeedPage:
    """Find the cached SSR `BoardFeedResource` for a board.

    Args:
        state: Pinterest `initialReduxState`.
        board_id: Target board ID.

    Returns:
        Initial board feed page.

    Raises:
        ValueError: If no matching resource can be found.
    """

    resources = state.get("resources")
    if not isinstance(resources, dict):
        raise ValueError("BoardFeedResource not found in SSR state")

    board_feed = resources.get("BoardFeedResource")
    if not isinstance(board_feed, dict):
        raise ValueError("BoardFeedResource not found in SSR state")

    for key, raw_resource in board_feed.items():
        if not isinstance(raw_resource, dict):
            continue
        if _resource_key_has_board_id(str(key), board_id) or _resource_has_board_id(
            raw_resource, board_id
        ):
            return _feed_page_from_resource(raw_resource)

    raise ValueError(f"BoardFeedResource not found for board {board_id}")


def _feed_page_from_resource(resource: dict[str, JsonValue]) -> BoardFeedPage:
    data = resource.get("data")
    if not isinstance(data, list):
        nested = resource.get("resource_response")
        if isinstance(nested, dict):
            nested_data = nested.get("data")
            data = nested_data if isinstance(nested_data, list) else []
        else:
            data = []

    items = [dict(item) for item in data if isinstance(item, dict)]
    bookmarks = _bookmarks_from_resource(resource)
    return BoardFeedPage(items=items, bookmarks=bookmarks)


def _bookmarks_from_resource(resource: dict[str, JsonValue]) -> list[str]:
    next_bookmark = resource.get("nextBookmark")
    if isinstance(next_bookmark, str):
        return [next_bookmark]

    options = resource.get("options")
    if isinstance(options, dict):
        raw_bookmarks = options.get("bookmarks")
        if isinstance(raw_bookmarks, list):
            return [bookmark for bookmark in raw_bookmarks if isinstance(bookmark, str)]

    return []


def _resource_key_has_board_id(resource_key: str, board_id: str) -> bool:
    try:
        options = json.loads(resource_key)
    except json.JSONDecodeError:
        return board_id in resource_key

    if isinstance(options, list):
        for item in options:
            if (
                isinstance(item, list | tuple)
                and len(item) == 2
                and item[0] == "board_id"
                and str(item[1]) == board_id
            ):
                return True
    if isinstance(options, dict):
        raw_options = options.get("options", options)
        if isinstance(raw_options, dict):
            return str(raw_options.get("board_id")) == board_id
    return False


def _resource_has_board_id(resource: dict[str, JsonValue], board_id: str) -> bool:
    options = resource.get("options")
    if isinstance(options, dict):
        return str(options.get("board_id")) == board_id
    return False


def _unwrap_data(raw: dict[str, JsonValue]) -> dict[str, JsonValue]:
    data = raw.get("data")
    return dict(data) if isinstance(data, dict) else raw


def _normalize_path(path: str) -> str:
    parsed_path = urlparse(path).path
    return f"/{parsed_path.strip('/')}/"


def _slug_from_path(path: str) -> str:
    parts = [part for part in urlparse(path).path.split("/") if part]
    return parts[-1] if parts else "board"


def _optional_int(value: JsonValue) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _optional_str(value: JsonValue) -> str | None:
    return value if isinstance(value, str) else None
