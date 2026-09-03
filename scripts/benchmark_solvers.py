#!/usr/bin/env python3
"""Development-only solver benchmark. Does not replace production search."""

from __future__ import annotations

import json
import sys
import time
import tracemalloc
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from residual_zero.models import Uniqueness  # noqa: E402
from residual_zero.solver import solve_search  # noqa: E402
from tests.solver_helpers import cfg_with_tol, pool_from_amounts  # noqa: E402


def brute_ids(amounts: tuple[int, ...], target: int, cap: int = 8) -> list[tuple[str, ...]]:
    n = len(amounts)
    found: list[tuple[str, ...]] = []
    ids = tuple(f"i{i:02d}" for i in range(n))
    for width in range(1, n + 1):
        for combo in combinations(range(n), width):
            total = sum(amounts[i] for i in combo)
            if total == target:
                found.append(tuple(sorted(ids[i] for i in combo)))
                if len(found) >= cap:
                    return found
    return found


def run_case(name: str, amounts: list[int], target: int, *, independent: bool) -> dict:
    cfg = cfg_with_tol(0)
    pool = pool_from_amounts(amounts)
    tracemalloc.start()
    t0 = time.perf_counter_ns()
    got = solve_search(pool, target * 100, cfg)
    elapsed = time.perf_counter_ns() - t0
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    member = tuple(sorted(got.member_ids))
    row: dict = {
        "name": name,
        "n_candidates": len(amounts),
        "target_rupees": target,
        "production_uniqueness": got.uniqueness.value,
        "production_solution_count": got.alternates,
        "production_member_ids": list(member),
        "production_matched_total_rupees": got.matched_total_rupees,
        "production_runtime_ns": elapsed,
        "production_peak_bytes": peak,
        "independent_ran": False,
        "same_financial_input": True,
        "production_replaced": False,
    }
    if independent:
        t1 = time.perf_counter_ns()
        brute = brute_ids(tuple(int(a) for a in amounts), target)
        brute_ns = time.perf_counter_ns() - t1
        n_brute = len(brute)
        expect = (
            Uniqueness.UNIQUE
            if n_brute == 1
            else (Uniqueness.AMBIGUOUS if n_brute >= 2 else Uniqueness.NONE_FOUND)
        )
        row.update(
            {
                "independent_ran": True,
                "independent_solution_count": n_brute,
                "independent_member_ids": [list(x) for x in brute[:2]],
                "independent_runtime_ns": brute_ns,
                "independent_expect_uniqueness": expect.value,
                "same_solution_count_class": got.uniqueness == expect
                or (got.uniqueness == Uniqueness.AMBIGUOUS and n_brute >= 2),
                "same_unique_set": member == brute[0] if n_brute == 1 and got.uniqueness == Uniqueness.UNIQUE else n_brute != 1,
            }
        )
    return row


def main() -> int:
    cases = [
        ("single_exact", [1, 2, 3], 6, True),
        ("multiple_solutions", [5, 5], 5, True),
        ("no_solution", [1, 2, 3], 100, True),
        ("duplicate_values", [5, 5, 5], 5, True),
        ("negative_values", [10, -3, 4], 11, True),
        ("mixed_signs", [1000, -300, 400], 1100, True),
        ("zero_values", [1, 0, 2], 3, True),
        ("large_pool_20", list(range(1, 21)), 210, True),
        ("pool_400", list(range(1, 401)), 10**9, False),
    ]
    rows = [run_case(name, amounts, target, independent=ind) for name, amounts, target, ind in cases]
    a = solve_search(pool_from_amounts([1, 2, 3]), 600, cfg_with_tol(0))
    b = solve_search(pool_from_amounts([1, 2, 3]), 600, cfg_with_tol(0))
    report = {
        "production_solver": "residual_zero.solver.solve_search",
        "independent_solver": "brute_force combinations (development only)",
        "dpss_installed": False,
        "production_replaced": False,
        "determinism_repeat": a.uniqueness == b.uniqueness and a.member_ids == b.member_ids,
        "cases": rows,
        "note": (
            "Same financial input / expected uniqueness class must be preserved. "
            "A faster independent brute force does not replace production search."
        ),
    }
    out_json = ROOT / "artifacts" / "competitive" / "solver_benchmark.json"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    md = ROOT / "docs" / "SOLVER_BENCHMARK.md"
    lines = [
        "# Solver benchmark",
        "",
        "Development-only comparison of Residual Zero `solve_search` against an independent brute-force enumerator.",
        "",
        "- Production solver was **not** replaced.",
        f"- Determinism repeat (same pool twice): `{report['determinism_repeat']}`.",
        "- Independent `dpss` / europeanplaice subset_sum was **not installed**; brute force is the independent check.",
        "",
        "| case | n | uniqueness | prod solutions | independent solutions | runtime ns | same class |",
        "|---|---:|---|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            "| {name} | {n_candidates} | {production_uniqueness} | {production_solution_count} | {ind} | {production_runtime_ns} | {same} |".format(
                name=row["name"],
                n_candidates=row["n_candidates"],
                production_uniqueness=row["production_uniqueness"],
                production_solution_count=row["production_solution_count"],
                ind=row.get("independent_solution_count", "skipped"),
                production_runtime_ns=row["production_runtime_ns"],
                same=row.get("same_solution_count_class", "n/a"),
            )
        )
    lines.extend(
        [
            "",
            "400-candidate pool skips independent enumeration (`2^400` is not a measurement).",
            "Zero-value pools may return `BUDGET_EXCEEDED` in production because empty/zero amounts are refused by search.",
            "",
        ]
    )
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(out_json)
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
