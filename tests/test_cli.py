"""Tests for the command line interface."""

from pathlib import Path

import pytest

from pinterest_crawler import cli
from pinterest_crawler.config import RuntimeConfig
from pinterest_crawler.models import BoardManifest, UserManifest


def test_build_parser_uses_hyphenated_project_name() -> None:
    assert cli.build_parser().prog == "pinterest-crawler"


def test_download_command_passes_v13_options_to_board_crawler(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[tuple[str, Path, RuntimeConfig, bool, bool]] = []

    def fake_crawl_board(
        board_url: str,
        output_dir: Path,
        config: RuntimeConfig,
        *,
        dry_run: bool,
        use_playwright: bool,
    ) -> BoardManifest:
        calls.append((board_url, output_dir, config, dry_run, use_playwright))
        return BoardManifest(
            board_id="104",
            board_url=board_url,
            board_name="Golden Hour",
            board_slug="golden-hour",
            scan_status="complete",
            download_status="not_started",
            next_bookmark=None,
            pages_done=0,
            accepted_pins=0,
            reached_end=True,
            error=None,
            records=[],
        )

    monkeypatch.setattr(cli, "crawl_board", fake_crawl_board)

    result = cli.main(
        [
            "download",
            "https://www.pinterest.com/adryanlong/golden-hour/",
            "--out",
            str(tmp_path),
            "--dry-run",
            "--no-playwright",
        ]
    )

    assert result == 0
    assert calls[0][0] == "https://www.pinterest.com/adryanlong/golden-hour/"
    assert calls[0][1] == tmp_path
    assert calls[0][2] == RuntimeConfig()
    assert calls[0][3] is True
    assert calls[0][4] is False
    assert "scan=complete" in capsys.readouterr().out


def test_download_user_command_passes_v13_options_to_batch_crawler(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[tuple[str, Path, RuntimeConfig, bool, bool]] = []

    def fake_crawl_user_boards(
        user_url: str,
        output_dir: Path,
        config: RuntimeConfig,
        *,
        dry_run: bool,
        use_playwright: bool,
    ) -> UserManifest:
        calls.append((user_url, output_dir, config, dry_run, use_playwright))
        return UserManifest(
            user_url=user_url,
            username="adryanlong",
            discovery_status="complete",
            status="complete",
            error=None,
            boards=[],
        )

    monkeypatch.setattr(cli, "crawl_user_boards", fake_crawl_user_boards)

    result = cli.main(
        [
            "download-user",
            "https://www.pinterest.com/adryanlong/",
            "--out",
            str(tmp_path),
        ]
    )

    assert result == 0
    assert calls[0][0] == "https://www.pinterest.com/adryanlong/"
    assert calls[0][1] == tmp_path
    assert calls[0][2] == RuntimeConfig()
    assert calls[0][3] is False
    assert calls[0][4] is True


@pytest.mark.parametrize(
    "removed_arg",
    [
        "--resume",
        "--use-playwright",
        "--page-size",
        "--overwrite",
        "--retries",
        "--limit",
        "--max-pages",
        "--image-concurrency",
        "--request-delay",
        "--jitter",
    ],
)
def test_download_command_rejects_removed_v13_args(removed_arg: str, tmp_path: Path) -> None:
    argv = [
        "download",
        "https://www.pinterest.com/adryanlong/golden-hour/",
        "--out",
        str(tmp_path),
        removed_arg,
    ]
    if removed_arg not in {"--resume", "--use-playwright", "--overwrite"}:
        argv.append("1")

    with pytest.raises(SystemExit):
        cli.main(argv)
