"""F38 effective-rate regression. Integer arithmetic only. Alert requires min_sample + band."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from math import isqrt
from typing import Sequence

from pydantic import BaseModel, ConfigDict, Field

from residual_zero.config import FeeSchedule
from residual_zero.models import Instrument, Kind, LedgerItem
from residual_zero.money import apply_bps, round_half_up_div

_STRICT = ConfigDict(frozen=True, extra="forbid")

MIN_SAMPLE = 8


class RatePoint(BaseModel):
    model_config = _STRICT

    instrument: Instrument
    iso_week: str
    n_payments: int = Field(ge=0)
    gross_paise: int
    fee_paise: int  # absolute
    effective_bps: int
    contracted_bps: int
    lo_bps: int
    hi_bps: int
    alert: bool


def _iso_week(day: date) -> str:
    iso = day.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def _band(effective_bps: int, n: int) -> tuple[int, int]:
    # Conservative integer 2-se band: ± max(1, 20000 / isqrt(n)) mill-nothing, in bps.
    half = max(1, round_half_up_div(2 * 10_000, max(1, isqrt(n))))
    return effective_bps - half, effective_bps + half


def triples_from_members(
    members: Sequence[LedgerItem],
    value_date: date,
) -> list[tuple[Instrument, str, int, int]]:
    """(instrument, iso_week, payment_gross, fee_abs) per instrument present."""
    week = _iso_week(value_date)
    gross: dict[Instrument, int] = defaultdict(int)
    fee: dict[Instrument, int] = defaultdict(int)
    for item in members:
        if item.kind == Kind.PAYMENT and item.instrument is not None:
            gross[item.instrument] += item.amount_paise
        elif item.kind == Kind.FEE and item.instrument is not None:
            fee[item.instrument] += -item.amount_paise if item.amount_paise < 0 else item.amount_paise
    out = []
    for inst, g in gross.items():
        out.append((inst, week, g, fee.get(inst, 0)))
    return out


def regress(
    points: Sequence[tuple[Instrument, str, int, int]],
    fees: FeeSchedule,
) -> tuple[RatePoint, ...]:
    """Aggregate (instrument, week) and alert if contracted rate is outside the band."""
    buckets: dict[tuple[Instrument, str], list[tuple[int, int]]] = defaultdict(list)
    for inst, week, gross, fee_abs in points:
        buckets[(inst, week)].append((gross, fee_abs))
    reports: list[RatePoint] = []
    for (inst, week) in sorted(buckets, key=lambda k: (k[0].value, k[1])):
        pairs = buckets[(inst, week)]
        gross = sum(g for g, _f in pairs)
        fee_abs = sum(f for _g, f in pairs)
        n = len(pairs)
        contracted = fees.per_instrument_bps[inst].bps
        effective = 0 if gross <= 0 else round_half_up_div(fee_abs * 10_000, gross)
        lo, hi = _band(effective, n)
        alert = n >= MIN_SAMPLE and (contracted < lo or contracted > hi)
        reports.append(
            RatePoint(
                instrument=inst,
                iso_week=week,
                n_payments=n,
                gross_paise=gross,
                fee_paise=fee_abs,
                effective_bps=effective,
                contracted_bps=contracted,
                lo_bps=lo,
                hi_bps=hi,
                alert=alert,
            )
        )
    return tuple(reports)


def rupee_error_paise(point: RatePoint) -> int:
    """|charged fee - contracted fee on the same gross|."""
    contracted_fee = apply_bps(point.gross_paise, point.contracted_bps)
    return abs(point.fee_paise - contracted_fee)
