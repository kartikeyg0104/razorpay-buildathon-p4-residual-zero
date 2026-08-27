"""Regime B search: enumerate across every hit total under one shared cap (§0.1)."""

from __future__ import annotations

from typing import Sequence

from pydantic import BaseModel, ConfigDict, Field

from residual_zero.candidates import CandidatePool, split_pool
from residual_zero.config import SolverConfig
from residual_zero.models import PoolScope, Uniqueness
from residual_zero.money import to_rupee_units

from .bitset_dp import BudgetExceeded, ReachabilityIndex

_STRICT = ConfigDict(frozen=True, extra="forbid")


def collect_enumerated(
    pool: CandidatePool,
    target_paise: int,
    cfg: SolverConfig,
    cap: int,
) -> tuple[tuple[int, ...], bool, bool]:
    """Return (index tuples, capped, budgeted). Budgeted True means do not disambiguate."""
    amounts = pool.amounts_rupees
    n = len(amounts)
    if n == 0 or n > cfg.search.max_pool or any(a == 0 for a in amounts):
        return (), False, True
    index = ReachabilityIndex(amounts)
    if index.axis_width > cfg.search.max_axis_width_rupees:
        return (), False, True
    target_rupees = to_rupee_units(target_paise)
    hits = index.hits_in_window(target_rupees, cfg.search.epsilon_rupees)
    if not hits:
        return (), False, True
    try:
        solutions = enumerate_solutions(
            index,
            amounts,
            hits,
            cap=cap,
            max_nodes=cfg.search.max_enum_nodes,
            require_nonempty=cfg.search.require_nonempty,
        )
    except BudgetExceeded:
        return (), False, True
    capped = len(solutions) >= cap
    return solutions, capped, False


class SolveResult(BaseModel):
    model_config = _STRICT

    uniqueness: Uniqueness
    matched_total_rupees: int | None
    member_ids: tuple[str, ...] = ()
    alternates: int = Field(ge=0)
    nearest_total_rupees: int | None = None
    nearest_delta_rupees: int | None = None
    pool_scope: PoolScope
    pool_size: int = Field(ge=0)
    axis_width: int = Field(ge=0)
    hit_totals: tuple[int, ...] = ()
    slack_rupees: int | None = None
    margin_rupees: int | None = None
    enum_nodes: int = Field(ge=0, default=0)


def enumerate_solutions(
    index: ReachabilityIndex,
    amounts_rupees: Sequence[int],
    totals: Sequence[int],
    cap: int,
    max_nodes: int,
    require_nonempty: bool,
) -> tuple[tuple[int, ...], ...]:
    """Backtrack across EVERY total in ``totals`` into one shared solution list with one shared cap.

    The empty subset is never a solution when ``require_nonempty`` is true. This is the §0.1
    correction: uniqueness is assessed across the window, not inside one reachable total.
    """
    amounts = tuple(amounts_rupees)
    n = len(amounts)
    solutions: list[tuple[int, ...]] = []
    nodes = 0

    def backtrack(prefix: int, remaining: int, chosen: list[int]) -> None:
        nonlocal nodes
        nodes += 1
        if nodes > max_nodes:
            raise BudgetExceeded("max_enum_nodes")
        if len(solutions) >= cap:
            return
        if prefix == 0:
            if remaining == 0:
                if require_nonempty and not chosen:
                    return
                solutions.append(tuple(reversed(chosen)))
            return
        amount = amounts[prefix - 1]
        if index.was_reachable_at(prefix - 1, remaining - amount):
            chosen.append(prefix - 1)
            backtrack(prefix - 1, remaining - amount, chosen)
            chosen.pop()
        if len(solutions) >= cap:
            return
        if index.was_reachable_at(prefix - 1, remaining):
            backtrack(prefix - 1, remaining, chosen)

    for total in totals:
        if len(solutions) >= cap:
            break
        backtrack(n, total, [])
    # Stash node count on the index so solve_search can read it without a parallel return.
    index._enum_nodes = nodes  # type: ignore[attr-defined]
    return tuple(solutions)


def _margin_rupees(index: ReachabilityIndex, matched: int) -> int | None:
    """Distance to the nearest reachable total other than ``matched``."""
    span = max(matched - index.NEG, index.POS - matched)
    delta = 1
    while delta <= span:
        if index.is_reachable(matched - delta) or index.is_reachable(matched + delta):
            return delta
        delta += 1
    return None


def _empty_result(
    uniqueness: Uniqueness,
    pool: CandidatePool,
    *,
    axis_width: int = 0,
    nearest: int | None = None,
    nearest_delta: int | None = None,
    hit_totals: tuple[int, ...] = (),
    enum_nodes: int = 0,
) -> SolveResult:
    return SolveResult(
        uniqueness=uniqueness,
        matched_total_rupees=None,
        member_ids=(),
        alternates=0,
        nearest_total_rupees=nearest,
        nearest_delta_rupees=nearest_delta,
        pool_scope=pool.scope,
        pool_size=len(pool.item_ids),
        axis_width=axis_width,
        hit_totals=hit_totals,
        slack_rupees=None,
        margin_rupees=None,
        enum_nodes=enum_nodes,
    )


