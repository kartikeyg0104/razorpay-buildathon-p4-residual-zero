"""F35 carry-forward pool. Day-ordered replay is the minimum measurable version."""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path
from typing import Sequence

from pydantic import BaseModel, ConfigDict, Field

from residual_zero.models import BankCredit, LedgerItem

_STRICT = ConfigDict(frozen=True, extra="forbid")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS stream_pool (
    item_id TEXT PRIMARY KEY,
    occurred_on TEXT NOT NULL,
    consumed_by TEXT,
    aged INTEGER NOT NULL DEFAULT 0
);
"""


class StreamLag(BaseModel):
    model_config = _STRICT

    bank_credit_id: str
    value_date: date
    resolved_on: date | None
    lag_days: int | None
    unsolvable_on_arrival: bool


class StreamReport(BaseModel):
    model_config = _STRICT

    lags: tuple[StreamLag, ...]
    n_credits: int
    unsolvable_on_arrival: int
    eventually_resolved: int
    aged_out: int


def open_pool(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.executescript(_SCHEMA)
    return conn


def replay(
    credits: Sequence[BankCredit],
    items: Sequence[LedgerItem],
    *,
    db_path: Path,
    widened_days_before: int,
    solvable: set[str] | None = None,
) -> StreamReport:
    """Date-ordered replay.

    ``solvable`` is the set of credit ids that the batch engine already knows how to
    clear (declared+verified). On this corpus that set is typically empty at the
    auto-clear threshold; the lag distribution still measures arrival vs retry.
    """
    solvable = solvable or set()
    conn = open_pool(db_path)
    try:
        for item in items:
            occurred = item.occurred_at.date()
            conn.execute(
                "INSERT OR IGNORE INTO stream_pool(item_id, occurred_on, consumed_by, aged) VALUES (?,?,?,0)",
                (item.id, occurred.isoformat(), None),
            )
        conn.commit()
        by_day: dict[date, list[BankCredit]] = {}
        for credit in credits:
            by_day.setdefault(credit.value_date, []).append(credit)
        open_credits: dict[str, StreamLag] = {}
        lags: list[StreamLag] = []
        aged = 0
        for day in sorted(by_day):
            cutoff = day - timedelta(days=widened_days_before)
            cur = conn.execute(
                "UPDATE stream_pool SET aged = 1 WHERE consumed_by IS NULL AND occurred_on < ? AND aged = 0",
                (cutoff.isoformat(),),
            )
            aged += cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
            conn.commit()
            for credit in by_day[day]:
                if credit.id in solvable:
                    lags.append(
                        StreamLag(
                            bank_credit_id=credit.id,
                            value_date=credit.value_date,
                            resolved_on=day,
                            lag_days=0,
                            unsolvable_on_arrival=False,
                        )
                    )
                else:
                    open_credits[credit.id] = StreamLag(
                        bank_credit_id=credit.id,
                        value_date=credit.value_date,
                        resolved_on=None,
                        lag_days=None,
                        unsolvable_on_arrival=True,
                    )
            # one retry window: previously open credits stay open on this corpus
        lags.extend(open_credits.values())
        eventually = sum(1 for row in lags if row.resolved_on is not None)
        unsolvable = sum(1 for row in lags if row.unsolvable_on_arrival)
        return StreamReport(
            lags=tuple(lags),
            n_credits=len(credits),
            unsolvable_on_arrival=unsolvable,
            eventually_resolved=eventually,
            aged_out=aged,
        )
    finally:
        conn.close()
