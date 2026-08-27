"""Closed-intent Q&A over the reconciled ledger. The model never writes SQL."""

from __future__ import annotations

import sqlite3
from enum import Enum
from typing import Mapping

from pydantic import BaseModel, ConfigDict

from residual_zero.semantic.llm import LLMClient

_STRICT = ConfigDict(frozen=True, extra="forbid")


class Intent(str, Enum):
    WHY_SHORT = "WHY_SHORT"
    DEDUCTION_STACK = "DEDUCTION_STACK"
    CREDIT_DETAIL = "CREDIT_DETAIL"
    EXCEPTION_SUMMARY = "EXCEPTION_SUMMARY"
    TIER_MIX = "TIER_MIX"
    UNRECOGNISED = "UNRECOGNISED"


class RetrievedRows(BaseModel):
    model_config = _STRICT

    intent: Intent
    rows: tuple[dict[str, int | str], ...]
    citations: tuple[str, ...]


def classify_intent(question: str, client: LLMClient | None) -> Intent:
    q = question.casefold()
    if "why" in q or "short" in q:
        return Intent.WHY_SHORT
    if "deduction" in q or "stack" in q or "fee" in q:
        return Intent.DEDUCTION_STACK
    if "exception" in q or "flag" in q:
        return Intent.EXCEPTION_SUMMARY
    if "tier" in q:
        return Intent.TIER_MIX
    if "credit" in q or "crd_" in q:
        return Intent.CREDIT_DETAIL
    if client is not None:
        # Model may only pick a closed id. Stub abstains -> UNRECOGNISED.
        return Intent.UNRECOGNISED
    return Intent.UNRECOGNISED


def retrieve(intent: Intent, params: Mapping[str, str], conn: sqlite3.Connection) -> RetrievedRows:
    """Parameterised SQL against the reconciled ledger only, over a read-only connection."""
    credit_id = params.get("credit_id", "")
    if intent == Intent.UNRECOGNISED:
        return RetrievedRows(intent=intent, rows=(), citations=())
    row = conn.execute(
        "SELECT bank_credit_id, claimed_total_paise, residual_paise, uniqueness, disposition "
        "FROM reconciliation WHERE bank_credit_id = ?",
        (credit_id,),
    ).fetchone()
    if row is None:
        return RetrievedRows(intent=intent, rows=(), citations=())
    payload = {
        "bank_credit_id": row[0],
        "claimed_total_paise": row[1],
        "residual_paise": row[2],
        "uniqueness": row[3],
        "disposition": row[4],
    }
    members = [
        r[0]
        for r in conn.execute(
            "SELECT item_id FROM decomposition_member WHERE bank_credit_id = ? ORDER BY item_id",
            (credit_id,),
        )
    ]
    return RetrievedRows(
        intent=intent,
        rows=(payload, {"member_count": len(members)}),
        citations=(credit_id, *members[:3]),
    )
