"""F36: the human reads the symmetric difference, not two full member lists."""

from __future__ import annotations

from residual_zero.config import load_fees, load_tax_rates
from residual_zero.models import Uniqueness
from residual_zero.solver.alt_diff import diff_sets, median_int, pair_stats, render_diff
from residual_zero.solver.disambiguate import disambiguate

from tests.test_disambiguation import _item
from residual_zero.models import Kind


def test_symmetric_difference_is_what_is_presented():
    diff = diff_sets(("a", "b", "c"), ("a", "d"))
    assert diff.only_a == ("b", "c")
    assert diff.only_b == ("d",)
    assert diff.shared == ("a",)
    assert diff.symmetric_difference_size == 3
    text = render_diff(diff)
    assert "only A: b, c" in text
    assert "symmetric-difference size: 3" in text


def test_both_medians_on_a_two_solution_fixture():
    ledger = {
        "p1": _item("p1", Kind.PAYMENT, 50_000, order_id="ord_1"),
        "p2": _item("p2", Kind.PAYMENT, 50_000, order_id="ord_2"),
        "p3": _item("p3", Kind.PAYMENT, 100_000, order_id="ord_3"),
        "p4": _item("p4", Kind.PAYMENT, 100_000, order_id="ord_4"),
    }
    pool = ("p1", "p2", "p3", "p4")
    enumerated = ((0, 1), (2,), (3,))
    d = disambiguate(
        pool, enumerated, ledger, load_tax_rates(), load_fees(), 0, frozenset(), enumeration_capped=False
    )
    assert d.uniqueness == Uniqueness.AMBIGUOUS
    assert d.enumeration_capped is False
    diffs, sizes = pair_stats(pool, enumerated, d.feasible_indices)
    assert median_int(diffs) is not None
    assert median_int(sizes) is not None
    assert median_int(sizes) >= 1


def test_capped_enumeration_yields_no_diff():
    diffs, sizes = pair_stats(("p1",), ((0,),), ())
    assert diffs == ()
    assert sizes == ()
    assert median_int(diffs) is None
    assert median_int(sizes) is None


def test_median_int_lower_on_even():
    assert median_int((1, 3, 5)) == 3
    assert median_int((2, 4)) == 2
    assert median_int(()) is None
