"""Optional NVIDIA NIM rewrite for Ask. Eval and auto-clear stay stub. Never writes CLEARED.

NVIDIA NIM is the only live provider. Groq was removed on 2026-09-03: its key is gone from
the environment and it is no longer a selectable backend, an endpoint, or a fallback. An
unrecognised ``AI_PROVIDER`` now resolves to no endpoint and makes no call, rather than
silently addressing someone else's API with whatever key is to hand.

Credentials come from NVIDIA_API_KEY (or the generic AI_API_KEY) in the environment.
Pytest never calls out.
"""

from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Callable, Iterator
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from residual_zero.semantic.redact import PiiLeakError, assert_no_pii
from residual_zero.semantic.schema import AmountLeakError, MONEY_PATTERN, assert_no_amounts

NVIDIA_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-oss-20b"
DEFAULT_PROVIDER = "nvidia"
PostJson = Callable[[str, str, bytes], dict[str, Any]]

# OpenAI-compatible chat-completions endpoints, selected by AI_PROVIDER.
# NVIDIA NIM only. There is deliberately no default entry and no fallback endpoint: an
# unknown provider must resolve to no URL so the caller makes no request at all.
PROVIDER_URLS: dict[str, str] = {
    "nvidia": NVIDIA_URL,
    "nim": NVIDIA_URL,
}
# Accepted key prefixes per provider. A key alone never means a live call succeeded.
PROVIDER_KEY_PREFIXES: dict[str, tuple[str, ...]] = {
    "nvidia": ("nvapi-",),
    "nim": ("nvapi-",),
}
# AI_PROVIDER values that mean "make no live call at all".
OFF_PROVIDERS = frozenset({"stub", "off", "none", "fallback", ""})

_LAST: dict[str, Any] = {
    "probed": False,
    "ok": False,
    "error": "",
    "llm_picks": 0,
}

_SYSTEM = (
    "You are Residual Zero, a settlement reconciliation controller. "
    "Rewrite FACTS in plain English for a finance operator. "
    "Do not invent counts, rates, or amounts. "
    "Do not write rupee signs or decimal money literals. "
    "Never say a credit is CLEARED. Overlay does not write CLEARED. "
    "Search auto-clear of zero is the product when uniqueness is AMBIGUOUS. "
    "Gate A (verify_declared) is not search auto-clear."
)


class ProviderError(RuntimeError):
    """Provider failure. Callers fall back to the fitted corpus. Never include secrets."""


def provider_model() -> str:
    """Model id for the live provider. Kept under the old name for report compatibility."""
    return os.environ.get("AI_MODEL", "").strip() or DEFAULT_MODEL


def ai_provider() -> str:
    return os.environ.get("AI_PROVIDER", DEFAULT_PROVIDER).strip().casefold() or DEFAULT_PROVIDER


def provider_url() -> str:
    """Chat-completions endpoint for the configured provider, or "" when there is none.

    No fallback endpoint. A typo in AI_PROVIDER must mean "no live call", never "send this
    request to whichever provider happens to be first in the table".
    """
    return PROVIDER_URLS.get(ai_provider(), "")


def _key_prefixes() -> tuple[str, ...]:
    """Accepted key prefixes, or () for a provider we do not support."""
    return PROVIDER_KEY_PREFIXES.get(ai_provider(), ())


def _api_key() -> str:
    """Provider key. The provider-specific variable wins, then the generic one.

    Only read for a supported provider, so a key can never be addressed to an endpoint
    this build does not know.
    """
    if ai_provider() not in PROVIDER_URLS:
        return ""
    specific = os.environ.get("NVIDIA_API_KEY", "").strip()
    return specific or os.environ.get("AI_API_KEY", "").strip()


def _key_looks_valid() -> bool:
    key = _api_key()
    prefixes = _key_prefixes()
    return bool(key) and bool(prefixes) and key.startswith(prefixes)


def _timeout_s() -> int:
    """Wall-clock cap on ONE provider call. NVIDIA NIM is slow, so allow tuning."""
    raw = os.environ.get("AI_TIMEOUT_S", "").strip()
    if raw.isdigit() and int(raw) > 0:
        return min(int(raw), 120)
    return 30


