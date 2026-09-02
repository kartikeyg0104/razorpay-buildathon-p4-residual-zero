"""Read-only Track 04 desk tools. Structured facts only. Never writes CLEARED."""

from __future__ import annotations

from typing import Any

from residual_zero.console.facts import t04_fields, track04_snapshot


def get_batch_summary() -> dict[str, Any]:
    snap = track04_snapshot()
    return {
        "scored": snap.scored,
        "exact": snap.exact,
        "search_cleared": snap.search_cleared,
        "flagged": snap.flagged,
        "budget_dev": snap.budget_dev,
        "test_exact": snap.test_exact,
        "test_budget": snap.test_budget,
        "unreconciled": snap.unreconciled,
        "double_claimed": snap.double_claimed,
        "throughput_per_1000s": snap.throughput_per_1000s,
        "wall_ns": snap.wall_ns,
        "writes_cleared": False,
        "auto_clear_is_not_exact": True,
    }


def batch_prose() -> str:
    snap = track04_snapshot()
    dev = t04_fields("dev")
    test = t04_fields("test")
    residual_zero = dev.get("residual-zero") or snap.residual_zero
    settlement = dev.get("settlement-linked / member-identified") or snap.settlement_linked
    # Sourced from the committed Test card; never a literal, so a missing card cannot
    # make the desk state an official figure it did not read.
    test_rz = test.get("residual-zero") or "—"
    return (
        f"Dev A3 scored n={snap.scored}: residual-zero {residual_zero}, "
        f"settlement-linked {settlement}, "
        f"search auto-clear {snap.search_cleared}/{snap.scored}, flagged {snap.flagged}, "
        f"budget-exceeded {snap.budget_dev}. Unreconciled {snap.unreconciled}; "
        f"double_claimed {snap.double_claimed}. Test A3 exact {snap.test_exact}, "
        f"budget-exceeded {snap.test_budget}, search-completed {snap.test_search_completed}, "
        f"residual-zero {test_rz}, cleared 0. "
        f"Exact is not auto-clear. Overlay does not write CLEARED."
    )
