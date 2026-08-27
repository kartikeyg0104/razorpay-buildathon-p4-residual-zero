"""F37 deterministic exception clustering. Cause labels never enter this module (NN-6 style)."""

from __future__ import annotations

from datetime import date
from typing import Sequence

from pydantic import BaseModel, ConfigDict, Field

from residual_zero.models import ExceptionClass, LedgerItem

_STRICT = ConfigDict(frozen=True, extra="forbid")

_BPS_EDGES: tuple[tuple[str, int], ...] = (
    ("0", 0),
    ("1-10", 10),
    ("11-50", 50),
    ("51-100", 100),
    ("101-500", 500),
)


def _bps_bucket(abs_delta: int, gross: int) -> str:
    if gross <= 0:
        return "none"
    bps = (abs_delta * 10_000) // gross
    if bps <= 0:
        return "0"
    for label, edge in _BPS_EDGES[1:]:
        if bps <= edge:
            return label
    return "501+"


def _iso_week(day: date) -> str:
    iso = day.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


class ExceptionRow(BaseModel):
    model_config = _STRICT

    bank_credit_id: str
    exception_class: ExceptionClass
    value_date: date
    nearest_delta_paise: int | None
    pool_gross_paise: int
    instrument: str
    missing_kind: str


class Cluster(BaseModel):
    model_config = _STRICT

    signature: str
    credit_ids: tuple[str, ...]
    size: int = Field(ge=1)


def row_signature(row: ExceptionRow) -> str:
    if row.nearest_delta_paise is None:
        sign = "none"
        bucket = "none"
    elif row.nearest_delta_paise < 0:
        sign = "neg"
        bucket = _bps_bucket(-row.nearest_delta_paise, row.pool_gross_paise)
    elif row.nearest_delta_paise > 0:
        sign = "pos"
        bucket = _bps_bucket(row.nearest_delta_paise, row.pool_gross_paise)
    else:
        sign = "zero"
        bucket = "0"
    return "|".join(
        (
            row.exception_class.value,
            sign,
            bucket,
            row.instrument,
            row.missing_kind,
            _iso_week(row.value_date),
        )
    )


def cluster_rows(rows: Sequence[ExceptionRow]) -> tuple[Cluster, ...]:
    grouped: dict[str, list[str]] = {}
    for row in rows:
        grouped.setdefault(row_signature(row), []).append(row.bank_credit_id)
    clusters = []
    for sig in sorted(grouped):
        ids = tuple(sorted(grouped[sig]))
        clusters.append(Cluster(signature=sig, credit_ids=ids, size=len(ids)))
    return tuple(clusters)


def instrument_of_pool(items: Sequence[LedgerItem]) -> str:
    pays = [it for it in items if it.kind.value == "PAYMENT"]
    if not pays:
        return "none"
    pays.sort(key=lambda it: it.id)
    inst = pays[0].instrument
    return inst.value if inst is not None else "none"


def compression_ratio(n_exceptions: int, n_clusters: int) -> tuple[int, int]:
    """Unreduced pair. Zero clusters is (n, 0) and must not be published as a float."""
    return n_exceptions, n_clusters
