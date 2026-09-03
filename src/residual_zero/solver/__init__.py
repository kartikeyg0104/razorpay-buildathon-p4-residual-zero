"""Solver package. Re-exports the CP3 surface and nothing else (PLAN-P1 D8)."""

from __future__ import annotations

from residual_zero.solver.bitset_dp import BudgetExceeded, ReachabilityIndex
from residual_zero.solver.disambiguate import disambiguate
from residual_zero.solver.enumerate import (
    SolveResult,
    collect_enumerated,
    enumerate_solutions,
    search_cap,
    solve_search,
    unsearched_result,
)
from residual_zero.solver.prune import prune_indices
from residual_zero.solver.fastpath import DeclaredLine, FastPathResult, verify_declared

__all__ = [
    "BudgetExceeded",
    "ReachabilityIndex",
    "SolveResult",
    "collect_enumerated",
    "disambiguate",
    "enumerate_solutions",
    "prune_indices",
    "search_cap",
    "solve_search",
    "unsearched_result",
    "DeclaredLine",
    "FastPathResult",
    "verify_declared",
]
