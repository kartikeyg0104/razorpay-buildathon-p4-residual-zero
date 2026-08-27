"""Regression: uniqueness under tolerance is counted across every hit total (§0.1)."""

from __future__ import annotations

from residual_zero.models import Uniqueness
from residual_zero.solver import solve_search
from tests.solver_helpers import brute_force_solutions, cfg_with_tol, pool_from_amounts


def test_two_totals_in_the_window_are_ambiguous():
    """amounts [10, 11], target 10, tol 1: two subsets, two totals. Must not report UNIQUE."""
    oracle = brute_force_solutions([10, 11], 10, 1)
    assert len(oracle) == 2
    result = solve_search(pool_from_amounts([10, 11]), 10 * 100, cfg_with_tol(1))
    assert result.uniqueness == Uniqueness.AMBIGUOUS
    assert result.member_ids == ()
