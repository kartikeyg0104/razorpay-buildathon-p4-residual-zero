"""Regression: one /ask is bounded end to end, not per provider call.

`AI_TIMEOUT_S` caps a SINGLE provider call. One answer can make up to four in series —
up to three `select_next_tool` picks plus one `explain_evidence` — and nothing bounded the
sum. `agent_loop.MAX_NS` covers only the loop and is checked BEFORE a call is dispatched,
so the last pick could start just under the line and run a further `AI_TIMEOUT_S`, and
`explain_evidence` then ran afterwards with no budget check at all.

Measured on NVIDIA NIM at ~12 s per call that is ~48 s for a four-call answer; at the
timeout it is 30 + 30 + 30 = 90 s. Raising `AI_TIMEOUT_S` would have made the worst case
worse, not better. The fix is a deadline shared by every call in the request.
"""

from __future__ import annotations

import json
import time

import pytest

import residual_zero.semantic.provider as provider

SECOND_NS = 1_000_000_000


@pytest.fixture(autouse=True)
def live_key(monkeypatch):
    monkeypatch.setenv("RZ_LLM_TEST", "1")
    monkeypatch.setenv("AI_PROVIDER", "nvidia")
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-" + "x" * 24)
    monkeypatch.delenv("RZ_LLM", raising=False)
    monkeypatch.delenv("AI_TOTAL_BUDGET_S", raising=False)
    monkeypatch.delenv("AI_TIMEOUT_S", raising=False)
    yield
    provider.record_live_result(ok=False, error="")


def _post(_url, _key, _body):
    return {
        "choices": [{"message": {"content": json.dumps({"tool": "get_transaction", "stop": False})}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1},
    }


def test_no_budget_open_leaves_behaviour_unchanged():
    """The CLI and the QA scripts call the provider with no request budget."""
    assert provider.remaining_ns() is None
    assert provider.budget_exhausted() is False
    assert provider._effective_timeout() == provider._timeout_s()


def test_the_per_call_timeout_is_clamped_to_what_the_request_has_left(monkeypatch):
    monkeypatch.setenv("AI_TIMEOUT_S", "30")
    with provider.request_budget(seconds=10):
        assert provider._effective_timeout() <= 10
    with provider.request_budget(seconds=120):
        # Never longer than the single-call cap.
        assert provider._effective_timeout() == 30


def test_a_spent_budget_dispatches_nothing(monkeypatch):
    """Every entry point must refuse to start, so the request cannot overrun."""
    dispatched: list[int] = []

    def counting(url, key, body):
        dispatched.append(1)
        return _post(url, key, body)

    monkeypatch.setattr(provider, "_default_post", counting)
    with provider.request_budget(seconds=1):
        time.sleep(1.1)
        assert provider.budget_exhausted() is True
        prose, err = provider.rewrite("q", "facts")
        assert (prose, err) == ("", "request budget exhausted")
        prose, err, _usage = provider.explain_evidence("q", {"stats": {}}, "fallback")
        assert (prose, err) == ("", "request budget exhausted")
        tool, err = provider.select_next_tool("q", [], ["get_transaction"], "crd_x")
        assert (tool, err) == ({}, "request budget exhausted")
    assert dispatched == [], "a call was dispatched with no budget left"


def test_exhaustion_is_reported_honestly_not_as_a_live_pass():
    provider.record_live_result(ok=True, error="")  # a previous call did succeed
    with provider.request_budget(seconds=1):
        time.sleep(1.1)
        provider.rewrite("q", "facts")
    status = provider.desk_ai_status()
    assert status["LIVE_PROVIDER"] != "YES"
    assert "budget" in status["error"]
    assert status["fallback"] is True


def test_nested_budgets_keep_the_earliest_deadline():
    """A helper must not be able to widen the budget its caller set."""
    with provider.request_budget(seconds=60):
        outer = provider.remaining_ns()
        with provider.request_budget(seconds=5):
            inner = provider.remaining_ns()
        restored = provider.remaining_ns()
    assert inner < outer
    assert inner <= 5 * SECOND_NS
    assert restored > 5 * SECOND_NS, "the outer budget must be restored on exit"


def test_the_budget_is_reset_even_when_the_body_raises():
    with pytest.raises(RuntimeError):
        with provider.request_budget(seconds=30):
            raise RuntimeError("boom")
    assert provider.remaining_ns() is None


def test_finance_ask_opens_a_budget_and_stays_bounded(monkeypatch):
    """A slow provider must not let one answer run past the request budget."""
    from residual_zero.qa.finance_controller import finance_ask

    monkeypatch.setenv("AI_TOTAL_BUDGET_S", "10")
    call_delay_s = 6

    def slow(url, key, body):
        time.sleep(call_delay_s)
        return _post(url, key, body)

    monkeypatch.setattr(provider, "_default_post", slow)
    started = time.monotonic_ns()
    got = finance_ask("give me a batch summary", "crd_001_acc_01_2025-01-09", post_json=slow)
    elapsed_s = (time.monotonic_ns() - started) / SECOND_NS

    # Four unbounded calls at this delay would be 24s. The budget caps it well below that.
    assert elapsed_s < 20, f"request ran {elapsed_s:.1f}s despite a 10s budget"
    # The answer is still served: the deterministic template is the authoritative content.
    assert got["answer"]
    assert got["writes_cleared"] is False


def test_budget_env_var_is_bounded_and_defaults(monkeypatch):
    monkeypatch.delenv("AI_TOTAL_BUDGET_S", raising=False)
    assert provider.total_budget_s() == 40
    monkeypatch.setenv("AI_TOTAL_BUDGET_S", "99999")
    assert provider.total_budget_s() == 300
    monkeypatch.setenv("AI_TOTAL_BUDGET_S", "not-a-number")
    assert provider.total_budget_s() == 40
    monkeypatch.setenv("AI_TOTAL_BUDGET_S", "0")
    assert provider.total_budget_s() == 40


def test_a_call_is_never_started_that_cannot_finish():
    """MIN_CALL_NS: dispatching with 2s left just buys a guaranteed timeout."""
    assert provider.MIN_CALL_NS >= 5 * SECOND_NS
    with provider.request_budget(seconds=int(provider.MIN_CALL_NS // SECOND_NS) - 1):
        assert provider.budget_exhausted() is True
