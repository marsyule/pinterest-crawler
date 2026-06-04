"""Image downloader that consumes board manifest records."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from pathlib import Path
from threading import Lock
from typing import Protocol
from urllib.parse import urlparse

import httpx

from pinterest_crawler.config import RuntimeConfig
from pinterest_crawler.http_client import PinterestHttpClient
from pinterest_crawler.images import select_best_image
from pinterest_crawler.manifest import load_board_manifest, save_board_manifest
from pinterest_crawler.models import BoardManifest, CrawlStatus, PinDownload
from pinterest_crawler.scanner import scan_board


class ImageDownloadClient(Protocol):
    """HTTP behavior required by the image downloader."""

    def download_bytes(self, url: str) -> bytes:
        """Download an image URL."""


def crawl_board(
    board_url: str,
    output_dir: Path,
    config: RuntimeConfig,
    *,
    dry_run: bool = False,
    use_playwright: bool = True,
    client: PinterestHttpClient | None = None,
    bootstrap: object | None = None,
) -> BoardManifest:
    """Scan a board if needed, then download unfinished records.

    Args:
        board_url: Public Pinterest board URL.
        output_dir: Directory for manifest and images.
        config: Runtime crawl configuration.
        dry_run: Scan only when true.
        use_playwright: Whether to allow Playwright SSR fallback.
        client: Optional HTTP client for tests.
        bootstrap: Optional Playwright bootstrap function for tests.

    Returns:
        Updated board manifest.
    """

    manifest = scan_board(
        board_url,
        output_dir,
        config,
        use_playwright=use_playwright,
        client=client,
        bootstrap=bootstrap,
    )
    if dry_run or manifest.scan_status != "complete":
        return manifest
    if manifest.download_status == "complete" and _success_files_exist(manifest, output_dir):
        return manifest
    return download_manifest(output_dir / "manifest.json", output_dir, config, client=client)


def download_manifest(
    manifest_path: Path,
    output_dir: Path,
    config: RuntimeConfig,
    *,
    client: ImageDownloadClient | None = None,
) -> BoardManifest:
    """Download unfinished image records from a board manifest.

    Args:
        manifest_path: Board manifest path.
        output_dir: Directory where image files are written.
        config: Runtime crawl configuration.
        client: Optional image download client for tests.

    Returns:
        Updated board manifest.
    """

    owns_client = client is None
    http_client = client or PinterestHttpClient(config=config)
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        manifest = _prepare_missing_files(load_board_manifest(manifest_path), output_dir)
        manifest = replace(manifest, download_status=_initial_download_status(manifest))
        save_board_manifest(manifest_path, manifest)

        indices = [
            index
            for index, record in enumerate(manifest.records)
            if record.status in {"planned", "failed", "missing_file", "downloading"}
        ]
        if not indices:
            complete = replace(manifest, download_status=_final_download_status(manifest))
            save_board_manifest(manifest_path, complete)
            return complete

        records = list(manifest.records)
        lock = Lock()

        def save_record(index: int, record: PinDownload) -> None:
            records[index] = record
            current = replace(
                manifest,
                records=list(records),
                download_status=_status_for_records(records),
                error=None,
            )
            save_board_manifest(manifest_path, current)

        def work(index: int) -> None:
            record = records[index]
            downloading = replace(record, status="downloading", error=None)
            with lock:
                save_record(index, downloading)
            finished = _download_one(http_client, downloading, output_dir, config)
            with lock:
                save_record(index, finished)

        with ThreadPoolExecutor(max_workers=config.image_concurrency) as executor:
            futures = [executor.submit(work, index) for index in indices]
            for future in as_completed(futures):
                future.result()

        final = replace(
            manifest,
            records=records,
            download_status=_final_download_status(replace(manifest, records=records)),
            error=None,
        )
        save_board_manifest(manifest_path, final)
        return final
    finally:
        if owns_client and isinstance(http_client, PinterestHttpClient):
            http_client.close()


def _download_one(
    client: ImageDownloadClient,
    record: PinDownload,
    output_dir: Path,
    config: RuntimeConfig,
) -> PinDownload:
    if not record.image_candidates:
        return replace(record, status="failed", error="No image URL found")

    attempted_urls: list[str] = []
    last_error: str | None = None
    for url in sorted(record.image_candidates, key=_candidate_rank):
        for _ in range(config.retries + 1):
            attempted_urls.append(url)
            try:
                content = client.download_bytes(url)
            except Exception as exc:
                last_error = str(exc)
                if _is_non_retryable_http_error(exc):
                    break
                continue

            local_path = _local_path_for_pin(output_dir, record.pin_id, url)
            local_path.write_bytes(content)
            return replace(
                record,
                selected_image_url=url,
                attempted_urls=attempted_urls,
                local_path=local_path.name,
                status="success",
                error=None,
            )

    return replace(
        record,
        attempted_urls=attempted_urls,
        status="failed",
        error=last_error,
    )


def _prepare_missing_files(manifest: BoardManifest, output_dir: Path) -> BoardManifest:
    records: list[PinDownload] = []
    for record in manifest.records:
        if record.status == "success" and record.local_path is not None:
            local_path = Path(record.local_path)
            if not local_path.is_absolute():
                local_path = output_dir / local_path
            if not local_path.exists():
                records.append(replace(record, status="missing_file"))
                continue
        records.append(record)
    return replace(manifest, records=records)


def _success_files_exist(manifest: BoardManifest, output_dir: Path) -> bool:
    for record in manifest.records:
        if record.status == "skipped":
            continue
        if record.status != "success" or record.local_path is None:
            return False
        local_path = Path(record.local_path)
        if not local_path.is_absolute():
            local_path = output_dir / local_path
        if not local_path.exists():
            return False
    return True


def _initial_download_status(manifest: BoardManifest) -> CrawlStatus:
    if not manifest.records:
        return "complete"
    if all(record.status in {"success", "skipped"} for record in manifest.records):
        return "complete"
    return "in_progress"


def _status_for_records(records: list[PinDownload]) -> CrawlStatus:
    if all(record.status in {"success", "skipped"} for record in records):
        return "complete"
    if any(record.status == "failed" for record in records):
        return "failed"
    return "in_progress"


def _final_download_status(manifest: BoardManifest) -> CrawlStatus:
    return _status_for_records(manifest.records)


def _candidate_rank(url: str) -> tuple[int, int]:
    selected = select_best_image([url])
    if selected is None:
        return (99, len(url))
    markers = (
        ("/originals/", 0),
        ("/1200x/", 1),
        ("/736x/", 2),
        ("/474x/", 3),
        ("/236x/", 4),
        ("/237x/", 5),
    )
    for marker, rank in markers:
        if marker in selected:
            return (rank, len(selected))
    return (99, len(selected))


def _is_non_retryable_http_error(exc: Exception) -> bool:
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in {403, 404}


def _local_path_for_pin(output_dir: Path, pin_id: str, url: str | None) -> Path:
    suffix = _suffix_from_url(url) if url else ".jpg"
    return output_dir / f"{pin_id}{suffix}"


def _suffix_from_url(url: str | None) -> str:
    if not url:
        return ".jpg"
    suffix = Path(urlparse(url).path).suffix.lower()
    return suffix if suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif"} else ".jpg"
