"""F31: CP-SAT over the DP's enumerated solution set (NN-18).

Variable domain IS the enumerated index-tuples. Constraints only forbid members of
that set. A cap-hit must not declare UNIQUE or structurally infeasible.
"""

from __future__ import annotations

from typing import Mapping, Sequence

from pydantic import BaseModel, ConfigDict, Field

from residual_zero.config import FeeSchedule, TaxRates
from residual_zero.models import Kind, LedgerItem, Uniqueness
from residual_zero.money import apply_bps

_STRICT = ConfigDict(frozen=True, extra="forbid")

CONSTRAINT_ORDER: tuple[str, ...] = (
    "order_at_most_one_payment",
    "refund_needs_parent",
    "fee_needs_instrument_payment",
    "gst_equals_fee_rate",
    "reserve_equals_gross",
    "representment_needs_chargeback",
)


class Disambiguation(BaseModel):
    model_config = _STRICT

    uniqueness: Uniqueness
    member_ids: tuple[str, ...]
    constraint_named: str | None
    structurally_infeasible: bool
    n_enumerated: int = Field(ge=0)
    n_feasible: int = Field(ge=0)
    enumeration_capped: bool
    feasible_indices: tuple[int, ...] = ()


def _members(pool_ids: Sequence[str], indices: Sequence[int], ledger: Mapping[str, LedgerItem]) -> list[LedgerItem]:
    out: list[LedgerItem] = []
    for i in indices:
        item_id = pool_ids[i]
        item = ledger.get(item_id)
        if item is not None:
            out.append(item)
    return out


def _order_at_most_one_payment(items: Sequence[LedgerItem]) -> bool:
    seen: set[str] = set()
    for item in items:
        if item.kind != Kind.PAYMENT or not item.order_id:
            continue
        if item.order_id in seen:
            return False
        seen.add(item.order_id)
    return True


def _refund_needs_parent(items: Sequence[LedgerItem], member_ids: set[str], cleared_parents: frozenset[str]) -> bool:
    for item in items:
        if item.kind != Kind.REFUND:
            continue
        if item.parent_id is None:
            return False
        if item.parent_id in member_ids or item.parent_id in cleared_parents:
            continue
        return False
    return True


def _fee_needs_instrument_payment(items: Sequence[LedgerItem]) -> bool:
    payments = {it.instrument for it in items if it.kind == Kind.PAYMENT}
    for item in items:
        if item.kind != Kind.FEE:
            continue
        if item.instrument is None:
            if not payments:
                return False
            continue
        if item.instrument not in payments:
            return False
    return True


def _gst_equals_fee_rate(items: Sequence[LedgerItem], rates: TaxRates) -> bool:
    fees = sum(it.amount_paise for it in items if it.kind == Kind.FEE)
    gst = sum(it.amount_paise for it in items if it.kind == Kind.TAX_GST)
    if fees == 0 and gst == 0:
        return True
    expected = -apply_bps(abs(fees), rates.gst_on_fee.bps)
    return gst == expected


def _reserve_equals_gross(items: Sequence[LedgerItem], reserve_bps: int) -> bool:
    holds = sum(it.amount_paise for it in items if it.kind == Kind.RESERVE_HOLD)
    if reserve_bps == 0 and holds == 0:
        return True
    gross = sum(it.amount_paise for it in items if it.kind == Kind.PAYMENT)
    expected = -apply_bps(gross, reserve_bps)
    return holds == expected


def _representment_needs_chargeback(items: Sequence[LedgerItem], member_ids: set[str]) -> bool:
    for item in items:
        if item.kind != Kind.REPRESENTMENT:
            continue
        if item.parent_id is None or item.parent_id not in member_ids:
            return False
        parent = next((p for p in items if p.id == item.parent_id), None)
        if parent is None or parent.kind != Kind.CHARGEBACK:
            return False
    return True


def solution_violations(
    items: Sequence[LedgerItem],
    rates: TaxRates,
    reserve_bps: int,
    cleared_parents: frozenset[str],
) -> tuple[str, ...]:
    member_ids = {it.id for it in items}
    checks: list[tuple[str, bool]] = [
        ("order_at_most_one_payment", _order_at_most_one_payment(items)),
        ("refund_needs_parent", _refund_needs_parent(items, member_ids, cleared_parents)),
        ("fee_needs_instrument_payment", _fee_needs_instrument_payment(items)),
        ("gst_equals_fee_rate", _gst_equals_fee_rate(items, rates)),
        ("reserve_equals_gross", _reserve_equals_gross(items, reserve_bps)),
        ("representment_needs_chargeback", _representment_needs_chargeback(items, member_ids)),
    ]
    return tuple(name for name, ok in checks if not ok)


