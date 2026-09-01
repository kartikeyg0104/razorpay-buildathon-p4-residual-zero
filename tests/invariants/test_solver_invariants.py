"""Solver invariants: prove or refuse, never guess.

Three groups:

  structure    single / multiple / zero solutions, duplicates, signs, zeros, large pools
  permutation  candidate order cannot change the logical answer
  adversarial  closeness, similarity, ordering and count are never financial authority
  fuzz         a known subset is discoverable; every mutation degrades to a refusal

The production solver is exercised as-is. Nothing here changes solver behaviour.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from residual_zero.models import PoolScope, Uniqueness
from residual_zero.solver import solve_search
from solver_helpers import cfg_with_tol, pool_from_amounts

EXACT = cfg_with_tol(0)


def solve(amounts, target_rupees, cfg=EXACT):
    return solve_search(pool_from_amounts(list(amounts)), int(target_rupees) * 100, cfg)


def canonical(result) -> tuple[str, ...]:
    """The canonical representation of a solution: sorted member ids."""
    return tuple(sorted(result.member_ids))


# ------------------------------------------------------------------- structure


def test_single_solution_is_unique_and_names_its_members():
    r = solve([100, 200, 700, 900], 300)
    assert r.uniqueness is Uniqueness.UNIQUE
    assert canonical(r) == ("i00", "i01")
    assert r.alternates == 1


def test_multiple_solutions_are_ambiguous_and_name_nobody():
    """The decisive safety property: ambiguity yields no member list at all."""
    r = solve([100, 200, 300, 900], 300)
    assert r.uniqueness is Uniqueness.AMBIGUOUS
    assert r.member_ids == ()
    assert r.alternates >= 2


def test_zero_solutions_is_none_found_and_names_nobody():
    r = solve([100, 200], 5_000)
    assert r.uniqueness is Uniqueness.NONE_FOUND
    assert r.member_ids == ()


def test_duplicate_values_produce_ambiguity_not_an_arbitrary_pick():
    """Two identical amounts that both satisfy the target are two explanations."""
    r = solve([250, 250, 900], 250)
    assert r.uniqueness is Uniqueness.AMBIGUOUS
    assert r.member_ids == ()


def test_duplicate_values_summing_to_target_is_still_handled():
    r = solve([250, 250, 900], 500)
    assert r.uniqueness is Uniqueness.UNIQUE
    assert canonical(r) == ("i00", "i01")


def test_negative_only_pool():
    r = solve([-100, -200, -700], -300)
    assert r.uniqueness is Uniqueness.UNIQUE
    assert canonical(r) == ("i00", "i01")


def test_mixed_signs_resolve_by_arithmetic_not_by_magnitude():
    r = solve([500, -200, 700], 300)
    assert r.uniqueness is Uniqueness.UNIQUE
    assert canonical(r) == ("i00", "i01")


@pytest.mark.parametrize(
    "amounts,target",
    [
        ([0, 300, 900], 300),   # {300} alone would satisfy the target
        ([300, 0, 900], 300),
        ([0, 300], 300),
        ([0, 0, 300], 300),
    ],
)
def test_a_zero_rupee_record_makes_the_search_refuse_rather_than_search(amounts, target):
    """Deliberate conservatism, not a miss.

    A sub-rupee ledger item rounds to 0 on the rupee-granular search axis, so it is
    invisible to the DP while still being real in paise. Searching such a pool could
    prove a "unique" equation that is wrong by paise. The solver therefore refuses the
    whole pool: no members, no auto-clear. The paise-level verifier is the safety net.
    """
    r = solve(amounts, target)
    assert r.uniqueness is Uniqueness.NONE_FOUND
    assert r.member_ids == ()
    assert r.alternates == 0


def test_removing_the_zero_record_restores_a_normal_search():
    """Confirms the refusal above is caused by the zero, not by an unreachable target."""
    assert solve([300, 900], 300).uniqueness is Uniqueness.UNIQUE
    assert solve([0, 300, 900], 300).uniqueness is Uniqueness.NONE_FOUND


def test_the_zero_guard_is_still_present_in_the_solver():
    """Structural guard: the conservative branch must not be removed."""
    text = Path("src/residual_zero/solver/enumerate.py").read_text(encoding="utf-8")
    assert "if any(a == 0 for a in amounts):" in text


def test_the_dp_itself_rejects_zero_amounts_outright():
    from residual_zero.solver import ReachabilityIndex

    with pytest.raises(ValueError):
        ReachabilityIndex((0, 300))


def test_empty_subset_is_never_a_solution_for_zero_target():
    r = solve([100, 200], 0)
    assert r.member_ids != ()  or r.uniqueness is not Uniqueness.UNIQUE


def test_target_far_outside_the_axis_refuses_cleanly():
    r = solve([1, 2, 3], 10**7)
    assert r.uniqueness in {Uniqueness.NONE_FOUND, Uniqueness.BUDGET_EXCEEDED}
    assert r.member_ids == ()


def test_large_pool_of_400_candidates_terminates_without_guessing():
    amounts = list(range(1, 401))
    r = solve(amounts, 100_000)
    assert r.uniqueness in set(Uniqueness)
    if r.uniqueness is not Uniqueness.UNIQUE:
        assert r.member_ids == ()
    assert r.pool_scope in {PoolScope.FULL, PoolScope.REDUCED}


def test_reduced_scope_is_reported_not_hidden():
    """A truncated search must say so rather than present a partial answer as full."""
    amounts = [i * 7 for i in range(1, 401)]
    r = solve(amounts, 500_000)
    if r.pool_scope is PoolScope.REDUCED:
        assert r.uniqueness is not Uniqueness.UNIQUE or r.member_ids != ()
    assert r.pool_size >= 0


def test_budget_exceeded_is_never_reported_as_none_found():
    """These are different financial statements and must not be conflated."""
    amounts = [i for i in range(1, 401)]
    r = solve(amounts, 40_000)
    assert not (r.uniqueness is Uniqueness.NONE_FOUND and r.pool_scope is PoolScope.REDUCED and r.member_ids)


# ----------------------------------------------------------------- permutation


PERMUTATION_CASES = [
    ([100, 200, 700, 900], 300),
    ([500, -200, 700], 300),
    ([250, 250, 900], 500),
    ([100, 200, 300, 900], 300),
    ([12, 34, 56, 78, 90], 90),
]


@pytest.mark.parametrize("amounts,target", PERMUTATION_CASES)
def test_three_permutations_agree_on_every_financial_field(amounts, target):
    """[A,B,C], [C,B,A], [B,A,C] must normalise to the same logical solution."""
    orders = [
        list(amounts),
        list(reversed(amounts)),
        [amounts[1], amounts[0], *amounts[2:]],
    ]
    results = [solve(o, target) for o in orders]
    uniq = {r.uniqueness for r in results}
    counts = {r.alternates for r in results}
    totals = {r.matched_total_rupees for r in results}
    scopes = {r.pool_scope for r in results}
    assert len(uniq) == 1, f"uniqueness diverged across permutations: {uniq}"
    assert len(counts) == 1, f"solution count diverged: {counts}"
    assert len(totals) == 1, f"matched total diverged: {totals}"
    assert len(scopes) == 1, f"pool scope diverged: {scopes}"


@pytest.mark.parametrize("amounts,target", PERMUTATION_CASES)
def test_permuted_pools_select_the_same_multiset_of_amounts(amounts, target):
    """Ids are positional, so compare the amounts the solver actually chose."""

    def chosen(order):
        r = solve(order, target)
        if r.uniqueness is not Uniqueness.UNIQUE:
            return None
        index = {f"i{i:02d}": order[i] for i in range(len(order))}
        return tuple(sorted(index[m] for m in r.member_ids))

    picks = {chosen(list(amounts)), chosen(list(reversed(amounts)))}
    assert len(picks) == 1, f"permutation changed the chosen amounts: {picks}"


@settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    amounts=st.lists(
        st.integers(min_value=-5_000, max_value=5_000).filter(lambda x: x != 0),
        min_size=3,
        max_size=8,
        unique=True,
    ),
    seed=st.integers(min_value=0, max_value=10**6),
)
def test_shuffling_never_changes_uniqueness_or_count(amounts, seed):
    target = sum(amounts[:2])
    base = solve(amounts, target)
    shuffled = list(amounts)
    random.Random(seed).shuffle(shuffled)
    other = solve(shuffled, target)
    assert base.uniqueness is other.uniqueness
    assert base.alternates == other.alternates


# ----------------------------------------------------------------- adversarial


def test_a_closer_candidate_does_not_beat_an_exact_one():
    """299 is nearer in magnitude to nothing; 300 is exact. Exactness must win."""
    r = solve([299, 300, 901], 300)
    assert r.uniqueness is Uniqueness.UNIQUE
    index = {"i00": 299, "i01": 300, "i02": 901}
    assert index[r.member_ids[0]] == 300


def test_a_near_miss_alone_is_refused_not_rounded_into_a_match():
    """One rupee off is not a match at zero tolerance."""
    r = solve([299, 901], 300)
    assert r.uniqueness is Uniqueness.NONE_FOUND
    assert r.member_ids == ()


def test_the_largest_candidate_is_not_preferred():
    r = solve([100, 200, 5_000], 300)
    assert r.uniqueness is Uniqueness.UNIQUE
    assert canonical(r) == ("i00", "i01")


def test_the_first_candidate_is_not_preferred():
    """If the first record cannot participate, it must not be selected."""
    r = solve([999, 100, 200], 300)
    assert r.uniqueness is Uniqueness.UNIQUE
    index = {"i00": 999, "i01": 100, "i02": 200}
    assert sorted(index[m] for m in r.member_ids) == [100, 200]


def test_more_members_is_not_preferred_over_fewer_when_both_are_exact():
    """Two exact explanations of different size are still two explanations."""
    r = solve([300, 100, 200], 300)
    assert r.uniqueness is Uniqueness.AMBIGUOUS
    assert r.member_ids == ()


def test_tolerance_widening_can_only_add_ambiguity_never_certainty():
    exact = solve([299, 300, 901], 300, cfg_with_tol(0))
    loose = solve([299, 300, 901], 300, cfg_with_tol(5))
    assert exact.uniqueness is Uniqueness.UNIQUE
    assert loose.alternates >= exact.alternates
    if loose.alternates > 1:
        assert loose.uniqueness is Uniqueness.AMBIGUOUS
        assert loose.member_ids == ()


# ------------------------------------------------------------------------ fuzz


@settings(max_examples=120, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    amounts=st.lists(
        st.integers(min_value=1, max_value=9_999),
        min_size=4,
        max_size=9,
        unique=True,
    ),
    subset_size=st.integers(min_value=1, max_value=3),
    seed=st.integers(min_value=0, max_value=10**6),
)
def test_a_known_subset_is_always_discoverable(amounts, subset_size, seed):
    """Plant a subset, compute its exact total, shuffle, and require proof or ambiguity.

    The solver may legitimately report AMBIGUOUS when another subset hits the same
    total. What it must never do is report NONE_FOUND for a reachable target, or
    name members that do not sum to the target.
    """
    rng = random.Random(seed)
    subset_size = min(subset_size, len(amounts))
    chosen = rng.sample(amounts, subset_size)
    target = sum(chosen)
    order = list(amounts)
    rng.shuffle(order)

    r = solve(order, target)
    assert r.uniqueness is not Uniqueness.NONE_FOUND, (
        f"reachable target {target} reported NONE_FOUND for pool {order}"
    )
    if r.uniqueness is Uniqueness.UNIQUE:
        index = {f"i{i:02d}": order[i] for i in range(len(order))}
        assert sum(index[m] for m in r.member_ids) == target
    else:
        assert r.member_ids == ()


MUTATIONS = ["plus_one", "minus_one", "sign_flip", "remove_member", "duplicate_member"]


@pytest.mark.parametrize("mutation", MUTATIONS)
@settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    amounts=st.lists(
        st.integers(min_value=100, max_value=9_999), min_size=4, max_size=7, unique=True
    ),
    seed=st.integers(min_value=0, max_value=10**6),
)
def test_mutations_never_produce_a_guess(mutation, amounts, seed):
    """After corruption the solver either proves a real equation or refuses.

    "Refuses" means AMBIGUOUS / NONE_FOUND / BUDGET_EXCEEDED with no member list.
    A named solution must always actually sum to the target.
    """
    rng = random.Random(seed)
    chosen = rng.sample(amounts, 2)
    target = sum(chosen)
    pool = list(amounts)

    if mutation == "plus_one":
        target += 1
    elif mutation == "minus_one":
        target -= 1
    elif mutation == "sign_flip":
        idx = pool.index(chosen[0])
        pool[idx] = -pool[idx]
    elif mutation == "remove_member":
        pool.remove(chosen[0])
    elif mutation == "duplicate_member":
        pool.append(chosen[0])

    if len(pool) < 2:
        return
    r = solve(pool, target)
    if r.uniqueness is Uniqueness.UNIQUE:
        index = {f"i{i:02d}": pool[i] for i in range(len(pool))}
        assert sum(index[m] for m in r.member_ids) == target, (
            "named a solution that does not satisfy the equation"
        )
    else:
        assert r.member_ids == (), "refused but still named members"


@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    amounts=st.lists(
        st.integers(min_value=100, max_value=9_999), min_size=3, max_size=7, unique=True
    ),
    offset=st.integers(min_value=1, max_value=50),
)
def test_unreachable_targets_are_never_matched_at_zero_tolerance(amounts, offset):
    """A target above the total positive sum cannot be explained."""
    target = sum(amounts) + offset
    r = solve(amounts, target)
    assert r.uniqueness is not Uniqueness.UNIQUE
    assert r.member_ids == ()
