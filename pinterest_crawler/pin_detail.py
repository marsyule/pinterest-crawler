"""Parsing helpers for Pinterest pin detail pages."""

from __future__ import annotations

import json
from json import JSONDecodeError
from typing import cast

from pinterest_crawler.models import JsonObject


_RELAY_CALL = "window.__PWS_RELAY_REGISTER_COMPLETED_REQUEST__("


class PinDetailParseError(ValueError):
    """Raised when Pinterest pin detail metadata cannot be extracted."""


def extract_pin_detail_metadata(html: str) -> JsonObject:
    """Extract raw Pinterest pin detail metadata from a pin detail page.

    Args:
        html: Raw Pinterest pin detail page HTML.

    Returns:
        Raw `payload.data.v3GetPinQueryv2.data` object.

    Raises:
        PinDetailParseError: If the relay payload is absent, malformed, or has
            non-object detail data.
    """

    saw_decode_error = False
    for payload_text in _iter_completed_request_payloads(html):
        try:
            payload = json.loads(payload_text)
        except JSONDecodeError:
            saw_decode_error = True
            continue

        if not isinstance(payload, dict):
            continue

        detail = _extract_detail_data(cast(JsonObject, payload))
        if detail is not None:
            return detail

    if saw_decode_error:
        raise PinDetailParseError("Could not decode completed request payload")
    raise PinDetailParseError("No completed request contains v3GetPinQueryv2.data")


def _iter_completed_request_payloads(html: str) -> list[str]:
    payloads: list[str] = []
    search_from = 0
    while True:
        call_start = html.find(_RELAY_CALL, search_from)
        if call_start == -1:
            return payloads
        args_start = call_start + len(_RELAY_CALL)
        payload_start = _find_second_argument_start(html, args_start)
        if payload_start is None:
            search_from = args_start
            continue
        payload_end = _find_json_value_end(html, payload_start)
        if payload_end is None:
            payloads.append(html[payload_start:])
            return payloads
        payloads.append(html[payload_start:payload_end])
        search_from = payload_end


def _find_second_argument_start(text: str, index: int) -> int | None:
    in_string = False
    escape = False
    quote = ""
    while index < len(text):
        char = text[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == quote:
                in_string = False
        elif char in {'"', "'"}:
            in_string = True
            quote = char
        elif char == ",":
            return _skip_whitespace(text, index + 1)
        index += 1
    return None


def _find_json_value_end(text: str, index: int) -> int | None:
    decoder = json.JSONDecoder()
    try:
        _, end = decoder.raw_decode(text[index:])
    except JSONDecodeError:
        return None
    return index + end


def _skip_whitespace(text: str, index: int) -> int:
    while index < len(text) and text[index].isspace():
        index += 1
    return index


def _extract_detail_data(payload: JsonObject) -> JsonObject | None:
    data = payload.get("data")
    if not isinstance(data, dict):
        return None
    query = data.get("v3GetPinQueryv2")
    if not isinstance(query, dict):
        return None
    detail = query.get("data")
    if not isinstance(detail, dict):
        raise PinDetailParseError("v3GetPinQueryv2.data must be a JSON object")
    return cast(JsonObject, detail)
