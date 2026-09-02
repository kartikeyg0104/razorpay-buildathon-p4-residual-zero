"""Auto-clear decision table. Overlay never writes CLEARED.

Residual-zero, Gate A, UNIQUE, and CLEARED are four different predicates.
This module is the only place the console explains why a credit is refused.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

THESIS = (
    "Reconstruct the explanation. Prove the amount. "
    "Verify uniqueness. Clear only when the evidence supports it."
)

@lru_cache(maxsize=1)
def derived_threshold() -> str | None:
    """The one authoritative auto-clear threshold: the derived value in config/solver.yaml.

    Never a literal. A second hardcoded copy here could drift from the value the
    orchestrator actually enforces, and the console would then render a gate the engine
    does not apply. When CP6 has not derived a threshold there is no threshold, and the
    gate refuses rather than falling back to something permissive.
    """
    from residual_zero.config import ThresholdNotDerivedError, load_solver_config

    try:
        return load_solver_config().autonomy.derived_threshold
    except (ThresholdNotDerivedError, OSError, ValueError):
        return None


def _pass_fail(ok: bool | None) -> str:
    if ok is None:
        return "—"
    return "PASS" if ok else "FAIL"


def auto_clear_decision(
    *,
    residual_paise: int | None,
    uniqueness: str,
    pool_scope: str = "FULL",
    ordering_score: str | None = None,
    threshold: str | None = None,
    disposition: str = "FLAGGED",
    overlay_writes_cleared: bool = False,
) -> dict[str, Any]:
    """Deterministic refuse table. Console overlay cannot clear even if UNIQUE."""
    if threshold is None:
        threshold = derived_threshold()
    uniq = str(uniqueness or "").strip().upper() or "AMBIGUOUS"
    scope = str(pool_scope or "FULL").strip().upper() or "FULL"
    disp = str(disposition or "FLAGGED").strip().upper() or "FLAGGED"
    residual_ok = residual_paise == 0 if residual_paise is not None else None
    uniqueness_ok = uniq == "UNIQUE"
    scope_ok = scope == "FULL" and uniq not in {"BUDGET_EXCEEDED"}
    ordering_ok: bool | None = None
    if ordering_score:
        # No derived threshold means auto-clear must not proceed, matching the orchestrator's
        # `threshold is not None` clause. Fail closed rather than comparing against a default.
        ordering_ok = threshold is not None and str(ordering_score) >= threshold
    elif uniqueness_ok:
        # A UNIQUE solution is rank 1 of 1. Missing score is not a refuse on uniqueness.
        ordering_ok = True

    eval_would = bool(
        residual_ok
        and uniqueness_ok
        and scope_ok
        and (ordering_ok is True)
        and disp != "BUDGET_EXCEEDED"
    )
    console_clears = False
    if overlay_writes_cleared:
        console_clears = eval_would
    final = "CLEARED" if console_clears else "REFUSE"

    if uniq == "AMBIGUOUS":
        reason = "Multiple valid financial explanations exist."
    elif uniq == "NONE_FOUND":
        reason = "No exact financial explanation was established."
    elif uniq == "BUDGET_EXCEEDED" or scope != "FULL":
        reason = "Search did not finish on the full pool. Not a match."
    elif residual_ok is False:
        reason = "Residual is not zero paise."
    elif uniqueness_ok and not overlay_writes_cleared:
        gate = (
            f"Threshold {threshold} is refuse-all on this corpus."
            if threshold is not None
            else "No threshold has been derived from the risk-coverage curve, so nothing clears."
        )
        reason = (
            "UNIQUE on a full pool is still not a console clear. "
            "Overlay does not write CLEARED. " + gate
        )
    elif not uniqueness_ok:
        reason = "Uniqueness is not UNIQUE."
    else:
        reason = "UNIQUE + FULL + residual 0 + threshold is required. Overlay does not write CLEARED."

    return {
        "thesis": THESIS,
        "residual": _pass_fail(residual_ok),
        "residual_paise": residual_paise,
        "uniqueness": uniq,
        "uniqueness_gate": _pass_fail(uniqueness_ok),
        "search_scope": scope,
        "search_scope_gate": _pass_fail(scope_ok),
        "ordering_score": ordering_score or "—",
        "ordering_gate": _pass_fail(ordering_ok),
        "threshold": threshold,
        "disposition": disp,
        "eval_would_clear": eval_would,
        "eval_label": "ELIGIBLE" if eval_would else "REFUSE",
        "overlay_writes_cleared": False,
        "console_clears": console_clears,
        "final": final,
        "reason": reason,
        "writes_cleared": False,
    }


def illegal_clear_transition(from_state: str, to_state: str, actor: str = "AI") -> bool:
    """True when the transition must be rejected."""
    src = str(from_state or "").strip().upper()
    dst = str(to_state or "").strip().upper()
    who = str(actor or "").strip().upper()
    if dst != "CLEARED":
        return False
    if who in {"AI", "ASK", "CONTROLLER", "GROQ", "NVIDIA", "NIM", "PROVIDER", "LLM",
               "MODEL", "OVERLAY", "EXPLORER", "TOOL"}:
        return True
    if src in {
        "AMBIGUOUS",
        "NONE_FOUND",
        "BUDGET_EXCEEDED",
        "UNMATCHED",
        "EVIDENCE_ONLY",
        "FLAGGED",
        "VERIFIED",
        "GATE_A",
        "RESIDUAL_ZERO",
    }:
        return True
    return True
