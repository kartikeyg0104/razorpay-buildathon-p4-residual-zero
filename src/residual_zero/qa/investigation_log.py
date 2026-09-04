"""Record what the AI was asked, which read-only tools ran, and what came back.

This is an **investigation** log, not a decision log. Nothing written here can influence a
reconciliation: there is no disposition column, the ``outcome`` values are constrained by a
CHECK that has no ``CLEARED`` in it, and the reconciliation tables are owned by a different
connection (``TABLE_OWNERS``) which this module does not open.

Why record it at all: when a finance operator says "the assistant told me something odd",
the answer has to be reconstructable — which tools it actually called, whether the provider
answered or the deterministic template stood in, and how long it took. Without that, an AI
surface on financial data is unauditable.

Failing to record must never fail the answer. Every write here is best-effort and logs its
own failure, because a full audit table is not a reason to stop telling an operator what
their deterministic engine computed.
"""

from __future__ import annotations

import secrets
from typing import Any, Mapping

from residual_zero import obs

# Mirrors the CHECK constraint in migrations/org/0001_financial.sql. Kept as a frozenset so
# an outcome the schema would reject is caught before the insert rather than as a database
# error, and so `CLEARED` is visibly not a member.
OUTCOMES = frozenset({
    "ANSWERED",
    "INSUFFICIENT_EVIDENCE",
    "PROVIDER_FAILED",
    "BUDGET_EXCEEDED",
    "REFUSED",
    "TEMPLATE_FALLBACK",
})


def classify_outcome(payload: Mapping[str, Any]) -> str:
    """Derive the outcome from what the controller returned. Never optimistic.

    A provider error or an unused provider is reported as such even when the answer itself
    is fine, because the answer being fine is exactly what the deterministic fallback is
    for and the distinction is the interesting one.
    """
    error = str(payload.get("provider_error") or "")
    if "budget" in error.casefold():
        return "BUDGET_EXCEEDED"
    if error:
        return "PROVIDER_FAILED"
    if not payload.get("answer"):
        return "INSUFFICIENT_EVIDENCE"
    if not payload.get("provider_used"):
        return "TEMPLATE_FALLBACK"
    return "ANSWERED"


def record(
    payload: Mapping[str, Any],
    *,
    question: str,
    credit_id: str = "",
    user_id: str = "",
    duration_ms: int = 0,
) -> str | None:
    """Append one investigation row for the current organisation. Returns its id, or None.

    ``None`` means the row was not written — no organisation is bound (the single-tenant
    CLI and the test suite), or the write failed. Neither is an error for the caller.
    """
    from residual_zero.tenancy import current_tenant

    if current_tenant() is None:
        return None
    outcome = classify_outcome(payload)
    if outcome not in OUTCOMES:  # pragma: no cover - defensive
        outcome = "REFUSED"
    investigation_id = "inv_" + secrets.token_hex(12)
    tools = payload.get("tools_called") or payload.get("tools") or ()
    if isinstance(tools, str):
        tools_text = tools
    else:
        tools_text = ",".join(str(t) for t in tools)
    usage = payload.get("usage") if isinstance(payload.get("usage"), Mapping) else {}
    try:
        from residual_zero.storage.engine import open_tenant_readwrite

        conn = open_tenant_readwrite("audit")
        try:
            conn.execute(
                "INSERT OR REPLACE INTO ai_investigation "
                "(investigation_id, credit_id, user_id, question, tools_called, provider, "
                "model, outcome, provider_error, fell_back, prompt_tokens, "
                "completion_tokens, duration_ms) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    investigation_id,
                    (credit_id or "")[:200] or None,
                    (user_id or "")[:200] or None,
                    # The question is the operator's own words about their own records. It
                    # is truncated, not redacted: it is not a credential, and an
                    # investigation log that cannot show the question is not a log.
                    question.strip()[:2000],
                    tools_text[:2000],
                    str(payload.get("provider") or "")[:64],
                    str(payload.get("provider_model") or "")[:128],
                    outcome,
                    str(payload.get("provider_error") or "")[:500],
                    not bool(payload.get("provider_used")),
                    int(usage.get("prompt_tokens") or 0),
                    int(usage.get("completion_tokens") or 0),
                    int(duration_ms),
                ),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:
        # Best effort by design. See the module docstring.
        obs.warn("ai_investigation.not_recorded", error=type(exc).__name__, outcome=outcome)
        return None
    obs.event(
        "ai.investigation", investigation_id=investigation_id, outcome=outcome,
        credit_id=credit_id, provider=str(payload.get("provider") or ""),
        fell_back=not bool(payload.get("provider_used")), duration_ms=duration_ms,
        writes_cleared=False,
    )
    return investigation_id
