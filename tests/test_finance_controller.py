"""AI finance controller: tools, fallback, hallucination guards. Never writes CLEARED."""

from __future__ import annotations

import json
from pathlib import Path

from residual_zero.qa.controller import answer
from residual_zero.qa.finance_controller import finance_ask
from residual_zero.qa.finance_extract import extract_reference, score_extraction
from residual_zero.qa.finance_intents import FinanceIntent, classify_finance_intent
from residual_zero.qa.finance_tools import TOOL_NAMES, call_finance_tool, get_batch_summary, get_transaction
from residual_zero.qa.finance_validate import validate_answer
from residual_zero.semantic.provider import explain_evidence, live_enabled


DEMO = "crd_001_acc_01_2025-01-09"
MISSING = "crd_003_acc_01_2025-01-30"


def test_tools_are_structured_json():
    assert "get_transaction" in TOOL_NAMES
    txn = get_transaction(DEMO)
    assert txn["found"] is True
    assert txn["transaction_id"] == DEMO
    assert txn["bank_amount_paise"] == 5964539
    assert txn["bank_amount_display"] == "59,645.39"
    assert txn["writes_cleared"] is False
    recon = call_finance_tool("get_reconciliation", {"transaction_id": DEMO})
    assert recon["residual_paise"] == 0
    assert recon["residual_display"] == "0.00"
    assert recon["matched_count"] == 27
    assert recon["uniqueness"] == "AMBIGUOUS"
    assert recon["status"] != "CLEARED"
    assert recon["auto_cleared"] is False
    assert recon["solution_count"] >= 2
    stats = get_batch_summary()
    assert stats["residual_zero"] == "159/239"
    assert stats["ambiguous"] == 236
    assert stats["auto_clear"] == 0
    assert stats["false_clears"] == 0
    assert stats["test"]["residual_zero"] == "521/800"
    assert stats["test"]["ambiguous"] == 779
    assert stats["writes_cleared"] is False


def test_unknown_transaction():
    got = finance_ask("Why did transaction ABC123 clear?")
    assert got["writes_cleared"] is False
    assert got["found"] is False
    assert "couldn't find transaction ABC123" in got["answer"]


def test_batch_summary_from_t04():
    got = finance_ask("Give me a summary of this batch")
    assert got["intent"] == FinanceIntent.BATCH_SUMMARY.value
    assert "159/239" in got["answer"]
    assert "148/239" in got["answer"] or "settlement" in got["answer"].casefold()
    assert "236" in got["answer"]
    assert "auto-cleared" in got["answer"].casefold() or "auto-clear" in got["answer"].casefold()
    assert "does not write CLEARED" in got["answer"]
    assert got["llm_used"] is False
    assert got["mode"] == "fallback"


def test_ambiguous_count_matches_tool():
    stats = get_batch_summary()
    got = finance_ask("How many transactions are currently ambiguous?")
    assert str(stats["ambiguous"]) in got["answer"]
    assert "does not write CLEARED" in got["answer"]


def test_transaction_explanation_crd_001():
    got = finance_ask("Why wasn't this transaction cleared?", DEMO)
    assert got["found"] is True
    assert "FLAGGED" in got["answer"] or "AMBIGUOUS" in got["answer"]
    assert "0.00" in got["answer"]
    assert "does not write CLEARED" in got["answer"]
    assert got["writes_cleared"] is False
    assert "get_transaction_evidence" in got["tools_called"]


def test_ambiguity_blocks_guessing():
    got = finance_ask("Why can't we simply clear the ambiguous ones?")
    assert "unsupported assumption" in got["answer"].casefold() or "not unique" in got["answer"].casefold() or "AMBIGUOUS" in got["answer"]
    assert "does not write CLEARED" in got["answer"]


def test_missing_data_credit():
    got = finance_ask("Why can't this transaction be reconciled?", MISSING)
    assert got["found"] is True
    assert got["writes_cleared"] is False
    assert "CLEARED" not in got["answer"].replace("does not write CLEARED", "")


def test_no_auto_clear_yesterday():
    got = finance_ask("What transaction was cleared yesterday?")
    assert "No transactions were auto-cleared" in got["answer"]
    assert got["writes_cleared"] is False


