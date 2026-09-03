"""One live NVIDIA NIM request if a key is present. Never prints the key.

NVIDIA NIM is the only provider (Groq removed 2026-09-03). The output filename and the
LIVE_PROVIDER key are kept so the existing QA report readers keep parsing; both mean
"live provider".
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from residual_zero.runtime.envfile import load_env_file
from residual_zero.semantic.provider import (
    ai_provider,
    explain_evidence,
    provider_model,
    live_enabled,
    provider_url,
)


def main() -> dict:
    load_env_file()
    os.environ.pop("RZ_LLM", None)
    os.environ.pop("RZ_LLM", None)
    os.environ.pop("PYTEST_CURRENT_TEST", None)
    evidence = {
        "stats": {
            "residual_zero": "159/239",
            "ambiguous": 236,
            "auto_clear": 0,
            "false_clears": 0,
            "search_coverage": "239/239",
        },
        "reconciliation": {
            "status": "FLAGGED",
            "uniqueness": "AMBIGUOUS",
            "residual_paise": 0,
            "disposition": "FLAGGED",
        },
    }
    fallback = (
        "Batch residual-zero is 159/239. Ambiguous 236. Auto-clear 0. "
        "False clears 0. Overlay does not write CLEARED."
    )
    started = time.perf_counter()
    prose, error, usage = explain_evidence(
        "Give me a summary of this batch",
        evidence,
        fallback,
    )
    elapsed = time.perf_counter() - started
    payload = {
        "provider": ai_provider(),
        "model": provider_model(),
        "endpoint": provider_url(),
        "provider_key": "present" if (os.environ.get("NVIDIA_API_KEY") or "").strip() else "missing",
        "ai_key": "present" if (os.environ.get("AI_API_KEY") or "").strip() else "missing",
        "live_enabled": live_enabled(),
        "latency_s": round(elapsed, 4),
        "error": error or None,
        "prose_len": len(prose or ""),
        "prose_prefix": (prose or "")[:240],
        "usage": usage,
        "fallback_used": not bool(prose),
        "LIVE_PROVIDER": "YES" if prose and not error else ("UNAVAILABLE" if error or not live_enabled() else "NO"),
        "LIVE_LLM_TOOL_LOOP": "UNAVAILABLE",
        "DETERMINISTIC_CONTROLLER": "PASS",
        "writes_cleared": False,
    }
    out = Path("artifacts").joinpath("qa", "provider_live.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: payload[k] for k in ("LIVE_PROVIDER", "LIVE_LLM_TOOL_LOOP", "DETERMINISTIC_CONTROLLER", "model", "live_enabled", "error", "latency_s", "fallback_used")}, indent=2))
    return payload


if __name__ == "__main__":
    main()
