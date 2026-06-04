"""Extract and rank image URLs from Pinterest pins."""

from __future__ import annotations

from pinterest_crawler.models import JsonObject, JsonValue


IMAGE_KEYS = ("orig", "originals", "1200x", "736x", "474x", "236x", "237x")


def extract_image_candidates(pin: JsonObject) -> list[str]:
    """Extract image URL candidates from a pin.

    Args:
        pin: Raw Pinterest pin object.

    Returns:
        Ordered, de-duplicated image URL candidates.
    """

    candidates: list[str] = []
    _extend_image_urls(candidates, pin.get("images"))
    _extend_story_image_urls(candidates, pin.get("story_pin_data"))
    return _dedupe(candidates)


def select_best_image(candidates: list[str]) -> str | None:
    """Select the best image URL from candidates.

    Args:
        candidates: Candidate image URLs.

    Returns:
        Best URL, or `None` when no candidates exist.
    """

    if not candidates:
        return None

    return sorted(candidates, key=_image_rank)[0]


def _extend_image_urls(candidates: list[str], images: JsonValue) -> None:
    if not isinstance(images, dict):
        return
    for key in IMAGE_KEYS:
        value = images.get(key)
        if not isinstance(value, dict):
            continue
        url = value.get("url")
        if isinstance(url, str):
            candidates.append(url)


def _extend_story_image_urls(candidates: list[str], story_pin_data: JsonValue) -> None:
    if not isinstance(story_pin_data, dict):
        return
    pages = story_pin_data.get("pages")
    if not isinstance(pages, list):
        return
    for page in pages:
        if not isinstance(page, dict):
            continue
        blocks = page.get("blocks")
        if not isinstance(blocks, list):
            continue
        for block in blocks:
            if not isinstance(block, dict):
                continue
            image = block.get("image")
            if not isinstance(image, dict):
                continue
            _extend_image_urls(candidates, image.get("images"))


def _image_rank(url: str) -> tuple[int, int]:
    ranks = (
        ("/originals/", 0),
        ("/1200x/", 1),
        ("/736x/", 2),
        ("/474x/", 3),
        ("/236x/", 4),
        ("/237x/", 5),
    )
    for marker, rank in ranks:
        if marker in url:
            return (rank, len(url))
    return (99, len(url))


def _dedupe(urls: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        result.append(url)
    return result
