"""F42 dispute lifecycle on class-19 chargebacks. No new corruption class."""

from __future__ import annotations

from datetime import date, timedelta
from enum import Enum
from typing import Sequence

from pydantic import BaseModel, ConfigDict, Field

from residual_zero.models import Kind, LedgerItem

_STRICT = ConfigDict(frozen=True, extra="forbid")


class DisputeState(str, Enum):
    RAISED = "RAISED"
    DEBITED = "DEBITED"
    REPRESENTED = "REPRESENTED"
    WON = "WON"
    LOST = "LOST"


class Dispute(BaseModel):
    model_config = _STRICT

    chargeback_id: str
    state: DisputeState
    deadline: date
    open_inside_7_days: bool
    reconstructed: bool


class DisputeReport(BaseModel):
    model_config = _STRICT

    disputes: tuple[Dispute, ...]
    reconstructed_end_to_end: int
    n_disputes: int
    open_inside_7_days: int


def track(
    items: Sequence[LedgerItem],
    *,
    as_of: date,
    deadline_days: int = 45,
) -> DisputeReport:
    representments = [it for it in items if it.kind is Kind.REPRESENTMENT]
    by_parent = {it.parent_id: it for it in representments if it.parent_id}
    adjustments = [it for it in items if it.kind is Kind.ADJUSTMENT]
    adj_parents = {it.parent_id for it in adjustments if it.parent_id}

    rows: list[Dispute] = []
    for cb in items:
        if cb.kind is not Kind.CHARGEBACK:
            continue
        raised = date.fromisoformat(cb.occurred_at.date().isoformat())
        deadline = raised + timedelta(days=deadline_days)
        state = DisputeState.DEBITED
        reconstructed = False
        if cb.id in by_parent:
            state = DisputeState.REPRESENTED
            reconstructed = True
            if cb.id in adj_parents:
                state = DisputeState.WON
        open_soon = state in {DisputeState.RAISED, DisputeState.DEBITED} and timedelta(0) <= (deadline - as_of) <= timedelta(days=7)
        rows.append(
            Dispute(
                chargeback_id=cb.id,
                state=state,
                deadline=deadline,
                open_inside_7_days=open_soon,
                reconstructed=reconstructed,
            )
        )
    n = len(rows)
    recon = sum(1 for r in rows if r.reconstructed)
    return DisputeReport(
        disputes=tuple(rows),
        reconstructed_end_to_end=recon,
        n_disputes=n,
        open_inside_7_days=sum(1 for r in rows if r.open_inside_7_days),
    )