# ---------------------------------------------------------------- request budget
# AI_TIMEOUT_S bounds one call. One /ask can make up to FOUR calls in series (up to three
# `select_next_tool` picks plus one `explain_evidence`), and nothing bounded the sum: the
# agent loop's own budget is checked BEFORE a call is dispatched, so the last pick could
# start just under the line and run a further AI_TIMEOUT_S, and `explain_evidence` then ran
# afterwards with no budget check at all. Measured at ~12 s per call that is ~48 s, and at
# the timeout it is 90 s. This deadline bounds the whole request instead.
_DEADLINE: ContextVar[int | None] = ContextVar("rz_provider_deadline", default=None)

# Do not start a call that cannot plausibly finish: a NIM rewrite needs ~10-14 s, so
# dispatching one with a couple of seconds left just buys a guaranteed timeout.
# Integer nanoseconds throughout, matching agent_loop.MAX_NS and keeping NN-1's no-float
# scan satisfied without an allow-list entry.
MIN_CALL_NS = 8_000_000_000
_NS_PER_S = 1_000_000_000


def total_budget_s() -> int:
    """Wall-clock cap on ALL provider calls for one request."""
    raw = os.environ.get("AI_TOTAL_BUDGET_S", "").strip()
    if raw.isdigit() and int(raw) > 0:
        return min(int(raw), 300)
    return 40


@contextmanager
def request_budget(seconds: int | None = None) -> Iterator[None]:
    """Open a shared deadline for every provider call made inside this block.

    Nested blocks keep the earliest deadline, so a helper cannot widen the budget its
    caller set. Uses a ContextVar, so concurrent requests never share a deadline.
    """
    budget_ns = (total_budget_s() if seconds is None else int(seconds)) * _NS_PER_S
    candidate = time.monotonic_ns() + budget_ns
    existing = _DEADLINE.get()
    token = _DEADLINE.set(candidate if existing is None else min(existing, candidate))
    try:
        yield
    finally:
        _DEADLINE.reset(token)


def remaining_ns() -> int | None:
    """Nanoseconds left in the request budget, or None when no budget is open."""
    deadline = _DEADLINE.get()
    return None if deadline is None else deadline - time.monotonic_ns()


def budget_exhausted() -> bool:
    """True when there is not enough budget left to be worth dispatching a call."""
    left = remaining_ns()
    return left is not None and left < MIN_CALL_NS


def _effective_timeout() -> int:
    """Per-call timeout in seconds, clamped to whatever the request budget has left."""
    call_cap = _timeout_s()
    left = remaining_ns()
    if left is None:
        return call_cap
    return max(1, min(call_cap, left // _NS_PER_S))


def _reasoning_headroom() -> int:
    """Extra completion tokens for endpoints that bill hidden reasoning against max_tokens.

    On NVIDIA NIM, gpt-oss emits several hundred reasoning tokens before any content, so a
    tight budget truncates the real payload mid-string.
    """
    raw = os.environ.get("AI_REASONING_HEADROOM", "").strip()
    if raw.isdigit():
        return min(int(raw), 4000)
    return 1200 if ai_provider() in {"nvidia", "nim"} else 0


def _budget(base: int) -> int:
    return base + _reasoning_headroom()


def live_enabled() -> bool:
    """True only in a real desk process, with a supported provider and a plausible key.

    Off under pytest unless RZ_LLM_TEST=1, and off whenever RZ_LLM=0.
    """
    if os.environ.get("PYTEST_CURRENT_TEST") and os.environ.get("RZ_LLM_TEST") != "1":
        return False
    if (os.environ.get("RZ_LLM") or "").strip() == "0":
        return False
    if not provider_url():
        return False
    if ai_provider() in OFF_PROVIDERS:
        return False
    return _key_looks_valid()


def record_live_result(*, ok: bool, error: str = "", llm_picks: int | None = None) -> None:
    """Remember the last live attempt. Never stores the key."""
    _LAST["probed"] = True
    _LAST["ok"] = bool(ok)
    _LAST["error"] = str(error or "")
    if llm_picks is not None:
        _LAST["llm_picks"] = int(llm_picks)


def desk_ai_status() -> dict[str, Any]:
    """Honest capability card. The live flag is YES only after a successful rewrite."""
    key = _key_looks_valid()
    live = live_enabled()
    provider = ai_provider()
    if _LAST["ok"]:
        live_provider = "YES"
    elif not key:
        live_provider = "OFF"
    else:
        live_provider = "UNAVAILABLE"
    tool_loop = "YES" if _LAST.get("llm_picks") else "UNAVAILABLE"
    err = str(_LAST.get("error") or "")
    note = (
        "Deterministic tools are financial truth. "
        f"A key for {provider} does not mean a live rewrite succeeded. "
        "A provider failure falls back to templates. Overlay does not write CLEARED."
    )
    if err:
        note = f"Last live error: {err}. Fallback templates. Overlay does not write CLEARED."
    return {
        # Kept as LIVE_PROVIDER for artifact/report compatibility; it means "live provider".
        # Written once: the key was repeated on consecutive lines, which is inert but reads
        # as though two different values were intended.
        "LIVE_PROVIDER": live_provider,
        "provider": provider,
        "endpoint": provider_url(),
        "LIVE_LLM_TOOL_LOOP": tool_loop,
        "DETERMINISTIC_CONTROLLER": "PASS",
        "key_present": key,
        "live_enabled": live,
        "probed": bool(_LAST.get("probed")),
        "error": err,
        "fallback": live_provider != "YES",
        "model": provider_model() if live else "",
        "note": note,
        "writes_cleared": False,
    }


def _strip_money(text: str) -> str:
    return MONEY_PATTERN.sub("—", text)


def _unsafe_clear_claim(text: str) -> bool:
    if "does not write CLEARED" in text:
        lowered = text.replace("does not write CLEARED", "")
        return "CLEARED" in lowered
    return "CLEARED" in text


def _message_text(message: dict[str, Any]) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or ""))
        return " ".join(p for p in parts if p).strip()
    # `reasoning` / `reasoning_content` are raw chain-of-thought on reasoning models such as
    # gpt-oss on NVIDIA NIM. They are deliberately not used as an answer: they are unvalidated
    # scratch text and can restate a claim the deterministic engine never made. An empty
    # content field means the caller falls back to the deterministic template.
    return ""


