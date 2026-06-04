"""Tests for board downloader orchestration."""

from pathlib import Path

import httpx

from pinterest_crawler.config import RuntimeConfig
from pinterest_crawler.downloader import download_manifest
from pinterest_crawler.manifest import load_board_manifest, save_board_manifest
from pinterest_crawler.models import BoardManifest, PinDownload


class FakeImageClient:
    """In-memory image downloader used by downloader tests."""

    def __init__(self, results: dict[str, list[bytes | Exception]] | None = None) -> None:
        self.results = results or {}
        self.downloaded_urls: list[str] = []

    def download_bytes(self, url: str) -> bytes:
        self.downloaded_urls.append(url)
        results = self.results.get(url)
        if not results:
            return f"bytes from {url}".encode()
        result = results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def test_download_manifest_processes_planned_records_with_fallback(tmp_path: Path) -> None:
    original = "https://i.pinimg.com/originals/aa/bb/pin-1.jpg"
    fallback = "https://i.pinimg.com/736x/aa/bb/pin-1.jpg"
    manifest_path = tmp_path / "manifest.json"
    save_board_manifest(
        manifest_path,
        _manifest(
            [
                _record(
                    "pin-1",
                    [original, fallback],
                    status="planned",
                )
            ]
        ),
    )
    client = FakeImageClient(results={original: [_http_error(404, original)]})

    manifest = download_manifest(
        manifest_path,
        tmp_path,
        RuntimeConfig(retries=1, image_concurrency=1),
        client=client,
    )

    assert client.downloaded_urls == [original, fallback]
    assert manifest.download_status == "complete"
    assert manifest.records[0].status == "success"
    assert manifest.records[0].selected_image_url == fallback
    assert manifest.records[0].attempted_urls == [original, fallback]
    assert (tmp_path / "pin-1.jpg").read_bytes() == f"bytes from {fallback}".encode()


def test_download_manifest_retries_failed_and_downloading_records(tmp_path: Path) -> None:
    url = "https://i.pinimg.com/originals/aa/bb/pin-1.jpg"
    manifest_path = tmp_path / "manifest.json"
    save_board_manifest(
        manifest_path,
        _manifest([_record("pin-1", [url], status="downloading")]),
    )
    client = FakeImageClient(results={url: [RuntimeError("temporary"), b"image bytes"]})

    manifest = download_manifest(
        manifest_path,
        tmp_path,
        RuntimeConfig(retries=1, image_concurrency=1),
        client=client,
    )

    assert client.downloaded_urls == [url, url]
    assert manifest.records[0].status == "success"
    assert manifest.records[0].attempted_urls == [url, url]


def test_download_manifest_marks_success_with_missing_file_for_redownload(tmp_path: Path) -> None:
    url = "https://i.pinimg.com/originals/aa/bb/pin-1.jpg"
    manifest_path = tmp_path / "manifest.json"
    save_board_manifest(
        manifest_path,
        _manifest(
            [
                _record(
                    "pin-1",
                    [url],
                    status="success",
                    selected_image_url=url,
                    local_path="pin-1.jpg",
                )
            ]
        ),
    )
    client = FakeImageClient()

    manifest = download_manifest(manifest_path, tmp_path, RuntimeConfig(), client=client)

    assert client.downloaded_urls == [url]
    assert manifest.records[0].status == "success"
    assert (tmp_path / "pin-1.jpg").exists()


def test_download_manifest_skips_existing_success_records(tmp_path: Path) -> None:
    url = "https://i.pinimg.com/originals/aa/bb/pin-1.jpg"
    (tmp_path / "pin-1.jpg").write_bytes(b"existing")
    manifest_path = tmp_path / "manifest.json"
    save_board_manifest(
        manifest_path,
        _manifest(
            [
                _record(
                    "pin-1",
                    [url],
                    status="success",
                    selected_image_url=url,
                    local_path="pin-1.jpg",
                )
            ]
        ),
    )
    client = FakeImageClient()

    manifest = download_manifest(manifest_path, tmp_path, RuntimeConfig(), client=client)

    assert client.downloaded_urls == []
    assert manifest.download_status == "complete"


def test_download_manifest_saves_downloading_checkpoint_before_network(tmp_path: Path) -> None:
    url = "https://i.pinimg.com/originals/aa/bb/pin-1.jpg"
    manifest_path = tmp_path / "manifest.json"
    save_board_manifest(manifest_path, _manifest([_record("pin-1", [url], status="planned")]))

    class InspectingClient(FakeImageClient):
        def download_bytes(self, url: str) -> bytes:
            assert load_board_manifest(manifest_path).records[0].status == "downloading"
            return super().download_bytes(url)

    download_manifest(
        manifest_path,
        tmp_path,
        RuntimeConfig(image_concurrency=1),
        client=InspectingClient(),
    )


def _manifest(records: list[PinDownload]) -> BoardManifest:
    return BoardManifest(
        board_id="104",
        board_url="https://www.pinterest.com/adryanlong/golden-hour/",
        board_name="Golden Hour",
        board_slug="golden-hour",
        scan_status="complete",
        download_status="not_started",
        next_bookmark=None,
        pages_done=0,
        accepted_pins=len(records),
        reached_end=True,
        error=None,
        records=records,
    )


def _record(
    pin_id: str,
    candidates: list[str],
    *,
    status: str,
    selected_image_url: str | None = None,
    local_path: str | None = None,
) -> PinDownload:
    return PinDownload(
        pin_id=pin_id,
        source_url=f"https://www.pinterest.com/pin/{pin_id}/",
        image_candidates=candidates,
        selected_image_url=selected_image_url,
        attempted_urls=[],
        local_path=local_path,
        status=status,  # type: ignore[arg-type]
        error=None,
    )


def _http_error(status_code: int, url: str) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", url)
    response = httpx.Response(status_code, request=request)
    return httpx.HTTPStatusError(f"{status_code} response", request=request, response=response)
