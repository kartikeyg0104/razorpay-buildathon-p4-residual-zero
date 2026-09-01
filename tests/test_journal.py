"""F40 journal: debits equal credits, control ties, no plug."""

from __future__ import annotations

from datetime import date, datetime, timezone

from residual_zero.journal import build_journal, control_residual, load_chart, render_tally_xml, trial_balance
from residual_zero.models import BankCredit, Instrument, Kind, LedgerItem, Source

_AWARE = datetime(2025, 1, 9, 6, 0, tzinfo=timezone.utc)


def test_unreconciled_credits_balance_and_tie_out():
    chart = load_chart()
    credits = (
        BankCredit(
            id="c1", amount_paise=10_000, value_date=date(2025, 1, 9),
            account_id="acc_01", currency="INR", narration_raw="x", narration_norm="x",
        ),
        BankCredit(
            id="c2", amount_paise=25_000, value_date=date(2025, 1, 10),
            account_id="acc_01", currency="INR", narration_raw="x", narration_norm="x",
        ),
    )
    lines = build_journal(credits, {}, {}, chart)
    dr, cr = trial_balance(lines)
    assert dr == cr
    assert control_residual(lines, credits, chart.bank_control.code) == 0


def test_cleared_credit_posts_members_without_a_plug():
    chart = load_chart()
    credit = BankCredit(
        id="c1", amount_paise=90_000, value_date=date(2025, 1, 9),
        account_id="acc_01", currency="INR", narration_raw="x", narration_norm="x",
    )
    pay = LedgerItem(
        id="p", kind=Kind.PAYMENT, amount_paise=100_000, occurred_at=_AWARE,
        account_id="acc_01", currency="INR", instrument=Instrument.UPI,
        narration_raw="p", narration_norm="p", source=Source.INTERNAL_LEDGER,
    )
    fee = LedgerItem(
        id="f", kind=Kind.FEE, amount_paise=-10_000, occurred_at=_AWARE,
        account_id="acc_01", currency="INR", instrument=Instrument.UPI,
        narration_raw="f", narration_norm="f", source=Source.INTERNAL_LEDGER,
    )
    lines = build_journal((credit,), {"p": pay, "f": fee}, {"c1": ("f", "p")}, chart)
    dr, cr = trial_balance(lines)
    assert dr == 100_000
    assert cr == 100_000
    assert control_residual(lines, (credit,), chart.bank_control.code) == 0
    xml = render_tally_xml(lines)
    assert "<ENVELOPE>" in xml
    assert "<REFERENCE>c1</REFERENCE>" in xml
    assert "900.00" in xml
