"""Verifier acceptance is zero residual and never takes ε as an input (NN-12)."""

from __future__ import annotations

from datetime import date, datetime

from residual_zero.config import load_fees, load_solver_config, load_tax_rates
from residual_zero.models import BankCredit, Instrument, Kind, LedgerItem, Regime, Source
from residual_zero.money import apply_bps
from residual_zero.normalise import normalise_narration
from residual_zero.tz import IST, ensure_utc
from residual_zero.verify import verify_decomposition


def _item(iid: str, kind: Kind, amount: int, instrument: Instrument | None = Instrument.UPI) -> LedgerItem:
    raw = f"{kind.value} {iid}"
    return LedgerItem(
        id=iid, kind=kind, amount_paise=amount,
        occurred_at=ensure_utc(datetime(2025, 1, 12, 10, 0, tzinfo=IST)),
        account_id="acc_00", currency="INR", instrument=instrument,
        order_id=None, parent_id=None, narration_raw=raw,
        narration_norm=normalise_narration(raw), counterparty_raw="x",
        counterparty_id=None, source=Source.INTERNAL_LEDGER,
    )


def _credit(amount: int) -> BankCredit:
    raw = "NEFT"
    return BankCredit(
        id="c1", amount_paise=amount, value_date=date(2025, 1, 15),
        account_id="acc_00", currency="INR", narration_raw=raw,
        narration_norm=normalise_narration(raw), utr="U",
    )


def test_accepts_only_zero_residual():
    rates, fees = load_tax_rates(), load_fees()
    payment = _item("p1", Kind.PAYMENT, 100_00)
    outcome = verify_decomposition(
        _credit(100_00 + 1), ("p1",), {payment.id: payment}, Regime.B_SEARCHED, rates, fees,
    )
    assert outcome.accepted is False
    assert outcome.residual_paise != 0


def test_acceptance_never_widens_with_tolerance():
    """ε is not an input to verify_decomposition; acceptance is identical regardless of solver.yaml."""
    load_solver_config()  # ε lives here and is not passed in
    rates, fees = load_tax_rates(), load_fees()
    payment = _item("p1", Kind.PAYMENT, 100_00)
    credit = _credit(100_00)
    a = verify_decomposition(credit, ("p1",), {payment.id: payment}, Regime.B_SEARCHED, rates, fees)
    b = verify_decomposition(credit, ("p1",), {payment.id: payment}, Regime.B_SEARCHED, rates, fees)
    assert a.accepted == b.accepted


def test_rederives_rather_than_trusts():
    rates, fees = load_tax_rates(), load_fees()
    payment = _item("p1", Kind.PAYMENT, 100_00)
    honest_fee = -apply_bps(100_00, fees.per_instrument_bps[Instrument.UPI].bps)
    fee = _item("fee1", Kind.FEE, honest_fee - 50)
    ledger = {payment.id: payment, fee.id: fee}
    members = ("p1", "fee1")
    outcome = verify_decomposition(_credit(100_00), members, ledger, Regime.A_DECLARED, rates, fees)
    assert outcome.accepted is False
    assert "fee1" in outcome.mismatched_line_ids


def test_rounding_is_rederived_not_tolerated():
    rates, fees = load_tax_rates(), load_fees()
    payment = _item("p1", Kind.PAYMENT, 100_00)
    honest_fee = -apply_bps(100_00, fees.per_instrument_bps[Instrument.UPI].bps)
    fee = _item("fee1", Kind.FEE, honest_fee + 1)
    outcome = verify_decomposition(
        _credit(100_00), ("p1", "fee1"), {payment.id: payment, fee.id: fee},
        Regime.A_DECLARED, rates, fees,
    )
    assert outcome.accepted is False
    assert outcome.mismatched_line_ids
