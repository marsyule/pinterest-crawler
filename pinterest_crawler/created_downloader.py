"""Download orchestration for Pinterest user `Created` feeds."""

from __future__ import annotations

from pathlib import Path

from pinterest_crawler.config import RuntimeConfig
from pinterest_crawler.downloader import download_manifest
from pinterest_crawler.http_client import PinterestHttpClient
from pinterest_crawler.models import BoardManifest
from pinterest_crawler.created_scanner import scan_created_feed


def crawl_created_feed(
    created_url: str,
    output_dir: Path,
    config: RuntimeConfig,
    *,
    dry_run: bool = False,
    use_playwright: bool = True,
    client: PinterestHttpClient | None = None,
) -> BoardManifest:
    """Scan a created feed if needed, then download unfinished records."""

    del use_playwright
    manifest = scan_created_feed(created_url, output_dir, config, client=client)
    if dry_run or manifest.scan_status != "complete":
        return manifest
    return download_manifest(output_dir / "manifest.json", output_dir, config, client=client)
