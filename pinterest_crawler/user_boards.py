"""Discover public Pinterest boards from user profile pages."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

from pinterest_crawler.models import Board, JsonObject, JsonValue
from pinterest_crawler.ssr import extract_initial_state


PINTEREST_BASE_URL = "https://www.pinterest.com"


@dataclass(frozen=True)
class NormalizedUserUrl:
    """Normalized Pinterest user URL details."""

    username: str
    url: str


@dataclass(frozen=True)
class UserBoards:
    """Public boards discovered from a Pinterest user profile page."""

    username: str
    user_url: str
    boards: list[Board]


def normalize_user_url(user_url: str) -> NormalizedUserUrl:
    """Normalize a Pinterest user profile URL.

    Args:
        user_url: Pinterest user profile URL.

    Returns:
        Normalized username and canonical URL.

    Raises:
        ValueError: If the URL does not contain a username.
    """

    parsed = urlparse(user_url)
    path_parts = [part for part in parsed.path.split("/") if part]
    if len(path_parts) != 1:
        raise ValueError("User URL must be a Pinterest profile URL")

    username = path_parts[0]
    return NormalizedUserUrl(username=username, url=f"{PINTEREST_BASE_URL}/{username}/")


def discover_user_boards(html: str, user_url: str) -> UserBoards:
    """Discover public boards from a Pinterest user profile HTML document.

    Args:
        html: Raw Pinterest user profile HTML.
        user_url: Requested user profile URL.

    Returns:
        Public boards discovered from SSR state.
    """

    normalized = normalize_user_url(user_url)
    state = extract_initial_state(html)
    boards = state.get("boards")
    if not isinstance(boards, dict):
        return UserBoards(username=normalized.username, user_url=normalized.url, boards=[])

    seen: set[str] = set()
    discovered: list[Board] = []
    for raw_board in boards.values():
        if not isinstance(raw_board, dict):
            continue
        board = _board_from_raw(raw_board)
        if board is None or board.id in seen:
            continue
        seen.add(board.id)
        discovered.append(board)

    return UserBoards(username=normalized.username, user_url=normalized.url, boards=discovered)


def _board_from_raw(raw_board: dict[str, JsonValue]) -> Board | None:
    board_data = _unwrap_data(raw_board)
    if board_data.get("privacy") != "public":
        return None

    raw_id = board_data.get("id")
    raw_name = board_data.get("name")
    raw_url = board_data.get("url")
    if not isinstance(raw_id, str | int):
        return None
    if not isinstance(raw_name, str) or not raw_name:
        return None
    if not isinstance(raw_url, str) or not raw_url:
        return None

    absolute_url = urljoin(PINTEREST_BASE_URL, raw_url)
    return Board(
        id=str(raw_id),
        name=raw_name,
        url=absolute_url,
        slug=_slug_from_url(raw_url),
        pin_count=_optional_int(board_data.get("pin_count")),
        privacy="public",
    )


def _unwrap_data(raw: dict[str, JsonValue]) -> JsonObject:
    data = raw.get("data")
    return dict(data) if isinstance(data, dict) else dict(raw)


def _slug_from_url(url: str) -> str:
    parts = [part for part in urlparse(url).path.split("/") if part]
    return parts[-1] if parts else "board"


def _optional_int(value: JsonValue) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None
