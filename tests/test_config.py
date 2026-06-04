"""Tests for runtime config loading."""

from pathlib import Path

import pytest

from pinterest_crawler.config import RuntimeConfig, load_runtime_config


def test_load_runtime_config_uses_defaults_when_yaml_missing(tmp_path: Path) -> None:
    assert load_runtime_config(cwd=tmp_path) == RuntimeConfig()


def test_load_runtime_config_reads_cwd_yaml(tmp_path: Path) -> None:
    (tmp_path / "pinterest-crawler.yaml").write_text(
        "page_size: 25\nimage_concurrency: 2\nrequest_delay: 0\n",
        encoding="utf-8",
    )

    config = load_runtime_config(cwd=tmp_path)

    assert config.page_size == 25
    assert config.image_concurrency == 2
    assert config.request_delay == 0
    assert config.max_pages == 50


def test_load_runtime_config_reads_explicit_yaml(tmp_path: Path) -> None:
    config_path = tmp_path / "custom.yaml"
    config_path.write_text("limit: 12\nretries: 0\n", encoding="utf-8")

    config = load_runtime_config(config_path)

    assert config.limit == 12
    assert config.retries == 0


def test_load_runtime_config_raises_for_missing_explicit_yaml(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_runtime_config(tmp_path / "missing.yaml")


def test_load_runtime_config_rejects_invalid_values(tmp_path: Path) -> None:
    config_path = tmp_path / "pinterest-crawler.yaml"
    config_path.write_text("image_concurrency: 0\n", encoding="utf-8")

    with pytest.raises(ValueError, match="image_concurrency"):
        load_runtime_config(cwd=tmp_path)
