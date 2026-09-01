"""Scale search: safe prune, 399–600 pools, identity, determinism. Not wall-clock flaky."""

from residual_zero.config import load_solver_config
from residual_zero.models import Uniqueness
from residual_zero.solver import prune_indices, solve_search
from residual_zero.solver.enumerate import search_cap

from tests.solver_helpers import cfg_with_tol, pool_from_amounts


def test_prune_drops_positive_amounts_above_the_window():
    kept = prune_indices((3, 100, 4), target_rupees=7, epsilon_rupees=0)
    assert kept == (0, 2)


def test_prune_keeps_a_negative_that_can_offset():
    kept = prune_indices((100, -20, 7), target_rupees=80, epsilon_rupees=0)
    assert 0 in kept and 1 in kept


def test_prune_empty_when_nothing_can_hit():
    assert prune_indices((10, 10, 10), target_rupees=5, epsilon_rupees=0) == ()


def test_search_cap_defaults_to_max_pool_when_scaled_unset():
    cfg = cfg_with_tol(0, max_pool=10)
    assert search_cap(cfg) == 10


def test_product_scaled_cap_is_above_test_max_pool():
    cfg = load_solver_config()
    assert cfg.search.max_pool == 400
    assert search_cap(cfg) >= 597


def test_pool_399_400_complete():
    cfg = load_solver_config()
    for n in (399, 400):
        amounts = [1] * n
        result = solve_search(pool_from_amounts(amounts), 1 * 100, cfg)
        assert result.uniqueness == Uniqueness.AMBIGUOUS, n
        assert result.strategy != "BUDGET_CAP", n
        assert result.pool_size_before == n


def test_pool_401_completes_under_scaled_cap():
    cfg = load_solver_config()
    result = solve_search(pool_from_amounts([1] * 401), 1 * 100, cfg)
    assert result.uniqueness == Uniqueness.AMBIGUOUS
    assert result.strategy == "BITSET_DP_SCALED"
    assert result.member_ids == ()


def test_pool_401_still_budgets_when_cap_is_400():
    cfg = cfg_with_tol(0, max_pool=400)
    result = solve_search(pool_from_amounts([1] * 401), 1 * 100, cfg)
    assert result.uniqueness == Uniqueness.BUDGET_EXCEEDED
    assert result.member_ids == ()


def test_pool_500_and_600_repeated_amounts_are_ambiguous():
    cfg = load_solver_config()
    for n in (500, 600):
        result = solve_search(pool_from_amounts([1] * n), 1 * 100, cfg)
        assert result.uniqueness == Uniqueness.AMBIGUOUS, n
        assert result.alternates >= 2, n
        assert result.member_ids == ()


def test_one_unique_solution_in_a_600_pool():
    amounts = [10_000] * 599 + [7]
    result = solve_search(pool_from_amounts(amounts), 7 * 100, load_solver_config())
    assert result.uniqueness == Uniqueness.UNIQUE
    assert result.member_ids == ("i599",)
    assert result.strategy == "BITSET_DP_PRUNED"
    assert result.pool_size == 1
    assert result.pool_size_before == 600


def test_no_solution_in_a_500_pool_is_none_found():
    result = solve_search(pool_from_amounts([10] * 500), 5 * 100, cfg_with_tol(0))
    assert result.uniqueness == Uniqueness.NONE_FOUND
    assert result.strategy == "PRUNED_EMPTY"
    assert result.member_ids == ()


def test_exact_paise_not_rupee_rounding():
    amounts = [10_000] * 50 + [3]
    result = solve_search(pool_from_amounts(amounts), 3 * 100, load_solver_config())
    assert result.uniqueness == Uniqueness.UNIQUE
    assert result.member_ids == ("i50",)


def test_repeated_execution_is_deterministic():
    pool = pool_from_amounts([10_000] * 200 + [4, 5])
    cfg = cfg_with_tol(0)
    first = solve_search(pool, 9 * 100, cfg)
    second = solve_search(pool, 9 * 100, cfg)
    assert first.uniqueness == second.uniqueness == Uniqueness.UNIQUE
    assert first.member_ids == second.member_ids
    assert first.strategy == second.strategy


def test_solution_identity_is_record_ids_not_amount_groups():
    amounts = [10_000] * 80 + [6, 6]
    result = solve_search(pool_from_amounts(amounts), 6 * 100, load_solver_config())
    assert result.uniqueness == Uniqueness.AMBIGUOUS
    assert result.member_ids == ()
