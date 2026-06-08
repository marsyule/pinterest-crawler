"""Tests for Pinterest pin detail metadata parsing."""

import json

import pytest

from pinterest_crawler.pin_detail import PinDetailParseError, extract_pin_detail_metadata


def _relay_call(payload: object) -> str:
    return (
        "<script>"
        "window.__PWS_RELAY_REGISTER_COMPLETED_REQUEST__("
        '"request-id",'
        f"{json.dumps(payload)}"
        ");"
        "</script>"
    )


def test_extract_pin_detail_metadata_reads_v3_get_pin_query_data() -> None:
    detail = {"id": "pin-1", "title": "Detail title", "closeup_description": "Full detail"}
    html = _relay_call({"data": {"v3GetPinQueryv2": {"data": detail}}})

    assert extract_pin_detail_metadata(html) == detail


def test_extract_pin_detail_metadata_ignores_unrelated_completed_requests() -> None:
    detail = {"id": "pin-2", "title": "Chosen detail"}
    html = "".join(
        [
            _relay_call({"data": {"SomeOtherQuery": {"data": {"id": "wrong"}}}}),
            _relay_call({"data": {"v3GetPinQueryv2": {"data": detail}}}),
        ]
    )

    assert extract_pin_detail_metadata(html) == detail


def test_extract_pin_detail_metadata_raises_when_detail_metadata_absent() -> None:
    html = _relay_call({"data": {"SomeOtherQuery": {"data": {"id": "wrong"}}}})

    with pytest.raises(PinDetailParseError, match="v3GetPinQueryv2.data"):
        extract_pin_detail_metadata(html)


def test_extract_pin_detail_metadata_raises_when_payload_is_malformed() -> None:
    html = (
        "<script>"
        "window.__PWS_RELAY_REGISTER_COMPLETED_REQUEST__("
        '"request-id",'
        '{"data": {"v3GetPinQueryv2": {"data": {"id": "pin-1"}}}'
        ");"
        "</script>"
    )

    with pytest.raises(PinDetailParseError, match="decode"):
        extract_pin_detail_metadata(html)


def test_extract_pin_detail_metadata_raises_when_detail_data_is_not_object() -> None:
    html = _relay_call({"data": {"v3GetPinQueryv2": {"data": ["pin-1"]}}})

    with pytest.raises(PinDetailParseError, match="JSON object"):
        extract_pin_detail_metadata(html)
