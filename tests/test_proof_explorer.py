"""Proof Explorer, candidate rejection, source matrix. Never writes CLEARED."""

from __future__ import annotations

from residual_zero.console.app import credit_view
from residual_zero.console.proof_explorer import (
    THESIS_AMBIGUOUS,
    explain_candidate_rejection,
    mixed_proof,
    proof_explorer,
    source_agreement_matrix,
)
from residual_zero.qa.finance_tools import TOOL_NAMES, call_finance_tool
from residual_zero.qa.playbooks import TERMINAL, playbook_for, terminal_state


TWINS = "crd_mix_ambiguous_twins"
DEMO = "crd_001_acc_01_2025-01-09"


def test_mixed_twins_two_solutions():
    blob = mixed_proof(TWINS)
    assert blob is not None
    assert blob["solution_count"] == 2
    assert blob["choose_one"] is False
    assert blob["writes_cleared"] is False
    assert blob["decision"] == "AMBIGUOUS"
    assert blob["distinguishing_authoritative_evidence"] == "NONE"
    assert blob["difference"]["common"] == 0
    assert len(blob["difference"]["only_a"]) == 1
    assert len(blob["difference"]["only_b"]) == 1
    assert THESIS_AMBIGUOUS in blob["thesis"]


def test_official_demo_stays_ambiguous():
    blob = proof_explorer(DEMO)
    assert blob["found"] is True
    assert blob["choose_one"] is False
    assert blob["writes_cleared"] is False
    assert blob["uniqueness"] == "AMBIGUOUS"
    assert blob["decision"] == "AMBIGUOUS"


def test_rejection_never_accepts():
    got = explain_candidate_rejection(TWINS, TWINS + "_i00")
    assert got["accepted"] is False
    assert got["writes_cleared"] is False
    assert got["reasons"]
    missing = explain_candidate_rejection(DEMO, "not_a_real_item")
    assert missing["accepted"] is False
    assert "missing ledger record" in missing["reasons"] or "uniqueness conflict" in missing["reasons"]


def test_source_matrix_present():
    matrix = source_agreement_matrix(DEMO)
    assert matrix["found"] is True
    assert matrix["writes_cleared"] is False
    assert matrix["matrix"]["BANK"]["BANK"] == "—"
    assert "SETTLEMENT" in matrix["matrix"]


def test_proof_pages_render():
    twins = credit_view(TWINS)
    assert twins.status_code == 200
    assert b"CONSTRUCTED_MIXED" in twins.body
    assert b"proof explorer" in twins.body.lower()
    assert b"Both explanations satisfy" in twins.body
    official = credit_view(DEMO)
    assert official.status_code == 200
    assert b"proof explorer" in official.body.lower()
    from residual_zero.console.app import app

    paths = {getattr(route, "path", "") for route in app.routes}
    assert "/proof/{credit_id}" in paths
    page = next(r for r in app.routes if getattr(r, "path", "") == "/proof/{credit_id}")
    body = page.endpoint(TWINS).body
    assert b"proof explorer" in body.lower()
    assert b"choose one" in body.lower() or b"choose_one" in body or b"NO" in body


def test_tools_are_allowlisted():
    assert "get_proof_explorer" in TOOL_NAMES
    assert "explain_candidate_rejection" in TOOL_NAMES
    blob = call_finance_tool("get_proof_explorer", {"transaction_id": TWINS})
    assert blob["writes_cleared"] is False
    assert blob["choose_one"] is False
    rejected = call_finance_tool(
        "explain_candidate_rejection",
        {"transaction_id": DEMO, "candidate_id": "x"},
    )
    assert rejected["accepted"] is False
    assert rejected["writes_cleared"] is False


def test_playbook_terminal_never_probably_matched():
    assert "PROBABLY_MATCHED" not in TERMINAL
    amb = terminal_state("AMBIGUOUS", residual_paise=0)
    assert amb == "AMBIGUOUS"
    proven = terminal_state("UNIQUE", residual_paise=0)
    assert proven == "PROVEN"
    book = playbook_for("AMBIGUOUS")
    assert book["steps"][-1] == "human_review"
    assert book["writes_cleared"] is False
