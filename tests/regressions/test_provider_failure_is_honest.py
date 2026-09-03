"""Regression: every provider failure mode fails safe AND downgrades the status card.

`desk_ai_status()` promises "the live flag is YES only after a successful rewrite". Four
failure branches — empty choices, a non-dict message, empty prose, and an amount/PII leak —
returned an error to the caller without calling `record_live_result`, so a single earlier
success left `LIVE_PROVIDER` reading YES with a blank error while the provider was in fact
returning nothing usable (found 2026-09). The /health card and the desk both read that flag.

No test here makes a network call: the HTTP layer is injected via `post_json`.
"""

from __future__ import annotations

import pytest

import residual_zero.semantic.provider as provider

FACTS = "Residual 0.00. Uniqueness AMBIGUOUS. Overlay does not write CLEARED."

# name -> a fake provider response
FAILURES = {
    "empty choices": lambda url, key, body: {"choices": []},
    "choices not a list": lambda url, key, body: {"choices": "nope"},
    "message not a dict": lambda url, key, body: {"choices": [{"message": "not-a-dict"}]},
    "empty prose": lambda url, key, body: {"choices": [{"message": {"content": ""}}]},
    "provider error object": lambda url, key, body: {"error": {"code": "403"}},
    "amount leak": lambda url, key, body: {
        "choices": [{"message": {"content": "The payout is 1,234.56 rupees"}}]
    },
    "cleared claim": lambda url, key, body: {
        "choices": [{"message": {"content": "The credit is CLEARED now"}}]
    },
}


@pytest.fixture(autouse=True)
def live_key(monkeypatch):
    monkeypatch.setenv("RZ_LLM_TEST", "1")
    monkeypatch.setenv("AI_PROVIDER", "nvidia")
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-" + "x" * 24)
    monkeypatch.delenv("RZ_LLM", raising=False)
    monkeypatch.delenv("RZ_LLM", raising=False)
    yield
    provider.record_live_result(ok=False, error="")


@pytest.mark.parametrize("name", sorted(FAILURES))
def test_failure_downgrades_a_stale_success(name):
    provider.record_live_result(ok=True, error="")  # an earlier call did succeed
    assert provider.desk_ai_status()["LIVE_PROVIDER"] == "YES"

    prose, err = provider.rewrite("why is this short", FACTS, post_json=FAILURES[name])

    assert prose == "", f"{name} returned prose"
    assert err, f"{name} returned no error string"
    status = provider.desk_ai_status()
    assert status["LIVE_PROVIDER"] != "YES", f"{name} left a stale LIVE=YES"
    assert status["error"], f"{name} left the error blank"
    assert status["fallback"] is True


@pytest.mark.parametrize("name", sorted(FAILURES))
def test_failure_never_leaks_the_key(name):
    provider.rewrite("q", FACTS, post_json=FAILURES[name])
    status = provider.desk_ai_status()
    blob = repr(status)
    assert "nvapi-" not in blob
    assert "gsk_" not in blob
    assert status["key_present"] is True  # presence only, never the value


def test_a_transport_exception_is_recorded_and_not_raised():
    def boom(url, key, body):
        raise provider.ProviderError("connection reset by peer")

    provider.record_live_result(ok=True, error="")
    prose, err = provider.rewrite("q", FACTS, post_json=boom)
    assert prose == ""
    assert "connection reset" in err
    assert provider.desk_ai_status()["LIVE_PROVIDER"] != "YES"


def test_a_successful_rewrite_still_reports_live():
    """The downgrade must not be so eager that a real success stops registering."""
    def good(url, key, body):
        return {"choices": [{"message": {"content": "Two candidate sets both fit; a human decides."}}]}

    provider.record_live_result(ok=False, error="stale failure")
    prose, err = provider.rewrite("q", FACTS, post_json=good)
    assert err == ""
    assert prose
    status = provider.desk_ai_status()
    assert status["LIVE_PROVIDER"] == "YES"
    assert status["fallback"] is False


def test_timeout_is_capped_at_two_minutes(monkeypatch):
    monkeypatch.setenv("AI_TIMEOUT_S", "99999")
    assert provider._timeout_s() == 120
    monkeypatch.setenv("AI_TIMEOUT_S", "not-a-number")
    assert provider._timeout_s() == 30
    monkeypatch.delenv("AI_TIMEOUT_S")
    assert provider._timeout_s() == 30
