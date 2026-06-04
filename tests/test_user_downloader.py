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

    def __init__(self, root_html: str, saved_html: str | None = None) -> None:
        self.root_html = root_html
        self.saved_html = saved_html if saved_html is not None else root_html
        self.closed = False

    def fetch_user_html(self, user_url: str) -> str:
        if user_url.rstrip("/").endswith("_saved"):
            return self.saved_html
        return self.root_html

    def close(self) -> None:
        self.closed = True


def test_crawl_user_boards_writes_user_manifest_and_calls_created_and_each_saved_board(
    tmp_path: Path,
) -> None:
    created_calls: list[tuple[str, Path, RuntimeConfig, bool, bool]] = []
    board_calls: list[tuple[str, Path, RuntimeConfig, bool, bool]] = []

    def created_crawler(
        created_url: str,
        output_dir: Path,
        config: RuntimeConfig,
        *,
        dry_run: bool,
        use_playwright: bool,
        client: object = None,
    ) -> BoardManifest:
        created_calls.append((created_url, output_dir, config, dry_run, use_playwright))
        manifest = _board_manifest(
            created_url,
            output_dir.name,
            board_id="created-user",
            download_status="complete",
        )
        save_board_manifest(output_dir / "manifest.json", manifest)
        return manifest

    def board_crawler(
        board_url: str,
        output_dir: Path,
        config: RuntimeConfig,
        *,
        dry_run: bool,
        use_playwright: bool,
        client: object = None,
    ) -> BoardManifest:
        board_calls.append((board_url, output_dir, config, dry_run, use_playwright))
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
        created_crawler=created_crawler,
        board_crawler=board_crawler,
    )

    assert [call[0] for call in created_calls] == [
        "https://www.pinterest.com/adryanlong/_created/",
    ]
    assert [call[1] for call in created_calls] == [tmp_path / "created"]
    assert [call[0] for call in board_calls] == [
        "https://www.pinterest.com/adryanlong/coastal-calm/",
        "https://www.pinterest.com/adryanlong/golden-hour/",
    ]
    assert [call[1] for call in board_calls] == [
        tmp_path / "saved" / "coastal-calm",
        tmp_path / "saved" / "golden-hour",
    ]
    assert created_calls[0][2].page_size == 25
    assert created_calls[0][3] is False
    assert created_calls[0][4] is True
    assert manifest.status == "complete"

    loaded = load_user_manifest(tmp_path / "user_manifest.json")
    assert loaded.username == "adryanlong"
    assert [target.kind for target in loaded.targets] == ["created", "saved_board", "saved_board"]
    assert [target.status for target in loaded.targets] == ["complete", "complete", "complete"]


def test_crawl_user_boards_dry_run_does_not_download_but_can_complete_scan(
    tmp_path: Path,
) -> None:
    def created_crawler(
        created_url: str,
        output_dir: Path,
        config: RuntimeConfig,
        *,
        dry_run: bool,
        use_playwright: bool,
        client: object = None,
    ) -> BoardManifest:
        assert dry_run is True
        return _board_manifest(created_url, output_dir.name, download_status="not_started")

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
        client=FakeUserClient(
            _user_html([_raw_board("104", "Coastal Calm", "/a/coastal/")]),
        ),
        created_crawler=created_crawler,
        board_crawler=board_crawler,
    )

    assert manifest.status == "complete"
    assert manifest.targets[0].status == "complete"


def test_crawl_user_boards_rejects_existing_board_id_mismatch_as_complete(
    tmp_path: Path,
) -> None:
    board_dir = tmp_path / "saved" / "coastal-calm"
    save_board_manifest(
        board_dir / "manifest.json",
        _board_manifest(
            "https://www.pinterest.com/adryanlong/coastal-calm/",
            "coastal-calm",
            board_id="wrong",
            download_status="complete",
        ),
    )

    def created_crawler(
        created_url: str,
        output_dir: Path,
        config: RuntimeConfig,
        *,
        dry_run: bool,
        use_playwright: bool,
        client: object = None,
    ) -> BoardManifest:
        return _board_manifest(created_url, output_dir.name, download_status="complete")

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
        created_crawler=created_crawler,
        board_crawler=board_crawler,
    )

    assert manifest.status == "failed"
    assert manifest.targets[1].status == "failed"
    assert manifest.targets[1].error == "Board manifest ID mismatch"


