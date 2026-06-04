"""Helpers for Pinterest user `Created` feeds."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import cast
from urllib.parse import urlparse

from pinterest_crawler.models import JsonObject, JsonValue


PINTEREST_BASE_URL = "https://www.pinterest.com"


@dataclass(frozen=True)
class NormalizedCreatedUrl:
    """Normalized Pinterest created-feed URL details."""

    username: str
    url: str
    slug: str


@dataclass(frozen=True)
class CreatedProfile:
    """Resolved user metadata for a public created feed."""

    user_id: str
    username: str
    display_name: str
    created_url: str
    slug: str
    pin_count: int | None


def normalize_created_url(created_url: str) -> NormalizedCreatedUrl:
    """Normalize a Pinterest created-feed URL."""

    parsed = urlparse(created_url)
    path_parts = [part for part in parsed.path.split("/") if part]
    if len(path_parts) != 2 or path_parts[1] != "_created":
        raise ValueError("Created URL must be a Pinterest /<username>/_created/ URL")

    username = path_parts[0]
    return NormalizedCreatedUrl(
        username=username,
        url=f"{PINTEREST_BASE_URL}/{username}/_created/",
        slug=f"{username}-created",
    )


def discover_created_profile(response: JsonObject, created_url: str) -> CreatedProfile:
    """Resolve created-feed metadata from a `UserResource` response."""

    normalized = normalize_created_url(created_url)
    user_data = _resource_data_dict(response)
    raw_id = user_data.get("id")
    raw_username = user_data.get("username")
    raw_name = user_data.get("full_name")
    if not isinstance(raw_id, str | int):
        raise ValueError("Created feed user ID not found")
    if not isinstance(raw_username, str) or not raw_username:
        raise ValueError("Created feed username not found")
    if not isinstance(raw_name, str) or not raw_name:
        raise ValueError("Created feed display name not found")

    return CreatedProfile(
        user_id=str(raw_id),
        username=raw_username,
        display_name=raw_name,
        created_url=normalized.url,
        slug=normalized.slug,
        pin_count=_optional_int(user_data.get("pin_count")),
    )


def filter_created_pins(items: list[JsonObject], user_id: str) -> list[JsonObject]:
    """Return only concrete created pins that belong to the target user."""

    return [
        item
        for item in items
        if item.get("type") == "pin" and _item_belongs_to_user(item, user_id=user_id)
    ]


def build_created_feed_params(
    *,
    user_id: str,
    username: str,
    source_url: str,
    bookmarks: list[str],
) -> dict[str, str]:
    """Build query parameters for `UserActivityPinsResource`."""

    options: dict[str, JsonValue] = {
        "exclude_add_pin_rep": True,
        "field_set_key": "profile_created_grid_item",
        "is_own_profile_pins": False,
        "user_id": user_id,
        "username": username,
    }
    if bookmarks:
        options["bookmarks"] = cast(JsonValue, bookmarks)

    payload = {"options": options, "context": {}}
    return {"source_url": source_url, "data": json.dumps(payload, separators=(",", ":"))}


def build_created_feed_headers(created_url: str) -> dict[str, str]:
    """Build required XHR headers for `UserActivityPinsResource`."""

    source_url = _source_url(created_url)
    return {
        "Accept": "application/json, text/javascript, */*, q=0.01",
        "Accept-Language": "en-US",
        "Referer": PINTEREST_BASE_URL + "/",
        "X-Requested-With": "XMLHttpRequest",
        "X-Pinterest-AppState": "active",
        "X-Pinterest-Source-Url": source_url,
        "X-Pinterest-PWS-Handler": "www/[username]/_created.js",
    }


def build_user_resource_params(*, created_url: str, username: str) -> dict[str, str]:
    """Build query parameters for the created-page `UserResource` lookup."""

    payload = {"options": {"username": username, "field_set_key": "profile"}, "context": {}}
    return {
        "source_url": _source_url(created_url),
        "data": json.dumps(payload, separators=(",", ":")),
    }


def build_user_resource_headers(created_url: str) -> dict[str, str]:
    """Build required XHR headers for the created-page `UserResource` lookup."""

    return build_created_feed_headers(created_url)


def _resource_data_dict(response: JsonObject) -> JsonObject:
    raw_resource = response.get("resource_response")
    if not isinstance(raw_resource, dict):
        raise ValueError("Pinterest resource response is missing resource_response")
    raw_data = raw_resource.get("data")
    if not isinstance(raw_data, dict):
        raise ValueError("Pinterest resource response did not return an object payload")
    return dict(raw_data)


def _item_belongs_to_user(item: JsonObject, *, user_id: str) -> bool:
    candidate_ids = (
        _nested_id(item, "pinner"),
        _nested_id(item, "native_creator"),
        _nested_id(item, "board", "owner"),
    )
    return any(candidate_id == user_id for candidate_id in candidate_ids)


def _nested_id(item: JsonObject, *keys: str) -> str | None:
    current: JsonValue = item
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    if not isinstance(current, dict):
        return None
    raw_id = current.get("id")
    if isinstance(raw_id, str | int):
        return str(raw_id)
    return None


def _source_url(url: str) -> str:
    parsed = urlparse(url)
    return f"/{parsed.path.strip('/')}/"


def _optional_int(value: JsonValue) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None
