"""Asymmetric date windows and deterministic candidate pools (spec §5.5)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Sequence

from pydantic import BaseModel, ConfigDict, Field

from residual_zero.config import SolverConfig
from residual_zero.models import BankCredit, Kind, LedgerItem, PoolScope
from residual_zero.money import to_rupee_units
from residual_zero.tz import to_ist_date_display

_STRICT = ConfigDict(frozen=True, extra="forbid")

WIDENED_KINDS: frozenset[Kind] = frozenset(
    {
        Kind.REFUND,
        Kind.CHARGEBACK,
        Kind.REPRESENTMENT,
        Kind.ADJUSTMENT,
        Kind.RESERVE_RELEASE,
    }
)


class CandidatePool(BaseModel):
    model_config = _STRICT

    bank_credit_id: str
    item_ids: tuple[str, ...]
    amounts_paise: tuple[int, ...]
    amounts_rupees: tuple[int, ...]
    scope: PoolScope
    sub_window: tuple[date, date] | None = None
    gross_paise: int
    kinds: tuple[Kind, ...] = ()
    occurred_on: tuple[date, ...] = ()
    value_date: date
    account_id: str = ""
    currency: str = ""


def _item_date(item: LedgerItem) -> date:
    """IST calendar date of an item. Windows are defined against the bank's value_date."""
    return date.fromisoformat(to_ist_date_display(item.occurred_at))


def _widened_from_cfg(cfg: SolverConfig) -> frozenset[Kind]:
    return frozenset(Kind(name) for name in cfg.windows.widened_kinds)


def build_pool(
    credit: BankCredit,
    items: Sequence[LedgerItem],
    cfg: SolverConfig,
) -> CandidatePool:
    """Filter by account and currency, apply the asymmetric date windows, sort deterministically.

    Returns the FULL pool even when it exceeds MAX_POOL — the cap is the solver's decision
    (NN-11).
    """
    widened = _widened_from_cfg(cfg)
    base_start = credit.value_date - timedelta(days=cfg.windows.base_days_before)
    wide_start = credit.value_date - timedelta(days=cfg.windows.widened_days_before)
    end = credit.value_date - timedelta(days=1)
    selected: list[LedgerItem] = []
    for item in items:
        if item.account_id != credit.account_id or item.currency != credit.currency:
            continue
        occurred = _item_date(item)
        if item.kind in widened:
            if not (wide_start <= occurred <= end):
                continue
        else:
            if not (base_start <= occurred <= end):
                continue
        selected.append(item)
    selected.sort(key=lambda it: (it.occurred_at, it.id))
    amounts_paise = tuple(it.amount_paise for it in selected)
    return CandidatePool(
        bank_credit_id=credit.id,
        item_ids=tuple(it.id for it in selected),
        amounts_paise=amounts_paise,
        amounts_rupees=tuple(to_rupee_units(a) for a in amounts_paise),
        scope=PoolScope.FULL,
        sub_window=None,
        gross_paise=sum(a for a in amounts_paise if a > 0),
        kinds=tuple(it.kind for it in selected),
        occurred_on=tuple(_item_date(it) for it in selected),
        value_date=credit.value_date,
        account_id=credit.account_id,
        currency=credit.currency,
    )


def split_pool(
    pool: CandidatePool,
    credit: BankCredit,
    cfg: SolverConfig,
) -> tuple[CandidatePool, ...]:
    """Suffix-growing day sub-windows, each retaining every widened-kind item.

    Deterministic, bounded by ``cfg.sub_window_split.max_attempts``. Every result has
    scope REDUCED.
    """
    widened = _widened_from_cfg(cfg)
    n = len(pool.item_ids)
    attempts = cfg.sub_window_split.max_attempts
    out: list[CandidatePool] = []
    k = 1
    while k <= attempts:
        start = credit.value_date - timedelta(days=k)
        end = credit.value_date - timedelta(days=1)
        keep: list[int] = []
        i = 0
        while i < n:
            kind = pool.kinds[i]
            occurred = pool.occurred_on[i]
            if kind in widened:
                keep.append(i)
            elif start <= occurred <= end:
                keep.append(i)
            i += 1
        sub = CandidatePool(
            bank_credit_id=pool.bank_credit_id,
            item_ids=tuple(pool.item_ids[i] for i in keep),
            amounts_paise=tuple(pool.amounts_paise[i] for i in keep),
            amounts_rupees=tuple(pool.amounts_rupees[i] for i in keep),
            scope=PoolScope.REDUCED,
            sub_window=(start, end),
            gross_paise=sum(pool.amounts_paise[i] for i in keep if pool.amounts_paise[i] > 0),
            kinds=tuple(pool.kinds[i] for i in keep),
            occurred_on=tuple(pool.occurred_on[i] for i in keep),
            value_date=pool.value_date,
            account_id=pool.account_id,
            currency=pool.currency,
        )
        out.append(sub)
        k += 1
    return tuple(out)


def take_indices(pool: CandidatePool, indices: Sequence[int]) -> CandidatePool:
    """Keep the listed indices, same order. Scope is unchanged."""
    keep = tuple(int(i) for i in indices)
    return CandidatePool(
        bank_credit_id=pool.bank_credit_id,
        item_ids=tuple(pool.item_ids[i] for i in keep),
        amounts_paise=tuple(pool.amounts_paise[i] for i in keep),
        amounts_rupees=tuple(pool.amounts_rupees[i] for i in keep),
        scope=pool.scope,
        sub_window=pool.sub_window,
        gross_paise=sum(pool.amounts_paise[i] for i in keep if pool.amounts_paise[i] > 0),
        kinds=tuple(pool.kinds[i] for i in keep),
        occurred_on=tuple(pool.occurred_on[i] for i in keep),
        value_date=pool.value_date,
        account_id=pool.account_id,
        currency=pool.currency,
    )
