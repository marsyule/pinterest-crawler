"""Tests for Pinterest image candidate extraction."""

from pinterest_crawler.images import extract_image_candidates, select_best_image
from pinterest_crawler.models import JsonObject


def test_select_best_image_prefers_originals_url() -> None:
    candidates = [
        "https://i.pinimg.com/736x/aa/bb/cc/example.jpg",
        "https://i.pinimg.com/originals/aa/bb/cc/example.jpg",
    ]

    assert select_best_image(candidates) == "https://i.pinimg.com/originals/aa/bb/cc/example.jpg"


def test_extract_image_candidates_reads_pin_and_story_pin_images() -> None:
    pin: JsonObject = {
        "images": {
            "736x": {"url": "https://i.pinimg.com/736x/aa/bb/cc/normal.jpg"},
            "orig": {"url": "https://i.pinimg.com/originals/aa/bb/cc/normal.jpg"},
        },
        "story_pin_data": {
            "pages": [
                {
                    "blocks": [
                        {
                            "image": {
                                "images": {
                                    "1200x": {
                                        "url": "https://i.pinimg.com/1200x/dd/ee/ff/story.jpg"
                                    }
                                }
                            }
                        }
                    ]
                }
            ]
        },
    }

    candidates = extract_image_candidates(pin)

    assert candidates == [
        "https://i.pinimg.com/originals/aa/bb/cc/normal.jpg",
        "https://i.pinimg.com/736x/aa/bb/cc/normal.jpg",
        "https://i.pinimg.com/1200x/dd/ee/ff/story.jpg",
    ]


def test_select_best_image_returns_none_for_empty_candidates() -> None:
    assert select_best_image([]) is None
