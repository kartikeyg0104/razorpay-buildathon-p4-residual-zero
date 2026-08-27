"""F57 stage timings. Integer nanoseconds; the machine line is required on every figure."""

from __future__ import annotations

import time
from collections import defaultdict

from pydantic import BaseModel, ConfigDict, Field

_STRICT = ConfigDict(frozen=True, extra="forbid")


class StageSample(BaseModel):
    model_config = _STRICT
    stage: str
    ns: int = Field(ge=0)


class Percentiles(BaseModel):
    model_config = _STRICT
    stage: str
    n: int
    p50_ns: int
    p95_ns: int
    p99_ns: int


class StageClock:
    def __init__(self) -> None:
        self._samples: dict[str, list[int]] = defaultdict(list)

    def add(self, stage: str, ns: int) -> None:
        if ns < 0:
            raise ValueError("negative duration")
        self._samples[stage].append(ns)

    def span(self, stage: str):
        start = time.perf_counter_ns()

        class _Span:
            def __enter__(_self):
                return _self

            def __exit__(_self, *exc):
                self.add(stage, time.perf_counter_ns() - start)
                return False

        return _Span()

    def percentiles(self) -> tuple[Percentiles, ...]:
        rows = []
        for stage in sorted(self._samples):
            xs = sorted(self._samples[stage])
            n = len(xs)
            rows.append(
                Percentiles(
                    stage=stage,
                    n=n,
                    p50_ns=_pct(xs, 50),
                    p95_ns=_pct(xs, 95),
                    p99_ns=_pct(xs, 99),
                )
            )
        return tuple(rows)

    def bottleneck(self) -> str | None:
        """Stage with the largest total time. p99 of a one-shot ingest is not a bottleneck."""
        if not self._samples:
            return None
        totals = {stage: sum(xs) for stage, xs in self._samples.items()}
        return max(totals, key=totals.get)


def _pct(xs: list[int], p: int) -> int:
    if not xs:
        return 0
    # nearest-rank, 1-indexed: i = ceil(p/100 * n) → integer
    n = len(xs)
    idx = (p * n + 99) // 100 - 1
    if idx < 0:
        idx = 0
    if idx >= n:
        idx = n - 1
    return xs[idx]


def render_latency_md(
    rows: tuple[Percentiles, ...],
    *,
    machine: str,
    n_credits: int,
    wall_ns: int,
    bottleneck: str | None,
) -> str:
    lines = [
        "# Latency (F57)",
        "",
        f"- machine: {machine}",
        f"- n_credits: {n_credits}",
        f"- wall_ns: {wall_ns}",
        f"- bottleneck: {bottleneck or 'n/a'}",
        "",
        "| stage | n | p50_ns | p95_ns | p99_ns |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row.stage} | {row.n} | {row.p50_ns} | {row.p95_ns} | {row.p99_ns} |"
        )
    if wall_ns > 0 and n_credits:
        # credits per 1000 seconds as an integer millirate to avoid floats in src
        per_ks = (n_credits * 1_000_000_000_000) // wall_ns
        lines.append("")
        lines.append(f"- throughput_credits_per_1000s: {per_ks}")
        # 5000-credit linear projection in ns
        proj = (wall_ns * 5000) // n_credits
        lines.append(f"- projected_5000_credit_wall_ns_if_linear: {proj}")
        lines.append(
            "- 5000-credit point is a linear projection from this n, not a separate corpus."
        )
    lines.append("")
    return "\n".join(lines)
