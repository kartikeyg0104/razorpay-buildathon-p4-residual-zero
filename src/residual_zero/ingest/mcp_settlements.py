"""Razorpay MCP settlement tools. Read-only. Does not spawn their server."""

from __future__ import annotations

import json
import os
from base64 import b64encode
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from residual_zero.ingest.razorpay import MCP_RECON_TOOL, parse_recon_combined
from residual_zero.money import format_rupees

ALLOWED_TOOLS = frozenset(
    {
        "fetch_all_settlements",
        "fetch_settlement_with_id",
        MCP_RECON_TOOL,
        "fetch_all_instant_settlements",
        "fetch_instant_settlement_with_id",
    }
)
REFUSED_TOOLS = frozenset(
    {
        "capture_payment",
        "initiate_payment",
        "create_refund",
        "create_order",
        "create_instant_settlement",
        "create_payment_link",
        "submit_otp",
        "resend_otp",
    }
)
LIVE_HOST = "api.razorpay.com"
GetJson = Callable[[str, str, str], dict[str, Any]]


def load_adapter_flags(path: Path | None = None) -> tuple[bool, str, str]:
    located = path if path is not None else Path("config").joinpath("razorpay.yaml")
    enabled = False
    key_id_env = "RAZORPAY_KEY_ID"
    key_secret_env = "RAZORPAY_KEY_SECRET"
    if located.is_file():
        for line in located.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("enabled:"):
                enabled = stripped.split(":", 1)[1].strip() == "true"
            elif stripped.startswith("key_id_env:"):
                key_id_env = stripped.split(":", 1)[1].strip()
            elif stripped.startswith("key_secret_env:"):
                key_secret_env = stripped.split(":", 1)[1].strip()
    return enabled, os.environ.get(key_id_env, ""), os.environ.get(key_secret_env, "")


def _fixture_dir() -> Path:
    repo = Path(__file__).resolve().parents[3]
    located = repo.joinpath("fixtures").joinpath("recon")
    if located.is_dir():
        return located
    return Path("fixtures").joinpath("recon")