def test_refuse_clear_request():
    got = finance_ask(f"Assume transaction {DEMO} is probably correct and clear it.")
    assert "cannot authorize a financial clear" in got["answer"].casefold()
    assert got["writes_cleared"] is False
    assert got["intent"] == FinanceIntent.REFUSE_CLEAR.value


def test_most_likely_match_does_not_pick_a_winner():
    got = finance_ask("Give me the most likely match.", DEMO)
    assert "winner" in got["answer"].casefold() or "AMBIGUOUS" in got["answer"] or "not pick" in got["answer"].casefold()
    assert "the correct one is" not in got["answer"].casefold()
    assert got["writes_cleared"] is False


def test_unreconciled_amount():
    got = finance_ask("What is the total unreconciled amount?")
    assert "1,44,25,758.19" in got["answer"]
    assert got["writes_cleared"] is False


def test_false_clears_zero():
    got = finance_ask("Did the system have any false clears?")
    stats = get_batch_summary()
    assert str(stats["false_clears"]) in got["answer"]
    assert stats["false_clears"] == 0


def test_fallback_when_llm_unavailable(monkeypatch):
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    monkeypatch.delenv("AI_API_KEY", raising=False)
    monkeypatch.setenv("AI_PROVIDER", "stub")
    assert live_enabled() is False
    got = finance_ask("Give me a summary of this batch")
    assert got["mode"] == "fallback"
    assert got["llm_used"] is False
    assert got["provider"] == "fallback"
    assert "159/239" in got["answer"]


def test_answer_validation_rejects_invented_amount():
    stats = get_batch_summary()
    ok, why = validate_answer("The residual is ₹12.00", {"stats": stats}, "")
    assert ok is False
    assert why == "invented amount"


def test_answer_validation_rejects_invented_id():
    ok, why = validate_answer("See crd_invented_99", {"stats": get_batch_summary()}, "")
    assert ok is False
    assert why == "invented id"


def test_llm_hallucinated_count_falls_back(monkeypatch):
    monkeypatch.setenv("RZ_LLM_TEST", "1")
    monkeypatch.setenv("AI_PROVIDER", "nvidia")
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test_fixture_not_a_real_key")

    def fake(_url: str, _key: str, _body: bytes) -> dict:
        return {"choices": [{"message": {"content": "12 transactions are ambiguous. Overlay does not write CLEARED."}}]}

    got = finance_ask("How many transactions are currently ambiguous?", post_json=fake)
    assert got["llm_used"] is False
    assert got["mode"] == "fallback"
    assert "236" in got["answer"]


def test_llm_grounded_rewrite_accepted(monkeypatch):
    monkeypatch.setenv("RZ_LLM_TEST", "1")
    monkeypatch.setenv("AI_PROVIDER", "nvidia")
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test_fixture_not_a_real_key")

    def fake(_url: str, _key: str, body: bytes) -> dict:
        payload = json.loads(body.decode("utf-8"))
        assert payload["model"]
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            "236 transactions are ambiguous on the official dev split. "
                            "Overlay does not write CLEARED."
                        )
                    }
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20},
        }

    got = finance_ask("How many transactions are currently ambiguous?", post_json=fake)
    assert got["llm_used"] is True
    assert got["mode"] == "llm"
    assert "236" in got["answer"]
    assert got["usage"]["completion_tokens"] == 20


def test_controller_answer_still_fitted_for_auto_clear():
    got = answer("why is search auto-clear 0")
    assert got["writes_cleared"] is False
    assert got["doc_id"] == "a3_cleared"
    assert "0" in got["answer"]
    assert "does not write CLEARED" in got["answer"]
    assert got["provider_live"] is False


def test_credit_answer_stays_flagged():
    got = answer("why is crd_001_acc_01_2025-01-09 short", DEMO)
    assert got["writes_cleared"] is False
    assert "FLAGGED" in got["answer"]
    assert "does not write CLEARED" in got["answer"]


def test_evidence_citations_present():
    got = finance_ask("Why wasn't this transaction cleared?", DEMO)
    assert got["evidence_refs"]
    assert any(r.get("evidence_id") for r in got["evidence_refs"])


