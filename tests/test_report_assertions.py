"""§9.8 report assertions and the NN-16 test-split gate."""

from __future__ import annotations

import pytest

from fractions import Fraction

from residual_zero.models import Regime

from eval.cli import main as eval_main
from eval.metrics import NA_CELL, ArmMetrics, CountedRatio
from eval.report import ReportAssertionError, assert_dispositions_sum_to_one, assert_exact_bounded_by_coverage_strict


def _m(**kwargs) -> ArmMetrics:
    base = dict(
        arm="a0",
        n_credits=10,
        n_cleared=4,
        n_cleared_correct=4,
        n_flagged=NA_CELL,
        n_budget_exceeded=NA_CELL,
        n_exact=4,
        assignment_precision=CountedRatio(1, 1),
        assignment_recall=CountedRatio(1, 1),
        exception_precision=NA_CELL,
        residual_median_paise=NA_CELL,
        residual_p95_paise=NA_CELL,
        residual_median_bp=NA_CELL,
        tokens=0,
        cost_paise=0,
        cache_hit_rate=Fraction(0, 1),
        wall_clock_ms=0,
        machine="test",
    )
    base.update(kwargs)
    return ArmMetrics(**base)


def test_impossible_disposition_sum_raises():
    m = _m(arm="a3", n_credits=10, n_cleared=4, n_flagged=3, n_budget_exceeded=2, n_exact=1, n_cleared_correct=1)
    with pytest.raises(ReportAssertionError):
        assert_dispositions_sum_to_one(m)


def test_exact_exceeding_cleared_correct_raises():
    m = _m(arm="a0", n_exact=5, n_cleared_correct=4)
    with pytest.raises(ReportAssertionError):
        assert_exact_bounded_by_coverage_strict(m, has_exception_path=False)


def test_a3_is_exempt_from_the_coverage_cap():
    m = _m(arm="a3", n_exact=8, n_cleared_correct=2, n_flagged=6, n_budget_exceeded=0, n_cleared=4)
    assert_exact_bounded_by_coverage_strict(m, has_exception_path=True)


def test_eval_cli_refuses_test_split_without_flag():
    rc = eval_main(["--split", "test", "--arms", "a0", "--out", "artifacts/dev/should_not_exist"])
    assert rc != 0