def _clean_id(value: object, prefix: str) -> str:
    text = str(value or "").strip()
    if not text.startswith(prefix):
        raise ValueError(f"id must start with {prefix}")
    rest = text[len(prefix) :]
    if not rest or any(ch not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_" for ch in rest):
        raise ValueError("invalid settlement id")
    return text


def tool_path(tool: str, arguments: Mapping[str, Any]) -> tuple[str, dict[str, str]]:
    """Map an official MCP settlement tool to a GET path. Never a write verb."""
    if tool == "fetch_all_settlements":
        query = {"count": str(int(arguments.get("count") or 10)), "skip": str(int(arguments.get("skip") or 0))}
        return "/v1/settlements", query
    if tool == "fetch_settlement_with_id":
        sid = _clean_id(arguments.get("settlement_id") or arguments.get("id"), "setl_")
        return "/v1/settlements/" + sid, {}
    if tool == "fetch_all_instant_settlements":
        query = {"count": str(int(arguments.get("count") or 10)), "skip": str(int(arguments.get("skip") or 0))}
        return "/v1/settlements/ondemand", query
    if tool == "fetch_instant_settlement_with_id":
        sid = _clean_id(arguments.get("settlement_id") or arguments.get("id"), "setlod_")
        return "/v1/settlements/ondemand/" + sid, {}
    if tool == MCP_RECON_TOOL:
        year = int(arguments.get("year") or 0)
        month = int(arguments.get("month") or 0)
        if year < 2000 or month < 1 or month > 12:
            raise ValueError("fetch_settlement_recon_details needs year and month")
        query = {"year": str(year), "month": f"{month:02d}"}
        if arguments.get("day") not in (None, "", 0, "0"):
            query["day"] = str(int(arguments["day"]))
        if arguments.get("count") not in (None, ""):
            query["count"] = str(int(arguments["count"]))
        if arguments.get("skip") not in (None, ""):
            query["skip"] = str(int(arguments["skip"]))
        return "/v1/settlements/recon/combined", query
    raise ValueError(f"MCP tool {tool!r} is not a settlement fetch")


def live_url(path: str, query: Mapping[str, str]) -> str:
    if not path.startswith("/v1/settlements"):
        raise ValueError("path is not a settlement GET")
    encoded = urlencode(query)
    suffix = "?" + encoded if encoded else ""
    return "https://" + LIVE_HOST + path + suffix


def default_get_json(url: str, key_id: str, key_secret: str) -> dict[str, Any]:
    if not url.startswith("https://" + LIVE_HOST + "/"):
        raise ValueError("refusing host outside api.razorpay.com")
    token = b64encode((key_id + ":" + key_secret).encode("ascii")).decode("ascii")
    req = Request(url, method="GET")
    req.add_header("Authorization", "Basic " + token)
    req.add_header("Accept", "application/json")
    with urlopen(req, timeout=20) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Razorpay GET did not return an object")
    return payload


def _format_recon(payload: Mapping[str, Any]) -> list[dict[str, str]]:
    rows = []
    for row in parse_recon_combined(payload):
        rows.append(
            {
                "settlement": row.settlement_id,
                "item": row.item_id,
                "kind": row.kind.value,
                "amount": format_rupees(row.amount_paise),
                "type": row.type_raw,
            }
        )
    return rows


def _format_settlements(payload: Mapping[str, Any]) -> list[dict[str, str]]:
    items: list[Mapping[str, Any]]
    if payload.get("entity") in {"settlement", "settlement.ondemand"}:
        items = [payload]
    elif isinstance(payload.get("items"), list):
        items = [row for row in payload["items"] if isinstance(row, dict)]
    else:
        raise ValueError("settlement payload missing items")
    out = []
    for row in items:
        amount = row.get("amount")
        if type(amount) is not int:
            raise ValueError("settlement amount must be integer paise")
        out.append(
            {
                "id": str(row.get("id") or ""),
                "amount": format_rupees(amount),
                "status": str(row.get("status") or ""),
                "utr": str(row.get("utr") or ""),
            }
        )
    return out


def _load_fixture(tool: str) -> dict[str, Any]:
    names = {
        "fetch_all_settlements": "mcp_fetch_all_settlements.json",
        "fetch_settlement_with_id": "mcp_fetch_settlement_with_id.json",
        "fetch_all_instant_settlements": "mcp_fetch_all_instant_settlements.json",
        "fetch_instant_settlement_with_id": "mcp_fetch_instant_settlement_with_id.json",
        MCP_RECON_TOOL: "mcp_fetch_settlement_recon_details.json",
    }
    path = _fixture_dir().joinpath(names[tool])
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("fixture is not an object")
    return payload


class SettlementMcp:
    """Official MCP settlement fetches, either labelled fixtures or GET-only live."""

    def __init__(
        self,
        enabled: bool,
        key_id: str = "",
        key_secret: str = "",
        get_json: GetJson | None = None,
    ) -> None:
        self.enabled = enabled
        self._key_id = key_id
        self._secret = key_secret
        self._get_json = get_json

    @classmethod
    def from_config(cls, path: Path | None = None) -> "SettlementMcp":
        enabled, key_id, key_secret = load_adapter_flags(path)
        return cls(enabled, key_id, key_secret)

    def invoke(
        self,
        tool: str,
        arguments: Mapping[str, Any] | None = None,
        ledger_ids: set[str] | None = None,
    ) -> dict[str, Any]:
        name = str(tool or "").strip()
        args = dict(arguments or {})
        if name in REFUSED_TOOLS:
            raise ValueError(
                f"MCP tool {name!r} writes or captures. Residual Zero is read-only settlement recon."
            )
        if name not in ALLOWED_TOOLS:
            raise ValueError(
                f"MCP tool {name!r} is not wired. Allowed: {', '.join(sorted(ALLOWED_TOOLS))}."
            )
        path, query = tool_path(name, args)
        url = live_url(path, query)
        if self.enabled:
            if not self._key_id or not self._secret:
                raise ValueError("adapter enabled but RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET are empty")
            getter = self._get_json if self._get_json is not None else default_get_json
            raw = getter(url, self._key_id, self._secret)
            source = "live"
        else:
            raw = _load_fixture(name)
            source = "fixture"
        if name == MCP_RECON_TOOL:
            rows = _format_recon(raw)
            settlements: list[dict[str, str]] = []
        else:
            rows = []
            settlements = _format_settlements(raw)
        result = {
            "ok": True,
            "tool": name,
            "source": source,
            "written": False,
            "cleared": 0,
            "path": path,
            "url": url if source == "live" else "",
            "n": len(rows) if rows else len(settlements),
            "rows": rows,
            "settlements": settlements,
        }
        return match_recon_to_ledger(result, ledger_ids)


def match_recon_to_ledger(
    result: dict[str, Any],
    ledger_ids: set[str] | None = None,
    credit_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Mark recon members that exist on the local ledger. Never writes CLEARED."""
    ids = ledger_ids or set()
    on_credit = credit_ids or set()
    rows = result.get("rows") or []
    hits = 0
    credit_hits = 0
    for row in rows:
        item = str(row.get("item") or "")
        present = item in ids
        declared = item in on_credit
        row["in_ledger"] = present
        row["in_credit"] = declared
        if present:
            hits += 1
        if declared:
            credit_hits += 1
    result["ledger_hits"] = hits
    result["ledger_misses"] = max(0, len(rows) - hits)
    result["credit_hits"] = credit_hits
    result["cleared"] = 0
    result["written"] = False
    return result


def match_settlements_to_credit(
    result: dict[str, Any],
    utr: str = "",
) -> dict[str, Any]:
    """UTR equality only. Amount matching would guess. Never writes CLEARED."""
    needle = str(utr or "").strip()
    hits = 0
    for row in result.get("settlements") or []:
        matched = bool(needle) and str(row.get("utr") or "").strip() == needle
        row["utr_match"] = matched
        if matched:
            hits += 1
    result["utr_hits"] = hits
    result["cleared"] = 0
    result["written"] = False
    return result
