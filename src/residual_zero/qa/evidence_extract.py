"""AI evidence extractor. Candidate fields only. confidence is always null."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

from residual_zero.normalise import extract_reference_token
from residual_zero.qa.finance_extract import extract_reference

PROMPT_VERSION = "extract-v1"
EVIDENCE_TYPE_DET = "DETERMINISTIC_EXTRACTED"
EVIDENCE_TYPE_LLM = "LLM_EXTRACTED"

_ORDER = re.compile(r"\b(ord_[A-Za-z0-9_]+)\b")
_ITEM = re.compile(r"\b(itm_[A-Za-z0-9_]+)\b")
_CREDIT = re.compile(r"\b(crd_[A-Za-z0-9_]+)\b")
_SET_SHORT = re.compile(r"\b(SET[-_][A-Z0-9]{2,})\b")
_TXN = re.compile(r"\b(?:TXN|TX)[-_#]?([A-Z0-9-]{3,})\b")
_REF_FLEX = re.compile(r"\bREF(?:ERENCE)?[#:\s-]*([A-Z0-9-]{3,})\b")


def _field(
    name: str,
    value: str,
    source_record_id: str,
    source_field: str,
    method: str,
    verified: bool = False,
) -> dict[str, Any]:
    return {
        "field": name,
        "value": value,
        "source_record_id": source_record_id,
        "source_field": source_field,
        "method": method,
        "verified": verified,
        "confidence": None,
        "evidence_type": EVIDENCE_TYPE_LLM if method == "LLM" else EVIDENCE_TYPE_DET,
    }


def normalize_identifier(raw: str) -> dict[str, str]:
    """Display normalisation. Never merge records on the normalised form alone."""
    text = (raw or "").strip()
    rule = "identity"
    stripped = text
    upper = stripped.upper()
    for prefix in ("REF#", "REF:", "REF ", "REFERENCE ", "TXN-", "TXN#", "TXN ", "INV-", "INV#", "INVOICE "):
        if upper.startswith(prefix):
            stripped = stripped[len(prefix) :].strip()
            rule = "strip_prefix"
            break
    compact = re.sub(r"[\s_\-#]+", "", stripped).upper()
    if compact != stripped.upper():
        rule = rule + "+strip_punct" if rule != "identity" else "strip_punct"
    return {
        "raw_value": text,
        "normalized_value": compact,
        "normalization_rule": rule,
        "source": "deterministic",
        "verification_status": "UNVERIFIED",
    }


def text_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def extract_unstructured(
    text: str,
    source_record_id: str,
    source_field: str,
    *,
    value_date: str = "",
    account_id: str = "",
    method: str = "deterministic",
) -> list[dict[str, Any]]:
    """Parse unstructured text into provenance-bearing candidate fields."""
    raw = text or ""
    fields: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    def add(name: str, value: str) -> None:
        token = value.strip()
        if not token:
            return
        key = (name, token.upper())
        if key in seen:
            return
        seen.add(key)
        fields.append(_field(name, token, source_record_id, source_field, method))

    base = extract_reference(raw, value_date, account_id)
    mapping = {
        "source": "source",
        "settlement_id": "settlement_id",
        "settlement_date": "date",
        "reference": "reference",
        "invoice_id": "invoice_id",
        "member_id": "member_id",
        "payment_type": "payment_type",
    }
    for src_key, out_key in mapping.items():
        val = base.get(src_key)
        if val:
            add(out_key, str(val))
    utr = extract_reference_token(raw)
    if utr:
        add("reference", utr)
    for match in _ORDER.finditer(raw):
        add("invoice_id", match.group(1))
        add("reference", match.group(1))
    for match in _ITEM.finditer(raw):
        add("member_id", match.group(1))
    for match in _CREDIT.finditer(raw):
        add("settlement_id", match.group(1))
    for match in _SET_SHORT.finditer(raw.upper()):
        add("settlement_id", match.group(1))
    for match in _TXN.finditer(raw.upper()):
        add("reference", match.group(1))
    for match in _REF_FLEX.finditer(raw.upper()):
        add("reference", match.group(1))
    return fields


def cache_path() -> Path:
    raw = os.environ.get("RZ_EXTRACT_CACHE", "").strip()
    if raw:
        return Path(raw)
    return Path("artifacts").joinpath("console", "extract_cache.jsonl")


def _cache_get(key: str) -> list[dict[str, Any]] | None:
    path = cache_path()
    if os.environ.get("PYTEST_CURRENT_TEST") and not os.environ.get("RZ_EXTRACT_CACHE", "").strip():
        return None
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("key") == key:
            fields = row.get("fields")
            if isinstance(fields, list):
                return fields
    return None


def _cache_put(key: str, fields: list[dict[str, Any]]) -> None:
    if os.environ.get("PYTEST_CURRENT_TEST") and not os.environ.get("RZ_EXTRACT_CACHE", "").strip():
        return
    path = cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"key": key, "fields": fields, "prompt_version": PROMPT_VERSION}) + "\n")


def extract_for_credit(
    transaction_id: str,
    narration: str,
    value_date: str = "",
    account_id: str = "",
    utr: str = "",
    extra_texts: tuple[tuple[str, str, str], ...] = (),
) -> dict[str, Any]:
    """Extract from bank narration plus optional extra (record_id, field, text) blobs.

    Cached by transaction_id + text hash + prompt version. Never writes CLEARED.
    """
    blobs = [(transaction_id, "narration_raw", narration)]
    if utr:
        blobs.append((transaction_id, "utr", utr))
    blobs.extend(extra_texts)
    joined = "\n".join(t[2] for t in blobs)
    key = "|".join((transaction_id, text_hash(joined), PROMPT_VERSION, "deterministic"))
    cached = _cache_get(key)
    cache_hit = cached is not None
    fields = cached if cached is not None else []
    if not cache_hit:
        for record_id, field, text in blobs:
            fields.extend(
                extract_unstructured(
                    text,
                    record_id,
                    field,
                    value_date=value_date,
                    account_id=account_id,
                )
            )
        _cache_put(key, fields)
    compact = {
        "source": None,
        "settlement_id": None,
        "reference": None,
        "invoice_id": None,
        "member_id": None,
        "payment_type": None,
        "date": None,
        "confidence": None,
        "evidence_type": EVIDENCE_TYPE_DET,
    }
    for row in fields:
        name = str(row.get("field") or "")
        if name in compact and compact[name] is None:
            compact[name] = row.get("value")
    return {
        "transaction_id": transaction_id,
        "ok": bool(fields),
        "fields": fields,
        "candidate": compact,
        "cache_hit": cache_hit,
        "prompt_version": PROMPT_VERSION,
        "method": "deterministic",
        "writes_cleared": False,
        "candidate_only": True,
    }
