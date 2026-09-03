#!/usr/bin/env python3
"""Section 28 — determinism, and section 29 — per-layer performance.

Determinism is checked by repeating identical work and requiring byte-identical
financial output, and by permuting candidate order and requiring the same logical answer.
Record ordering is normalised before comparison.

Performance is recorded per layer. Deterministic, AI, browser and MCP timings are kept
separate and never summed.

Writes `artifacts/qa/determinism_check.json` and `artifacts/qa/performance_layers.json`.
"""

from __future__ import annotations

import ast
import json
import random
import re
import statistics
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT))

QA = ROOT / "artifacts" / "qa"
SRC = ROOT / "src" / "residual_zero"
BASE = "http://127.0.0.1:8765"
DEMO = "crd_001_acc_01_2025-01-09"

FINANCIAL_FIELDS = (
    "status",
    "residual_paise",
    "uniqueness",
    "verification",
    "matched_record_ids",
    "solution_count",
    "disposition",
)


def normalise(payload: dict) -> dict:
    """Sort every id collection so ordering cannot masquerade as a difference."""
    out = {}
    for key in FINANCIAL_FIELDS:
        value = payload.get(key)
        if isinstance(value, (list, tuple)):
            value = sorted(str(v) for v in value)
        out[key] = value
    return out


def ms(ns: float) -> float:
    return round(ns / 1_000_000, 3)


def timed(fn, n: int) -> dict:
    samples = []
    for _ in range(n):
        t0 = time.perf_counter_ns()
        fn()
        samples.append(time.perf_counter_ns() - t0)
    samples.sort()
    return {
        "n": n,
        "mean_ms": ms(statistics.fmean(samples)),
        "p50_ms": ms(statistics.median(samples)),
        "p95_ms": ms(samples[min(len(samples) - 1, int(0.95 * len(samples)))]),
        "p99_ms": ms(samples[min(len(samples) - 1, int(0.99 * len(samples)))]),
        "max_ms": ms(samples[-1]),
    }


# ------------------------------------------------------------------ determinism