def _default_post(url: str, api_key: str, body: bytes) -> dict[str, Any]:
    provider = ai_provider()
    if not url or url not in PROVIDER_URLS.values():
        # Defence in depth. live_enabled() already refuses an unsupported provider, but the
        # bearer token is attached one line below and must never leave for an endpoint this
        # build does not recognise.
        raise ProviderError(f"{provider} is not a supported provider; no request was sent")
    req = Request(url, data=body, method="POST")
    req.add_header("Authorization", "Bearer " + api_key)
    req.add_header("Content-Type", "application/json")
    try:
        with urlopen(req, timeout=_effective_timeout()) as resp:
            raw = resp.read()
    except HTTPError as exc:
        hint = f"{provider} http {exc.code}"
        try:
            parsed = json.loads(exc.read().decode("utf-8", errors="replace"))
            err = parsed.get("error")
            if isinstance(err, dict):
                code = str(err.get("code") or "").strip()
                if code:
                    hint = f"{provider} http {exc.code} {code}"
            elif isinstance(parsed.get("title"), str):
                hint = f"{provider} http {exc.code} {parsed['title'].strip()}"
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
            pass
        raise ProviderError(hint) from None
    except TimeoutError:
        raise ProviderError(f"{provider} timeout after {_timeout_s()}s") from None
    except URLError as exc:
        reason = getattr(exc, "reason", "")
        if isinstance(reason, TimeoutError) or "timed out" in str(reason).casefold():
            raise ProviderError(f"{provider} timeout after {_timeout_s()}s") from None
        raise ProviderError(f"{provider} unreachable") from None
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProviderError(f"{provider} returned non-json") from exc
    if not isinstance(parsed, dict):
        raise ProviderError(f"{provider} returned a non-object")
    return parsed


