"""A2: rules-only. Same pools as A3, greedy subset, no uniqueness check."""

from __future__ import annotations

from typing import Sequence

from residual_zero.candidates import build_pool
from residual_zero.config import FeeSchedule, SolverConfig, TaxRates
from residual_zero.models import BankCredit, Disposition, LedgerItem
from residual_zero.money import to_rupee_units

from . import ArmResult


def run_a2(
    items: Sequence[LedgerItem],
    credits: Sequence[BankCredit],
    rates: TaxRates,
    fees: FeeSchedule,
    cfg: SolverConfig,
) -> ArmResult:
    """Largest-first greedy subset selection. Clears on the first subset within tolerance."""
    predictions: dict[str, tuple[str, ...]] = {}
    dispositions: dict[str, Disposition] = {}
    epsilon = cfg.search.epsilon_rupees
    for credit in credits:
        pool = build_pool(credit, items, cfg)
        target = to_rupee_units(credit.amount_paise)
        unused = list(range(len(pool.item_ids)))
        unused.sort(key=lambda i: (-abs(pool.amounts_rupees[i]), pool.item_ids[i]))
        running = 0
        chosen: list[int] = []
        while unused:
            best = min(
                unused,
                key=lambda i: (
                    abs(running + pool.amounts_rupees[i] - target),
                    -abs(pool.amounts_rupees[i]),
                    pool.item_ids[i],
                ),
            )
            nxt = running + pool.amounts_rupees[best]
            if chosen and abs(nxt - target) > abs(running - target):
                break
            chosen.append(best)
            running = nxt
            unused.remove(best)
            if abs(running - target) <= epsilon:
                break
        if abs(running - target) <= epsilon and chosen:
            predictions[credit.id] = tuple(pool.item_ids[i] for i in sorted(chosen))
            dispositions[credit.id] = Disposition.CLEARED
        elif len(pool.item_ids) > cfg.search.max_pool:
            predictions[credit.id] = ()
            dispositions[credit.id] = Disposition.BUDGET_EXCEEDED
        else:
            predictions[credit.id] = ()
            dispositions[credit.id] = Disposition.FLAGGED
    return ArmResult(
        arm="a2",
        predictions=predictions,
        dispositions=dispositions,
        has_exception_path=True,
        has_budget_path=True,
    )
