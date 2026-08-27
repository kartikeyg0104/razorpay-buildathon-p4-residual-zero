"""A1: fuzzy 1:1, optimally assigned. Not greedy (§9.1, NN-13)."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import NamedTuple, Sequence

import numpy as np
from pydantic import BaseModel, ConfigDict, Field
from rapidfuzz import fuzz
from scipy.optimize import linear_sum_assignment

from residual_zero.models import BankCredit, Disposition, LedgerItem

from . import ArmResult
from .a0_exact import item_ist_date

_STRICT = ConfigDict(frozen=True, extra="forbid")
SENTINEL = 10.0

# Swept on dev; the pair that maximises A1's own exact-decomposition rate is frozen in
# docs/EVALUATION.md. A sandbagged baseline is worse than none (NN-13, §9.1).
SIM_GRID = (50, 60, 70, 80, 90)
TOL_GRID = (1_00, 5_00, 10_00, 50_00, 100_00, 500_00)


class A1Config(BaseModel):
    model_config = _STRICT

    sim_threshold: int = Field(ge=0, le=100)
    amount_tol_paise: int = Field(gt=0)
    w_sim: int = 1
    w_amt: int = 1
    window_days: int = 5


class TuningLog(NamedTuple):
    rows: tuple[tuple[int, int, str], ...]  # sim, tol, exact-rate as fraction string
    chosen: A1Config


def build_cost_matrix(
    items: Sequence[LedgerItem],
    credits: Sequence[BankCredit],
    cfg: A1Config,
) -> tuple[np.ndarray, tuple[int, ...], tuple[int, ...]]:
    """Cost = w_sim*(1-sim/100) + w_amt*min(1, |delta|/tol). Ineligible pairs are omitted.

    Returns a *rectangular* credits-by-eligible-items matrix. Padding to a square of the
    larger dimension made Hungarian cubic in the item count and is how a 248-credit sweep
    previously hung.
    """
    by_acct: dict[tuple[str, str], list[tuple[int, LedgerItem, date]]] = defaultdict(list)
    for ii, item in enumerate(items):
        by_acct[(item.account_id, item.currency)].append((ii, item, item_ist_date(item)))
    triples: list[tuple[int, int, float]] = []
    used_items: set[int] = set()
    for ci, credit in enumerate(credits):
        start = credit.value_date - timedelta(days=cfg.window_days)
        end = credit.value_date - timedelta(days=1)
        for ii, item, occurred in by_acct.get((credit.account_id, credit.currency), ()):
            if not (start <= occurred <= end):
                continue
            delta = abs(item.amount_paise - credit.amount_paise)
            if delta > cfg.amount_tol_paise:
                continue
            sim = fuzz.ratio(credit.narration_norm, item.narration_norm)
            if sim < cfg.sim_threshold:
                continue
            amt_term = min(1.0, delta / cfg.amount_tol_paise)
            sim_term = 1.0 - (sim / 100.0)
            triples.append((ci, ii, cfg.w_sim * sim_term + cfg.w_amt * amt_term))
            used_items.add(ii)
    item_order = tuple(sorted(used_items))
    n_c = len(credits)
    n_col = len(item_order)
    if n_c == 0 or n_col == 0:
        return np.full((max(n_c, 1), max(n_col, 1)), SENTINEL), tuple(range(n_c)), item_order
    col_of = {ii: col for col, ii in enumerate(item_order)}
    cost = np.full((n_c, n_col), SENTINEL)
    for ci, ii, value in triples:
        cost[ci, col_of[ii]] = value
    return cost, tuple(range(n_c)), item_order


def run_a1(
    items: Sequence[LedgerItem],
    credits: Sequence[BankCredit],
    cfg: A1Config,
) -> ArmResult:
    """Optimal 1:1 assignment via linear_sum_assignment, NOT greedy."""
    if not credits:
        return ArmResult(arm="a1", predictions={}, dispositions={}, has_exception_path=False, has_budget_path=False)
    cost, _, item_order = build_cost_matrix(items, credits, cfg)
    predictions: dict[str, tuple[str, ...]] = {c.id: () for c in credits}
    dispositions: dict[str, Disposition] = {c.id: Disposition.FLAGGED for c in credits}
    if not item_order or cost.shape[1] == 0:
        return ArmResult(
            arm="a1",
            predictions=predictions,
            dispositions=dispositions,
            has_exception_path=False,
            has_budget_path=False,
        )
    rows, cols = linear_sum_assignment(cost)
    used_items: set[str] = set()
    for r, c in zip(rows, cols):
        if r >= len(credits) or c >= len(item_order):
            continue
        if cost[r, c] >= SENTINEL:
            continue
        credit = credits[r]
        item = items[item_order[c]]
        if item.id in used_items:
            continue
        predictions[credit.id] = (item.id,)
        dispositions[credit.id] = Disposition.CLEARED
        used_items.add(item.id)
    return ArmResult(
        arm="a1",
        predictions=predictions,
        dispositions=dispositions,
        has_exception_path=False,
        has_budget_path=False,
    )


def tune_a1_on_dev(
    items: Sequence[LedgerItem],
    credits: Sequence[BankCredit],
    truth_members: dict[str, tuple[str, ...]],
) -> tuple[A1Config, TuningLog]:
    """Sweep similarity threshold and amount tolerance; pick A1's own best exact rate."""
    from eval.metrics import exact_decomposition_counted

    best_cfg = A1Config(sim_threshold=70, amount_tol_paise=10_00)
    best_exact = -1
    rows: list[tuple[int, int, str]] = []
    for sim in SIM_GRID:
        for tol in TOL_GRID:
            cfg = A1Config(sim_threshold=sim, amount_tol_paise=tol)
            result = run_a1(items, credits, cfg)
            counted = exact_decomposition_counted(result.predictions, truth_members)
            exact = counted.as_fraction()
            rows.append((sim, tol, f"{counted.numerator}/{counted.denominator}"))
            tighter_tol = exact == best_exact and tol < best_cfg.amount_tol_paise
            if exact > best_exact or tighter_tol:
                best_exact = exact
                best_cfg = cfg
    return best_cfg, TuningLog(rows=tuple(rows), chosen=best_cfg)


# Re-export so callers that imported the helper from here keep working.
__all__ = [
    "A1Config",
    "TuningLog",
    "SIM_GRID",
    "TOL_GRID",
    "SENTINEL",
    "build_cost_matrix",
    "run_a1",
    "tune_a1_on_dev",
]
