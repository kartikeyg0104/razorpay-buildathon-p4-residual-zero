"""Deterministic investigation playbooks. Terminal states are never PROBABLY_MATCHED."""

from __future__ import annotations

from typing import Any

TERMINAL = ("PROVEN", "NOT_PROVEN", "MISSING_DATA", "AMBIGUOUS", "CONFLICTING_SOURCES")

PLAYBOOKS: dict[str, tuple[str, ...]] = {
    "NONE_FOUND": (
        "transaction",
        "evidence",
        "reference",
        "settlement",
        "candidates",
        "sources",
        "equations",
        "timeline",
    ),
    "AMBIGUOUS": (
        "transaction",
        "solution_a",
        "solution_b",
        "common_records",
        "differences",
        "distinguishing_evidence",
        "human_review",
    ),
    "MISSING_RECORD": (
        "transaction",
        "settlement",
        "ledger",
        "tax",
        "refund",
        "reserve",
        "source_agreement",
    ),
    "REFUND_MISMATCH": (
        "refund",
        "settlement",
        "bank",
        "ledger",
        "negative_entries",
        "authoritative_amount",
    ),
    "SOURCE_CORRUPTION": (
        "bank",
        "settlement",
        "ledger",
        "fee",
        "gst",
        "withholding",
        "refund",
        "reserve",
    ),
}


def terminal_state(
    uniqueness: str,
    *,
    residual_paise: int | None = None,
    missing_ledger: bool = False,
    missing_settlement: bool = False,
    source_conflict: bool = False,
) -> str:
    if uniqueness == "UNIQUE" and residual_paise == 0:
        return "PROVEN"
    if uniqueness == "AMBIGUOUS":
        return "AMBIGUOUS"
    if missing_ledger or missing_settlement:
        return "MISSING_DATA"
    if source_conflict:
        return "CONFLICTING_SOURCES"
    return "NOT_PROVEN"


def playbook_for(kind: str) -> dict[str, Any]:
    key = str(kind or "NONE_FOUND")
    steps = PLAYBOOKS.get(key, PLAYBOOKS["NONE_FOUND"])
    return {
        "kind": key if key in PLAYBOOKS else "NONE_FOUND",
        "steps": list(steps),
        "writes_cleared": False,
        "forbidden_state": "PROBABLY_MATCHED",
        "note": "Investigation ends in PROVEN / NOT_PROVEN / MISSING_DATA / AMBIGUOUS / CONFLICTING_SOURCES.",
    }
