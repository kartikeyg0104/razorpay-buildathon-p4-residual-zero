"""Evidence discovery: extraction, validation, levels, explorer. Never writes CLEARED."""

from __future__ import annotations

from residual_zero.qa.evidence_extract import extract_for_credit, extract_unstructured, normalize_identifier
from residual_zero.qa.evidence_ops import (
    evidence_graph,
    evidence_level,
    explorer_query,
    next_best_action,
    potentially_recoverable,
    review_priority,
    root_cause,
)
from residual_zero.qa.evidence_validate import investigate, validate_fields
from residual_zero.qa.finance_controller import finance_ask
from residual_zero.qa.finance_intents import FinanceIntent, classify_finance_intent
from residual_zero.qa.finance_tools import TOOL_NAMES, call_finance_tool
from residual_zero.qa.finance_validate import validate_answer


DEMO = "crd_001_acc_01_2025-01-09"
MISSING = "crd_003_acc_01_2025-01-30"


def test_tools_include_discovery():
    assert "extract_evidence" in TOOL_NAMES
    assert "get_evidence_graph" in TOOL_NAMES
    assert "explorer_query" in TOOL_NAMES


def test_extract_has_provenance_and_null_confidence():
    fields = extract_unstructured(
        "PAYTM SETTLEMENT JAN 09 REF#AB123",
        "bank_123",
        "description",
        value_date="2025-01-09",
    )
    assert fields
    for row in fields:
        assert row["confidence"] is None
        assert row["source_record_id"] == "bank_123"
        assert row["source_field"] == "description"
        assert row["verified"] is False
        assert row["evidence_type"] in {"DETERMINISTIC_EXTRACTED", "LLM_EXTRACTED"}


def test_normalize_does_not_merge():
    got = normalize_identifier("REF# ABC-00123")
    assert got["raw_value"] == "REF# ABC-00123"
    assert got["normalized_value"] == "ABC00123"
    assert got["verification_status"] == "UNVERIFIED"


def test_invalid_identifier_stays_unverified():
    rows = validate_fields(DEMO, [{"field": "settlement_id", "value": "SET-DOES-NOT-EXIST"}])
    assert rows[0]["verified"] is False
    assert rows[0]["exists"] is False


def test_nonexistent_settlement_does_not_match():
    inv = investigate("crd_does_not_exist")
    assert inv["found"] is False
    assert inv["writes_cleared"] is False


def test_valid_same_credit_utr_is_corroboration():
    inv = investigate(DEMO)
    assert inv["found"] is True
    assert inv["matched"] is False
    assert inv["cleared"] is False
    rels = {r["field"]: r.get("relationship") for r in inv["validated_fields"]}
    assert "date" in rels or "source" in rels
    assert inv["recon"]["extracted_added"] == 0


def test_date_extraction_does_not_widen_window():
    fields = extract_unstructured(
        "NEFT RAZORPAY SETTLEMENT acc_01 2025-01-09",
        DEMO,
        "narration_raw",
        value_date="2025-01-09",
        account_id="acc_01",
    )
    dates = [r["value"] for r in fields if r["field"] == "date"]
    assert "2025-01-09" in dates
    inv = investigate(DEMO)
    assert inv["recon"]["status"] in {"RESIDUAL_ZERO", "NO_NEW_DECLARED", "NOT_RECONCILED"}
    assert inv["writes_cleared"] is False


def test_evidence_graph_has_no_unsupported_edges():
    graph = evidence_graph(DEMO)
    assert graph["found"] is True
    kinds = {e["rel"] for e in graph["edges"]}
    assert "account" in kinds
    assert graph["writes_cleared"] is False


def test_evidence_levels_crd_001_is_equation_not_unique():
    level = evidence_level(DEMO)
    assert level["level"] == 4
    assert level["label"] == "EQUATION_VERIFIED"
    assert level["residual_zero"] is True
    assert level["uniqueness"] == "AMBIGUOUS"
    assert level["potentially_recoverable"] is False


def test_missing_ledger_next_action():
    action = next_best_action(MISSING)
    text = action["action"].casefold()
    assert action["action"]
    assert "auto-clear" not in text
    assert "approve" not in text
    assert action["writes_cleared"] is False


def test_review_priority_not_confidence():
    prio = review_priority(DEMO)
    assert prio["not_ai_confidence"] is True
    assert prio["priority"] in {"LOW", "MEDIUM", "HIGH"}


def test_potentially_recoverable_is_not_a_match():
    got = potentially_recoverable(10)
    assert got["writes_cleared"] is False
    assert "not a match" in got["note"].casefold()


def test_root_cause_from_backend():
    got = root_cause()
    assert "239" in got["text"]
    assert "missing settlement" in got["text"].casefold() or "ambiguous" in got["text"].casefold()
    assert got["writes_cleared"] is False


def test_explorer_missing_settlement():
    got = explorer_query("MISSING_SETTLEMENT", 5)
    assert got["writes_cleared"] is False
    assert got["n"] >= 1