def rewrite(
    question: str,
    facts: str,
    post_json: PostJson | None = None,
) -> tuple[str, str]:
    """Return (prose, error). Empty prose means fall back to facts. Never returns CLEARED writes."""
    if not live_enabled():
        return "", "live provider off"
    if budget_exhausted():
        record_live_result(ok=False, error="request budget exhausted")
        return "", "request budget exhausted"
    key = _api_key()
    q = _strip_money(question.strip())
    blob = _strip_money(facts.strip())
    if not blob:
        return "", "empty facts"
    user = "QUESTION: " + q + "\nFACTS: " + blob
    outbound = (_SYSTEM + "\n" + user).encode("utf-8")
    try:
        assert_no_amounts(outbound)
        assert_no_pii(outbound)
    except (AmountLeakError, PiiLeakError) as exc:
        return "", str(exc)
    payload = json.dumps(
        {
            "model": provider_model(),
            "messages": [
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": user},
            ],
            "max_tokens": _budget(400),
        }
    ).encode("utf-8")
    sender = post_json if post_json is not None else _default_post
    try:
        data = sender(provider_url(), key, payload)
    except ProviderError as exc:
        record_live_result(ok=False, error=str(exc))
        return "", str(exc)
    err_obj = data.get("error")
    if isinstance(err_obj, dict):
        code = str(err_obj.get("code") or "error").strip()
        record_live_result(ok=False, error="provider " + code)
        return "", "provider " + code
    # Every failure below must be recorded, or a stale success keeps the status card
    # reading LIVE=YES after the provider started returning nothing (found 2026-09).
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        record_live_result(ok=False, error="provider returned no usable content")
        return "", "provider returned no usable content"
    first = choices[0]
    if not isinstance(first, dict):
        record_live_result(ok=False, error="provider returned no usable content")
        return "", "provider returned no usable content"
    message = first.get("message")
    if not isinstance(message, dict):
        record_live_result(ok=False, error="provider returned no usable content")
        return "", "provider returned no usable content"
    prose = _message_text(message)
    if not prose:
        record_live_result(ok=False, error="provider returned no usable content")
        return "", "provider returned no usable content"
    try:
        assert_no_amounts(prose.encode("utf-8"))
        assert_no_pii(prose.encode("utf-8"))
    except (AmountLeakError, PiiLeakError) as exc:
        record_live_result(ok=False, error=str(exc))
        return "", str(exc)
    if _unsafe_clear_claim(prose):
        record_live_result(ok=False, error="cleared claim")
        return "", "cleared claim"
    record_live_result(ok=True, error="")
    return prose, ""


_EXPLAIN_SYSTEM = (
    "You are the AI Finance Controller for Residual Zero. "
    "The deterministic reconciliation engine is financial truth. "
    "You only explain the EVIDENCE JSON. "
    "Never invent transaction IDs, amounts, dates, counts, statuses, tax values, or missing records. "
    "Never say a credit is CLEARED unless evidence.disposition is CLEARED. "
    "Never claim uniqueness UNIQUE unless solution_count is 1. "
    "Never claim residual-zero unless residual_paise is 0. "
    "Never authorize a financial clear. "
    "Never output an AI confidence percentage. "
    "If evidence is insufficient, say the records do not support a conclusive answer. "
    "Overlay does not write CLEARED. Copy figures from EVIDENCE only."
)


def explain_evidence(
    question: str,
    evidence: dict[str, Any],
    fallback: str,
    post_json: PostJson | None = None,
) -> tuple[str, str, dict[str, int]]:
    """Rewrite FALLBACK using EVIDENCE. Amounts are allowed only if they appear in EVIDENCE.

    Returns (prose, error, usage). Empty prose means the caller must keep fallback.
    """
    usage = {"prompt_tokens": 0, "completion_tokens": 0}
    if not live_enabled():
        return "", "live provider off", usage
    if budget_exhausted():
        record_live_result(ok=False, error="request budget exhausted")
        return "", "request budget exhausted", usage
    key = _api_key()
    blob = json.dumps(evidence, default=str)
    user = "QUESTION: " + question.strip() + "\nEVIDENCE: " + blob + "\nFALLBACK: " + fallback
    try:
        assert_no_pii(user.encode("utf-8"))
    except PiiLeakError as exc:
        return "", str(exc), usage
    payload = json.dumps(
        {
            "model": provider_model(),
            "messages": [
                {"role": "system", "content": _EXPLAIN_SYSTEM},
                {"role": "user", "content": user},
            ],
            "max_tokens": _budget(700),
        }
    ).encode("utf-8")
    sender = post_json if post_json is not None else _default_post
    try:
        data = sender(provider_url(), key, payload)
    except ProviderError as exc:
        record_live_result(ok=False, error=str(exc))
        return "", str(exc), usage
    err_obj = data.get("error")
    if isinstance(err_obj, dict):
        err = "provider " + str(err_obj.get("code") or "error").strip()
        record_live_result(ok=False, error=err)
        return "", err, usage
    raw_usage = data.get("usage")
    if isinstance(raw_usage, dict):
        usage["prompt_tokens"] = int(raw_usage.get("prompt_tokens") or 0)
        usage["completion_tokens"] = int(raw_usage.get("completion_tokens") or 0)
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        record_live_result(ok=False, error="provider returned no usable content")
        return "", "provider returned no usable content", usage
    first = choices[0]
    if not isinstance(first, dict):
        record_live_result(ok=False, error="provider returned no usable content")
        return "", "provider returned no usable content", usage
    message = first.get("message")
    if not isinstance(message, dict):
        record_live_result(ok=False, error="provider returned no usable content")
        return "", "provider returned no usable content", usage
    prose = _message_text(message)
    if not prose:
        record_live_result(ok=False, error="provider returned no usable content")
        return "", "provider returned no usable content", usage
    try:
        assert_no_pii(prose.encode("utf-8"))
    except PiiLeakError as exc:
        record_live_result(ok=False, error=str(exc))
        return "", str(exc), usage
    if _unsafe_clear_claim(prose):
        record_live_result(ok=False, error="cleared claim")
        return "", "cleared claim", usage
    record_live_result(ok=True, error="")
    return prose, "", usage


