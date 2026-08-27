"""F39 leakage sweep. Detector on synthetic data, not incidence (spec §2.3)."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Sequence

from pydantic import BaseModel, ConfigDict, Field

from residual_zero.models import BankCredit, Kind, LedgerItem

_STRICT = ConfigDict(frozen=True, extra="forbid")


class LeakEvidence(BaseModel):
    model_config = _STRICT

    kind: str
    subject_id: str
    paise: int
    note: str


class LeakageReport(BaseModel):
    model_config = _STRICT

    evidence: tuple[LeakEvidence, ...]
    rupees_identified_paise: int
    by_kind_paise: dict[str, int]


def sweep(
    items: Sequence[LedgerItem],
    credits: Sequence[BankCredit],
    *,
    as_of: date,
    reserve_lag_days: int,
    representment_window_days: int = 45,
) -> LeakageReport:
    """Deterministic detectors. Amounts stay integer paise."""
    by_parent: dict[str, list[LedgerItem]] = defaultdict(list)
    by_kind: dict[Kind, list[LedgerItem]] = defaultdict(list)
    for item in items:
        by_kind[item.kind].append(item)
        if item.parent_id:
            by_parent[item.parent_id].append(item)
    evidence: list[LeakEvidence] = []

    releases_by_parent = {it.parent_id for it in by_kind.get(Kind.RESERVE_RELEASE, ()) if it.parent_id}
    for hold in by_kind.get(Kind.RESERVE_HOLD, ()):
        due = date.fromisoformat(hold.occurred_at.date().isoformat()) + timedelta(days=reserve_lag_days)
        if as_of > due and hold.id not in releases_by_parent:
            amt = -hold.amount_paise if hold.amount_paise < 0 else hold.amount_paise
            evidence.append(
                LeakEvidence(
                    kind="overdue_reserve",
                    subject_id=hold.id,
                    paise=amt,
                    note=f"scheduled {due.isoformat()}",
                )
            )

    representments = {it.parent_id for it in by_kind.get(Kind.REPRESENTMENT, ()) if it.parent_id}
    for cb in by_kind.get(Kind.CHARGEBACK, ()):
        raised = date.fromisoformat(cb.occurred_at.date().isoformat())
        deadline = raised + timedelta(days=representment_window_days)
        if cb.id not in representments and as_of <= deadline:
            amt = -cb.amount_paise if cb.amount_paise < 0 else cb.amount_paise
            evidence.append(
                LeakEvidence(
                    kind="chargeback_unrepresented",
                    subject_id=cb.id,
                    paise=amt,
                    note=f"deadline {deadline.isoformat()}",
                )
            )

    refunds_by_parent: dict[str, list[LedgerItem]] = defaultdict(list)
    for ref in by_kind.get(Kind.REFUND, ()):
        if ref.parent_id:
            refunds_by_parent[ref.parent_id].append(ref)
    for parent, group in refunds_by_parent.items():
        if len(group) > 1:
            extra = sum(abs(it.amount_paise) for it in group[1:])
            evidence.append(
                LeakEvidence(
                    kind="duplicate_refund",
                    subject_id=parent,
                    paise=extra,
                    note=f"count={len(group)}",
                )
            )

    by_key: dict[tuple[str, int, date], list[BankCredit]] = defaultdict(list)
    for credit in credits:
        by_key[(credit.account_id, credit.amount_paise, credit.value_date)].append(credit)
    for key, group in by_key.items():
        if len(group) > 1:
            extra = sum(c.amount_paise for c in group[1:])
            evidence.append(
                LeakEvidence(
                    kind="duplicate_credit",
                    subject_id=group[0].id,
                    paise=extra,
                    note=f"count={len(group)}",
                )
            )

    voided_parents = {
        it.id for it in items if it.kind in {Kind.REFUND, Kind.CHARGEBACK, Kind.ADJUSTMENT}
    }
    for fee in list(by_kind.get(Kind.FEE, ())) + list(by_kind.get(Kind.TAX_GST, ())):
        if fee.parent_id and fee.parent_id in voided_parents:
            evidence.append(
                LeakEvidence(
                    kind="fee_on_voided",
                    subject_id=fee.id,
                    paise=abs(fee.amount_paise),
                    note=fee.kind.value,
                )
            )

    by_kind_paise: dict[str, int] = defaultdict(int)
    total = 0
    for row in evidence:
        by_kind_paise[row.kind] += row.paise
        total += row.paise
    return LeakageReport(
        evidence=tuple(evidence),
        rupees_identified_paise=total,
        by_kind_paise=dict(by_kind_paise),
    )
