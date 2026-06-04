"""Runtime configuration loading for Pinterest crawling."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


DEFAULT_CONFIG_FILE = "pinterest-crawler.yaml"


@dataclass(frozen=True)
class RuntimeConfig:
    """Settings that control crawl intensity and download retry behavior.

    Args:
        page_size: Requested `BoardFeedResource` page size.
        image_concurrency: Maximum concurrent image downloads.
        request_delay: Base delay before Pinterest data requests.
        jitter: Random extra delay added to Pinterest data requests.
        max_pages: Maximum `BoardFeedResource` pages per board.
        limit: Maximum accepted board-owned pins per board.
        retries: Retry count per image candidate URL.
    """

    page_size: int = 15
    image_concurrency: int = 4
    request_delay: float = 1.0
    jitter: float = 0.5
    max_pages: int = 50
    limit: int = 500
    retries: int = 2


def load_runtime_config(
    config_path: Path | None = None, *, cwd: Path | None = None
) -> RuntimeConfig:
    """Load runtime configuration from defaults and optional YAML.

    Args:
        config_path: Explicit YAML path. Missing explicit paths are errors.
        cwd: Directory used for default config discovery.

    Returns:
        Validated runtime configuration.

    Raises:
        FileNotFoundError: If an explicit config path does not exist.
        ValueError: If the YAML content or merged values are invalid.
    """

    search_dir = cwd or Path.cwd()
    path = config_path if config_path is not None else search_dir / DEFAULT_CONFIG_FILE
    values = _defaults_dict()

    if path.exists():
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if raw is None:
            raw = {}
        if not isinstance(raw, dict):
            raise ValueError("Runtime config must be a YAML mapping")
        for key, value in raw.items():
            if not isinstance(key, str):
                raise ValueError("Runtime config keys must be strings")
            if key not in values:
                raise ValueError(f"Unknown runtime config key: {key}")
            values[key] = value
    elif config_path is not None:
        raise FileNotFoundError(f"Config file not found: {path}")

    config = RuntimeConfig(
        page_size=_int_value(values["page_size"], "page_size"),
        image_concurrency=_int_value(values["image_concurrency"], "image_concurrency"),
        request_delay=_float_value(values["request_delay"], "request_delay"),
        jitter=_float_value(values["jitter"], "jitter"),
        max_pages=_int_value(values["max_pages"], "max_pages"),
        limit=_int_value(values["limit"], "limit"),
        retries=_int_value(values["retries"], "retries"),
    )
    _validate(config)
    return config


def _defaults_dict() -> dict[str, object]:
    defaults = RuntimeConfig()
    return {
        "page_size": defaults.page_size,
        "image_concurrency": defaults.image_concurrency,
        "request_delay": defaults.request_delay,
        "jitter": defaults.jitter,
        "max_pages": defaults.max_pages,
        "limit": defaults.limit,
        "retries": defaults.retries,
    }


def _int_value(value: object, name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be an integer")
    if isinstance(value, int):
        return value
    raise ValueError(f"{name} must be an integer")


def _float_value(value: object, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a number")
    if isinstance(value, int | float):
        return float(value)
    raise ValueError(f"{name} must be a number")


def _validate(config: RuntimeConfig) -> None:
    if config.page_size < 1:
        raise ValueError("page_size must be >= 1")
    if config.image_concurrency < 1:
        raise ValueError("image_concurrency must be >= 1")
    if config.request_delay < 0:
        raise ValueError("request_delay must be >= 0")
    if config.jitter < 0:
        raise ValueError("jitter must be >= 0")
    if config.max_pages < 1:
        raise ValueError("max_pages must be >= 1")
    if config.limit < 1:
        raise ValueError("limit must be >= 1")
    if config.retries < 0:
        raise ValueError("retries must be >= 0")
