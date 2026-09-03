"""Regression: NVIDIA NIM is the only live provider. Groq is gone (2026-09-03).

Groq's key was removed from the environment. Before this change the code still:
  * defaulted `AI_PROVIDER` to "groq" whenever the variable was unset — which is exactly
    what happens when the console starts without loading .env,
  * fell back to `GROQ_URL` for any unrecognised provider, so a typo in AI_PROVIDER meant
    "send this request to api.groq.com" rather than "make no request",
  * read GROQ_API_KEY, and accepted a `gsk_` key as valid.

The invariant is now: a supported provider or no call at all.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from residual_zero.semantic import provider

SRC = Path("src/residual_zero")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ("AI_PROVIDER", "NVIDIA_API_KEY", "GROQ_API_KEY", "AI_API_KEY",
                 "AI_MODEL", "RZ_LLM", "RZ_LLM_TEST"):
        monkeypatch.delenv(name, raising=False)
    yield


def test_groq_is_not_a_selectable_backend():
    assert "groq" not in provider.PROVIDER_URLS
    assert "groq" not in provider.PROVIDER_KEY_PREFIXES
    assert all("groq" not in url for url in provider.PROVIDER_URLS.values())
    assert not hasattr(provider, "GROQ_URL")


def test_no_source_file_points_at_the_groq_endpoint():
    hits = [
        path
        for path in SRC.rglob("*.py")
        if "api.groq.com" in path.read_text(encoding="utf-8")
    ]
    assert not hits, f"still addressing Groq: {hits}"


def test_the_default_provider_is_nvidia():
    """An unset AI_PROVIDER must not resurrect Groq."""
    assert provider.ai_provider() == "nvidia"
    assert provider.provider_url() == provider.NVIDIA_URL


@pytest.mark.parametrize("value", ["groq", "gorq", "openai", "anthropic", "nvida", "  "])
def test_an_unsupported_provider_has_no_endpoint_and_makes_no_call(value, monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", value)
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-" + "x" * 24)
    monkeypatch.setenv("AI_API_KEY", "nvapi-" + "y" * 24)
    monkeypatch.setenv("RZ_LLM_TEST", "1")
    if value.strip():  # a blank value falls back to the nvidia default, which is fine
        assert provider.provider_url() == ""
        assert provider._api_key() == ""
        assert provider.live_enabled() is False
        prose, err = provider.rewrite("q", "facts")
        assert prose == ""
        assert err


def test_a_groq_key_is_never_accepted(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "nvidia")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_" + "x" * 24)
    monkeypatch.setenv("RZ_LLM_TEST", "1")
    assert provider._api_key() == "", "GROQ_API_KEY is still being read"
    assert provider.live_enabled() is False


def test_a_gsk_prefixed_key_fails_the_prefix_check(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "nvidia")
    monkeypatch.setenv("AI_API_KEY", "gsk_" + "x" * 24)
    monkeypatch.setenv("RZ_LLM_TEST", "1")
    assert provider._key_looks_valid() is False
    assert provider.live_enabled() is False


def test_the_bearer_token_is_never_posted_to_an_unrecognised_url():
    """Defence in depth: _default_post attaches the key, so it must refuse a stray URL."""
    for url in ("", "https://api.groq.com/openai/v1/chat/completions",
                "http://evil.example/v1/chat/completions"):
        with pytest.raises(provider.ProviderError):
            provider._default_post(url, "nvapi-secret", b"{}")


def test_nvidia_is_reachable_in_config(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "nvidia")
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-" + "x" * 24)
    monkeypatch.setenv("RZ_LLM_TEST", "1")
    assert provider.live_enabled() is True
    assert provider.provider_url() == provider.NVIDIA_URL
    assert provider.desk_ai_status()["provider"] == "nvidia"


def test_env_example_documents_nvidia_only():
    text = Path(".env.example").read_text(encoding="utf-8")
    assert "NVIDIA_API_KEY" in text
    assert "GROQ_API_KEY" not in text
    assert "GROQ_MODEL" not in text
    assert "api.groq.com" not in text
