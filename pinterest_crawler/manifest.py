"""Manifest persistence for resumable board and user downloads."""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import cast

from pinterest_crawler.models import (
    BoardManifest,
    CrawlStatus,
    JsonObject,
    PinDownload,
    RecordStatus,
    UserTargetKind,
    UserTargetManifestEntry,
    UserBoardStatus,
    UserManifest,
)


def save_board_manifest(path: Path, manifest: BoardManifest) -> None:
    """Save a board manifest as stable JSON.

    Args:
        path: Manifest file path.
        manifest: Manifest to write.
    """

    _atomic_write_json(path, asdict(manifest))


def load_board_manifest(path: Path) -> BoardManifest:
    """Load a board manifest from disk.

    Args:
        path: Manifest file path.

    Returns:
        Parsed manifest.
    """

    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Manifest must be a JSON object")

    raw_records = raw.get("records")
    if not isinstance(raw_records, list):
        raise ValueError("Manifest is missing records")

    return BoardManifest(
        board_id=str(raw["board_id"]),
        board_url=str(raw["board_url"]),
        board_name=str(raw["board_name"]),
        board_slug=str(raw["board_slug"]),
        scan_status=_crawl_status_from_str(str(raw["scan_status"])),
        download_status=_crawl_status_from_str(str(raw["download_status"])),
        next_bookmark=_optional_str(raw.get("next_bookmark")),
        pages_done=_required_int(raw.get("pages_done")),
        accepted_pins=_required_int(raw.get("accepted_pins")),
        reached_end=_required_bool(raw.get("reached_end")),
        error=_optional_str(raw.get("error")),
        records=[_pin_from_dict(record) for record in raw_records if isinstance(record, dict)],
    )


def save_user_manifest(path: Path, manifest: UserManifest) -> None:
    """Save a user manifest as stable JSON."""

    _atomic_write_json(path, asdict(manifest))


def load_user_manifest(path: Path) -> UserManifest:
    """Load a user manifest from disk."""

    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("User manifest must be a JSON object")

    raw_targets = raw.get("targets")
    if not isinstance(raw_targets, list):
        raise ValueError("User manifest is missing targets")

    return UserManifest(
        user_url=str(raw["user_url"]),
        username=str(raw["username"]),
        discovery_status=_crawl_status_from_str(str(raw["discovery_status"])),
        status=_crawl_status_from_str(str(raw["status"])),
        error=_optional_str(raw.get("error")),
        targets=[
            _user_target_entry_from_dict(target)
            for target in raw_targets
            if isinstance(target, dict)
        ],
    )


def _pin_from_dict(raw: dict[str, object]) -> PinDownload:
    candidates = raw.get("image_candidates")
    attempted_urls = raw.get("attempted_urls")
    return PinDownload(
        pin_id=str(raw["pin_id"]),
        source_url=str(raw["source_url"]),
        image_candidates=[str(url) for url in candidates] if isinstance(candidates, list) else [],
        selected_image_url=_optional_str(raw.get("selected_image_url")),
        attempted_urls=(
            [str(url) for url in attempted_urls] if isinstance(attempted_urls, list) else []
        ),
        local_path=_optional_str(raw.get("local_path")),
        status=_record_status_from_str(str(raw["status"])),
        error=_optional_str(raw.get("error")),
        pinterest_metadata=_required_json_object(
            raw.get("pinterest_metadata"),
            pin_id=str(raw["pin_id"]),
        ),
    )


def _user_target_entry_from_dict(raw: dict[str, object]) -> UserTargetManifestEntry:
    return UserTargetManifestEntry(
        kind=_user_target_kind_from_str(str(raw["kind"])),
        target_id=str(raw["target_id"]),
        target_url=str(raw["target_url"]),
        target_slug=str(raw["target_slug"]),
        manifest_path=str(raw["manifest_path"]),
        status=_user_board_status_from_str(str(raw["status"])),
        error=_optional_str(raw.get("error")),
    )


def _crawl_status_from_str(value: str) -> CrawlStatus:
    if value in {"not_started", "in_progress", "complete", "failed"}:
        return cast(CrawlStatus, value)
    raise ValueError(f"Invalid crawl status: {value}")


def _record_status_from_str(value: str) -> RecordStatus:
    if value in {"planned", "downloading", "success", "failed", "missing_file", "skipped"}:
        return cast(RecordStatus, value)
    raise ValueError(f"Invalid record status: {value}")


def _user_board_status_from_str(value: str) -> UserBoardStatus:
    if value in {"pending", "in_progress", "complete", "failed"}:
        return cast(UserBoardStatus, value)
    raise ValueError(f"Invalid user board status: {value}")


def _user_target_kind_from_str(value: str) -> UserTargetKind:
    if value in {"created", "saved_board"}:
        return cast(UserTargetKind, value)
    raise ValueError(f"Invalid user target kind: {value}")


def _atomic_write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    tmp_path.replace(path)


def _required_int(value: object) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    raise ValueError("Expected integer value")


def _required_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    raise ValueError("Expected boolean value")


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _required_json_object(value: object, *, pin_id: str) -> JsonObject:
    if value is None:
        raise ValueError(f"Record {pin_id} is missing pinterest_metadata")
    if isinstance(value, dict):
        return cast(JsonObject, value)
    raise ValueError(f"Record {pin_id} pinterest_metadata must be an object")


# Backwards-compatible aliases for import stability.
Manifest = BoardManifest
save_manifest = save_board_manifest
load_manifest = load_board_manifest