def _solve_one(pool: CandidatePool, target_rupees: int, cfg: SolverConfig) -> SolveResult:
    amounts = pool.amounts_rupees
    n = len(amounts)
    if n == 0:
        return _empty_result(Uniqueness.NONE_FOUND, pool)
    if n > cfg.search.max_pool:
        return _empty_result(Uniqueness.BUDGET_EXCEEDED, pool)
    if any(a == 0 for a in amounts):
        # A sub-rupee item rounded to 0 rupees is invisible on the search axis and illegal
        # as a DP input. Do not auto-clear; the verifier still sees the paise.
        return _empty_result(Uniqueness.NONE_FOUND, pool)
    index = ReachabilityIndex(amounts)
    if index.axis_width > cfg.search.max_axis_width_rupees:
        return _empty_result(Uniqueness.BUDGET_EXCEEDED, pool, axis_width=index.axis_width)
    epsilon = cfg.search.epsilon_rupees
    if target_rupees + epsilon < index.NEG or target_rupees - epsilon > index.POS:
        nearest = index.nearest_reachable(target_rupees)
        return _empty_result(
            Uniqueness.NONE_FOUND,
            pool,
            axis_width=index.axis_width,
            nearest=nearest,
            nearest_delta=None if nearest is None else nearest - target_rupees,
        )
    hits = index.hits_in_window(target_rupees, epsilon)
    if not hits:
        nearest = index.nearest_reachable(target_rupees)
        return _empty_result(
            Uniqueness.NONE_FOUND,
            pool,
            axis_width=index.axis_width,
            nearest=nearest,
            nearest_delta=None if nearest is None else nearest - target_rupees,
        )
    try:
        solutions = enumerate_solutions(
            index,
            amounts,
            hits,
            cap=cfg.search.enumerate_cap,
            max_nodes=cfg.search.max_enum_nodes,
            require_nonempty=cfg.search.require_nonempty,
        )
    except BudgetExceeded:
        return _empty_result(Uniqueness.BUDGET_EXCEEDED, pool, axis_width=index.axis_width)
    enum_nodes = int(getattr(index, "_enum_nodes", 0))
    n_found = len(solutions)
    if n_found == 0:
        nearest = index.nearest_reachable(target_rupees)
        return _empty_result(
            Uniqueness.NONE_FOUND,
            pool,
            axis_width=index.axis_width,
            nearest=nearest,
            nearest_delta=None if nearest is None else nearest - target_rupees,
            hit_totals=hits,
            enum_nodes=enum_nodes,
        )
    matched = target_rupees if target_rupees in hits else hits[min(range(len(hits)), key=lambda i: abs(hits[i] - target_rupees))]
    if n_found == 1:
        members = tuple(pool.item_ids[i] for i in solutions[0])
        signed_sum = sum(amounts[i] for i in solutions[0])
        return SolveResult(
            uniqueness=Uniqueness.UNIQUE,
            matched_total_rupees=signed_sum,
            member_ids=members,
            alternates=1,
            nearest_total_rupees=None,
            nearest_delta_rupees=None,
            pool_scope=pool.scope,
            pool_size=n,
            axis_width=index.axis_width,
            hit_totals=hits,
            slack_rupees=abs(signed_sum - target_rupees),
            margin_rupees=_margin_rupees(index, signed_sum),
            enum_nodes=enum_nodes,
        )
    return SolveResult(
        uniqueness=Uniqueness.AMBIGUOUS,
        matched_total_rupees=matched,
        member_ids=(),
        alternates=n_found,
        nearest_total_rupees=None,
        nearest_delta_rupees=None,
        pool_scope=pool.scope,
        pool_size=n,
        axis_width=index.axis_width,
        hit_totals=hits,
        slack_rupees=abs(matched - target_rupees),
        margin_rupees=_margin_rupees(index, matched),
        enum_nodes=enum_nodes,
    )


def solve_search(pool: CandidatePool, target_paise: int, cfg: SolverConfig) -> SolveResult:
    """Regime B. Rupee-granular signed subset-sum with tolerance and uniqueness detection.

    Sub-window retries are internal and bounded (NN-5, NN-11). A UNIQUE on a REDUCED pool is
    still UNIQUE-on-reduced, never silently truncated from a FULL pool.
    """
    target_rupees = to_rupee_units(target_paise)
    n = len(pool.item_ids)
    if n <= cfg.search.max_pool:
        return _solve_one(pool, target_rupees, cfg)
    if not cfg.sub_window_split.enabled:
        return _empty_result(Uniqueness.BUDGET_EXCEEDED, pool)

    class _ValueDate:
        value_date = pool.value_date

    for sub in split_pool(pool, _ValueDate(), cfg):  # type: ignore[arg-type]
        if len(sub.item_ids) > cfg.search.max_pool:
            continue
        result = _solve_one(sub, target_rupees, cfg)
        if result.uniqueness in (Uniqueness.UNIQUE, Uniqueness.AMBIGUOUS):
            return result
    return _empty_result(Uniqueness.BUDGET_EXCEEDED, pool)
