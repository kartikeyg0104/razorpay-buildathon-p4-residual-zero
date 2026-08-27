"""F57 percentiles and bottleneck."""

from __future__ import annotations

from residual_zero.runtime.latency import StageClock, _pct, render_latency_md


def test_percentiles_and_bottleneck():
    clock = StageClock()
    for ns in (10, 20, 30, 40, 50, 60, 70, 80, 90, 100):
        clock.add("dp", ns)
    clock.add("ingest", 1)
    rows = clock.percentiles()
    by = {r.stage: r for r in rows}
    assert by["dp"].p50_ns == _pct(list(range(10, 110, 10)), 50)
    assert clock.bottleneck() == "dp"
    md = render_latency_md(rows, machine="Darwin 25.5.0 (arm64)", n_credits=10, wall_ns=1000, bottleneck="dp")
    assert "bottleneck: dp" in md
    assert "Darwin 25.5.0" in md
