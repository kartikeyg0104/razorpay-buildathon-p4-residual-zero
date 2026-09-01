"""Safe failure: provider 403, unknown tool, missing DB. Never writes CLEARED."""

from __future__ import annotations

from residual_zero.qa.finance_tools import call_finance_tool
from residual_zero.semantic.provider import ProviderError, explain_evidence, record_live_result, desk_ai_status


def test_unknown_tool_fails_closed():
    got = call_finance_tool("drop_table", {})
    assert got["ok"] is False
    assert got["writes_cleared"] is False


def test_provider_403_falls_back_and_is_unavailable(monkeypatch):
    monkeypatch.setenv("RZ_LLM_TEST", "1")
    monkeypatch.setenv("AI_PROVIDER", "nvidia")
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test_fixture_not_a_real_key")

    def boom(url: str, key: str, body: bytes):
        raise ProviderError("nvidia http 403")

    prose, err, usage = explain_evidence("q", {"stats": {"auto_clear": 0}}, "fallback", post_json=boom)
    assert prose == ""
    assert "403" in err
    record_live_result(ok=False, error=err)
    status = desk_ai_status()
    assert status["LIVE_PROVIDER"] in {"UNAVAILABLE", "OFF"}
    assert status["DETERMINISTIC_CONTROLLER"] == "PASS"
    assert status["writes_cleared"] is False
    assert usage["prompt_tokens"] == 0
