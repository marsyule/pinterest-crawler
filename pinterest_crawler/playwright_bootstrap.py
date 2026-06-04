"""Playwright bootstrap fallback for Pinterest board pages."""

from __future__ import annotations


def bootstrap_board_page(board_url: str, *, timeout_ms: int = 30_000) -> tuple[str, dict[str, str]]:
    """Fetch rendered board HTML and cookies with Playwright.

    Args:
        board_url: Pinterest board URL.
        timeout_ms: Navigation timeout in milliseconds.

    Returns:
        A tuple of rendered HTML and cookies keyed by cookie name.
    """

    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            context = browser.new_context()
            page = context.new_page()
            page.goto(board_url, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_load_state("networkidle", timeout=timeout_ms)
            html = page.content()
            cookies = {
                cookie["name"]: cookie["value"]
                for cookie in context.cookies()
                if "pinterest.com" in cookie.get("domain", "")
            }
            return html, cookies
        finally:
            browser.close()
