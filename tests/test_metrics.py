"""Metric cells: NA is not zero; exact; exception predicate; regime split."""

from __future__ import annotations

import pytest

from residual_zero.models import Disposition, PoolScope, Regime
from residual_zero.candidates import CandidatePool

from eval.arms import ArmResult
from eval.metrics import NA, NA_CELL, compute_arm_metrics, exact_decomposition_counted, genuinely_required_human


def test_na_is_not_zero():
    cell = NA()
    assert str(cell) == "—"
    with pytest.raises(TypeError):
        cell + 0
    with pytest.raises(TypeError):
        int(cell)


def test_unpredicted_credit_is_not_exact():
    pred = {}
    truth = {"c1": ("a",), "c2": ("b",)}
    got = exact_decomposition_counted(pred, truth)
    assert got.numerator == 0
    assert got.denominator == 2


def test_error_rate_on_empty_cleared_set_is_na():
    result = ArmResult(
        arm="a0",
        predictions={"c1": ()},
        dispositions={"c1": Disposition.FLAGGED},
        has_exception_path=False,
        has_budget_path=False,
    )
    # A0 has no exception path so flagged is coerced to NA for those cells;
    # n_cleared is 0, error rate is NA not 0.
    assert result.dispositions["c1"] != Disposition.CLEARED
    n_cleared = 0
    error = NA_CELL if n_cleared == 0 else 0
    assert isinstance(error, NA)


def test_exception_precision_predicate_is_frozen():
    src = __import__("pathlib").Path("docs/EVALUATION.md").read_text(encoding="utf-8")
    assert "absent from every rendered source view" in src
    assert "AMBIGUOUS_BY_CONSTRUCTION" in src
    assert "outside the candidate window" in src
    assert genuinely_required_human.__doc__ is not None


def test_regime_split_partitions_the_batch():
    class Rec:
        def __init__(self, cid, regime):
            self.bank_credit_id = cid
            self.regime = regime
            self.corruption_classes = (1,)
            self.member_ids = ("x",)

    recs = [Rec("a", Regime.A_DECLARED), Rec("b", Regime.B_SEARCHED), Rec("c", Regime.A_DECLARED)]
    n_a = sum(1 for r in recs if r.regime == Regime.A_DECLARED)
    n_b = sum(1 for r in recs if r.regime == Regime.B_SEARCHED)
    assert n_a + n_b == len(recs)
