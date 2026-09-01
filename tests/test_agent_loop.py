"""Multi-step agent loop, investigation tools, limits. Never writes CLEARED."""

from __future__ import annotations

from residual_zero.qa.agent_loop import MAX_REPEAT, MAX_TOOLS, playbook, run_agent
from residual_zero.qa.finance_controller import finance_ask
from residual_zero.qa.finance_intents import FinanceIntent
from residual_zero.qa.finance_tools import TOOL_NAMES, call_finance_tool
from residual_zero.qa.finance_validate import validate_answer
from residual_zero.qa.investigate_tools import compare_sources, get_candidate_equations

DEMO = "crd_001_acc_01_2025-01-09"
NONE = "crd_001_acc_00_2025-01-08"


def test_playbook_is_multi_step():
    steps = playbook(FinanceIntent.INVESTIGATE, DEMO, "investigate")
    assert 2 <= len(steps) <= MAX_TOOLS
    assert steps[0][0] == "get_transaction"


def test_run_agent_without_a_live_provider():
    got = run_agent("Can you investigate why this wasn't reconciled?", DEMO, FinanceIntent.INVESTIGATE)
    assert got["writes_cleared"] is False
    assert len(got["tools"]) >= 4
    assert len(got["tools"]) <= MAX_TOOLS
    assert got["llm_picks"] == 0
    assert all(t["source"] == "playbook" for t in got["tools"])
    names = [t["tool"] for t in got["tools"]]
    assert "compare_sources" in names
    assert "get_candidate_equations" in names


def test_tool_limit_and_repeat():
    assert MAX_TOOLS == 8
    assert MAX_REPEAT == 2
    first = call_finance_tool("get_transaction", {"transaction_id": DEMO})
    assert first.get("found") is True
    bad = call_finance_tool("drop_table", {})
    assert bad["ok"] is False


def test_invalid_tool_stays_closed():
    got = call_finance_tool("invent_match", {})
    assert got["ok"] is False
    assert got["writes_cleared"] is False


def test_compare_sources_computes_difference():
    got = compare_sources(DEMO)
    assert got["found"] is True
    assert "bank_minus_settlement_display" in got
    assert got["writes_cleared"] is False
    assert any(s["source"] == "BANK" for s in got["sources"])


def test_candidate_equations_do_not_choose():
    got = get_candidate_equations(DEMO)
    assert got["choose_one"] is False
    assert got["writes_cleared"] is False


def test_none_found_investigation_does_not_clear():
    got = finance_ask("Can you investigate why this wasn't reconciled?", NONE)
    assert got["writes_cleared"] is False
    assert "CLEARED" not in got["answer"].replace("does not write CLEARED", "")
    assert len(got["investigation_steps"]) >= 3


def test_ambiguity_refuses_to_pick():
    got = finance_ask("Why is this transaction ambiguous?", DEMO)
    assert got["writes_cleared"] is False
    names = got["tools_called"]
    assert "compare_solutions" in names or "get_proof_explorer" in names or "get_candidate_equations" in names
    assert "write_cleared" not in names


def test_llm_next_tool_allowlist(monkeypatch):
    monkeypatch.setenv("RZ_LLM_TEST", "1")
    monkeypatch.setenv("AI_PROVIDER", "nvidia")
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test_fixture_not_a_real_key")

    def fake(_url: str, _key: str, body: bytes):
        import json

        payload = json.loads(body.decode("utf-8"))
        if any("REMAINING" in str(m.get("content")) for m in payload.get("messages") or []):
            return {
                "choices": [
                    {"message": {"content": '{"tool": "get_audit_trail", "arguments": {}, "stop": false}'}}
                ]
            }
        return {"choices": [{"message": {"content": ""}}]}

    got = run_agent("investigate this", DEMO, FinanceIntent.INVESTIGATE, post_json=fake)
    assert got["writes_cleared"] is False
    assert got["llm_picks"] >= 1
    assert any(t["tool"] == "get_audit_trail" and t["source"] == "llm" for t in got["tools"])


def test_llm_unknown_tool_rejected(monkeypatch):
    monkeypatch.setenv("RZ_LLM_TEST", "1")
    monkeypatch.setenv("AI_PROVIDER", "nvidia")
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test_fixture_not_a_real_key")

    def fake(_url: str, _key: str, _body: bytes):
        return {"choices": [{"message": {"content": '{"tool": "write_cleared", "stop": false}'}}]}

    got = run_agent("investigate this", DEMO, FinanceIntent.INVESTIGATE, post_json=fake)
    assert got["writes_cleared"] is False
    assert all(t["tool"] != "write_cleared" or t.get("ok") is False for t in got["tools"])


def test_hallucinated_residual_rejected():
    ok, why = validate_answer(
        "residual of ₹0.00",
        {"reconciliation": {"uniqueness": "NONE_FOUND", "residual_paise": 49648}},
        "",
    )
    assert ok is False
    assert why in {"invented residual", "invented amount"}


def test_schema_and_constraint_eval_do_not_install_rules():
    from eval.constraint_effectiveness import run_constraint_audit
    from eval.schema_relationships import run_schema_audit

    schema = run_schema_audit("dev")
    cons = run_constraint_audit("dev")
    assert schema["implemented_new_rules"] == 0
    assert cons["new_unique_matches"] == 0
    assert cons["false_clears"] == 0
    assert "compare_sources" in TOOL_NAMES


def test_agent_repeatable():
    a = run_agent("investigate", DEMO, FinanceIntent.INVESTIGATE)
    b = run_agent("investigate", DEMO, FinanceIntent.INVESTIGATE)
    assert [t["tool"] for t in a["tools"]] == [t["tool"] for t in b["tools"]]
