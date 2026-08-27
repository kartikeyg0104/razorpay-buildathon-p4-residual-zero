"""A0: exact single-item amount match inside the base window. Cannot express N:M."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from functools import lru_cache
from typing import Sequence

from residual_zero.config import SolverConfig
from residual_zero.models import BankCredit, Disposition, LedgerItem
from residual_zero.tz import to_ist_date_display

from . import ArmResult


@lru_cache(maxsize=None)
def item_ist_date(item: LedgerItem) -> date:
    """IST calendar date of an item. Cached: A0/A1 used to recompute this per pair."""
    return date.fromisoformat(to_ist_date_display(item.occurred_at))


def run_a0(
    items: Sequence[LedgerItem], credits: Sequence[BankCredit], cfg: SolverConfig,
) -> ArmResult:
    """Predict the single in-window item whose amount equals the credit; otherwise nothing."""
    days = cfg.windows.base_days_before
    by_key: dict[tuple[str, str, int], list[tuple[LedgerItem, date]]] = defaultdict(list)
    for item in items:
        by_key[(item.account_id, item.currency, item.amount_paise)].append(
            (item, item_ist_date(item))
        )
    predictions: dict[str, tuple[str, ...]] = {}
    dispositions: dict[str, Disposition] = {}
    for credit in credits:
        start = credit.value_date - timedelta(days=days)
        end = credit.value_date - timedelta(days=1)
        matches = [
            item
            for item, occurred in by_key.get(
                (credit.account_id, credit.currency, credit.amount_paise), ()
            )
            if start <= occurred <= end
        ]
        if len(matches) == 1:
            predictions[credit.id] = (matches[0].id,)
            dispositions[credit.id] = Disposition.CLEARED
        else:
            predictions[credit.id] = ()
            dispositions[credit.id] = Disposition.FLAGGED
    return ArmResult(
        arm="a0",
        predictions=predictions,
        dispositions=dispositions,
        has_exception_path=False,
        has_budget_path=False,
    )


def _in_window(item: LedgerItem, credit: BankCredit, days_before: int) -> bool:
    occurred = item_ist_date(item)
    start = credit.value_date - timedelta(days=days_before)
    end = credit.value_date - timedelta(days=1)
    return start <= occurred <= end