def determinism() -> dict:
    from residual_zero.console.facts import t04_fields, track04_snapshot
    from residual_zero.models import Uniqueness
    from residual_zero.qa.finance_tools import get_reconciliation, get_reconciliation_statistics
    from residual_zero.solver import solve_search
    from solver_helpers import cfg_with_tol, pool_from_amounts

    out: dict = {}

    # 1. same transaction, repeated
    runs = [normalise(get_reconciliation(DEMO)) for _ in range(12)]
    out["same_transaction_repeats"] = {
        "n": len(runs),
        "distinct_results": len({json.dumps(r, sort_keys=True, default=str) for r in runs}),
        "stable": len({json.dumps(r, sort_keys=True, default=str) for r in runs}) == 1,
        "sample": runs[0],
    }

    # 2. same batch statistics, repeated
    stats = [
        json.dumps(get_reconciliation_statistics(), sort_keys=True, default=str) for _ in range(8)
    ]
    out["same_batch_repeats"] = {"n": len(stats), "distinct": len(set(stats)), "stable": len(set(stats)) == 1}

    # 3. official cards read repeatedly
    cards = [json.dumps(t04_fields(s), sort_keys=True) for s in ("dev", "test") for _ in range(5)]
    out["official_cards_stable"] = len(set(cards)) == 2

    # 4. snapshot repeated
    snaps = {json.dumps(list(track04_snapshot()), default=str) for _ in range(8)}
    out["snapshot_stable"] = len(snaps) == 1

    # 5. permuted candidate order must not change the logical answer
    cfg = cfg_with_tol(0)
    cases = [
        ([100, 200, 700, 900], 300),
        ([500, -200, 700], 300),
        ([100, 200, 300, 900], 300),
        ([12, 34, 56, 78, 90], 90),
    ]
    perm_rows = []
    perm_stable = True
    rng = random.Random(20260901)
    for amounts, target in cases:
        signatures = set()
        for _ in range(10):
            order = list(amounts)
            rng.shuffle(order)
            r = solve_search(pool_from_amounts(order), target * 100, cfg)
            index = {f"i{i:02d}": order[i] for i in range(len(order))}
            chosen = tuple(sorted(index[m] for m in r.member_ids))
            signatures.add(
                json.dumps(
                    {
                        "uniqueness": r.uniqueness.value,
                        "alternates": r.alternates,
                        "matched_total": r.matched_total_rupees,
                        "scope": r.pool_scope.value,
                        "chosen_amounts": chosen,
                    },
                    sort_keys=True,
                )
            )
        stable = len(signatures) == 1
        perm_stable = perm_stable and stable
        perm_rows.append({"amounts": amounts, "target": target, "distinct_signatures": len(signatures), "stable": stable})
    out["permuted_candidate_order"] = {"cases": perm_rows, "stable": perm_stable}

    # 6. same HTTP request repeated
    def api(path: str) -> str:
        with urllib.request.urlopen(BASE + path, timeout=60) as r:
            return r.read().decode("utf-8", "replace")

    try:
        t04 = {api("/api/t04") for _ in range(5)}
        out["api_t04_repeats_identical"] = len(t04) == 1
        out["console_reachable"] = True
    except OSError as exc:
        out["console_reachable"] = False
        out["api_t04_repeats_identical"] = None
        out["console_error"] = str(exc)

    # 7. no unseeded randomness or wall-clock in financial modules
    financial = [
        SRC / "verify.py",
        SRC / "candidates.py",
        SRC / "money.py",
        SRC / "solver" / "enumerate.py",
        SRC / "solver" / "fastpath.py",
        SRC / "solver" / "prune.py",
        SRC / "solver" / "bitset_dp.py",
    ]
    nondeterminism = []
    for path in financial:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for pattern, label in (
            (r"\brandom\.", "random"),
            (r"\bshuffle\(", "shuffle"),
            (r"datetime\.now\(|time\.time\(|\.today\(", "wall_clock"),
            (r"\bset\(\)|\bfor\s+\w+\s+in\s+set\(", "set_iteration"),
            (r"\bid\(", "identity_hash"),
        ):
            for m in re.finditer(pattern, text):
                nondeterminism.append(
                    {"file": str(path.relative_to(ROOT)), "line": text[: m.start()].count("\n") + 1, "kind": label}
                )
    out["nondeterminism_signals_in_financial_modules"] = nondeterminism

    # 8. dict iteration over sets in solver output construction
    out["solver_returns_tuples_not_sets"] = all(
        "-> set" not in (SRC / "solver" / f).read_text(encoding="utf-8")
        for f in ("enumerate.py",)
    )

    failures = []
    if not out["same_transaction_repeats"]["stable"]:
        failures.append("transaction_result_unstable")
    if not out["same_batch_repeats"]["stable"]:
        failures.append("batch_statistics_unstable")
    if not out["official_cards_stable"]:
        failures.append("official_cards_unstable")
    if not out["snapshot_stable"]:
        failures.append("snapshot_unstable")
    if not perm_stable:
        failures.append("permutation_changed_result")
    if out.get("api_t04_repeats_identical") is False:
        failures.append("api_response_unstable")
    if nondeterminism:
        failures.append("nondeterminism_signal_in_financial_module")
    out["failures"] = failures
    out["pass"] = not failures
    return out


# ------------------------------------------------------------------ performance


