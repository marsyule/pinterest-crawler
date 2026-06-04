"""Tests for user-level board orchestration."""

import json
from pathlib import Path

import pytest

from pinterest_crawler.config import RuntimeConfig
from pinterest_crawler.manifest import load_user_manifest, save_board_manifest
from pinterest_crawler.models import BoardManifest, CrawlStatus
from pinterest_crawler.user_downloader import crawl_user_boards


class FakeUserClient:
    """In-memory client that returns one user profile page."""

    def __init__(self, html: str) -> None:
        self.html = html
        self.closed = False

    def fetch_user_html(self, user_url: str) -> str:
        return self.html

    def close(self) -> None:
        self.closed = True


def test_crawl_user_boards_writes_user_manifest_and_calls_each_board(
    tmp_path: Path,
) -> None:
    calls: list[tuple[str, Path, RuntimeConfig, bool, bool]] = []

    def board_crawler(
        board_url: str,
        output_dir: Path,
        config: RuntimeConfig,
        *,
        dry_run: bool,
        use_playwright: bool,
        client: object = None,
    ) -> BoardManifest:
        calls.append((board_url, output_dir, config, dry_run, use_playwright))
        board_id = "105" if board_url.endswith("/golden-hour/") else "104"
        manifest = _board_manifest(
            board_url,
            output_dir.name,
            board_id=board_id,
            download_status="complete",
        )
        save_board_manifest(output_dir / "manifest.json", manifest)
        return manifest

    manifest = crawl_user_boards(
        "https://www.pinterest.com/adryanlong/",
        tmp_path,
        RuntimeConfig(page_size=25),
        client=FakeUserClient(
            _user_html(
                [
                    _raw_board("104", "Coastal Calm", "/adryanlong/coastal-calm/"),
                    _raw_board("105", "Golden Hour", "/adryanlong/golden-hour/"),
                ]
            )
        ),
        board_crawler=board_crawler,
    )

    assert [call[0] for call in calls] == [
        "https://www.pinterest.com/adryanlong/coastal-calm/",
        "https://www.pinterest.com/adryanlong/golden-hour/",
    ]
    assert [call[1] for call in calls] == [tmp_path / "coastal-calm", tmp_path / "golden-hour"]
    assert calls[0][2].page_size == 25
    assert calls[0][3] is False
    assert calls[0][4] is True
    assert manifest.status == "complete"

    loaded = load_user_manifest(tmp_path / "user_manifest.json")
    assert loaded.username == "adryanlong"
    assert [board.status for board in loaded.boards] == ["complete", "complete"]


def test_crawl_user_boards_dry_run_does_not_download_but_can_complete_scan(
    tmp_path: Path,
) -> None:
    def board_crawler(
        board_url: str,
        output_dir: Path,
        config: RuntimeConfig,
        *,
        dry_run: bool,
        use_playwright: bool,
        client: object = None,
    ) -> BoardManifest:
        assert dry_run is True
        return _board_manifest(board_url, output_dir.name, download_status="not_started")

    manifest = crawl_user_boards(
        "https://www.pinterest.com/adryanlong/",
        tmp_path,
        RuntimeConfig(),
        dry_run=True,
        client=FakeUserClient(_user_html([_raw_board("104", "Coastal Calm", "/a/coastal/")])),
        board_crawler=board_crawler,
    )

    assert manifest.status == "complete"
    assert manifest.boards[0].status == "complete"


