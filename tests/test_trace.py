"""F52: a raise still leaves a trace terminating in one disposition."""

from __future__ import annotations

from residual_zero.models import Disposition
from residual_zero.trace import TraceBuilder


def test_finish_always_has_one_disposition():
    b = TraceBuilder("c1")
    b.gate("pool", True, "8")
    tr = b.finish(Disposition.FLAGGED)
    assert tr.disposition == Disposition.FLAGGED
    assert tr.gates[0].name == "pool"


def test_raise_path_still_terminates():
    b = TraceBuilder("c1")
    b.gate("dp", False, "boom")
    tr = b.finish(Disposition.FLAGGED, error="RuntimeError")
    assert tr.error == "RuntimeError"
    assert tr.disposition == Disposition.FLAGGED
    assert len(tr.gates) == 1
