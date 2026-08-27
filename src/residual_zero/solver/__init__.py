"""Solver package. Re-exports the CP3 surface and nothing else (PLAN-P1 D8)."""

from __future__ import annotations

from residual_zero.solver.bitset_dp import BudgetExceeded, ReachabilityIndex
from residual_zero.solver.disambiguate import disambiguate
from residual_zero.solver.enumerate import SolveResult, collect_enumerated, enumerate_solutions, solve_search
from residual_zero.solver.fastpath import DeclaredLine, FastPathResult, verify_declared

__all__ = [
    "BudgetExceeded",
    "ReachabilityIndex",
    "SolveResult",
    "collect_enumerated",
    "disambiguate",
    "enumerate_solutions",
    "solve_search",
    "DeclaredLine",
    "FastPathResult",
    "verify_declared",
]
