"""F34: partition credits by id, map, reduce in sorted credit_id order. SQLite stays serial."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Sequence

from residual_zero.canonical import canonical_json
from residual_zero.candidates import build_pool
from residual_zero.config import SolverConfig
from residual_zero.models import BankCredit, LedgerItem
from residual_zero.solver import solve_search


def partition_ids(credit_ids: Sequence[str], n_workers: int) -> tuple[tuple[str, ...], ...]:
    """Contiguous slices of sorted ids. Worker count does not change membership, only grouping."""
    if n_workers < 1:
        raise ValueError(f"n_workers must be >= 1, got {n_workers}")
    ordered = tuple(sorted(credit_ids))
    n = len(ordered)
    base = n // n_workers
    rem = n % n_workers
    out: list[tuple[str, ...]] = []
    start = 0
    for i in range(n_workers):
        extra = 1 if i < rem else 0
        end = start + base + extra
        out.append(ordered[start:end])
        start = end
    return tuple(out)


def solve_one(credit: BankCredit, items: Sequence[LedgerItem], cfg: SolverConfig) -> dict:
    """Pure map body. No RNG. Result is a dict ready for canonical_json."""
    pool = build_pool(credit, items, cfg)
    solve = solve_search(pool, credit.amount_paise, cfg)
    return {
        "credit_id": credit.id,
        "uniqueness": solve.uniqueness.value,
        "member_ids": list(solve.member_ids),
        "alternates": solve.alternates,
        "pool_scope": solve.pool_scope.value,
        "pool_size": solve.pool_size,
    }


def map_reduce(
    credits: Sequence[BankCredit],
    items: Sequence[LedgerItem],
    cfg: SolverConfig,
    n_workers: int,
    fn: Callable[[BankCredit, Sequence[LedgerItem], SolverConfig], dict] | None = None,
) -> tuple[dict, ...]:
    """Map over credits partitioned by id. Reduce by sorting credit_id. Threads, not SQLite."""
    if n_workers < 1:
        raise ValueError(f"n_workers must be >= 1, got {n_workers}")
    work = fn if fn is not None else solve_one
    by_id = {c.id: c for c in credits}
    slices = partition_ids(tuple(by_id), n_workers)
    ordered_credits = tuple(by_id[cid] for part in slices for cid in part)

    def _call(credit: BankCredit) -> dict:
        return work(credit, items, cfg)

    if n_workers == 1 or len(ordered_credits) <= 1:
        rows = [_call(c) for c in ordered_credits]
    else:
        with ThreadPoolExecutor(max_workers=n_workers) as pool:
            rows = list(pool.map(_call, ordered_credits))
    rows.sort(key=lambda r: str(r["credit_id"]))
    return tuple(rows)


def canonical_payload(rows: Sequence[dict]) -> bytes:
    """Byte-stable encoding of a map_reduce result."""
    return canonical_json({"rows": list(rows)})
