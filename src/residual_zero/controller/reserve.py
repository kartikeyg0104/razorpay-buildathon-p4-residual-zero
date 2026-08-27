"""F41 reserve sub-ledger. Arithmetic over known dates, not a forecast (spec §1.3)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Sequence

from pydantic import BaseModel, ConfigDict, Field

from residual_zero.models import Kind, LedgerItem

_STRICT = ConfigDict(frozen=True, extra="forbid")


class ReserveHold(BaseModel):
    model_config = _STRICT

    item_id: str
    held_paise: int
    held_on: date
    scheduled_release: date
    released_paise: int
    overdue: bool


class ReserveReport(BaseModel):
    model_config = _STRICT

    holds: tuple[ReserveHold, ...]
    outstanding_paise: int
    overdue_count: int
    identity_holds: bool


def subledger(
    items: Sequence[LedgerItem],
    *,
    as_of: date,
    lag_days: int,
) -> ReserveReport:
    """outstanding = -(sum of RESERVE_HOLD + RESERVE_RELEASE amounts)."""
    holds_items = [it for it in items if it.kind is Kind.RESERVE_HOLD]
    releases = [it for it in items if it.kind is Kind.RESERVE_RELEASE]
    released_by_parent: dict[str, int] = {}
    for rel in releases:
        key = rel.parent_id or rel.id
        released_by_parent[key] = released_by_parent.get(key, 0) + rel.amount_paise

    rows: list[ReserveHold] = []
    overdue = 0
    for hold in holds_items:
        held_on = date.fromisoformat(hold.occurred_at.date().isoformat())
        scheduled = held_on + timedelta(days=lag_days)
        released = released_by_parent.get(hold.id, 0)
        held_amt = -hold.amount_paise if hold.amount_paise < 0 else hold.amount_paise
        is_overdue = as_of > scheduled and released == 0
        if is_overdue:
            overdue += 1
        rows.append(
            ReserveHold(
                item_id=hold.id,
                held_paise=held_amt,
                held_on=held_on,
                scheduled_release=scheduled,
                released_paise=released,
                overdue=is_overdue,
            )
        )
    held_abs = 0
    for it in holds_items:
        held_abs += -it.amount_paise if it.amount_paise < 0 else it.amount_paise
    released_abs = 0
    for it in releases:
        released_abs += it.amount_paise if it.amount_paise > 0 else -it.amount_paise
    outstanding = held_abs - released_abs
    signed = sum(it.amount_paise for it in items if it.kind in {Kind.RESERVE_HOLD, Kind.RESERVE_RELEASE})
    identity = outstanding == -signed
    return ReserveReport(
        holds=tuple(rows),
        outstanding_paise=outstanding,
        overdue_count=overdue,
        identity_holds=identity,
    )