_NEXT_SYSTEM = (
    "You pick the next read-only finance tool. "
    "Return JSON only: {\"tool\": \"name\", \"arguments\": {}, \"stop\": false}. "
    "Use stop true when enough evidence exists. "
    "Never invent a tool name. Never authorize a clear. Never say CLEARED."
)


def select_next_tool(
    question: str,
    called: list[str],
    remaining: list[str],
    credit_id: str = "",
    post_json: PostJson | None = None,
) -> tuple[dict[str, Any], str]:
    """Ask the provider which allowlisted tool to run next. Empty dict means stop/fallback."""
    if not live_enabled():
        return {}, "live provider off"
    if budget_exhausted():
        return {}, "request budget exhausted"
    key = _api_key()
    user = (
        "QUESTION: " + question.strip()
        + "\nCREDIT: " + credit_id
        + "\nCALLED: " + ",".join(called)
        + "\nREMAINING: " + ",".join(remaining[:40])
        + "\nReturn one tool from REMAINING or stop."
    )
    try:
        assert_no_pii(user.encode("utf-8"))
        assert_no_amounts(user.encode("utf-8"))
    except (AmountLeakError, PiiLeakError) as exc:
        return {}, str(exc)
    payload = json.dumps(
        {
            "model": provider_model(),
            "messages": [
                {"role": "system", "content": _NEXT_SYSTEM},
                {"role": "user", "content": user},
            ],
            "max_tokens": _budget(80),
        }
    ).encode("utf-8")
    sender = post_json if post_json is not None else _default_post
    try:
        data = sender(provider_url(), key, payload)
    except ProviderError as exc:
        record_live_result(ok=False, error=str(exc))
        return {}, str(exc)
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        return {}, "provider returned no usable content"
    first = choices[0]
    if not isinstance(first, dict):
        return {}, "provider returned no usable content"
    message = first.get("message")
    if not isinstance(message, dict):
        return {}, "provider returned no usable content"
    tool_calls = message.get("tool_calls")
    if isinstance(tool_calls, list) and tool_calls:
        call = tool_calls[0]
        if isinstance(call, dict):
            fn = call.get("function") if isinstance(call.get("function"), dict) else {}
            name = str(fn.get("name") or "")
            raw_args = fn.get("arguments") or "{}"
            parsed_args: dict[str, Any] = {}
            if isinstance(raw_args, str):
                try:
                    loaded = json.loads(raw_args)
                    if isinstance(loaded, dict):
                        parsed_args = loaded
                except json.JSONDecodeError:
                    parsed_args = {}
            if name in remaining:
                return {"tool": name, "arguments": parsed_args, "stop": False}, ""
            return {}, "unknown_tool"
    prose = _message_text(message)
    if not prose:
        return {}, "provider returned no usable content"
    if _unsafe_clear_claim(prose):
        return {}, "cleared claim"
    try:
        blob = json.loads(prose[prose.find("{") : prose.rfind("}") + 1] if "{" in prose else prose)
    except json.JSONDecodeError:
        return {}, "provider response was not JSON"
    if not isinstance(blob, dict):
        return {}, "provider response was not JSON"
    if blob.get("stop") is True or str(blob.get("tool") or "").casefold() == "stop":
        return {"stop": True}, ""
    name = str(blob.get("tool") or "")
    if name not in remaining:
        return {}, "unknown_tool"
    args = blob.get("arguments") if isinstance(blob.get("arguments"), dict) else {}
    return {"tool": name, "arguments": args, "stop": False}, ""

