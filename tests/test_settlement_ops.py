"""Settlement-declared operational amounts recover class 5/18; class 8 still fails."""

from __future__ import annotations

from datetime import date, datetime

from residual_zero.config import load_fees, load_tax_rates
from residual_zero.features import FeatureFlags, load_features
from residual_zero.models import BankCredit, Instrument, Kind, LedgerItem, Source
from residual_zero.money import apply_bps
from residual_zero.normalise import normalise_narration
from residual_zero.solver.fastpath import SETTLEMENT_OPS, DeclaredLine, verify_declared
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


def _stack(payment_ledger: int, payment_declared: int):
    rates = load_tax_rates()
    fees = load_fees()
    honest_fee = -apply_bps(payment_declared, fees.per_instrument_bps[Instrument.UPI].bps)
    honest_gst = apply_bps(honest_fee, rates.gst_on_fee.bps) if honest_fee != 0 else 0
    fee_item = _item("fee1", Kind.FEE, honest_fee)
    gst_item = _item("gst1", Kind.TAX_GST, honest_gst)
    declared = (
        DeclaredLine("p1", Kind.PAYMENT, payment_declared, Instrument.UPI),
        DeclaredLine("fee1", Kind.FEE, honest_fee, Instrument.UPI),
        DeclaredLine("gst1", Kind.TAX_GST, honest_gst, Instrument.UPI),
    )
    honest_ledger = {
        "p1": _item("p1", Kind.PAYMENT, payment_declared),
        fee_item.id: fee_item,
        gst_item.id: gst_item,
    }
    probe = verify_declared(
        _credit(payment_declared), declared, honest_ledger, rates, fees, allow_declared_ops=False,
    )
    credit = _credit(probe.computed_total_paise)
    ledger = {
        "p1": _item("p1", Kind.PAYMENT, payment_ledger),
        fee_item.id: fee_item,
        gst_item.id: gst_item,
    }
    return credit, declared, ledger, rates, fees


def test_transposed_ledger_payment_recovers_from_settlement_ops():
    credit, declared, ledger, rates, fees = _stack(100_00, 91_00)
    denied = verify_declared(credit, declared, ledger, rates, fees, allow_declared_ops=False)
    accepted = verify_declared(credit, declared, ledger, rates, fees, allow_declared_ops=True)
    assert denied.ok is False
    assert accepted.ok is True
    assert accepted.residual_paise == 0
    assert accepted.ops_source == SETTLEMENT_OPS
    assert accepted.line_deltas == ()


def test_sign_flipped_ledger_payment_recovers_from_settlement_ops():
    credit, declared, ledger, rates, fees = _stack(-91_00, 91_00)
    denied = verify_declared(credit, declared, ledger, rates, fees, allow_declared_ops=False)
    accepted = verify_declared(credit, declared, ledger, rates, fees, allow_declared_ops=True)
    assert denied.ok is False
    assert accepted.ok is True
    assert accepted.ops_source == SETTLEMENT_OPS


def test_partial_payment_on_both_sources_still_fails():
    """Class 8 shortens ledger and settlement; bank stays at the original amount."""
    credit, declared, ledger, rates, fees = _stack(85_00, 85_00)
    credit = credit.model_copy(update={"amount_paise": 100_00})
    result = verify_declared(credit, declared, ledger, rates, fees, allow_declared_ops=True)
    assert result.ok is False
    assert result.residual_paise != 0


def test_missing_ledger_id_still_fails_on_settlement_ops():
    rates = load_tax_rates()
    fees = load_fees()
    declared = (DeclaredLine("ghost", Kind.PAYMENT, 100_00, Instrument.UPI),)
    result = verify_declared(_credit(100_00), declared, {}, rates, fees, allow_declared_ops=True)
    assert result.ok is False
    assert "ghost" in result.missing_item_ids


def test_corrupt_declared_fee_still_emits_delta():
    rates = load_tax_rates()
    fees = load_fees()
    honest_fee = -apply_bps(100_00, fees.per_instrument_bps[Instrument.UPI].bps)
    payment = _item("p1", Kind.PAYMENT, 100_00)
    ledger = {payment.id: payment, "fee1": _item("fee1", Kind.FEE, honest_fee)}
    declared = (
        DeclaredLine("p1", Kind.PAYMENT, 100_00, Instrument.UPI),
        DeclaredLine("fee1", Kind.FEE, honest_fee - 50, Instrument.UPI),
    )
    result = verify_declared(_credit(100_00), declared, ledger, rates, fees, allow_declared_ops=True)
    assert result.ok is False
    assert result.line_deltas != ()


def test_f59_defaults():
    assert load_features().f59_settlement_declared_ops is True
    assert FeatureFlags.all_off().f59_settlement_declared_ops is False
    assert load_features().f60_reconstruct_missing_rate_ids is True
    assert FeatureFlags.all_off().f60_reconstruct_missing_rate_ids is False


def test_missing_withholding_id_is_reconstructed():
    credit, declared, ledger, rates, fees = _stack(91_00, 91_00)
    honest_wh = -apply_bps(91_00, rates.withholding.bps) if rates.withholding.bps > 0 else 0
    declared = declared + (DeclaredLine("wh1", Kind.TAX_WITHHOLDING, honest_wh, None),)
    accepted = verify_declared(credit, declared, ledger, rates, fees, allow_missing_rate_ids=True)
    denied = verify_declared(credit, declared, ledger, rates, fees, allow_missing_rate_ids=False)
    assert "wh1" in accepted.missing_item_ids
    assert accepted.ok is True
    assert denied.ok is False


def test_missing_payment_id_still_fails():
    credit, declared, ledger, rates, fees = _stack(91_00, 91_00)
    declared = declared + (DeclaredLine("ghost_pay", Kind.PAYMENT, 50_00, Instrument.UPI),)
    result = verify_declared(credit, declared, ledger, rates, fees, allow_missing_rate_ids=True)
    assert result.ok is False
    assert "ghost_pay" in result.missing_item_ids