def test_crawl_user_boards_rejects_existing_board_id_mismatch_as_complete(
    tmp_path: Path,
) -> None:
    board_dir = tmp_path / "coastal-calm"
    save_board_manifest(
        board_dir / "manifest.json",
        _board_manifest(
            "https://www.pinterest.com/adryanlong/coastal-calm/",
            "coastal-calm",
            board_id="wrong",
            download_status="complete",
        ),
    )

    def board_crawler(
        board_url: str,
        output_dir: Path,
        config: RuntimeConfig,
        *,
        dry_run: bool,
        use_playwright: bool,
        client: object = None,
    ) -> BoardManifest:
        return _board_manifest(
            board_url, output_dir.name, board_id="wrong", download_status="complete"
        )

    manifest = crawl_user_boards(
        "https://www.pinterest.com/adryanlong/",
        tmp_path,
        RuntimeConfig(),
        client=FakeUserClient(
            _user_html([_raw_board("104", "Coastal Calm", "/adryanlong/coastal-calm/")])
        ),
        board_crawler=board_crawler,
    )

    assert manifest.status == "failed"
    assert manifest.boards[0].status == "failed"
    assert manifest.boards[0].error == "Board manifest ID mismatch"


def test_crawl_user_boards_resumes_from_existing_user_manifest(tmp_path: Path) -> None:
    first_calls = 0

    def board_crawler(
        board_url: str,
        output_dir: Path,
        config: RuntimeConfig,
        *,
        dry_run: bool,
        use_playwright: bool,
        client: object = None,
    ) -> BoardManifest:
        nonlocal first_calls
        first_calls += 1
        manifest = _board_manifest(board_url, output_dir.name, download_status="complete")
        save_board_manifest(output_dir / "manifest.json", manifest)
        return manifest

    crawl_user_boards(
        "https://www.pinterest.com/adryanlong/",
        tmp_path,
        RuntimeConfig(),
        client=FakeUserClient(
            _user_html([_raw_board("104", "Coastal Calm", "/adryanlong/coastal-calm/")])
        ),
        board_crawler=board_crawler,
    )

    second = crawl_user_boards(
        "https://www.pinterest.com/adryanlong/",
        tmp_path,
        RuntimeConfig(),
        client=FakeUserClient(_user_html([])),
        board_crawler=board_crawler,
    )

    assert first_calls == 1
    assert second.status == "complete"


def test_crawl_user_boards_passes_board_directory_without_double_prefix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    output_dirs: list[Path] = []

    def board_crawler(
        board_url: str,
        output_dir: Path,
        config: RuntimeConfig,
        *,
        dry_run: bool,
        use_playwright: bool,
        client: object = None,
    ) -> BoardManifest:
        output_dirs.append(output_dir)
        manifest = _board_manifest(board_url, output_dir.name, download_status="complete")
        save_board_manifest(output_dir / "manifest.json", manifest)
        return manifest

    manifest = crawl_user_boards(
        "https://www.pinterest.com/adryanlong/",
        Path("downloads/adryanlong"),
        RuntimeConfig(),
        client=FakeUserClient(
            _user_html([_raw_board("104", "Coastal Calm", "/adryanlong/coastal-calm/")])
        ),
        board_crawler=board_crawler,
    )

    assert manifest.status == "complete"
    assert output_dirs == [Path("downloads/adryanlong/coastal-calm")]


def _user_html(boards: list[dict[str, object]]) -> str:
    props = {
        "initialReduxState": {"boards": {str(index): board for index, board in enumerate(boards)}}
    }
    return f'<script id="__PWS_INITIAL_PROPS__">{json.dumps(props)}</script>'


def _raw_board(board_id: str, name: str, url: str) -> dict[str, object]:
    return {
        "id": board_id,
        "name": name,
        "url": url,
        "pin_count": 1,
        "privacy": "public",
    }


def _board_manifest(
    board_url: str,
    board_slug: str,
    *,
    board_id: str = "104",
    download_status: CrawlStatus,
) -> BoardManifest:
    return BoardManifest(
        board_id=board_id,
        board_url=board_url,
        board_name="Board",
        board_slug=board_slug,
        scan_status="complete",
        download_status=download_status,
        next_bookmark=None,
        pages_done=0,
        accepted_pins=0,
        reached_end=True,
        error=None,
        records=[],
    )
