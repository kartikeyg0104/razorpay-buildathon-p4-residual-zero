"""NVIDIA NIM Ask rewrite. Pytest never calls out. Never writes CLEARED."""

from __future__ import annotations

import json

from residual_zero.semantic.provider import live_enabled, rewrite


def test_pytest_does_not_enable_live_provider():
    assert live_enabled() is False


def test_rewrite_accepts_injected_post(monkeypatch):
    monkeypatch.setenv("RZ_LLM_TEST", "1")
    monkeypatch.setenv("AI_PROVIDER", "nvidia")
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test_fixture_not_a_real_key")

    def fake(_url: str, _key: str, body: bytes) -> dict:
        payload = json.loads(body.decode("utf-8"))
        assert payload["model"]
        assert "CLEARED" in payload["messages"][0]["content"]
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            "Search auto-clear stays zero because uniqueness is AMBIGUOUS. "
                            "Overlay does not write CLEARED."
                        )
                    }
                }
            ]
        }

    prose, err = rewrite(
        "why is search auto-clear 0",
        "Search auto-clear is zero. Overlay does not write CLEARED.",
        post_json=fake,
    )
    assert err == ""
    assert "does not write CLEARED" in prose
    assert "12.00" not in prose


def test_rewrite_rejects_money_and_cleared_claims(monkeypatch):
    monkeypatch.setenv("RZ_LLM_TEST", "1")
    monkeypatch.setenv("AI_PROVIDER", "nvidia")
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test_fixture_not_a_real_key")

    def money(_url: str, _key: str, _body: bytes) -> dict:
        return {"choices": [{"message": {"content": "The residual is 12.00 paise."}}]}

    prose, err = rewrite("why short", "residual is unexplained.", post_json=money)
    assert prose == ""
    assert err

    def cleared(_url: str, _key: str, _body: bytes) -> dict:
        return {"choices": [{"message": {"content": "This credit is CLEARED."}}]}

    prose, err = rewrite("why short", "residual is unexplained.", post_json=cleared)
    assert prose == ""
    assert err == "cleared claim"
