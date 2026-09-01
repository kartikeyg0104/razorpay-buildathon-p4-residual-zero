"""Solution uniqueness is a set of record ids, not a permutation of the walk."""

from residual_zero.models import Uniqueness
from residual_zero.solver import solve_search
from residual_zero.solver.bitset_dp import ReachabilityIndex
from residual_zero.solver.enumerate import enumerate_solutions

from tests.solver_helpers import brute_force_solutions, cfg_with_tol, pool_from_amounts


def test_two_identical_amounts_are_two_record_sets():
    """[5, 5] hitting 5 is two different ledger ids, not one permutation."""
    oracle = brute_force_solutions([5, 5], 5, 0)
    assert len(oracle) == 2
    result = solve_search(pool_from_amounts([5, 5]), 5 * 100, cfg_with_tol(0))
    assert result.uniqueness == Uniqueness.AMBIGUOUS
    assert result.alternates == 2
    assert result.member_ids == ()


def test_one_full_stack_is_unique_regardless_of_walk_order():
    result = solve_search(pool_from_amounts([1, 2, 3]), 6 * 100, cfg_with_tol(0))
    assert result.uniqueness == Uniqueness.UNIQUE
    assert result.member_ids == ("i00", "i01", "i02")
    assert result.alternates == 1


def test_permutation_of_amounts_is_one_solution():
    """[A,B,C] / [C,B,A] / [B,A,C] are one UNIQUE set after sorting record amounts."""
    for amounts in ([1, 2, 3], [3, 2, 1], [2, 1, 3]):
        pool = pool_from_amounts(amounts)
        got = solve_search(pool, 6 * 100, cfg_with_tol(0))
        assert got.uniqueness == Uniqueness.UNIQUE
        by_id = dict(zip(pool.item_ids, pool.amounts_rupees, strict=True))
        selected = tuple(sorted(by_id[i] for i in got.member_ids))
        assert selected == (1, 2, 3)


def test_enumerate_collapses_duplicate_index_sets():
    amounts = (10, 11)
    index = ReachabilityIndex(amounts)
    # Same subset {0} is reachable at total 10. Feeding the total twice must not
    # count two solutions.
    solutions = enumerate_solutions(
        index, amounts, totals=(10, 10), cap=8, max_nodes=200000, require_nonempty=True,
    )
    assert solutions == ((0,),)
