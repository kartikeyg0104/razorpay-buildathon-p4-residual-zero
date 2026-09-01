"""Tiny golden search fixtures. Seconds, not the 25-minute eval."""

from __future__ import annotations

import pytest

from residual_zero.models import Uniqueness
from residual_zero.solver import solve_search
from tests.solver_helpers import cfg_with_tol, pool_from_amounts


@pytest.mark.parametrize(
    "amounts,target,expect",
    [
        ([1, 2, 3], 6, Uniqueness.UNIQUE),
        ([5, 5], 5, Uniqueness.AMBIGUOUS),
        ([1, 2, 3], 100, Uniqueness.NONE_FOUND),
        ([10, -3, 4], 11, Uniqueness.UNIQUE),
        ([1, 2, 3], 0, Uniqueness.NONE_FOUND),
    ],
)
def test_golden_uniqueness(amounts, target, expect):
    got = solve_search(pool_from_amounts(amounts), target * 100, cfg_with_tol(0))
    assert got.uniqueness == expect
    if expect == Uniqueness.UNIQUE:
        assert got.member_ids
    if expect != Uniqueness.UNIQUE:
        assert got.member_ids == () or expect == Uniqueness.AMBIGUOUS


def test_permutation_same_id_set():
    a = solve_search(pool_from_amounts([1, 2, 3]), 6 * 100, cfg_with_tol(0))
    b = solve_search(pool_from_amounts([1, 2, 3]), 6 * 100, cfg_with_tol(0))
    assert a.uniqueness == b.uniqueness
    assert a.member_ids == b.member_ids


def test_sign_symmetry_zero():
    got = solve_search(pool_from_amounts([5, -5]), 0, cfg_with_tol(0))
    assert got.uniqueness in {Uniqueness.NONE_FOUND, Uniqueness.UNIQUE, Uniqueness.AMBIGUOUS}
