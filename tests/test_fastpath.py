"""Regime A recomputes fees from the rate table; declared amounts are claims, not inputs."""

from __future__ import annotations

from datetime import date, datetime

from residual_zero.config import load_fees, load_tax_rates
from residual_zero.models import BankCredit, Instrument, Kind, LedgerItem, Source
from residual_zero.money import apply_bps
from residual_zero.normalise import normalise_narration
from residual_zero.solver.fastpath import DeclaredLine, verify_declared
from residual_zero.tz import IST, ensure_utc


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


def test_fee_is_recomputed_not_copied():
    rates = load_tax_rates()
    fees = load_fees()
    honest_fee = -apply_bps(100_00, fees.per_instrument_bps[Instrument.UPI].bps)
    payment = _item("p1", Kind.PAYMENT, 100_00)
    fee_item = _item("fee1", Kind.FEE, honest_fee)
    ledger = {payment.id: payment, fee_item.id: fee_item}
    declared_honest = (
        DeclaredLine("p1", Kind.PAYMENT, 100_00, Instrument.UPI),
        DeclaredLine("fee1", Kind.FEE, honest_fee, Instrument.UPI),
    )
    declared_corrupt = (
        DeclaredLine("p1", Kind.PAYMENT, 100_00, Instrument.UPI),
        DeclaredLine("fee1", Kind.FEE, honest_fee - 50, Instrument.UPI),
    )
    credit = _credit(100_00)
    honest = verify_declared(credit, declared_honest, ledger, rates, fees)
    corrupt = verify_declared(credit, declared_corrupt, ledger, rates, fees)
    assert honest.computed_total_paise == corrupt.computed_total_paise
    assert corrupt.line_deltas != honest.line_deltas
    assert any(delta != 0 for _, delta in corrupt.line_deltas)


def test_gst_derives_from_recomputed_fee():
    rates = load_tax_rates()
    fees = load_fees()
    payment = _item("p1", Kind.PAYMENT, 100_00)
    honest_fee = -apply_bps(100_00, fees.per_instrument_bps[Instrument.UPI].bps)
    honest_gst = apply_bps(honest_fee, rates.gst_on_fee.bps)
    ledger = {
        payment.id: payment,
        "fee1": _item("fee1", Kind.FEE, honest_fee - 80),
        "gst1": _item("gst1", Kind.TAX_GST, honest_gst),
    }
    declared = (
        DeclaredLine("p1", Kind.PAYMENT, 100_00, Instrument.UPI),
        DeclaredLine("fee1", Kind.FEE, honest_fee - 80, Instrument.UPI),
        DeclaredLine("gst1", Kind.TAX_GST, honest_gst, Instrument.UPI),
    )
    result = verify_declared(_credit(100_00), declared, ledger, rates, fees)
    gst_delta = {iid: delta for iid, delta in result.line_deltas}.get("gst1", 0)
    assert gst_delta == 0


def test_missing_ledger_item_is_reported():
    rates = load_tax_rates()
    fees = load_fees()
    declared = (DeclaredLine("ghost", Kind.PAYMENT, 100_00, Instrument.UPI),)
    result = verify_declared(_credit(100_00), declared, {}, rates, fees)
    assert "ghost" in result.missing_item_ids
