"""Financial state-machine invariants.

The authoritative auto-clear gate lives in `orchestrator.py` as a six-conjunct predicate:

    can_clear = (
        outcome.accepted
        and solve.uniqueness == Uniqueness.UNIQUE
        and solve.pool_scope == PoolScope.FULL
        and unresolved == 0
        and threshold is not None
        and score_s >= threshold
    )

These tests pin the closed state sets, prove each conjunct is load-bearing in the console
gate, and structurally guard the orchestrator predicate so a removed conjunct fails CI
rather than silently widening auto-clear.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from residual_zero.console.clear_gate import auto_clear_decision, illegal_clear_transition
from residual_zero.models import Disposition, PoolScope, Uniqueness

ORCHESTRATOR = Path("src/residual_zero/orchestrator.py")

# Actors that must never be able to reach CLEARED.
NON_HUMAN_ACTORS = ("AI", "ASK", "CONTROLLER", "GROQ", "NVIDIA", "NIM", "PROVIDER",
                    "LLM", "MODEL", "OVERLAY", "EXPLORER", "TOOL")

# Every state a credit can sit in before someone tries to clear it.
SOURCE_STATES = (
    "AMBIGUOUS",
    "NONE_FOUND",
    "BUDGET_EXCEEDED",
    "UNMATCHED",
    "EVIDENCE_ONLY",
    "FLAGGED",
    "VERIFIED",
    "GATE_A",
    "RESIDUAL_ZERO",
    "POTENTIALLY_RECOVERABLE",
    "UNIQUE",
)


# --------------------------------------------------------------- closed state sets


def test_uniqueness_is_a_closed_four_value_set():
    assert {u.value for u in Uniqueness} == {
        "UNIQUE",
        "AMBIGUOUS",
        "NONE_FOUND",
        "BUDGET_EXCEEDED",
    }


def test_pool_scope_is_a_closed_two_value_set():
    assert {s.value for s in PoolScope} == {"FULL", "REDUCED"}


def test_disposition_is_a_closed_three_value_set():
    """There is no fourth terminal outcome and no silent pass."""
    assert {d.value for d in Disposition} == {"CLEARED", "FLAGGED", "BUDGET_EXCEEDED"}


def test_the_distinct_states_are_actually_distinct():
    """AMBIGUOUS is not UNIQUE, not VERIFIED, not CLEARED. Same for the rest."""
    assert Uniqueness.AMBIGUOUS.value != Uniqueness.UNIQUE.value
    assert Uniqueness.AMBIGUOUS.value != Disposition.CLEARED.value
    assert Uniqueness.BUDGET_EXCEEDED.value != Uniqueness.UNIQUE.value
    assert Disposition.FLAGGED.value != Disposition.CLEARED.value
    assert Disposition.BUDGET_EXCEEDED.value != Disposition.CLEARED.value


# ------------------------------------------------------- illegal clear transitions


@pytest.mark.parametrize("actor", NON_HUMAN_ACTORS)
@pytest.mark.parametrize("src", SOURCE_STATES)
def test_no_machine_actor_may_transition_any_state_to_cleared(actor: str, src: str):
    assert illegal_clear_transition(src, "CLEARED", actor) is True


@pytest.mark.parametrize("src", SOURCE_STATES)
def test_even_a_human_actor_cannot_transition_to_cleared_in_this_build(src: str):
    """Auto-clear is refuse-all on this corpus; the console never writes CLEARED."""
    assert illegal_clear_transition(src, "CLEARED", "HUMAN") is True


@pytest.mark.parametrize(
    "dst", ["FLAGGED", "REVIEW_REQUIRED", "ESCALATED", "VERIFIED", "AMBIGUOUS"]
)
def test_non_cleared_destinations_are_not_blanket_rejected(dst: str):
    """The guard targets CLEARED specifically, not every transition."""
    assert illegal_clear_transition("AMBIGUOUS", dst, "HUMAN") is False


# ------------------------------------------------- each conjunct is load-bearing


def _decision(**over):
    base = {
        "residual_paise": 0,
        "uniqueness": "UNIQUE",
        "pool_scope": "FULL",
        "ordering_score": "1.000000",
        "disposition": "FLAGGED",
        "overlay_writes_cleared": True,  # forced on to isolate the deterministic gate
    }
    base.update(over)
    return auto_clear_decision(**base)


def test_all_conjuncts_satisfied_is_the_only_eligible_case():
    """Control: with every gate satisfied the evaluation would consider it eligible."""
    assert _decision()["eval_would_clear"] is True


@pytest.mark.parametrize("residual", [1, -1, 100, -100, 999_999])
def test_nonzero_residual_blocks_clear(residual: int):
    assert _decision(residual_paise=residual)["eval_would_clear"] is False


@pytest.mark.parametrize("uniq", ["AMBIGUOUS", "NONE_FOUND", "BUDGET_EXCEEDED", ""])
def test_non_unique_blocks_clear(uniq: str):
    assert _decision(uniqueness=uniq)["eval_would_clear"] is False


def test_reduced_pool_scope_blocks_clear():
    """A UNIQUE found on a REDUCED pool was never shown unique over the full pool."""
    assert _decision(pool_scope=PoolScope.REDUCED.value)["eval_would_clear"] is False


def test_budget_exceeded_disposition_blocks_clear():
    assert _decision(disposition="BUDGET_EXCEEDED")["eval_would_clear"] is False


def test_residual_zero_alone_never_clears():
    """The headline invariant: residual == 0 is necessary, never sufficient."""
    for uniq in ("AMBIGUOUS", "NONE_FOUND", "BUDGET_EXCEEDED"):
        d = auto_clear_decision(residual_paise=0, uniqueness=uniq)
        assert d["eval_would_clear"] is False
        assert d["final"] == "REFUSE"
        assert d["writes_cleared"] is False


def test_ambiguous_with_residual_zero_is_never_treated_as_unique():
    d = auto_clear_decision(residual_paise=0, uniqueness="AMBIGUOUS")
    assert d["uniqueness"] == "AMBIGUOUS"
    assert d["uniqueness_gate"] == "FAIL"
    assert "Multiple valid financial explanations" in d["reason"]


def test_console_overlay_never_writes_cleared_regardless_of_gates():
    """Default construction cannot clear even when every deterministic gate passes."""
    d = auto_clear_decision(
        residual_paise=0, uniqueness="UNIQUE", pool_scope="FULL", ordering_score="1.000000"
    )
    assert d["console_clears"] is False
    assert d["overlay_writes_cleared"] is False
    assert d["writes_cleared"] is False
    assert d["final"] == "REFUSE"


# ----------------------------------------- structural guard on the real gate


def _can_clear_expression() -> str:
    text = ORCHESTRATOR.read_text(encoding="utf-8")
    m = re.search(r"can_clear\s*=\s*\((.*?)\)\n", text, re.S)
    assert m, "can_clear predicate not found in orchestrator.py"
    return m.group(1)


@pytest.mark.parametrize(
    "conjunct",
    [
        "outcome.accepted",
        "solve.uniqueness == Uniqueness.UNIQUE",
        "solve.pool_scope == PoolScope.FULL",
        "unresolved == 0",
        "threshold is not None",
        "score_s >= threshold",
    ],
)
def test_auto_clear_gate_still_requires_every_conjunct(conjunct: str):
    """Fails loudly if a gate is dropped from the deterministic auto-clear predicate."""
    assert conjunct in _can_clear_expression()


def test_auto_clear_gate_is_pure_conjunction():
    """No `or` may creep into the auto-clear predicate."""
    expr = _can_clear_expression()
    assert " or " not in expr
    assert expr.count("and") == 5


def test_budget_exceeded_or_reduced_scope_short_circuits_away_from_cleared():
    text = ORCHESTRATOR.read_text(encoding="utf-8")
    assert re.search(
        r"if\s+solve\.uniqueness\s*==\s*Uniqueness\.BUDGET_EXCEEDED\s+or\s+"
        r"solve\.pool_scope\s*==\s*PoolScope\.REDUCED:\s*\n\s*disposition\s*=\s*Disposition\.BUDGET_EXCEEDED",
        text,
    ), "BUDGET_EXCEEDED / REDUCED must map to the BUDGET_EXCEEDED disposition"


def test_write_cleared_is_gated_by_the_write_policy_flag():
    text = ORCHESTRATOR.read_text(encoding="utf-8")
    assert re.search(r"if\s+pol\.allow_writes:\s*\n\s*write_cleared\(", text)
