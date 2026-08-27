"""Canonical JSON. D11 pins every byte of this; a second implementation is a defect."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from datetime import date, datetime
from typing import Any, Mapping

from residual_zero.tz import iso_utc


def _nfc(value: Any) -> Any:
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, dict):
        return {unicodedata.normalize("NFC", str(k)): _nfc(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_nfc(v) for v in value]
    if isinstance(value, float):
        raise TypeError("floats are forbidden in a canonical payload")
    if isinstance(value, datetime):
        return iso_utc(value)
    if isinstance(value, date):
        return value.isoformat()
    return value


def canonical_json(payload: Mapping[str, Any]) -> bytes:
    """json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
    allow_nan=False).encode('utf-8'), with every string NFC-normalised first.
    """
    prepared = _nfc(dict(payload))
    return json.dumps(
        prepared,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def payload_digest(payload: Mapping[str, Any]) -> str:
    """Lowercase hex sha256 of canonical_json(payload)."""
    return hashlib.sha256(canonical_json(payload)).hexdigest()
