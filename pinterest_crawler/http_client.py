"""HTTP client for Pinterest board crawling."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass

import httpx

from pinterest_crawler.board_feed import build_board_feed_headers, build_board_feed_params
from pinterest_crawler.config import RuntimeConfig
from pinterest_crawler.created_feed import (
    build_created_feed_headers,
    build_created_feed_params,
    build_user_resource_headers,
    build_user_resource_params,
)
from pinterest_crawler.models import JsonObject


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)


@dataclass
class RequestLimiter:
    """Serial delay helper for Pinterest data requests."""

    request_delay: float
    jitter: float

    def wait(self) -> None:
        """Sleep for the configured delay and jitter."""

        delay = self.request_delay + random.uniform(0, self.jitter)
        if delay > 0:
            time.sleep(delay)


class PinterestHttpClient:
    """HTTP session wrapper for one Pinterest crawl."""

    def __init__(self, timeout: float = 30.0, config: RuntimeConfig | None = None) -> None:
        self._limiter = (
            RequestLimiter(config.request_delay, config.jitter) if config is not None else None
        )
        self._client = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={
                "User-Agent": DEFAULT_USER_AGENT,
                "Accept-Language": "en-US,en;q=0.9",
            },
        )

    def fetch_board_html(self, board_url: str) -> str:
        """Fetch a Pinterest board page."""

        self._wait_for_data_request()
        response = self._client.get(
            board_url,
            headers={"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"},
        )
        response.raise_for_status()
        return response.text

    def fetch_user_html(self, user_url: str) -> str:
        """Fetch a Pinterest user profile page."""

        self._wait_for_data_request()
        response = self._client.get(
            user_url,
            headers={"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"},
        )
        response.raise_for_status()
        return response.text

    def fetch_user_resource(self, created_url: str, username: str) -> JsonObject:
        """Fetch `UserResource` for a Pinterest created page."""

        self._wait_for_data_request()
        response = self._client.get(
            "https://www.pinterest.com/resource/UserResource/get/",
            params=build_user_resource_params(created_url=created_url, username=username),
            headers=build_user_resource_headers(created_url),
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("UserResource response must be a JSON object")
        return data

    def fetch_user_activity_pins(
        self,
        *,
        created_url: str,
        username: str,
        user_id: str,
        bookmarks: list[str],
    ) -> JsonObject:
        """Fetch one `UserActivityPinsResource` page for a created feed."""

        self._wait_for_data_request()
        response = self._client.get(
            "https://www.pinterest.com/resource/UserActivityPinsResource/get/",
            params=build_created_feed_params(
                user_id=user_id,
                username=username,
                source_url=f"/{created_url.split('pinterest.com/', 1)[-1].strip('/')}/",
                bookmarks=bookmarks,
            ),
            headers=build_created_feed_headers(created_url),
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("UserActivityPinsResource response must be a JSON object")
        return data

    def fetch_board_feed(
        self,
        *,
        board_url: str,
        board_id: str,
        source_url: str,
        bookmarks: list[str],
        page_size: int,
    ) -> JsonObject:
        """Fetch one `BoardFeedResource` page."""

        self._wait_for_data_request()
        response = self._client.get(
            "https://www.pinterest.com/resource/BoardFeedResource/get/",
            params=build_board_feed_params(
                board_id=board_id,
                source_url=source_url,
                bookmarks=bookmarks,
                page_size=page_size,
            ),
            headers=build_board_feed_headers(board_url),
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("BoardFeedResource response must be a JSON object")
        return data

    def download_bytes(self, url: str) -> bytes:
        """Download an image URL."""

        response = self._client.get(url)
        response.raise_for_status()
        return response.content

    def apply_cookies(self, cookies: dict[str, str]) -> None:
        """Apply cookies captured by Playwright."""

        for name, value in cookies.items():
            self._client.cookies.set(name, value, domain=".pinterest.com")

    def close(self) -> None:
        """Close the underlying HTTP session."""

        self._client.close()

    def __enter__(self) -> "PinterestHttpClient":
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()

    def _wait_for_data_request(self) -> None:
        if self._limiter is not None:
            self._limiter.wait()
