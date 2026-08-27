"""F24 adversarial catalogue: attempts that must not auto-clear."""

from __future__ import annotations

from datetime import datetime, timezone

from residual_zero.config import load_fees, load_solver_config, load_tax_rates
from residual_zero.models import Disposition, Instrument, Kind, LedgerItem, PoolScope, Source, Uniqueness
from residual_zero.solver.disambiguate import disambiguate
from residual_zero.verify import verify_decomposition
from residual_zero.models import BankCredit, Regime
from datetime import date

_AWARE = datetime(2025, 1, 9, 6, 0, tzinfo=timezone.utc)


def _item(iid, kind, amt, order=None):
    return LedgerItem(
        id=iid, kind=kind, amount_paise=amt, occurred_at=_AWARE,
        account_id="acc_01", currency="INR", instrument=Instrument.UPI,
        order_id=order, narration_raw="x", narration_norm="x", source=Source.INTERNAL_LEDGER,
    )


def test_two_equal_pairs_do_not_become_unique_without_structure():
    """Class-23 shape: two disjoint pairs, same rupee sum. Both structurally valid payments."""
    ledger = {
        "a": _item("a", Kind.PAYMENT, 10_000, "o1"),
        "b": _item("b", Kind.PAYMENT, 10_000, "o2"),
        "c": _item("c", Kind.PAYMENT, 6_000, "o3"),
        "d": _item("d", Kind.PAYMENT, 14_000, "o4"),
    }
    enumerated = ((0, 1), (2, 3))
    d = disambiguate(
        ("a", "b", "c", "d"), enumerated, ledger, load_tax_rates(), load_fees(), 0,
        frozenset(), enumeration_capped=False,
    )
    assert d.uniqueness == Uniqueness.AMBIGUOUS
    assert d.structurally_infeasible is False


def test_empty_member_set_is_rejected_by_verifier():
    credit = BankCredit(
        id="c", amount_paise=10_000, value_date=date(2025, 1, 9),
        account_id="acc_01", currency="INR", narration_raw="x", narration_norm="x",
    )
    out = verify_decomposition(credit, (), {}, Regime.B_SEARCHED, load_tax_rates(), load_fees())
    assert out.accepted is False
