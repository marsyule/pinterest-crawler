"""Tests for Pinterest HTTP client request construction."""

import httpx
import pytest

from pinterest_crawler.http_client import PinterestHttpClient


def test_fetch_pin_html_requests_public_pin_detail_page() -> None:
    seen_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_requests.append(request)
        return httpx.Response(200, text="<html>pin detail</html>")

    client = PinterestHttpClient()
    client._client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        html = client.fetch_pin_html("12345")
    finally:
        client.close()

    assert html == "<html>pin detail</html>"
    assert str(seen_requests[0].url) == "https://www.pinterest.com/pin/12345/"
    assert seen_requests[0].headers["accept"].startswith("text/html")


def test_http_client_configures_stable_compression_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_headers: dict[str, str] = {}

    class SpyClient:
        def __init__(self, **kwargs: object) -> None:
            headers = kwargs["headers"]
            if not isinstance(headers, dict):
                raise AssertionError("headers must be a dictionary")
            captured_headers.update(headers)

    monkeypatch.setattr("pinterest_crawler.http_client.httpx.Client", SpyClient)

    PinterestHttpClient()

    assert captured_headers["Accept-Encoding"] == "gzip, deflate"