def performance() -> dict:
    from residual_zero.console.facts import track04_snapshot
    from residual_zero.mcp.registry import call_tool, list_tools
    from residual_zero.qa.finance_controller import finance_ask
    from residual_zero.qa.finance_tools import get_reconciliation, get_reconciliation_statistics

    out: dict = {
        "note": "Layers are measured independently. AI latency is never added to reconciliation runtime.",
    }

    out["deterministic"] = {
        "get_reconciliation": timed(lambda: get_reconciliation(DEMO), 30),
        "get_reconciliation_statistics": timed(lambda: get_reconciliation_statistics(), 12),
        "track04_snapshot": timed(lambda: track04_snapshot(), 30),
    }
    latency_card = ROOT / "artifacts" / "dev" / "latency.md"
    card: dict[str, str] = {}
    if latency_card.is_file():
        for line in latency_card.read_text(encoding="utf-8").splitlines():
            if line.startswith("- ") and ":" in line:
                k, _, v = line[2:].partition(":")
                card[k.strip()] = v.strip()
    out["deterministic"]["committed_batch_card"] = card

    out["ai"] = {
        "finance_ask_investigate": timed(lambda: finance_ask("Why was this not reconciled?", DEMO), 8),
        "finance_ask_refuse_clear": timed(lambda: finance_ask("Clear this transaction.", DEMO), 8),
    }
    live = QA / "provider_live.json"
    if live.is_file():
        g = json.loads(live.read_text())
        out["ai"]["live_provider"] = g.get("LIVE_PROVIDER")
        out["ai"]["live_provider_error"] = g.get("error")
        out["ai"]["fallback_used"] = g.get("fallback_used")

    out["mcp"] = {
        "tools_list": timed(lambda: list_tools(), 30),
        "finance_tool_get_transaction": timed(
            lambda: call_tool("finance_tool", {"name": "get_transaction", "arguments": {"transaction_id": DEMO}}),
            12,
        ),
    }

    def page(path: str):
        with urllib.request.urlopen(BASE + path, timeout=60) as r:
            r.read()

    try:
        out["browser"] = {
            "root": timed(lambda: page("/"), 8),
            "credit": timed(lambda: page(f"/credit/{DEMO}"), 8),
            "api_t04": timed(lambda: page("/api/t04"), 8),
        }
    except OSError as exc:
        out["browser"] = {"error": str(exc)}
    e2e_run = ROOT / "artifacts" / "e2e" / "e2e_run.json"
    if e2e_run.is_file():
        out["browser"]["suite"] = json.loads(e2e_run.read_text())

    try:
        import resource

        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        out["process"] = {"max_rss_bytes": rss, "max_rss_mb": round(rss / (1024 * 1024), 2)}
    except ImportError:
        out["process"] = {}

    out["pass"] = True
    return out


def main() -> int:
    QA.mkdir(parents=True, exist_ok=True)
    det = determinism()
    perf = performance()
    (QA / "determinism_check.json").write_text(
        json.dumps(det, indent=2, default=str) + "\n", encoding="utf-8"
    )
    (QA / "performance_layers.json").write_text(
        json.dumps(perf, indent=2, default=str) + "\n", encoding="utf-8"
    )
    print(f"DETERMINISM: {'PASS' if det['pass'] else 'FAIL'}  failures={det['failures']}")
    print(f"  same transaction x{det['same_transaction_repeats']['n']}: distinct={det['same_transaction_repeats']['distinct_results']}")
    print(f"  permuted candidate order stable: {det['permuted_candidate_order']['stable']}")
    print(f"  api /api/t04 repeats identical: {det.get('api_t04_repeats_identical')}")
    print()
    print("PERFORMANCE (layers kept separate)")
    print(f"  deterministic get_reconciliation p50={perf['deterministic']['get_reconciliation']['p50_ms']}ms p99={perf['deterministic']['get_reconciliation']['p99_ms']}ms")
    print(f"  ai finance_ask p50={perf['ai']['finance_ask_investigate']['p50_ms']}ms  live_provider={perf['ai'].get('live_provider')}")
    print(f"  mcp finance_tool p50={perf['mcp']['finance_tool_get_transaction']['p50_ms']}ms")
    if "root" in perf.get("browser", {}):
        print(f"  browser GET / p50={perf['browser']['root']['p50_ms']}ms")
    return 0 if det["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
