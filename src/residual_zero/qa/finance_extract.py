"""Unstructured narration extraction. Candidate evidence only — never a clear."""

from __future__ import annotations

import re
from typing import Any

from residual_zero.semantic.provider import live_enabled, rewrite

_SOURCES = (
    "RAZORPAY",
    "PAYTM",
    "PHONEPE",
    "GPAY",
    "GOOGLEPAY",
    "STRIPE",
    "CASHFREE",
    "PAYU",
    "BILLDESK",
)
_MONTHS = {
    "JAN": "01",
    "FEB": "02",
    "MAR": "03",
    "APR": "04",
    "MAY": "05",
    "JUN": "06",
    "JUL": "07",
    "AUG": "08",
    "SEP": "09",
    "OCT": "10",
    "NOV": "11",
    "DEC": "12",
}
_ISO_DATE = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")
_MON_DAY = re.compile(r"\b(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)[A-Z]*\.?\s+(\d{1,2})\b")
_REF = re.compile(r"\bREF#?\s*([A-Z0-9-]{3,})\b")
_INV = re.compile(r"\bINV(?:OICE)?[#:\s-]*([A-Z0-9-]{3,})\b")
_SETL = re.compile(r"\b(setl_[A-Za-z0-9]+)\b")
_MEMBER = re.compile(r"\b(acc_\d+|mem_[A-Za-z0-9]+|member[_-]?[A-Za-z0-9]+)\b", re.I)
_PAY = re.compile(r"\b(NEFT|IMPS|RTGS|UPI|ACH)\b")


def extract_reference(narration: str, value_date: str = "", account_id: str = "") -> dict[str, Any]:
    """Deterministic parse. Empty fields stay absent. Never writes CLEARED."""
    raw = (narration or "").strip()
    upper = raw.upper()
    out: dict[str, Any] = {
        "ok": False,
        "source": None,
        "settlement_id": None,
        "settlement_date": None,
        "reference": None,
        "invoice_id": None,
        "member_id": None,
        "payment_type": None,
        "method": "deterministic",
        "candidate_only": True,
        "writes_cleared": False,
    }
    if not raw:
        return out
    for name in _SOURCES:
        if name in upper:
            out["source"] = "GPAY" if name == "GOOGLEPAY" else name
            break
    iso = _ISO_DATE.search(raw)
    if iso:
        out["settlement_date"] = iso.group(1)
    else:
        mon = _MON_DAY.search(upper)
        if mon:
            month = _MONTHS[mon.group(1)]
            day = mon.group(2).zfill(2)
            year = value_date[:4] if len(value_date) >= 4 else ""
            if year.isdigit():
                out["settlement_date"] = year + "-" + month + "-" + day
    ref = _REF.search(upper)
    if ref:
        out["reference"] = ref.group(1)
    inv = _INV.search(upper)
    if inv:
        out["invoice_id"] = inv.group(1)
    setl = _SETL.search(raw)
    if setl:
        out["settlement_id"] = setl.group(1)
    mem = _MEMBER.search(raw)
    if mem:
        out["member_id"] = mem.group(1)
    elif account_id:
        if account_id.upper() in upper or account_id in raw:
            out["member_id"] = account_id
    pay = _PAY.search(upper)
    if pay:
        out["payment_type"] = pay.group(1)
    out["ok"] = any(
        out[k]
        for k in ("source", "settlement_id", "settlement_date", "reference", "invoice_id", "member_id", "payment_type")
    )
    return out


def extract_with_optional_llm(narration: str, value_date: str = "", account_id: str = "") -> dict[str, Any]:
    """Deterministic extract first. LLM may only fill empty keys; then lookup still required."""
    got = extract_reference(narration, value_date, account_id)
    if not live_enabled() or got["ok"]:
        return got
    prose, err = rewrite(
        "extract payment reference fields",
        "Narration has no money amounts. Return source settlement_date reference only if present.",
    )
    if not prose or err:
        got["llm_error"] = err
        return got
    got["llm_attempted"] = True
    got["method"] = "deterministic+llm_unused_without_schema"
    return got


def score_extraction(predicted: dict[str, Any], gold: dict[str, Any]) -> dict[str, int]:
    """Integer field counts. precision = correct/predicted, recall = correct/gold."""
    keys = ("source", "settlement_id", "settlement_date", "reference", "invoice_id", "member_id", "payment_type")
    pred_n = 0
    gold_n = 0
    correct = 0
    false_n = 0
    for key in keys:
        p = predicted.get(key)
        g = gold.get(key)
        if p:
            pred_n += 1
            if g and str(p).upper() == str(g).upper():
                correct += 1
            else:
                false_n += 1
        if g:
            gold_n += 1
    return {
        "predicted_fields": pred_n,
        "gold_fields": gold_n,
        "correct_fields": correct,
        "false_fields": false_n,
    }
