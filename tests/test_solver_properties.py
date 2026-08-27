"""Solver properties. The oracle that licenses every uniqueness claim, including under tolerance."""

from __future__ import annotations

import inspect
import random

from hypothesis import given, settings
from hypothesis import strategies as st

from residual_zero.models import Uniqueness
from residual_zero.solver import ReachabilityIndex, solve_search

from tests.solver_helpers import brute_force_solutions, cfg_with_tol, pool_from_amounts


def _ids_to_indices(member_ids: tuple[str, ...]) -> frozenset[int]:
    return frozenset(int(mid[1:]) for mid in member_ids)


def test_reference_solver_misses_cross_total_ambiguity():
    """§0.1: the unmodified reference reports UNIQUE when two totals in the window each have a subset.

    This is the evidence the change is needed. Run against ``solver.py`` at the repo root.
    """
    from solver import Uniqueness as RefUniqueness
    from solver import solve as ref_solve

    result = ref_solve([10, 11], 10, tol=1)
    assert result.uniqueness == RefUniqueness.UNIQUE
    oracle = brute_force_solutions([10, 11], 10, 1)
    assert len(oracle) == 2


def test_corrected_solver_reports_cross_total_ambiguity():
    result = solve_search(pool_from_amounts([10, 11]), 10 * 100, cfg_with_tol(1))
    assert result.uniqueness == Uniqueness.AMBIGUOUS
    assert result.member_ids == ()
    assert result.alternates >= 2
    assert result.hit_totals == (10, 11)


def test_reachability_agrees_with_brute_force():
    random.seed(7)
    for _ in range(800):
        n = random.randint(3, 10)
        amounts = [random.choice([1, -1]) * random.randint(1, 60) for _ in range(n)]
        target = random.randint(-100, 140)
        result = solve_search(pool_from_amounts(amounts), target * 100, cfg_with_tol(0))
        oracle = brute_force_solutions(amounts, target, 0)
        found = result.uniqueness in (Uniqueness.UNIQUE, Uniqueness.AMBIGUOUS)
        assert found == (len(oracle) > 0), (amounts, target, result, oracle)


def test_uniqueness_agrees_with_brute_force_under_tolerance():
    random.seed(11)
    for _ in range(300):
        n = random.randint(3, 10)
        amounts = [random.choice([1, -1]) * random.randint(1, 50) for _ in range(n)]
        target = random.randint(-60, 90)
        tol = random.randint(0, 3)
        result = solve_search(pool_from_amounts(amounts), target * 100, cfg_with_tol(tol))
        oracle = brute_force_solutions(amounts, target, tol)
        if len(oracle) == 0:
            assert result.uniqueness == Uniqueness.NONE_FOUND
        elif len(oracle) == 1:
            assert result.uniqueness == Uniqueness.UNIQUE
            assert _ids_to_indices(result.member_ids) == next(iter(oracle))
        else:
            assert result.uniqueness == Uniqueness.AMBIGUOUS
            assert result.member_ids == ()


def test_claimed_match_verifies():
    random.seed(3)
    for _ in range(500):
        n = random.randint(5, 12)
        amounts = [random.choice([1, -1]) * random.randint(1, 200) for _ in range(n)]
        target = random.randint(-300, 400)
        tol = 2
        result = solve_search(pool_from_amounts(amounts), target * 100, cfg_with_tol(tol))
        if result.uniqueness == Uniqueness.UNIQUE:
            total = sum(amounts[i] for i in _ids_to_indices(result.member_ids))
            assert abs(total - target) <= tol
            assert total == result.matched_total_rupees


def test_members_empty_unless_unique():
    random.seed(19)
    for _ in range(40):
        n = random.randint(3, 10)
        amounts = [random.choice([1, -1]) * random.randint(1, 40) for _ in range(n)]
        target = random.randint(-80, 80)
        result = solve_search(pool_from_amounts(amounts), target * 100, cfg_with_tol(1))
        if result.uniqueness != Uniqueness.UNIQUE:
            assert result.member_ids == ()


def test_empty_subset_is_never_a_solution():
    result = solve_search(pool_from_amounts([5, 8, 13]), 0, cfg_with_tol(3))
    assert result.uniqueness != Uniqueness.UNIQUE or result.member_ids != ()
    oracle = brute_force_solutions([5, 8, 13], 0, 3)
    assert frozenset() not in oracle
    if not oracle:
        assert result.uniqueness == Uniqueness.NONE_FOUND


