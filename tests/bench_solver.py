"""Throughput of solve_search on pools built from a real split.

Run: python -m tests.bench_solver --pools-from data/dev
"""

from __future__ import annotations

import argparse
import platform
import statistics
import sys
import time
from pathlib import Path

from residual_zero.candidates import build_pool
from residual_zero.config import load_solver_config
from residual_zero.ingest.csv_bank import load_bank_credits
from residual_zero.ingest.csv_ledger import load_ledger_items
from residual_zero.ingest.source_root import SourceRoot
from residual_zero.solver import solve_search


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pools-from", default="data/dev")
    parser.add_argument("--limit", type=int, default=25)
    args = parser.parse_args(argv)
    root = SourceRoot(Path(args.pools_from).joinpath("rendered"))
    items = load_ledger_items(root)
    credits = load_bank_credits(root)
    cfg = load_solver_config()
    times: list[float] = []
    n = 0
    for credit in credits:
        pool = build_pool(credit, items, cfg)
        t0 = time.perf_counter()
        solve_search(pool, credit.amount_paise, cfg)
        times.append(time.perf_counter() - t0)
        n += 1
        if n >= args.limit:
            break
    times.sort()
    median = statistics.median(times)
    worst = times[-1]
    print(
        f"{platform.system()} {platform.release()} ({platform.machine()}), "
        f"{platform.python_implementation()} {platform.python_version()}"
    )
    print(
        f"{n} credits from {args.pools_from}: "
        f"median {median * 1000:.0f} ms, worst {worst * 1000:.0f} ms"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
