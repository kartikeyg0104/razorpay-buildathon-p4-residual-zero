"""The canonical model validates at the boundary, and sign is a DERIVED check (PLAN-P1 D1.1)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from residual_zero.models import (
    Kind,
    LedgerItem,
    Regime,
    Source,
    Uniqueness,
    PoolScope,
    ProofRecord,
    Decomposition,
    expected_sign,
    has_expected_sign,
    render_score,
)
from residual_zero.tz import IST

_AWARE = datetime(2026, 8, 19, 12, 0, tzinfo=timezone.utc)


def _item(**overrides) -> LedgerItem:
    base = dict(
        id="pay_1", kind=Kind.PAYMENT, amount_paise=50_000, occurred_at=_AWARE,
        account_id="acct_1", currency="INR", narration_raw="ACME PVT LTD",
        narration_norm="ACME PRIVATE LIMITED", source=Source.INTERNAL_LEDGER,
    )
    base.update(overrides)
    return LedgerItem(**base)


def test_amount_zero_rejected():
    """A zero-value ledger item is a defect, not a legitimate line."""
    with pytest.raises(ValidationError):
        _item(amount_paise=0)


def test_naive_datetime_rejected():
    """A naive datetime in a reconciliation system is an off-by-one-window bug waiting to happen."""
    with pytest.raises(ValidationError):
        _item(occurred_at=datetime(2026, 8, 19, 12, 0))


def test_ist_input_is_stored_as_utc():
    """Stored UTC, displayed IST (spec §5.3). An IST-aware input converts on the way in."""
    item = _item(occurred_at=datetime(2026, 8, 19, 17, 30, tzinfo=IST))
    assert item.occurred_at.utcoffset().total_seconds() == 0
    assert item.occurred_at == datetime(2026, 8, 19, 12, 0, tzinfo=timezone.utc)


def test_sign_is_derived_not_enforced():
    """A wrong-signed item MUST construct successfully.

    This is what keeps corruption class 18 SIGN_REVERSAL ingestible. A validator rejecting a
    positive REFUND would make the loader raise on the corrupted view instead of producing the
    case the system exists to diagnose.
    """
    reversed_refund = _item(kind=Kind.REFUND, amount_paise=+50_000)
    assert reversed_refund.kind is Kind.REFUND
    assert reversed_refund.amount_paise > 0
    assert has_expected_sign(reversed_refund) is False

    proper_refund = _item(kind=Kind.REFUND, amount_paise=-50_000)
    assert has_expected_sign(proper_refund) is True


def test_expected_sign_covers_every_kind():
    """Adding a Kind without deciding its sign breaks this test rather than defaulting silently."""
    for kind in Kind:
        assert expected_sign(kind) in (-1, 0, 1)


def test_adjustment_accepts_either_sign():
    """Prior-period adjustments legitimately go both ways (spec §3.2)."""
    assert expected_sign(Kind.ADJUSTMENT) == 0
    assert has_expected_sign(_item(kind=Kind.ADJUSTMENT, amount_paise=+1)) is True
    assert has_expected_sign(_item(kind=Kind.ADJUSTMENT, amount_paise=-1)) is True


def test_extra_fields_forbidden():
    """Validation failures surface at the boundary, not as a mystery three stages later."""
    with pytest.raises(ValidationError):
        _item(unexpected_field="surprise")


def test_models_are_frozen():
    """Typed state flows through the pipeline; nothing mutates an item in place."""
    item = _item()
    with pytest.raises(ValidationError):
        item.amount_paise = 1


def test_bank_credit_amount_must_be_positive():
    from residual_zero.models import BankCredit
    from datetime import date

    with pytest.raises(ValidationError):
        BankCredit(
            id="setl_1", amount_paise=-1, value_date=date(2026, 8, 19), account_id="acct_1",
            currency="INR", narration_raw="x", narration_norm="x",
        )


def _proof() -> ProofRecord:
    return ProofRecord(
        bank_credit_id="setl_1", lines=(), computed_total_paise=0, residual_paise=0,
        regime=Regime.B_SEARCHED, uniqueness=Uniqueness.UNIQUE, alternate_count=1,
        pool_size=3, pool_scope=PoolScope.FULL, rate_config_digest="0" * 64,
    )


def test_member_ids_must_be_sorted():
    """Fixed ordering everywhere is an NN-9 requirement, so unsorted members are rejected."""
    with pytest.raises(ValidationError):
        Decomposition(
            bank_credit_id="setl_1", member_ids=("b", "a"), claimed_total_paise=1,
            residual_paise=0, regime=Regime.B_SEARCHED, uniqueness=Uniqueness.UNIQUE,
            alternate_count=1, pool_scope=PoolScope.FULL, ordering_score=0.5, proof=_proof(),
        )


def test_member_ids_must_be_unique():
    """An item cannot be its own sibling in a decomposition."""
    with pytest.raises(ValidationError):
        Decomposition(
            bank_credit_id="setl_1", member_ids=("a", "a"), claimed_total_paise=1,
            residual_paise=0, regime=Regime.B_SEARCHED, uniqueness=Uniqueness.UNIQUE,
            alternate_count=1, pool_scope=PoolScope.FULL, ordering_score=0.5, proof=_proof(),
        )


def test_render_score_is_fixed_width():
    """The score is compared and serialised as a six-decimal string so NN-9 survives."""
    assert render_score(0.9123456789) == "0.912346"
    assert render_score(0.0) == "0.000000"
    assert render_score(1.0) == "1.000000"
    assert len(render_score(0.5)) == len(render_score(0.123456789))
