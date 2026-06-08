"""Shared data models for Pinterest board crawling."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


JsonValue = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject = dict[str, JsonValue]
CrawlStatus = Literal["not_started", "in_progress", "complete", "failed"]
RecordStatus = Literal["planned", "downloading", "success", "failed", "missing_file", "skipped"]
UserBoardStatus = Literal["pending", "in_progress", "complete", "failed"]
UserTargetKind = Literal["created", "saved_board"]


@dataclass(frozen=True)
class Board:
    """Metadata for a Pinterest board.

    Args:
        id: Pinterest board ID.
        name: Human-readable board name.
        url: Board path as reported by Pinterest.
        slug: URL slug for local output naming.
        pin_count: Pinterest-reported pin count, when available.
        privacy: Pinterest privacy label, when available.
    """

    id: str
    name: str
    url: str
    slug: str
    pin_count: int | None
    privacy: str | None


@dataclass(frozen=True)
class BoardFeedPage:
    """A page of board feed items and the bookmarks for the next request."""

    items: list[JsonObject]
    bookmarks: list[str]


@dataclass(frozen=True)
class PinDownload:
    """Manifest entry for one pin image download."""

    pin_id: str
    source_url: str
    image_candidates: list[str]
    selected_image_url: str | None
    attempted_urls: list[str]
    local_path: str | None
    status: RecordStatus
    error: str | None
    pinterest_metadata: JsonObject


@dataclass(frozen=True)
class BoardManifest:
    """Checkpoint and task queue for one board crawl."""

    board_id: str
    board_url: str
    board_name: str
    board_slug: str
    scan_status: CrawlStatus
    download_status: CrawlStatus
    next_bookmark: str | None
    pages_done: int
    accepted_pins: int
    reached_end: bool
    error: str | None
    records: list[PinDownload]


@dataclass(frozen=True)
class UserTargetManifestEntry:
    """User-level index entry for one created or saved-board manifest."""

    kind: UserTargetKind
    target_id: str
    target_url: str
    target_slug: str
    manifest_path: str
    status: UserBoardStatus
    error: str | None


@dataclass(frozen=True)
class UserManifest:
    """Checkpoint for a user-profile batch crawl."""

    user_url: str
    username: str
    discovery_status: CrawlStatus
    status: CrawlStatus
    error: str | None
    targets: list[UserTargetManifestEntry]
