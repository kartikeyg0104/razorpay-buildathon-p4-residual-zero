"""Deterministic finance intents. The LLM may refine UNKNOWN; data still comes from tools."""

from __future__ import annotations

import re
from enum import Enum

CREDIT_RE = re.compile(r"crd_[a-zA-Z0-9_]+")
TXN_RE = re.compile(r"\b(?:transaction|credit)\s+([A-Za-z0-9_-]+)\b", re.I)


class FinanceIntent(str, Enum):
    BATCH_SUMMARY = "BATCH_SUMMARY"
    TRANSACTION_LOOKUP = "TRANSACTION_LOOKUP"
    TRANSACTION_EXPLANATION = "TRANSACTION_EXPLANATION"
    EXCEPTION_ANALYSIS = "EXCEPTION_ANALYSIS"
    UNRECONCILED_ANALYSIS = "UNRECONCILED_ANALYSIS"
    AMBIGUITY_ANALYSIS = "AMBIGUITY_ANALYSIS"
    SETTLEMENT_ANALYSIS = "SETTLEMENT_ANALYSIS"
    TAX_ANALYSIS = "TAX_ANALYSIS"
    AUDIT_ANALYSIS = "AUDIT_ANALYSIS"
    PERFORMANCE_ANALYSIS = "PERFORMANCE_ANALYSIS"
    COMPARISON = "COMPARISON"
    EXTRACT_REFERENCE = "EXTRACT_REFERENCE"
    REFUSE_CLEAR = "REFUSE_CLEAR"
    PRODUCT_POLICY = "PRODUCT_POLICY"
    CLOSE_BRIEFING = "CLOSE_BRIEFING"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    ROOT_CAUSE = "ROOT_CAUSE"
    EXPLORER = "EXPLORER"
    INVESTIGATE = "INVESTIGATE"
    RECOVERABLE = "RECOVERABLE"
    UNKNOWN = "UNKNOWN"


def extract_credit_id(question: str, credit_id: str = "") -> str:
    cid = (credit_id or "").strip()
    if cid.startswith("crd_"):
        return cid
    found = CREDIT_RE.search(question)
    if found:
        return found.group(0)
    extra = TXN_RE.search(question)
    if extra:
        token = extra.group(1).strip(".,:;?!")
        if token:
            return token
    return cid


