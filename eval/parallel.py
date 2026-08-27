"""F34: throughput at 1/4/8 workers on a slice of the live corpus."""

from __future__ import annotations

import time
from pathlib import Path

from residual_zero.config import load_solver_config
from residual_zero.runtime.pool import canonical_payload, map_reduce
from residual_zero.solver.tolerance import apply_derived_epsilon
from residual_zero.features import load_features

from eval.loader import load_split


def measure(split: str = "dev", n_credits: int = 16) -> str:
    items, credits = load_split(split)
    credits = tuple(sorted(credits, key=lambda c: c.id)[:n_credits])
    cfg = apply_derived_epsilon(load_solver_config(), load_features())
    lines = [
        "# F34 deterministic parallelism",
        "",
        f"- n_credits: {len(credits)}",
        "- workers: threads (CPython GIL; DP is Python). Byte-identity is the load-bearing claim.",
        "",
        "| workers | wall_ns | credits_per_1000s | payload_sha256 |",
        "|---:|---:|---:|---|",
    ]
    payloads: list[bytes] = []
    import hashlib

    for n_workers in (1, 4, 8):
        t0 = time.perf_counter_ns()
        rows = map_reduce(credits, items, cfg, n_workers)
        wall = time.perf_counter_ns() - t0
        payload = canonical_payload(rows)
        payloads.append(payload)
        digest = hashlib.sha256(payload).hexdigest()
        per_1000s = (len(credits) * 1_000_000_000_000) // wall if wall else 0
        lines.append(f"| {n_workers} | {wall} | {per_1000s} | {digest} |")
    identical = payloads[0] == payloads[1] == payloads[2]
    lines.extend(
        [
            "",
            f"- byte_identical_1_4_8: {str(identical).lower()}",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    out = Path("artifacts").joinpath("p4")
    out.mkdir(parents=True, exist_ok=True)
    text = measure("dev")
    out.joinpath("parallel.md").write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
