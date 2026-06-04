"""Tests for discovering public boards from Pinterest user pages."""

import json

from pinterest_crawler.models import JsonObject
from pinterest_crawler.user_boards import discover_user_boards, normalize_user_url


def test_discover_user_boards_extracts_public_boards_from_ssr_state() -> None:
    html = _user_html(
        {
            "104": {
                "id": "104",
                "name": "Coastal Calm",
                "url": "/adryanlong/coastal-calm/",
                "pin_count": 10,
                "privacy": "public",
            },
            "105": {
                "data": {
                    "id": "105",
                    "name": "Golden Hour",
                    "url": "/adryanlong/golden-hour/",
                    "pin_count": "20",
                    "privacy": "public",
                }
            },
        }
    )

    profile = discover_user_boards(html, "https://www.pinterest.com/adryanlong/")

    assert profile.username == "adryanlong"
    assert profile.saved_url == "https://www.pinterest.com/adryanlong/_saved/"
    assert [board.name for board in profile.boards] == ["Coastal Calm", "Golden Hour"]
    assert profile.boards[0].url == "https://www.pinterest.com/adryanlong/coastal-calm/"
    assert profile.boards[1].pin_count == 20


def test_discover_user_boards_filters_invalid_private_and_duplicate_boards() -> None:
    html = _user_html(
        {
            "104": {
                "id": "104",
                "name": "Coastal Calm",
                "url": "/adryanlong/coastal-calm/",
                "pin_count": 10,
                "privacy": "public",
            },
            "duplicate": {
                "id": "104",
                "name": "Coastal Calm Copy",
                "url": "/adryanlong/coastal-calm-copy/",
                "pin_count": 10,
                "privacy": "public",
            },
            "private": {
                "id": "105",
                "name": "Secret",
                "url": "/adryanlong/secret/",
                "privacy": "private",
            },
            "missing-url": {"id": "106", "name": "No URL", "privacy": "public"},
            "missing-name": {"id": "107", "url": "/adryanlong/no-name/", "privacy": "public"},
        }
    )

    profile = discover_user_boards(html, "https://www.pinterest.com/adryanlong")

    assert [board.id for board in profile.boards] == ["104"]
    assert profile.boards[0].slug == "coastal-calm"


def test_normalize_user_url_accepts_trailing_slash_and_query_string() -> None:
    normalized = normalize_user_url("https://www.pinterest.com/adryanlong/?foo=bar")

    assert normalized.username == "adryanlong"
    assert normalized.user_url == "https://www.pinterest.com/adryanlong/"
    assert normalized.created_url == "https://www.pinterest.com/adryanlong/_created/"
    assert normalized.saved_url == "https://www.pinterest.com/adryanlong/_saved/"


def test_normalize_user_url_accepts_missing_trailing_slash() -> None:
    normalized = normalize_user_url("https://www.pinterest.com/dikaazriltarunaaa")

    assert normalized.username == "dikaazriltarunaaa"
    assert normalized.user_url == "https://www.pinterest.com/dikaazriltarunaaa/"
    assert normalized.created_url == "https://www.pinterest.com/dikaazriltarunaaa/_created/"
    assert normalized.saved_url == "https://www.pinterest.com/dikaazriltarunaaa/_saved/"


def _user_html(boards: dict[str, JsonObject]) -> str:
    props = {"initialReduxState": {"boards": boards}}
    return (
        f'<html><body><script id="__PWS_INITIAL_PROPS__">{json.dumps(props)}</script></body></html>'
    )