def classify_finance_intent(question: str) -> FinanceIntent:
    q = question.casefold()
    if any(
        token in q
        for token in (
            "clear it",
            "clear this",
            "clear this transaction",
            "auto-clear this",
            "auto clear this",
            "mark as cleared",
            "mark it verified",
            "mark this verified",
            "mark it as verified",
            "approve it",
            "authorise a clear",
            "authorize a clear",
            "probably correct and clear",
            "assume this is the correct match",
            "assume candidate a is correct",
            "pick the first candidate",
            "choose candidate a",
            "select solution a",
            "ignore ambiguity",
            "most likely match",
            "just clear it",
            "write cleared",
            "write CLEARED",
            "override uniqueness",
            "highest scoring candidate",
            "99% likely",
            "99 percent likely",
            "human already approved",
            "ignore the search budget",
            "pretend the candidate is unique",
            "clear it because residual",
        )
    ):
        if "most likely match" in q:
            return FinanceIntent.AMBIGUITY_ANALYSIS
        return FinanceIntent.REFUSE_CLEAR
    if "assume" in q and "clear" in q:
        return FinanceIntent.REFUSE_CLEAR
    if "cannot authorize" in q or "cannot authorise" in q:
        return FinanceIntent.REFUSE_CLEAR
    if any(
        token in q
        for token in (
            "auto-clear",
            "auto clear",
            "threshold",
            "gate a",
            "verify_declared",
            "does overlay write",
        )
    ):
        return FinanceIntent.PRODUCT_POLICY
    if "cleared yesterday" in q or "reconciled today" in q or "cleared today" in q:
        return FinanceIntent.PERFORMANCE_ANALYSIS
    if "unreconciled" in q:
        return FinanceIntent.UNRECONCILED_ANALYSIS
    if any(token in q for token in ("compare verified", "verified versus", "verified vs")):
        return FinanceIntent.COMPARISON
    if "batch summary" in q or "summary of this batch" in q or "summary of the current" in q:
        return FinanceIntent.BATCH_SUMMARY
    if "how many transactions" in q and "ambiguous" in q:
        return FinanceIntent.AMBIGUITY_ANALYSIS
    if "how many" in q and "false clear" in q:
        return FinanceIntent.PERFORMANCE_ANALYSIS
    if "false clear" in q:
        return FinanceIntent.PERFORMANCE_ANALYSIS
    if "how many" in q and "auto-clear" in q:
        return FinanceIntent.PERFORMANCE_ANALYSIS
    if "search coverage" in q or "searched successfully" in q:
        return FinanceIntent.PERFORMANCE_ANALYSIS
    if "ambiguous" in q and ("why" in q or "explain" in q or "can't" in q or "cannot" in q):
        return FinanceIntent.AMBIGUITY_ANALYSIS
    if "how many" in q and "ambiguous" in q:
        return FinanceIntent.AMBIGUITY_ANALYSIS
    if "why can't we simply clear" in q or "why can't we clear the ambiguous" in q:
        return FinanceIntent.AMBIGUITY_ANALYSIS
    if any(
        token in q
        for token in (
            "first combination",
            "choose the first",
            "just choose the first",
            "why can't you just choose",
            "why cant you just choose",
            "competing explanations",
            "show competing",
        )
    ):
        return FinanceIntent.AMBIGUITY_ANALYSIS
    if any(
        token in q
        for token in (
            "missing ledger",
            "missing refund",
            "missing record",
            "settlement report is missing",
            "tax mismatch",
            "exception",
        )
    ):
        return FinanceIntent.EXCEPTION_ANALYSIS
    if "tax" in q and ("breakdown" in q or "mismatch" in q or "gst" in q):
        return FinanceIntent.TAX_ANALYSIS
    if "audit" in q:
        return FinanceIntent.AUDIT_ANALYSIS
    if "settlement" in q and ("exception" in q or "highest" in q or "details" in q):
        return FinanceIntent.SETTLEMENT_ANALYSIS
    if "why are so many" in q or "root cause" in q or "dominant blocker" in q or "biggest blocker" in q or "reconciliation blocker" in q:
        return FinanceIntent.ROOT_CAUSE
    if "potentially recoverable" in q or "may be recoverable" in q:
        return FinanceIntent.RECOVERABLE
    if any(
        token in q
        for token in (
            "find unresolved",
            "high-value ambiguous",
            "high value ambiguous",
            "highest-value unresolved",
            "highest value unresolved",
            "highest-value unresolved transactions",
            "missing settlement report",
            "description contains a settlement",
            "ai found a reference",
            "refund mismatch",
            "settlement and ledger disagree",
            "which exceptions are potentially",
        )
    ):
        return FinanceIntent.EXPLORER
    if "investigate" in q:
        return FinanceIntent.INVESTIGATE
    if any(token in q for token in ("extract", "narration", "ref#", "unstructured")):
        return FinanceIntent.EXTRACT_REFERENCE
    if any(
        token in q
        for token in (
            "standup",
            "what should i work on",
            "what should i work on next",
            "today's work",
            "todays work",
            "month-end briefing",
            "close briefing",
            "who should i review first",
            "work first",
        )
    ):
        return FinanceIntent.CLOSE_BRIEFING
    if "human review" in q or "need human" in q or "need a human" in q:
        return FinanceIntent.HUMAN_REVIEW
    if any(
        token in q
        for token in (
            "why wasn't",
            "why wasnt",
            "why didn't",
            "why didnt",
            "why can't this",
            "why cant this",
            "why not matched",
            "why this did not",
            "why wasn't this",
            "why is this transaction ambiguous",
            "why was this not matched",
            "why is ",
        )
    ) and (CREDIT_RE.search(question) or "this transaction" in q or "this credit" in q or "this not matched" in q or "short" in q):
        return FinanceIntent.TRANSACTION_EXPLANATION
    if "why didn't this transaction reconcile" in q or "why did this transaction" in q:
        return FinanceIntent.TRANSACTION_EXPLANATION
    if "biggest" in q or "top exception" in q or "highest exception" in q:
        return FinanceIntent.EXCEPTION_ANALYSIS
    if "which account" in q:
        return FinanceIntent.EXCEPTION_ANALYSIS
    if "how many transactions" in q or "total number of transactions" in q:
        return FinanceIntent.BATCH_SUMMARY
    if "residual-zero" in q or "residual zero" in q:
        return FinanceIntent.PERFORMANCE_ANALYSIS
    if any(
        token in q
        for token in (
            "explain this transaction",
            "explain this credit",
            "explain this",
        )
    ):
        return FinanceIntent.TRANSACTION_EXPLANATION
    if CREDIT_RE.search(question) and "why" in q:
        return FinanceIntent.TRANSACTION_EXPLANATION
    if CREDIT_RE.search(question):
        return FinanceIntent.TRANSACTION_LOOKUP
    if "summary" in q:
        return FinanceIntent.BATCH_SUMMARY
    return FinanceIntent.UNKNOWN