def test_crawl_user_boards_resumes_from_existing_user_manifest(tmp_path: Path) -> None:
    first_calls = 0

    def created_crawler(
        created_url: str,
        output_dir: Path,
        config: RuntimeConfig,
        *,
        dry_run: bool,
        use_playwright: bool,
        client: object = None,
    ) -> BoardManifest:
        nonlocal first_calls
        first_calls += 1
        manifest = _board_manifest(created_url, output_dir.name, download_status="complete")
        save_board_manifest(output_dir / "manifest.json", manifest)
        return manifest

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
        created_crawler=created_crawler,
        board_crawler=board_crawler,
    )

    second = crawl_user_boards(
        "https://www.pinterest.com/adryanlong/",
        tmp_path,
        RuntimeConfig(),
        client=FakeUserClient(_user_html([])),
        created_crawler=created_crawler,
        board_crawler=board_crawler,
    )

    assert first_calls == 2
    assert second.status == "complete"


def test_crawl_user_boards_rediscovers_targets_when_existing_manifest_is_stale(
    tmp_path: Path,
) -> None:
    first_calls = 0

    def created_crawler(
        created_url: str,
        output_dir: Path,
        config: RuntimeConfig,
        *,
        dry_run: bool,
        use_playwright: bool,
        client: object = None,
    ) -> BoardManifest:
        nonlocal first_calls
        first_calls += 1
        manifest = _board_manifest(created_url, output_dir.name, download_status="complete")
        save_board_manifest(output_dir / "manifest.json", manifest)
        return manifest

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
        manifest = _board_manifest(
            board_url,
            output_dir.name,
            board_id="104",
            download_status="complete",
        )
        save_board_manifest(output_dir / "manifest.json", manifest)
        return manifest

    crawl_user_boards(
        "https://www.pinterest.com/adryanlong/",
        tmp_path,
        RuntimeConfig(),
        client=FakeUserClient(_user_html({})),
        created_crawler=created_crawler,
        board_crawler=board_crawler,
    )

    manifest = crawl_user_boards(
        "https://www.pinterest.com/adryanlong/",
        tmp_path,
        RuntimeConfig(),
        client=FakeUserClient(
            _user_html([_raw_board("104", "Coastal Calm", "/adryanlong/coastal-calm/")])
        ),
        created_crawler=created_crawler,
        board_crawler=board_crawler,
    )

    assert first_calls == 2
    assert [target.kind for target in manifest.targets] == ["created", "saved_board"]
    assert manifest.status == "complete"


def test_crawl_user_boards_passes_saved_board_directory_without_double_prefix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    output_dirs: list[Path] = []

    def created_crawler(
        created_url: str,
        output_dir: Path,
        config: RuntimeConfig,
        *,
        dry_run: bool,
        use_playwright: bool,
        client: object = None,
    ) -> BoardManifest:
        output_dirs.append(output_dir)
        manifest = _board_manifest(created_url, output_dir.name, download_status="complete")
        save_board_manifest(output_dir / "manifest.json", manifest)
        return manifest

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
        created_crawler=created_crawler,
        board_crawler=board_crawler,
    )

    assert manifest.status == "complete"
    assert output_dirs == [
        Path("downloads/adryanlong/created"),
        Path("downloads/adryanlong/saved/coastal-calm"),
    ]


def _user_html(boards: list[dict[str, object]] | dict[str, dict[str, object]]) -> str:
    if isinstance(boards, list):
        board_map = {str(index): board for index, board in enumerate(boards)}
    else:
        board_map = boards
    props = {"initialReduxState": {"boards": board_map}}
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
