"""Gate A overlay, greedy-vs-declared, recon parse. Eval A3 dispositions stay frozen."""

from __future__ import annotations

from datetime import date, datetime, timezone

from residual_zero.books import identity_from_cleared
from residual_zero.config import load_fees, load_solver_config, load_tax_rates
from residual_zero.console.ops import (
    build_overlay,
    fixture_rival_sets,
    gate_a_for,
    greedy_versus_declared,
)
from residual_zero.ingest.razorpay import parse_recon_combined
from residual_zero.ingest.settlement_report import DeclaredLine
from residual_zero.models import BankCredit, Instrument, Kind, LedgerItem, Source
from residual_zero.money import apply_bps
from residual_zero.normalise import normalise_narration
from residual_zero.solver.fastpath import DeclaredLine as FastLine
from residual_zero.solver.fastpath import verify_declared

_AWARE = datetime(2025, 1, 8, 6, 0, tzinfo=timezone.utc)


def _credit(cid: str, amount: int) -> BankCredit:
    return BankCredit(
        id=cid, amount_paise=amount, value_date=date(2025, 1, 9),
        account_id="acc_01", currency="INR", narration_raw="NEFT",
        narration_norm=normalise_narration("NEFT"), utr="U",
    )


def _item(iid: str, kind: Kind, amount: int) -> LedgerItem:
    return LedgerItem(
        id=iid, kind=kind, amount_paise=amount, occurred_at=_AWARE,
        account_id="acc_01", currency="INR", instrument=Instrument.UPI,
        narration_raw="x", narration_norm="x", source=Source.INTERNAL_LEDGER,
    )


def _full_stack():
    rates, fees = load_tax_rates(), load_fees()
    gross = 10_000
    fee_amt = -apply_bps(gross, fees.per_instrument_bps[Instrument.UPI].bps)
    gst_amt = apply_bps(fee_amt, rates.gst_on_fee.bps)
    wh_amt = -apply_bps(gross, rates.withholding.bps)
    computed = gross + fee_amt + gst_amt + wh_amt
    ledger = {
        "p1": _item("p1", Kind.PAYMENT, gross),
        "f1": _item("f1", Kind.FEE, fee_amt),
        "g1": _item("g1", Kind.TAX_GST, gst_amt),
        "w1": _item("w1", Kind.TAX_WITHHOLDING, wh_amt),
    }
    declared = (
        DeclaredLine("c1", "p1", Kind.PAYMENT, gross, Instrument.UPI, None),
        DeclaredLine("c1", "f1", Kind.FEE, fee_amt, Instrument.UPI, None),
        DeclaredLine("c1", "g1", Kind.TAX_GST, gst_amt, Instrument.UPI, None),
        DeclaredLine("c1", "w1", Kind.TAX_WITHHOLDING, wh_amt, None, None),
    )
    return _credit("c1", computed), declared, ledger, rates, fees, computed


def test_gate_a_accepts_when_declared_rederives():
    credit, declared, ledger, rates, fees, computed = _full_stack()
    gate = gate_a_for(credit, declared, ledger, rates, fees, 0)
    assert gate is not None
    assert gate.ok
    assert gate.residual_paise == 0
    assert gate.posted_sum_paise == computed


def test_overlay_journalable_requires_posted_sum_equals_credit():
    credit, declared, ledger, rates, fees, _computed = _full_stack()
    overlay = build_overlay((credit,), {"c1": declared}, ledger, rates, fees, 0)
    assert overlay.n_ok == 1
    assert overlay.journalable["c1"] == ("p1", "f1", "g1", "w1")
    assert overlay.n_mismatch == 0
    report = identity_from_cleared(
        (credit,), ledger, "acc_01", date(2025, 1, 1), date(2025, 12, 31), overlay.journalable,
    )
    assert report.identity_holds
    assert report.n_cleared == 1


def test_gate_a_none_without_declared_rows():
    credit = _credit("c1", 10_000)
    assert gate_a_for(credit, (), {"p1": _item("p1", Kind.PAYMENT, 10_000)}, load_tax_rates(), load_fees(), 0) is None


def test_greedy_can_differ_from_declared():
    credit = _credit("c1", 10_000)
    items = (
        _item("p_small", Kind.PAYMENT, 4_000),
        _item("p_fit", Kind.PAYMENT, 10_000),
        _item("p_other", Kind.PAYMENT, 6_000),
    )
    declared_ids = ("p_small", "p_other")
    hit = greedy_versus_declared(credit, items, load_solver_config(), declared_ids)
    assert hit.would_clear
    assert hit.member_ids == ("p_fit",)
    assert hit.same_as_declared is False


def test_overlay_n_mismatch_when_posted_differs_from_credit():
    credit, declared, ledger, rates, fees, _computed = _full_stack()
    fee = ledger["f1"]
    drifted = dict(ledger)
    drifted["f1"] = _item("f1", Kind.FEE, fee.amount_paise + 17)
    overlay = build_overlay((credit,), {"c1": declared}, drifted, rates, fees, 0)
    assert overlay.n_ok == 1
    assert overlay.n_journalable == 0
    assert overlay.n_mismatch == 1
    assert "c1" not in overlay.journalable


def test_fixture_rivals_are_labelled_not_live():
    a, b, diff = fixture_rival_sets()
    assert a == ("p1", "p2")
    assert b == ("p3",)
    assert diff.symmetric_difference_size == 3


def test_recon_combined_parses_integer_paise():
    rows = parse_recon_combined(
        {
            "entity": "collection",
            "items": [
                {
                    "settlement_id": "setl_1",
                    "entity_type": "payment",
                    "entity_id": "pay_1",
                    "amount": 100000,
                }
            ],
        }
    )
    assert len(rows) == 1
    assert rows[0].amount_paise == 100000
    assert rows[0].kind is Kind.PAYMENT


def test_recon_rejects_non_integer_amount():
    try:
        parse_recon_combined({"items": [{"settlement_id": "s", "entity_id": "p", "type": "payment", "amount": "100"}]})
    except ValueError as exc:
        assert "integer paise" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_verify_declared_ok_matches_gate_a():
    credit, declared, ledger, rates, fees, _computed = _full_stack()
    lines = tuple(FastLine(r.item_id, r.kind, r.amount_paise, r.instrument) for r in declared)
    fast = verify_declared(credit, lines, ledger, rates, fees, 0)
    assert fast.ok
    assert fast.residual_paise == 0
