"""F43: parameter substitution over a known member set, not a behavioural counterfactual."""

from __future__ import annotations

from datetime import datetime, timezone

from residual_zero.config import load_fees, load_tax_rates
from residual_zero.controller.whatif import recompute, reproduces_exactly
from residual_zero.models import BankCredit, Instrument, Kind, LedgerItem, Source
from residual_zero.money import apply_bps

_AWARE = datetime(2025, 1, 8, 6, 0, tzinfo=timezone.utc)


def _item(item_id: str, kind: Kind, amount: int, instrument: Instrument | None = Instrument.UPI) -> LedgerItem:
    return LedgerItem(
        id=item_id,
        kind=kind,
        amount_paise=amount,
        occurred_at=_AWARE,
        account_id="acc_01",
        currency="INR",
        instrument=instrument,
        narration_raw=kind.value,
        narration_norm=kind.value,
        source=Source.INTERNAL_LEDGER,
    )


def test_generator_params_reproduce_a_known_set():
    rates, fees = load_tax_rates(), load_fees()
    gross = 10_000
    fee = -apply_bps(gross, fees.per_instrument_bps[Instrument.UPI].bps)
    gst = apply_bps(fee, rates.gst_on_fee.bps)
    withholding = -apply_bps(gross, rates.withholding.bps)
    reserve_bps = 100
    reserve = -apply_bps(gross, reserve_bps)
    total = gross + fee + gst + withholding + reserve
    credit = BankCredit(
        id="crd_w",
        amount_paise=total,
        value_date=_AWARE.date(),
        account_id="acc_01",
        currency="INR",
        narration_raw="neft",
        narration_norm="neft",
    )
    ledger = {
        "p": _item("p", Kind.PAYMENT, gross),
        "f": _item("f", Kind.FEE, fee),
        "g": _item("g", Kind.TAX_GST, gst),
        "w": _item("w", Kind.TAX_WITHHOLDING, withholding),
        "r": _item("r", Kind.RESERVE_HOLD, reserve),
    }
    members = ("p", "f", "g", "w", "r")
    outcome = reproduces_exactly(credit, members, ledger, rates, fees, reserve_bps)
    assert outcome.accepted is True
    assert outcome.residual_paise == 0
    other = recompute(credit, members, ledger, rates, fees, reserve_bps=200)
    assert other.ok is False
    assert other.residual_paise != 0