def _first_eliminator(feasible_masks: list[set[str]], survivor: int) -> str | None:
    """Name the first constraint that leaves only ``survivor`` standing, else None."""
    others = [i for i in range(len(feasible_masks)) if i != survivor]
    if not others:
        return None
    remaining = set(range(len(feasible_masks)))
    for name in CONSTRAINT_ORDER:
        remaining = {i for i in remaining if name not in feasible_masks[i]}
        if remaining == {survivor}:
            return name
    return None


def disambiguate(
    pool_ids: Sequence[str],
    enumerated: tuple[tuple[int, ...], ...],
    ledger: Mapping[str, LedgerItem],
    rates: TaxRates,
    fees: FeeSchedule,
    reserve_bps: int,
    cleared_parent_ids: frozenset[str],
    *,
    enumeration_capped: bool,
) -> Disambiguation:
    """Filter enumerated solutions. CP-SAT domain is exactly ``enumerated`` (NN-18)."""
    del fees  # rates/fees reserved for GST/reserve; fees.yaml unused in predicates
    n = len(enumerated)
    if n == 0 or enumeration_capped:
        return Disambiguation(
            uniqueness=Uniqueness.AMBIGUOUS,
            member_ids=(),
            constraint_named=None,
            structurally_infeasible=False,
            n_enumerated=n,
            n_feasible=n,
            enumeration_capped=enumeration_capped,
        )
    violation_sets: list[set[str]] = []
    feasible: list[int] = []
    for i, indices in enumerate(enumerated):
        items = _members(pool_ids, indices, ledger)
        viol = solution_violations(items, rates, reserve_bps, cleared_parent_ids)
        violation_sets.append(set(viol))
        if not viol:
            feasible.append(i)

    n_feas = len(feasible)
    sat_support: list[int] = []
    try:
        from ortools.sat.python import cp_model

        model = cp_model.CpModel()
        xs = [model.NewBoolVar(f"sol_{i}") for i in range(n)]
        for i in range(n):
            if violation_sets[i]:
                model.Add(xs[i] == 0)
        model.Add(sum(xs) <= 1)
        solver = cp_model.CpSolver()
        status = solver.Solve(model)
        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            sat_support = [i for i in range(n) if solver.Value(xs[i]) == 1]
        if not set(sat_support).issubset(set(range(n))):
            raise RuntimeError("CP-SAT produced an index outside the DP enumerated set (NN-18)")
        if sat_support and sat_support[0] not in feasible:
            raise RuntimeError("CP-SAT picked a DP solution that failed a structural predicate")
    except ImportError:
        sat_support = feasible[:1]

    if not set(feasible).issubset(set(range(n))):
        raise RuntimeError("feasible index outside enumerated set")

    n_feas = len(feasible)
    if n_feas == 0:
        return Disambiguation(
            uniqueness=Uniqueness.AMBIGUOUS,
            member_ids=(),
            constraint_named=None,
            structurally_infeasible=True,
            n_enumerated=n,
            n_feasible=0,
            enumeration_capped=False,
            feasible_indices=(),
        )
    if n_feas == 1:
        idx = feasible[0]
        member_ids = tuple(sorted(pool_ids[i] for i in enumerated[idx]))
        named = _first_eliminator(violation_sets, idx)
        return Disambiguation(
            uniqueness=Uniqueness.UNIQUE,
            member_ids=member_ids,
            constraint_named=named,
            structurally_infeasible=False,
            n_enumerated=n,
            n_feasible=1,
            enumeration_capped=False,
            feasible_indices=(idx,),
        )
    return Disambiguation(
        uniqueness=Uniqueness.AMBIGUOUS,
        member_ids=(),
        constraint_named=None,
        structurally_infeasible=False,
        n_enumerated=n,
        n_feasible=n_feas,
        enumeration_capped=False,
        feasible_indices=tuple(feasible),
    )
