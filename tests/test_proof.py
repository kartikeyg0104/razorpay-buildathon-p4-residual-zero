"""Proof lines sum, render is calculator-checkable, every line names its derivation."""

from __future__ import annotations

import re
from datetime import date, datetime

from residual_zero.config import load_fees, load_tax_rates, config_digest
from residual_zero.models import BankCredit, Instrument, Kind, LedgerItem, Regime, Source, Uniqueness, PoolScope
from residual_zero.normalise import normalise_narration
from residual_zero.proof import build_proof, render_proof
from residual_zero.solver.enumerate import SolveResult
from residual_zero.tz import IST, ensure_utc
from residual_zero.verify import verify_decomposition


def _parse_rupees(text: str) -> int:
    from residual_zero.normalise import parse_rupee_display
    return parse_rupee_display(text)


def test_proof_lines_sum_to_computed_total():
    rates, fees = load_tax_rates(), load_fees()
    raw = "PAY"
    item = LedgerItem(
        id="p1", kind=Kind.PAYMENT, amount_paise=100_00,
        occurred_at=ensure_utc(datetime(2025, 1, 12, 10, 0, tzinfo=IST)),
        account_id="acc_00", currency="INR", instrument=Instrument.UPI,
        order_id=None, parent_id=None, narration_raw=raw, narration_norm=normalise_narration(raw),
        counterparty_raw="x", counterparty_id=None, source=Source.INTERNAL_LEDGER,
    )
    credit = BankCredit(
        id="c1", amount_paise=100_00, value_date=date(2025, 1, 15),
        account_id="acc_00", currency="INR", narration_raw="NEFT",
        narration_norm=normalise_narration("NEFT"), utr="U",
    )
    outcome = verify_decomposition(credit, ("p1",), {item.id: item}, Regime.B_SEARCHED, rates, fees)
    solve = SolveResult(
        uniqueness=Uniqueness.NONE_FOUND, matched_total_rupees=None, member_ids=(),
        alternates=0, pool_scope=PoolScope.FULL, pool_size=1, axis_width=1,
    )
    proof = build_proof(credit, outcome, solve, Regime.B_SEARCHED, {}, config_digest(rates, fees))
    assert sum(line.amount_paise for line in proof.lines) == item.amount_paise


def test_rendered_block_is_calculator_checkable():
    rates, fees = load_tax_rates(), load_fees()
    raw = "PAY"
    item = LedgerItem(
        id="p1", kind=Kind.PAYMENT, amount_paise=50_00,
        occurred_at=ensure_utc(datetime(2025, 1, 12, 10, 0, tzinfo=IST)),
        account_id="acc_00", currency="INR", instrument=Instrument.UPI,
        order_id=None, parent_id=None, narration_raw=raw, narration_norm=normalise_narration(raw),
        counterparty_raw="x", counterparty_id=None, source=Source.INTERNAL_LEDGER,
    )
    credit = BankCredit(
        id="c1", amount_paise=50_00, value_date=date(2025, 1, 15),
        account_id="acc_00", currency="INR", narration_raw="NEFT",
        narration_norm=normalise_narration("NEFT"), utr="U",
    )
    outcome = verify_decomposition(credit, ("p1",), {item.id: item}, Regime.B_SEARCHED, rates, fees)
    solve = SolveResult(
        uniqueness=Uniqueness.NONE_FOUND, matched_total_rupees=None, member_ids=(),
        alternates=0, pool_scope=PoolScope.FULL, pool_size=1, axis_width=1,
    )
    proof = build_proof(credit, outcome, solve, Regime.B_SEARCHED, {}, config_digest(rates, fees))
    block = render_proof(proof, credit)
    from residual_zero.normalise import parse_rupee_display
    figures = re.findall(r"-?[\d,]+\.\d{2}", block)
    # last three labelled computed/credit/residual; residual + computed should relate to credit
    assert parse_rupee_display(figures[-2]) == credit.amount_paise


def test_every_line_names_its_derivation():
    rates, fees = load_tax_rates(), load_fees()
    raw = "PAY"
    item = LedgerItem(
        id="p1", kind=Kind.PAYMENT, amount_paise=50_00,
        occurred_at=ensure_utc(datetime(2025, 1, 12, 10, 0, tzinfo=IST)),
        account_id="acc_00", currency="INR", instrument=Instrument.UPI,
        order_id=None, parent_id=None, narration_raw=raw, narration_norm=normalise_narration(raw),
        counterparty_raw="x", counterparty_id=None, source=Source.INTERNAL_LEDGER,
    )
    credit = BankCredit(
        id="c1", amount_paise=50_00, value_date=date(2025, 1, 15),
        account_id="acc_00", currency="INR", narration_raw="NEFT",
        narration_norm=normalise_narration("NEFT"), utr="U",
    )
    outcome = verify_decomposition(credit, ("p1",), {item.id: item}, Regime.B_SEARCHED, rates, fees)
    for line in outcome.derived_lines:
        assert line.derived_from == "LEDGER" or line.derived_from.startswith("RATE_TABLE:") or line.derived_from == "DECLARED"