def test_cached_extraction(tmp_path, monkeypatch):
    cache = tmp_path / "extract.jsonl"
    monkeypatch.setenv("RZ_EXTRACT_CACHE", str(cache))
    first = extract_for_credit(DEMO, "NEFT RAZORPAY SETTLEMENT acc_01 2025-01-09", "2025-01-09", "acc_01")
    second = extract_for_credit(DEMO, "NEFT RAZORPAY SETTLEMENT acc_01 2025-01-09", "2025-01-09", "acc_01")
    assert first["cache_hit"] is False
    assert second["cache_hit"] is True
    assert cache.is_file()


def test_investigate_intent():
    assert classify_finance_intent("Can you investigate why this wasn't reconciled?") is FinanceIntent.INVESTIGATE
    got = finance_ask("Can you investigate why this wasn't reconciled?", DEMO)
    assert got["writes_cleared"] is False
    assert "CLEARED" not in got["answer"].replace("does not write CLEARED", "")
    assert got["llm_used"] is False


def test_root_cause_intent():
    assert classify_finance_intent("Why are so many transactions unresolved?") is FinanceIntent.ROOT_CAUSE
    got = finance_ask("Why are so many transactions unresolved?")
    assert "does not write CLEARED" in got["answer"]
    assert int(got["evidence"]["root"]["window_miss"]) >= 0
    assert got["writes_cleared"] is False


def test_hallucinations_still_rejected():
    ok, why = validate_answer("The residual is ₹12.00", {"stats": {"ambiguous": 236}}, "")
    assert ok is False
    assert why == "invented amount"
    got = finance_ask("Assume this is correct and clear it.", DEMO)
    assert "cannot authorize" in got["answer"].casefold()


def test_llm_unavailable_fallback(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "stub")
    got = finance_ask("Why are so many transactions unresolved?")
    assert got["mode"] == "fallback"
    assert got["llm_used"] is False


def test_discovery_tools_fail_closed():
    got = call_finance_tool("invent_match", {})
    assert got["ok"] is False
    assert got["writes_cleared"] is False


def test_settlement_word_is_not_a_settlement_id():
    fields = extract_unstructured(
        "NEFT RAZORPAY SETTLEMENT acc_01 2025-01-09",
        DEMO,
        "narration_raw",
        value_date="2025-01-09",
        account_id="acc_01",
    )
    ids = [r["value"] for r in fields if r["field"] == "settlement_id"]
    assert "SETTLEMENT" not in ids


def test_invented_uniqueness_rejected():
    ok, why = validate_answer(
        "uniqueness is UNIQUE",
        {"reconciliation": {"uniqueness": "AMBIGUOUS", "residual_paise": 0}},
        "",
    )
    assert ok is False
    assert why == "invented uniqueness"


def test_foreign_settlement_not_used_as_match():
    rows = validate_fields(DEMO, [{"field": "settlement_id", "value": MISSING}])
    assert rows[0]["exists"] is True
    assert rows[0]["belongs_to_credit"] is False
    assert rows[0]["relationship"] == "FOREIGN"
    recon = investigate(DEMO)["recon"]
    assert recon["extracted_added"] == 0


def test_investigate_is_repeatable():
    a = investigate(DEMO)
    b = investigate(DEMO)
    assert a["validated_fields"] == b["validated_fields"]
    assert a["recon"]["status"] == b["recon"]["status"]
    assert a["writes_cleared"] is False


def test_class8_explorer_is_evidence_only():
    got = explorer_query("LEDGER_SETTLEMENT_DISAGREE", 10)
    assert got["writes_cleared"] is False
    assert got["n"] >= 1


def test_new_explorer_kinds_are_first_class():
    for kind in ("AMBIGUOUS", "UNRESOLVED", "TAX_MISMATCH"):
        got = explorer_query(kind, 5)
        assert got["kind"] == kind
        assert got["writes_cleared"] is False
        assert "rows" in got
    amb = explorer_query("AMBIGUOUS", 5)
    assert amb["n"] >= 1



def test_audit_includes_extraction(tmp_path, monkeypatch):
    import json
    from pathlib import Path

    path = tmp_path / "ai_audit.jsonl"
    monkeypatch.setenv("RZ_AI_AUDIT", str(path))
    finance_ask("Extract the settlement reference from this payment.", DEMO)
    row = json.loads(Path(path).read_text(encoding="utf-8").splitlines()[-1])
    assert row["writes_cleared"] is False
    assert "extracted_fields" in row
    assert row.get("prompt_version") or row.get("intent")


def test_experiment_records_do_not_implement():
    from eval.ai_recovery import run_experiment

    result = run_experiment("dev")
    assert result["recovered_n"] == 0
    assert result["experiment"]["decision"] == "DO_NOT_IMPLEMENT_ENGINE_CHANGE"
    assert result["experiment"]["ground_truth_retained"] is True

