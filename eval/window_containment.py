"""Window and pool audit. Eval-only. Does not change production windows.

Measures whether truth members sit inside candidate pools under several date
windows. Does not run subset-sum. Does not write CLEARED.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from residual_zero.candidates import WIDENED_KINDS, build_pool
from residual_zero.config import load_solver_config
from residual_zero.features import load_features
from residual_zero.solver.tolerance import apply_derived_epsilon
from residual_zero.tz import to_ist_date_display

from eval.loader import load_split
from eval.truth_loader import load_truth


def _item_date(item) -> date:
    return date.fromisoformat(to_ist_date_display(item.occurred_at))


def _pct(xs: list[int], p: int) -> int:
    if not xs:
        return 0
    ys = sorted(xs)
    idx = (p * (len(ys) - 1)) // 100
    return ys[idx]


def _contained(credit, truth_ids, ledger, start: date | None, end: date) -> tuple[int, int, int]:
    """Return (in_window, account_miss, ledger_miss)."""
    in_window = 0
    account_miss = 0
    ledger_miss = 0
    for iid in truth_ids:
        item = ledger.get(iid)
        if item is None:
            ledger_miss += 1
            continue
        if item.account_id != credit.account_id:
            account_miss += 1
            continue
        occurred = _item_date(item)
        if start is None:
            if occurred <= end:
                in_window += 1
        elif start <= occurred <= end:
            in_window += 1
    return in_window, account_miss, ledger_miss


def _window_row(name: str, credits, truth_by, ledger, start_fn, end_fn) -> dict:
    n = 0
    full = 0
    for credit in credits:
        rec = truth_by.get(credit.id)
        if rec is None:
            continue
        n += 1
        truth_ids = tuple(rec.member_ids)
        in_window, _acc, miss = _contained(
            credit, truth_ids, ledger, start_fn(credit), end_fn(credit),
        )
        if miss == 0 and in_window == len(truth_ids) and truth_ids:
            full += 1
    return {"window": name, "scored": n, "truth_fully_contained": full}


def main() -> int:
    items, credits = load_split("dev")
    truth_recs = load_truth("dev")
    truth_by = {r.bank_credit_id: r for r in truth_recs}
    ledger = {it.id: it for it in items}
    cfg = apply_derived_epsilon(load_solver_config(), load_features())
    scored = [c for c in credits if c.id in truth_by]

    current_pools = [len(build_pool(c, items, cfg).item_ids) for c in scored]
    current_contained = 0
    for credit in scored:
        rec = truth_by[credit.id]
        pool = set(build_pool(credit, items, cfg).item_ids)
        truth_ids = tuple(rec.member_ids)
        if truth_ids and all(i in pool for i in truth_ids):
            current_contained += 1

    # Asymmetric product windows: [D-k, D-1]. Same-day is value_date itself.
    asymmetric = []
    for k in (0, 1, 2, 3, 5, 35):
        def start_fn(c, k=k):
            return c.value_date - timedelta(days=k)

        def end_fn(c):
            return c.value_date - timedelta(days=1)

        if k == 0:
            asymmetric.append(
                _window_row(
                    "same_day_value_date",
                    scored,
                    truth_by,
                    ledger,
                    lambda c: c.value_date,
                    lambda c: c.value_date,
                )
            )
        else:
            asymmetric.append(_window_row(f"D_minus_{k}_to_D_minus_1", scored, truth_by, ledger, start_fn, end_fn))

    symmetric = []
    for k in (1, 2, 3, 5):
        symmetric.append(
            _window_row(
                f"plus_minus_{k}",
                scored,
                truth_by,
                ledger,
                lambda c, k=k: c.value_date - timedelta(days=k),
                lambda c, k=k: c.value_date + timedelta(days=k),
            )
        )

    include_value_date = []
    for k in (1, 2, 3, 5, 35):
        include_value_date.append(
            _window_row(
                f"D_minus_{k}_to_D_inclusive",
                scored,
                truth_by,
                ledger,
                lambda c, k=k: c.value_date - timedelta(days=k),
                lambda c: c.value_date,
            )
        )

    full = _window_row(
        "full_account_no_date",
        scored,
        truth_by,
        ledger,
        lambda _c: None,
        lambda c: date(9999, 12, 31),
    )

    test_items, test_credits = load_split("test")
    test_pools = [len(build_pool(c, test_items, cfg).item_ids) for c in test_credits]
    max_pool = cfg.search.max_pool
    test_over = sum(1 for n in test_pools if n > max_pool)

    out = {
        "dev_n_scored": len(scored),
        "current_window_truth_fully_contained": current_contained,
        "current_pool": {
            "min": min(current_pools) if current_pools else 0,
            "p50": _pct(current_pools, 50),
            "p95": _pct(current_pools, 95),
            "max": max(current_pools) if current_pools else 0,
            "over_max_pool": sum(1 for n in current_pools if n > max_pool),
            "max_pool": max_pool,
        },
        "asymmetric_D_minus_k_to_D_minus_1": asymmetric,
        "asymmetric_include_value_date": include_value_date,
        "symmetric_plus_minus_k": symmetric,
        "full_account": full,
        "test_pool": {
            "n_credits": len(test_credits),
            "min": min(test_pools) if test_pools else 0,
            "p50": _pct(test_pools, 50),
            "p95": _pct(test_pools, 95),
            "max": max(test_pools) if test_pools else 0,
            "over_max_pool": test_over,
            "max_pool": max_pool,
            "reason": "BUDGET_EXCEEDED fires when n_pool > max_pool before DP. Do not raise max_pool; shrink pools.",
        },
        "adopt": "Keep production PAYMENT window [D-5, D-1] and widened kinds [D-35, D-1]. Including value_date raises full-stack containment from 9/239 to 191/239, but those extra members sit on settlement day and would enlarge already-p50-287 pools toward max_pool 400. Search uniqueness is already AMBIGUOUS; a wider pool would not create unique auto-clears. Do not adopt plus-minus windows (post-credit items are not in the credit).",
    }
    dest = Path("artifacts").joinpath("dev", "window_containment.json")
    dest.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=2))
    print("wrote", dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
