"""Helpers for solver tests: unreduced oracle, config with a chosen ε, amount-only pools."""

from __future__ import annotations

from datetime import date
from itertools import combinations
from typing import Sequence

from residual_zero.candidates import CandidatePool
from residual_zero.config import SolverConfig, load_solver_config
from residual_zero.models import Kind, PoolScope


def brute_force_solutions(
    amounts: Sequence[int], target: int, tol: int,
) -> set[frozenset[int]]:
    """Every non-empty index subset whose signed sum lies within tol of target."""
    n = len(amounts)
    found: set[frozenset[int]] = set()
    for width in range(1, n + 1):
        for combo in combinations(range(n), width):
            total = sum(amounts[i] for i in combo)
            if abs(total - target) <= tol:
                found.add(frozenset(combo))
    return found


def cfg_with_tol(tol: int, *, max_pool: int | None = None) -> SolverConfig:
    base = load_solver_config()
    search_update = {
        "epsilon_rupees": tol,
        "epsilon_paise_equivalent": tol * 100,
    }
    if max_pool is not None:
        search_update["max_pool"] = max_pool
    search = base.search.model_copy(update=search_update)
    diagnosis = base.diagnosis.model_copy(
        update={"rounding_delta_ceiling_paise": tol * 100}
    )
    return base.model_copy(update={"search": search, "diagnosis": diagnosis})


def pool_from_amounts(amounts: Sequence[int], *, day: date = date(2025, 1, 15)) -> CandidatePool:
    n = len(amounts)
    paise = tuple(int(a) * 100 for a in amounts)
    return CandidatePool(
        bank_credit_id="c0",
        item_ids=tuple(f"i{i:02d}" for i in range(n)),
        amounts_paise=paise,
        amounts_rupees=tuple(int(a) for a in amounts),
        scope=PoolScope.FULL,
        sub_window=None,
        gross_paise=sum(p for p in paise if p > 0),
        kinds=tuple(Kind.PAYMENT for _ in range(n)),
        occurred_on=tuple(day for _ in range(n)),
        value_date=day,
        account_id="acc_00",
        currency="INR",
    )
