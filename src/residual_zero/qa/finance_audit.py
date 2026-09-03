"""Append-only AI audit log. No API keys. Truncated tool payloads."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def audit_path() -> Path:
    raw = os.environ.get("RZ_AI_AUDIT", "").strip()
    if raw:
        return Path(raw)
    return Path("artifacts").joinpath("console", "ai_audit.jsonl")


def _trim(value: Any, depth: int = 0) -> Any:
    if depth > 4:
        return "…"
    if isinstance(value, dict):
        out = {}
        for i, (k, v) in enumerate(value.items()):
            if i >= 40:
                out["…"] = "truncated"
                break
            if k in {"matched_record_ids", "member_ids"} and isinstance(v, list):
                out[k] = v[:12]
            else:
                out[k] = _trim(v, depth + 1)
        return out
    if isinstance(value, list):
        return [_trim(v, depth + 1) for v in value[:20]]
    if isinstance(value, str) and len(value) > 400:
        return value[:400] + "…"
    return value


def record_audit(entry: dict[str, Any]) -> None:
    if os.environ.get("PYTEST_CURRENT_TEST") and not os.environ.get("RZ_AI_AUDIT", "").strip():
        return
    path = audit_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _trim(dict(entry))
    payload.pop("api_key", None)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, default=str) + "\n")
