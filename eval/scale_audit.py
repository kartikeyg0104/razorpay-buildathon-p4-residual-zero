"""Per-credit search timing on a split. Eval-only. Does not write CLEARED."""

from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path

from residual_zero.candidates import build_pool
from residual_zero.config import load_solver_config
from residual_zero.features import load_features
from residual_zero.solver import prune_indices, solve_search
from residual_zero.solver.tolerance import apply_derived_epsilon
from residual_zero.money import to_rupee_units

from eval.loader import load_split
from eval.truth_loader import load_truth


def _pct(xs: list[int], p: int) -> int:
    if not xs:
        return 0
    ys = sorted(xs)
    return ys[(p * (len(ys) - 1)) // 100]


def main(split: str = "test") -> int:
    items, credits = load_split(split)
    truth = {r.bank_credit_id for r in load_truth(split)}
    cfg = apply_derived_epsilon(load_solver_config(), load_features())
    old_search = cfg.search.model_copy(update={"max_pool_scaled": cfg.search.max_pool})
    old_cfg = cfg.model_copy(update={"search": old_search})
    rows = []
    t0 = time.perf_counter()
    for credit in credits:
        if credit.id not in truth:
            continue
        pool = build_pool(credit, items, cfg)
        before = len(pool.item_ids)
        target_r = to_rupee_units(credit.amount_paise)
        kept = prune_indices(pool.amounts_rupees, target_r, cfg.search.epsilon_rupees)
        after = len(kept)
        s0 = time.perf_counter()
        result = solve_search(pool, credit.amount_paise, cfg)
        ns = int((time.perf_counter() - s0) * 1_000_000_000)
        if before > cfg.search.max_pool:
            prior = solve_search(pool, credit.amount_paise, old_cfg)
        else:
            prior = result
        def _disp(sol) -> str:
            if sol.uniqueness.value == "BUDGET_EXCEEDED" or sol.pool_scope.value == "REDUCED":
                return "BUDGET_EXCEEDED"
            return sol.uniqueness.value
        rows.append(
            {
                "id": credit.id,
                "n_before": before,
                "n_after": after,
                "strategy": result.strategy,
                "uniqueness": result.uniqueness.value,
                "scope": result.pool_scope.value,
                "uniqueness_before": prior.uniqueness.value,
                "scope_before": prior.pool_scope.value,
                "disposition_before": _disp(prior),
                "disposition_after": _disp(result),
                "enum_nodes": result.enum_nodes,
                "axis_width": result.axis_width,
                "search_ns": ns,
            }
        )
    wall_ns = int((time.perf_counter() - t0) * 1_000_000_000)
    times = [r["search_ns"] for r in rows]
    n = len(rows)
    uniq = Counter(r["uniqueness"] for r in rows)
    strats = Counter(r["strategy"] for r in rows)
    completed = n - uniq.get("BUDGET_EXCEEDED", 0)
    before_sizes = [r["n_before"] for r in rows]
    after_sizes = [r["n_after"] for r in rows]
    summary = {
        "split": split,
        "n_scored": n,
        "uniqueness": dict(uniq),
        "strategy": dict(strats),
        "search_completed": completed,
        "budget_exceeded": uniq.get("BUDGET_EXCEEDED", 0),
        "pool_before": {
            "min": min(before_sizes) if before_sizes else 0,
            "p50": _pct(before_sizes, 50),
            "p95": _pct(before_sizes, 95),
            "max": max(before_sizes) if before_sizes else 0,
        },
        "pool_after_prune": {
            "min": min(after_sizes) if after_sizes else 0,
            "p50": _pct(after_sizes, 50),
            "p95": _pct(after_sizes, 95),
            "max": max(after_sizes) if after_sizes else 0,
        },
        "search_ns": {
            "mean": (sum(times) // n) if n else 0,
            "p50": _pct(times, 50),
            "p95": _pct(times, 95),
            "max": max(times) if times else 0,
        },
        "wall_ns": wall_ns,
        "throughput_per_1000s": (n * 1_000_000_000_000 // wall_ns) if wall_ns else 0,
        "transitions_from_budget": dict(
            Counter(
                r["uniqueness"]
                for r in rows
                if r["disposition_before"] == "BUDGET_EXCEEDED"
            )
        ),
        "budget_before": sum(1 for r in rows if r["disposition_before"] == "BUDGET_EXCEEDED"),
        "budget_after": sum(1 for r in rows if r["disposition_after"] == "BUDGET_EXCEEDED"),
    }
    dest = Path("artifacts").joinpath(split, "scale_audit.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps({"summary": summary, "rows": rows}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print("wrote", dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