def test_bounds_guard_returns_cleanly():
    cfg = cfg_with_tol(0)
    high = solve_search(pool_from_amounts([10, 20, 30]), 10_000_000 * 100, cfg)
    assert high.uniqueness == Uniqueness.NONE_FOUND
    low = solve_search(pool_from_amounts([10, 20, 30]), -10_000_000 * 100, cfg)
    assert low.uniqueness == Uniqueness.NONE_FOUND


def test_nearest_reachable_is_the_true_argmin():
    amounts = [10, 20, 30]
    index = ReachabilityIndex(amounts)
    target = 3
    nearest = index.nearest_reachable(target)
    reachable = [t for t in range(index.NEG, index.POS + 1) if index.is_reachable(t)]
    expected = min(reachable, key=lambda t: (abs(t - target), t))
    assert nearest == expected


def test_solution_count_monotone_in_tolerance():
    amounts = [10, 11, 25, 3]
    target = 10
    prev = 0
    prev_unique = False
    for tol in range(0, 6):
        oracle = brute_force_solutions(amounts, target, tol)
        result = solve_search(pool_from_amounts(amounts), target * 100, cfg_with_tol(tol))
        assert len(oracle) >= prev
        if prev_unique and len(oracle) > 1:
            assert result.uniqueness == Uniqueness.AMBIGUOUS
        prev = len(oracle)
        prev_unique = result.uniqueness == Uniqueness.UNIQUE


def test_order_independence():
    amounts = [40, -15, 20, 7, -3]
    target = 32
    cfg = cfg_with_tol(2)
    base = solve_search(pool_from_amounts(amounts), target * 100, cfg)
    for perm in (
        [40, 20, -15, 7, -3],
        [-3, 7, 20, -15, 40],
        [7, 40, -3, 20, -15],
    ):
        other = solve_search(pool_from_amounts(perm), target * 100, cfg)
        assert other.uniqueness == base.uniqueness
        if base.uniqueness == Uniqueness.UNIQUE:
            base_sum = sum(amounts[i] for i in _ids_to_indices(base.member_ids))
            other_vals = [perm[int(mid[1:])] for mid in other.member_ids]
            assert sum(other_vals) == base_sum


def test_no_public_raw_bitmask():
    index = ReachabilityIndex([10, -4, 7, 3])
    public_ints = []
    for name, _ in inspect.getmembers(index):
        if name.startswith("_"):
            continue
        value = getattr(index, name)
        if isinstance(value, int):
            public_ints.append((name, value))
    for name, value in public_ints:
        assert value.bit_length() <= 64, f"{name} looks like a raw bitmask (bit_length={value.bit_length()})"


def test_budget_exceeded_rather_than_silent_truncation():
    amounts = list(range(1, 50))
    result = solve_search(pool_from_amounts(amounts), 100 * 100, cfg_with_tol(0, max_pool=10))
    assert result.uniqueness == Uniqueness.BUDGET_EXCEEDED
    assert result.member_ids == ()


def test_axis_width_cap_is_deterministic():
    cfg = cfg_with_tol(0)
    search = cfg.search.model_copy(update={"max_axis_width_rupees": 20})
    tight = cfg.model_copy(update={"search": search})
    amounts = [100, 200, 300]
    first = solve_search(pool_from_amounts(amounts), 100 * 100, tight)
    second = solve_search(pool_from_amounts(amounts), 100 * 100, tight)
    assert first.uniqueness == Uniqueness.BUDGET_EXCEEDED
    assert second.uniqueness == Uniqueness.BUDGET_EXCEEDED


@given(
    amounts=st.lists(st.integers(-60, 60).filter(lambda x: x != 0), min_size=1, max_size=10),
    target=st.integers(-200, 200),
    tol=st.integers(0, 5),
)
@settings(max_examples=40, deadline=None)
def test_hypothesis_uniqueness_under_tolerance(amounts, target, tol):
    result = solve_search(pool_from_amounts(amounts), target * 100, cfg_with_tol(tol))
    oracle = brute_force_solutions(amounts, target, tol)
    if len(oracle) == 0:
        assert result.uniqueness in (Uniqueness.NONE_FOUND, Uniqueness.BUDGET_EXCEEDED)
    elif len(oracle) == 1:
        assert result.uniqueness == Uniqueness.UNIQUE
        assert _ids_to_indices(result.member_ids) == next(iter(oracle))
    else:
        assert result.uniqueness == Uniqueness.AMBIGUOUS
        assert result.member_ids == ()
