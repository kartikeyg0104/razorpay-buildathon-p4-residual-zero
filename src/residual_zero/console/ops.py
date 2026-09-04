"""Ops overlay: Gate A (declared re-derive) is not Gate B (search uniqueness).

Eval A3 still auto-clears only on UNIQUE+FULL+threshold. This module never writes
reconciliation rows. The console uses it to show the close a merchant can actually run.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Mapping, NamedTuple, Sequence

from residual_zero.candidates import build_pool
from residual_zero.config import FeeSchedule, SolverConfig, TaxRates
from residual_zero.models import BankCredit, LedgerItem
from residual_zero.money import to_rupee_units
from residual_zero.solver.alt_diff import AlternateDiff, diff_sets
from residual_zero.solver.fastpath import DeclaredLine, verify_declared


class GateA(NamedTuple):
    credit_id: str
    member_ids: tuple[str, ...]
    residual_paise: int
    computed_total_paise: int
    posted_sum_paise: int
    ok: bool
    n_deltas: int


class GreedyHit(NamedTuple):
    member_ids: tuple[str, ...]
    would_clear: bool
    same_as_declared: bool


class Overlay(NamedTuple):
    by_id: dict[str, GateA]
    n_ok: int
    n_residual_zero: int
    n_declared: int
    n_journalable: int
    journalable: dict[str, tuple[str, ...]]
    double_claimed: tuple[str, ...]
    n_mismatch: int


def gate_a_for(
    credit: BankCredit,
    declared: Sequence,
    ledger: Mapping[str, LedgerItem],
    rates: TaxRates,
    fees: FeeSchedule,
    reserve_bps: int,
) -> GateA | None:
    """None when the credit has no settlement-report rows (Regime B)."""
    if not declared:
        return None
    lines = tuple(
        DeclaredLine(r.item_id, r.kind, r.amount_paise, r.instrument) for r in declared
    )
    fast = verify_declared(credit, lines, ledger, rates, fees, reserve_bps=reserve_bps)
    member_ids = tuple(r.item_id for r in declared if r.item_id in ledger)
    posted = 0
    for mid in member_ids:
        posted += ledger[mid].amount_paise
    return GateA(
        credit_id=credit.id,
        member_ids=member_ids,
        residual_paise=fast.residual_paise,
        computed_total_paise=fast.computed_total_paise,
        posted_sum_paise=posted,
        ok=fast.ok,
        n_deltas=len(fast.line_deltas),
    )


def build_overlay(
    credits: Sequence[BankCredit],
    by_credit: Mapping[str, Sequence],
    ledger: Mapping[str, LedgerItem],
    rates: TaxRates,
    fees: FeeSchedule,
    reserve_bps: int,
) -> Overlay:
    by_id: dict[str, GateA] = {}
    journalable: dict[str, tuple[str, ...]] = {}
    n_ok = n_zero = n_declared = 0
    claimed: dict[str, list[str]] = defaultdict(list)
    for credit in credits:
        gate = gate_a_for(credit, by_credit.get(credit.id, ()), ledger, rates, fees, reserve_bps)
        if gate is None:
            continue
        n_declared += 1
        by_id[credit.id] = gate
        if gate.residual_paise == 0:
            n_zero += 1
        if gate.ok:
            n_ok += 1
            if gate.posted_sum_paise == credit.amount_paise:
                journalable[credit.id] = gate.member_ids
                for mid in gate.member_ids:
                    claimed[mid].append(credit.id)
    double = tuple(sorted(i for i, owners in claimed.items() if len(set(owners)) > 1))
    return Overlay(
        by_id=by_id,
        n_ok=n_ok,
        n_residual_zero=n_zero,
        n_declared=n_declared,
        n_journalable=len(journalable),
        journalable=journalable,
        double_claimed=double,
        n_mismatch=n_ok - len(journalable),
    )


def greedy_members(
    credit: BankCredit,
    items: Sequence[LedgerItem],
    cfg: SolverConfig,
) -> GreedyHit:
    """Largest-first greedy, same rule as eval arm A2. One credit, no uniqueness."""
    pool = build_pool(credit, items, cfg)
    target = to_rupee_units(credit.amount_paise)
    unused = list(range(len(pool.item_ids)))
    unused.sort(key=lambda i: (-abs(pool.amounts_rupees[i]), pool.item_ids[i]))
    running = 0
    chosen: list[int] = []
    epsilon = cfg.search.epsilon_rupees
    while unused:
        best = min(
            unused,
            key=lambda i: (
                abs(running + pool.amounts_rupees[i] - target),
                -abs(pool.amounts_rupees[i]),
                pool.item_ids[i],
            ),
        )
        nxt = running + pool.amounts_rupees[best]
        if chosen and abs(nxt - target) > abs(running - target):
            break
        chosen.append(best)
        running = nxt
        unused.remove(best)
        if abs(running - target) <= epsilon:
            break
    members = tuple(pool.item_ids[i] for i in sorted(chosen)) if chosen else ()
    would = abs(running - target) <= epsilon and bool(chosen)
    return GreedyHit(member_ids=members, would_clear=would, same_as_declared=False)


def greedy_versus_declared(
    credit: BankCredit,
    items: Sequence[LedgerItem],
    cfg: SolverConfig,
    declared_ids: Sequence[str],
) -> GreedyHit:
    hit = greedy_members(credit, items, cfg)
    same = set(hit.member_ids) == set(declared_ids) and bool(declared_ids)
    return GreedyHit(hit.member_ids, hit.would_clear, same)


def fixture_rival_sets() -> tuple[tuple[str, ...], tuple[str, ...], AlternateDiff]:
    """Fully enumerated fixture from tests/test_alt_diff.py. Live F36 is cap-refused."""
    set_a = ("p1", "p2")
    set_b = ("p3",)
    return set_a, set_b, diff_sets(set_a, set_b)
