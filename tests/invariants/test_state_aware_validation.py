"""A model may not rewrite an unresolved transaction into a resolved one.

Observed in live testing: for an AMBIGUOUS credit the rewrite said "the reconciliation
engine found a match", and the old validator accepted it because it only forbade a few
literal uppercase tokens (CLEARED / UNIQUE / VERIFIED).
"""

from __future__ import annotations

import pytest

from residual_zero.qa.finance_validate import validate_answer

# Mirrors the real shape of `evidence` for crd_001_acc_01_2025-01-09.
AMBIGUOUS_EVIDENCE = {
    "reconciliation": {
        "transaction_id": "crd_001_acc_01_2025-01-09",
        "uniqueness": "AMBIGUOUS",
        "status": "REVIEW_REQUIRED",
        "disposition": "FLAGGED",
        "auto_cleared": False,
        "solution_count": 2,
        "residual_paise": 0,
        "matched_count": 27,
    },
    "stats": {"ambiguous": 236, "auto_clear": 0, "false_clears": 0, "none_found": 3},
}

UNIQUE_EVIDENCE = {
    "reconciliation": {
        "transaction_id": "crd_mix_unique_pair",
        "uniqueness": "UNIQUE",
        "status": "VERIFIED",
        "disposition": "FLAGGED",
        "auto_cleared": False,
        "solution_count": 1,
        "residual_paise": 0,
        "matched_count": 2,
    },
    "stats": {"ambiguous": 236, "auto_clear": 0, "false_clears": 0, "none_found": 3},
}


# --------------------------------------------------------- the reported regression


def test_found_a_match_is_rejected_for_an_ambiguous_transaction():
    """The exact sentence seen in live testing."""
    ok, why = validate_answer(
        "The reconciliation engine found a match.", AMBIGUOUS_EVIDENCE
    )
    assert ok is False
    assert "state contradiction" in why or why == "invented uniqueness"


def test_safe_ambiguity_wording_is_accepted():
    """Arithmetic may match while the explanation stays ambiguous."""
    ok, why = validate_answer(
        "The amount matches, but multiple valid explanations exist and human review is required.",
        AMBIGUOUS_EVIDENCE,
    )
    assert ok is True, why


# ------------------------------------------------------------- rejected on unresolved


@pytest.mark.parametrize(
    "prose",
    [
        "The reconciliation engine found a match.",
        "The reconciliation engine found a match for this credit.",
        "A match was found against the ledger.",
        "This transaction is matched.",
        "The credit has been reconciled.",
        "The transaction was successfully reconciled.",
        "This credit has been verified.",
        "Uniqueness is UNIQUE for this transaction.",
        "A unique explanation was established.",
        "Candidate A is the correct explanation.",
        "We selected candidate A as the explanation.",
        "The correct subset is the first one.",
    ],
)
def test_resolution_claims_rejected_when_engine_did_not_resolve(prose: str):
    ok, why = validate_answer(prose, AMBIGUOUS_EVIDENCE)
    assert ok is False, f"accepted a resolution claim: {prose!r}"
    assert "state contradiction" in why or why


@pytest.mark.parametrize(
    "intent", ["REFUSE_CLEAR", "FinanceIntent.REFUSE_CLEAR"]
)
def test_refuse_clear_intent_alone_blocks_resolution_claims(intent: str):
    """Even if the evidence looked resolved, a refuse-clear answer cannot assert a match."""
    ok, why = validate_answer(
        "The reconciliation engine found a match.", UNIQUE_EVIDENCE, intent=intent
    )
    assert ok is False
    assert "state contradiction" in why or why == "invented uniqueness"


# --------------------------------------------------------------- still accepted


@pytest.mark.parametrize(
    "prose",
    [
        "The amount matches, but multiple valid explanations exist and human review is required.",
        "The totals match exactly, yet two candidate sets satisfy the same equation.",
        "Residual is zero, however uniqueness is AMBIGUOUS so this cannot be cleared.",
        "The equation matches; no unique explanation was established.",
        "No match was found for this credit.",
        "This transaction is not matched and has not been reconciled.",
        "The engine did not find a unique match, so a human must review it.",
        "Two competing explanations exist. The AI cannot pick candidate A.",
        "The arithmetic matches. Human review is required because the explanation is ambiguous.",
    ],
)
def test_honest_ambiguity_wording_still_passes(prose: str):
    ok, why = validate_answer(prose, AMBIGUOUS_EVIDENCE)
    assert ok is True, f"rejected safe prose {prose!r}: {why}"


def test_unique_transaction_may_be_described_as_unique():
    """The gate keys on state, so it must not fire when the engine did resolve."""
    ok, why = validate_answer(
        "Uniqueness is UNIQUE and the declared stack re-derives.", UNIQUE_EVIDENCE
    )
    assert ok is True, why


def test_gate_does_not_fire_without_reconciliation_evidence():
    """Batch-level answers carry no per-transaction state and must not be blocked."""
    ok, why = validate_answer(
        "239 scored credits. Search auto-clear is 0.",
        {"stats": {"ambiguous": 236, "auto_clear": 0, "false_clears": 0}},
    )
    assert ok is True, why


# ------------------------------------------------------------- deterministic wording


def test_the_deterministic_refusal_template_passes_its_own_gate():
    """The engine's own refusal must never be rejected by the validator."""
    refusal = (
        "I cannot authorize a financial clear because the deterministic reconciliation "
        "engine has not established a unique verified explanation. The AI finance "
        "controller does not write CLEARED. Human review is required for AMBIGUOUS rows."
    )
    ok, why = validate_answer(refusal, AMBIGUOUS_EVIDENCE, intent="REFUSE_CLEAR")
    assert ok is True, why