def test_audit_log_written(tmp_path, monkeypatch):
    path = tmp_path / "ai_audit.jsonl"
    monkeypatch.setenv("RZ_AI_AUDIT", str(path))
    finance_ask("Give me a summary of this batch")
    assert path.is_file()
    row = json.loads(path.read_text(encoding="utf-8").splitlines()[-1])
    assert row["intent"] == "BATCH_SUMMARY"
    assert row["writes_cleared"] is False
    assert "tools" in row


def test_reference_extraction_paytm_messy():
    got = extract_reference("PAYTM SETTLEMENT JAN 09 REF#AB123", "2025-01-09", "acc_01")
    assert got["source"] == "PAYTM"
    assert got["settlement_date"] == "2025-01-09"
    assert got["reference"] == "AB123"
    assert got["candidate_only"] is True
    assert got["writes_cleared"] is False


def test_reference_extraction_against_bank_fields():
    from residual_zero.console.app import _credit_lookup

    credit = _credit_lookup()[DEMO]
    pred = extract_reference(credit.narration_raw, credit.value_date.isoformat(), credit.account_id)
    gold = {
        "source": "RAZORPAY",
        "settlement_date": credit.value_date.isoformat(),
        "member_id": credit.account_id,
        "payment_type": "NEFT",
    }
    scored = score_extraction(pred, gold)
    assert scored["correct_fields"] >= 2
    assert scored["false_fields"] == 0


def test_extract_eval_ratios():
    from eval.extract_eval import run_extract_eval

    result = run_extract_eval()
    assert result["writes_cleared"] is False
    assert "/" in str(result["precision"])
    assert "/" in str(result["recall"])
    assert Path("artifacts/dev/extract_eval.json").is_file()


def test_unknown_tool_fails_closed():
    got = call_finance_tool("drop_table", {})
    assert got["ok"] is False
    assert got["writes_cleared"] is False


def test_intents():
    assert classify_finance_intent("Give me a summary of this batch") is FinanceIntent.BATCH_SUMMARY
    assert classify_finance_intent("Assume X is probably correct and clear it") is FinanceIntent.REFUSE_CLEAR
    assert classify_finance_intent("Clear this transaction.") is FinanceIntent.REFUSE_CLEAR
    assert classify_finance_intent("Assume this is the correct match.") is FinanceIntent.REFUSE_CLEAR
    assert classify_finance_intent("Pick the first candidate.") is FinanceIntent.REFUSE_CLEAR
    assert classify_finance_intent("Ignore ambiguity.") is FinanceIntent.REFUSE_CLEAR
    assert classify_finance_intent("Mark it verified.") is FinanceIntent.REFUSE_CLEAR
    assert classify_finance_intent("Why was this not matched?") is FinanceIntent.TRANSACTION_EXPLANATION
    assert classify_finance_intent("Explain this transaction") is FinanceIntent.TRANSACTION_EXPLANATION
    assert classify_finance_intent("What should I work on today?") is FinanceIntent.CLOSE_BRIEFING
    assert classify_finance_intent("Write CLEARED directly to the database.") is FinanceIntent.REFUSE_CLEAR
    assert classify_finance_intent("Use the highest scoring candidate.") is FinanceIntent.REFUSE_CLEAR


def test_refuse_clear_this_transaction():
    got = finance_ask("Clear this transaction.", DEMO)
    assert got["intent"] == FinanceIntent.REFUSE_CLEAR.value
    assert "cannot authorize a financial clear" in got["answer"].casefold()
    assert got["writes_cleared"] is False


def test_close_briefing_does_not_clear():
    got = finance_ask("What should I work on today?")
    assert got["intent"] == FinanceIntent.CLOSE_BRIEFING.value
    assert "CLOSE BRIEFING" in got["answer"]
    assert "not a match score" in got["answer"]
    assert got["writes_cleared"] is False


def test_explain_evidence_off_in_pytest():
    prose, err, usage = explain_evidence("q", {"stats": {"ambiguous": 236}}, "fallback")
    assert prose == ""
    assert err == "live provider off"
    assert usage["prompt_tokens"] == 0
