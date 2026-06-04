"""Tests for manifest persistence."""

import json
from pathlib import Path

from pinterest_crawler.manifest import (
    load_board_manifest,
    load_user_manifest,
    save_board_manifest,
    save_user_manifest,
)
from pinterest_crawler.models import (
    BoardManifest,
    PinDownload,
    UserTargetManifestEntry,
    UserManifest,
)


def test_save_and_load_board_manifest_round_trips_manifest_shape(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest = _board_manifest()

    save_board_manifest(manifest_path, manifest)

    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert "schema_version" not in raw
    loaded = load_board_manifest(manifest_path)
    assert loaded.board_id == "104"
    assert loaded.scan_status == "complete"
    assert loaded.records[0].selected_image_url == "https://i.pinimg.com/originals/a.jpg"
    assert loaded.records[0].status == "success"


def test_save_and_load_user_manifest_round_trips_v13_shape(tmp_path: Path) -> None:
    manifest_path = tmp_path / "user_manifest.json"
    manifest = UserManifest(
        user_url="https://www.pinterest.com/adryanlong/",
        username="adryanlong",
        discovery_status="complete",
        status="in_progress",
        error=None,
        targets=[
            UserTargetManifestEntry(
                kind="created",
                target_id="adryanlong",
                target_url="https://www.pinterest.com/adryanlong/_created/",
                target_slug="created",
                manifest_path="created/manifest.json",
                status="complete",
                error=None,
            ),
            UserTargetManifestEntry(
                kind="saved_board",
                target_id="104",
                target_url="https://www.pinterest.com/adryanlong/golden-hour/",
                target_slug="golden-hour",
                manifest_path="saved/golden-hour/manifest.json",
                status="in_progress",
                error=None,
            ),
        ],
    )

    save_user_manifest(manifest_path, manifest)

    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert "schema_version" not in raw
    loaded = load_user_manifest(manifest_path)
    assert loaded.username == "adryanlong"
    assert loaded.targets[0].kind == "created"
    assert loaded.targets[1].status == "in_progress"


def test_atomic_board_manifest_write_leaves_no_temp_file(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"

    save_board_manifest(manifest_path, _board_manifest())

    assert manifest_path.exists()
    assert not (tmp_path / "manifest.json.tmp").exists()


def _board_manifest() -> BoardManifest:
    return BoardManifest(
        board_id="104",
        board_url="https://www.pinterest.com/adryanlong/golden-hour/",
        board_name="Golden Hour",
        board_slug="golden-hour",
        scan_status="complete",
        download_status="complete",
        next_bookmark=None,
        pages_done=1,
        accepted_pins=1,
        reached_end=True,
        error=None,
        records=[
            PinDownload(
                pin_id="pin-1",
                source_url="https://www.pinterest.com/pin/pin-1/",
                image_candidates=["https://i.pinimg.com/originals/a.jpg"],
                selected_image_url="https://i.pinimg.com/originals/a.jpg",
                attempted_urls=["https://i.pinimg.com/originals/a.jpg"],
                local_path="pin-1.jpg",
                status="success",
                error=None,
            )
        ],
    )
