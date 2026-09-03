"""Regime A: re-derive a declared composition from the rate table, never from declared rate amounts."""

from __future__ import annotations

from collections import defaultdict
from typing import Mapping, NamedTuple, Sequence

from pydantic import BaseModel, ConfigDict

from residual_zero.config import FeeSchedule, TaxRates
from residual_zero.models import BankCredit, Instrument, Kind, LedgerItem
from residual_zero.money import apply_bps

_STRICT = ConfigDict(frozen=True, extra="forbid")

RATE_DERIVED = frozenset({Kind.FEE, Kind.TAX_GST, Kind.TAX_WITHHOLDING, Kind.RESERVE_HOLD})

LEDGER_OPS = "LEDGER"
SETTLEMENT_OPS = "SETTLEMENT_OPS"


class DeclaredLine(NamedTuple):
    item_id: str
    kind: Kind
    amount_paise: int
    instrument: Instrument | None


class FastPathResult(BaseModel):
    model_config = _STRICT

    ok: bool
    member_ids: tuple[str, ...]
    computed_total_paise: int
    residual_paise: int
    line_deltas: tuple[tuple[str, int], ...]
    missing_item_ids: tuple[str, ...]
    ops_source: str = LEDGER_OPS


def _rate_total(
    payments_by_instrument: Mapping[Instrument, int],
    rates: TaxRates,
    fees: FeeSchedule,
    reserve_bps: int,
) -> tuple[dict[Instrument, int], dict[Instrument, int], int, int, int]:
    recomputed_fee: dict[Instrument, int] = {}
    recomputed_gst: dict[Instrument, int] = {}
    for instrument, gross in sorted(payments_by_instrument.items(), key=lambda kv: kv[0].value):
        fee = -apply_bps(gross, fees.per_instrument_bps[instrument].bps)
        recomputed_fee[instrument] = fee
        recomputed_gst[instrument] = apply_bps(fee, rates.gst_on_fee.bps) if fee != 0 else 0

    selected_gross = sum(payments_by_instrument.values())
    recomputed_withholding = 0
    if selected_gross > 0 and rates.withholding.bps > 0:
        if rates.withholding.base == "GROSS_PAYMENTS":
            recomputed_withholding = -apply_bps(selected_gross, rates.withholding.bps)
        else:
            fee_total = sum(-v for v in recomputed_fee.values())
            recomputed_withholding = -apply_bps(fee_total, rates.withholding.bps)
    recomputed_reserve = 0
    if selected_gross > 0 and reserve_bps > 0:
        recomputed_reserve = -apply_bps(selected_gross, reserve_bps)
    rate_total = (
        sum(recomputed_fee.values())
        + sum(recomputed_gst.values())
        + recomputed_withholding
        + recomputed_reserve
    )
    return recomputed_fee, recomputed_gst, recomputed_withholding, recomputed_reserve, rate_total


def _verify_one(
    credit: BankCredit,
    declared: Sequence[DeclaredLine],
    ledger: Mapping[str, LedgerItem],
    rates: TaxRates,
    fees: FeeSchedule,
    reserve_bps: int,
    *,
    use_declared_ops: bool,
    allow_missing_rate_ids: bool,
) -> FastPathResult:
    missing_ops: list[str] = []
    missing_rate: list[str] = []
    operational_total = 0
    payments_by_instrument: dict[Instrument, int] = defaultdict(int)
    member_ids: list[str] = []
    declared_rate_lines: list[DeclaredLine] = []

    for line in declared:
        member_ids.append(line.item_id)
        item = ledger.get(line.item_id)
        if item is None:
            if line.kind in RATE_DERIVED:
                missing_rate.append(line.item_id)
            else:
                missing_ops.append(line.item_id)
            continue
        if line.kind in RATE_DERIVED:
            declared_rate_lines.append(line)
            continue
        amount = line.amount_paise if use_declared_ops else item.amount_paise
        operational_total += amount
        instrument = item.instrument if item.kind == Kind.PAYMENT else None
        if use_declared_ops and line.kind == Kind.PAYMENT:
            instrument = line.instrument if line.instrument is not None else item.instrument
        if instrument is not None and (
            item.kind == Kind.PAYMENT or (use_declared_ops and line.kind == Kind.PAYMENT)
        ):
            payments_by_instrument[instrument] += amount

    recomputed_fee, recomputed_gst, withholding, reserve, rate_total = _rate_total(
        payments_by_instrument, rates, fees, reserve_bps,
    )
    computed_total = operational_total + rate_total

    deltas: list[tuple[str, int]] = []
    for line in declared_rate_lines:
        if line.kind == Kind.FEE and line.instrument is not None:
            recomputed = recomputed_fee.get(line.instrument, 0)
        elif line.kind == Kind.TAX_GST and line.instrument is not None:
            recomputed = recomputed_gst.get(line.instrument, 0)
        elif line.kind == Kind.TAX_WITHHOLDING:
            recomputed = withholding
        elif line.kind == Kind.RESERVE_HOLD:
            recomputed = reserve
        else:
            recomputed = 0
        delta = line.amount_paise - recomputed
        if delta != 0:
            deltas.append((line.item_id, delta))

    residual = credit.amount_paise - computed_total
    missing_t = tuple(missing_ops + missing_rate)
    blocking_missing = tuple(missing_ops) if allow_missing_rate_ids else missing_t
    ok = residual == 0 and not blocking_missing and not deltas
    return FastPathResult(
        ok=ok,
        member_ids=tuple(member_ids),
        computed_total_paise=computed_total,
        residual_paise=residual,
        line_deltas=tuple(deltas),
        missing_item_ids=missing_t,
        ops_source=SETTLEMENT_OPS if use_declared_ops else LEDGER_OPS,
    )


def verify_declared(
    credit: BankCredit,
    declared: Sequence[DeclaredLine],
    ledger: Mapping[str, LedgerItem],
    rates: TaxRates,
    fees: FeeSchedule,
    reserve_bps: int = 0,
    *,
    allow_declared_ops: bool = True,
    allow_missing_rate_ids: bool = True,
) -> FastPathResult:
    """Regime A. Re-derive every rate-derived line from the instrument and the rate table.

    Operational amounts are taken from the ledger first. If that residual is nonzero and
    ``allow_declared_ops`` is true, retry using settlement-declared operational amounts
    (the report that named the members). Rate lines are never copied from the declaration;
    they are always re-derived. Missing operational ledger ids still fail. Missing
    rate-derived ids are reconstructed from the rate table when ``allow_missing_rate_ids``.

    ``reserve_bps`` is the live rolling-reserve rate. ``fees.reserve_bps`` is the synthetic
    zero in ``config/fees.yaml``; the Phase 1 generator stores the real rate on the merchant
    profile (CP1).
    """
    ledger_path = _verify_one(
        credit, declared, ledger, rates, fees, reserve_bps,
        use_declared_ops=False, allow_missing_rate_ids=allow_missing_rate_ids,
    )
    if ledger_path.ok or not allow_declared_ops:
        return ledger_path
    settle_path = _verify_one(
        credit, declared, ledger, rates, fees, reserve_bps,
        use_declared_ops=True, allow_missing_rate_ids=allow_missing_rate_ids,
    )
    if settle_path.ok:
        return settle_path
    return ledger_path
