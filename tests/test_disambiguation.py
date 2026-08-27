"""F31: CP-SAT domain is the DP enumerated set (NN-18)."""

from __future__ import annotations

from datetime import datetime, timezone

from residual_zero.config import load_fees, load_tax_rates
from residual_zero.models import Instrument, Kind, LedgerItem, Source, Uniqueness
from residual_zero.solver.disambiguate import disambiguate

_AWARE = datetime(2025, 1, 9, 6, 0, tzinfo=timezone.utc)


def _item(item_id: str, kind: Kind, amount: int, order_id: str | None = None, parent_id: str | None = None,
          instrument: Instrument | None = Instrument.UPI) -> LedgerItem:
    return LedgerItem(
        id=item_id, kind=kind, amount_paise=amount, occurred_at=_AWARE,
        account_id="acc_01", currency="INR", instrument=instrument,
        order_id=order_id, parent_id=parent_id,
        narration_raw=kind.value, narration_norm=kind.value, source=Source.INTERNAL_LEDGER,
    )


def test_two_payments_same_order_are_eliminated():
    ledger = {
        "p1": _item("p1", Kind.PAYMENT, 50_000, order_id="ord_1"),
        "p2": _item("p2", Kind.PAYMENT, 50_000, order_id="ord_1"),
        "p3": _item("p3", Kind.PAYMENT, 100_000, order_id="ord_2"),
    }
    pool = ("p1", "p2", "p3")
    enumerated = ((0, 1), (2,))  # {p1,p2} illegal; {p3} legal
    d = disambiguate(pool, enumerated, ledger, load_tax_rates(), load_fees(), 0, frozenset(), enumeration_capped=False)
    assert d.uniqueness == Uniqueness.UNIQUE
    assert d.member_ids == ("p3",)
    assert d.feasible_indices == (1,)
    assert set(d.member_ids).issubset(set(pool))


def test_capped_enumeration_refuses_unique():
    ledger = {"p1": _item("p1", Kind.PAYMENT, 10_000, order_id="a")}
    d = disambiguate(("p1",), ((0,),), ledger, load_tax_rates(), load_fees(), 0, frozenset(), enumeration_capped=True)
    assert d.uniqueness == Uniqueness.AMBIGUOUS
    assert d.structurally_infeasible is False


def test_all_illegal_is_structurally_infeasible():
    ledger = {
        "p1": _item("p1", Kind.PAYMENT, 50_000, order_id="ord_1"),
        "p2": _item("p2", Kind.PAYMENT, 50_000, order_id="ord_1"),
    }
    d = disambiguate(("p1", "p2"), ((0, 1),), ledger, load_tax_rates(), load_fees(), 0, frozenset(), enumeration_capped=False)
    assert d.structurally_infeasible is True
    assert d.member_ids == ()


def test_nn18_support_is_subset_of_enumerated():
    ledger = {
        "a": _item("a", Kind.PAYMENT, 10_000, order_id="o1"),
        "b": _item("b", Kind.PAYMENT, 20_000, order_id="o2"),
        "c": _item("c", Kind.PAYMENT, 30_000, order_id="o3"),
    }
    enumerated = ((0,), (1,), (0, 1))
    d = disambiguate(("a", "b", "c"), enumerated, ledger, load_tax_rates(), load_fees(), 0, frozenset(), enumeration_capped=False)
    for idx in d.feasible_indices:
        ids = tuple(sorted(("a", "b", "c")[i] for i in enumerated[idx]))
        assert set(ids) <= {"a", "b", "c"}
        # Never the unenumerated {c}
        assert "c" not in ids or ids != ("c",)
