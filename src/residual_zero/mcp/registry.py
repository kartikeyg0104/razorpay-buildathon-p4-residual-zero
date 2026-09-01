"""MCP tool registry. Same names as Razorpay settlement fetches, plus the desk."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from residual_zero.ingest.mcp_settlements import (
    ALLOWED_TOOLS,
    REFUSED_TOOLS,
    SettlementMcp,
    match_recon_to_ledger,
    match_settlements_to_credit,
)
from residual_zero.ingest.razorpay import parse_recon_combined
from residual_zero.money import format_rupees

DEMO_CREDIT = "crd_001_acc_01_2025-01-09"
SERVER_NAME = "residual-zero"
SERVER_VERSION = "0.1.0"
INSTRUCTIONS = (
    "Residual Zero is a read-only settlement recon desk. "
    "Search auto-clear is 0. Overlay does not write CLEARED. "
    "Use the Razorpay settlement fetch tools, then lookup_credit / credit_proof / ask_controller. "
    "capture_payment, create_refund, create_instant_settlement, and OTP are refused."
)

DESK_TOOLS = frozenset(
    {
        "desk_status",
        "lookup_credit",
        "credit_proof",
        "match_recon",
        "ask_controller",
        "finance_tool",
        "close_ops",
        "standup",
    }
)


def _object_schema(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "object", "properties": properties, "additionalProperties": False}
    if required:
        schema["required"] = required
    return schema


TOOL_DEFS: tuple[dict[str, Any], ...] = (
    {
        "name": "fetch_settlement_recon_details",
        "description": (
            "Razorpay GET /v1/settlements/recon/combined. Members are matched to the local "
            "ledger. A hit is not a clear. Default is a labelled fixture."
        ),
        "inputSchema": _object_schema(
            {
                "year": {"type": "integer", "minimum": 2000, "maximum": 2100},
                "month": {"type": "integer", "minimum": 1, "maximum": 12},
                "day": {"type": "integer", "minimum": 1, "maximum": 31},
                "count": {"type": "integer", "minimum": 1},
                "skip": {"type": "integer", "minimum": 0},
            },
            ["year", "month"],
        ),
    },
    {
        "name": "fetch_all_settlements",
        "description": "Razorpay GET /v1/settlements. Read-only. Does not write CLEARED.",
        "inputSchema": _object_schema(
            {
                "count": {"type": "integer", "minimum": 1},
                "skip": {"type": "integer", "minimum": 0},
            }
        ),
    },
    {
        "name": "fetch_settlement_with_id",
        "description": "Razorpay GET /v1/settlements/:id. settlement_id must start with setl_.",
        "inputSchema": _object_schema(
            {"settlement_id": {"type": "string"}, "id": {"type": "string"}},
        ),
    },
    {
        "name": "fetch_all_instant_settlements",
        "description": "Razorpay GET /v1/settlements/ondemand. create_instant_settlement is refused.",
        "inputSchema": _object_schema(
            {
                "count": {"type": "integer", "minimum": 1},
                "skip": {"type": "integer", "minimum": 0},
            }
        ),
    },
    {
        "name": "fetch_instant_settlement_with_id",
        "description": "Razorpay GET /v1/settlements/ondemand/:id. Id must start with setlod_.",
        "inputSchema": _object_schema(
            {"settlement_id": {"type": "string"}, "id": {"type": "string"}},
        ),
    },
    {
        "name": "desk_status",
        "description": "Residual Zero overlay KPIs. Search auto-clear 0. Overlay does not write CLEARED.",
        "inputSchema": _object_schema({}),
    },
    {
        "name": "lookup_credit",
        "description": "Find bank credits by id prefix or account. Read-only.",
        "inputSchema": _object_schema({"q": {"type": "string"}}, ["q"]),
    },
    {
        "name": "credit_proof",
        "description": (
            "Gate A / uniqueness for one credit, plus MCP recon members matched to that "
            "credit's declared set. Never writes CLEARED."
        ),
        "inputSchema": _object_schema({"credit_id": {"type": "string"}}, ["credit_id"]),
    },
    {
        "name": "match_recon",
        "description": "Parse a recon JSON or MCP envelope and mark ledger hits. Never writes.",
        "inputSchema": _object_schema({"payload": {"type": "object"}}, ["payload"]),
    },
    {
        "name": "ask_controller",
        "description": (
            "AI finance controller. Deterministic tools first; optional NVIDIA NIM explanation. "
            "Never writes CLEARED. Eval A3 stays stub."
        ),
        "inputSchema": _object_schema(
            {"question": {"type": "string"}, "credit_id": {"type": "string"}},
            ["question"],
        ),
    },
    {
        "name": "finance_tool",
        "description": (
            "Call a read-only structured finance tool (get_transaction, get_batch_summary, …). "
            "Never writes CLEARED."
        ),
        "inputSchema": _object_schema(
            {"name": {"type": "string"}, "arguments": {"type": "object"}},
            ["name"],
        ),
    },
    {
        "name": "close_ops",
        "description": (
            "Month-end ops JSON: cash bridge, tax radar, exposure rank, duplicate UTR, "
            "four-way gaps. Residual unplugged. Never writes CLEARED."
        ),
        "inputSchema": _object_schema({}),
    },
    {
        "name": "standup",
        "description": "Deterministic close-day briefing markdown. Overlay does not write CLEARED.",
        "inputSchema": _object_schema({}),
    },
)


def _console_route(path: str):
    from residual_zero.console.app import app as _app

    for route in _app.routes:
        if getattr(route, "path", "") == path:
            return route.endpoint()
    return None


def _console_json(path: str) -> dict[str, Any] | None:
    resp = _console_route(path)
    if resp is None:
        return None
    return json.loads(resp.body.decode("utf-8"))


def _console_text(path: str) -> str | None:
    resp = _console_route(path)
    if resp is None:
        return None
    return resp.body.decode("utf-8")


def list_tools() -> list[dict[str, Any]]:
    return [dict(row) for row in TOOL_DEFS]


def ledger_ids() -> set[str]:
    rendered = Path("data").joinpath("dev", "rendered")
    if not rendered.is_dir():
        return set()
    from residual_zero.ingest.csv_ledger import load_ledger_items
    from residual_zero.ingest.source_root import SourceRoot

    return {item.id for item in load_ledger_items(SourceRoot(rendered))}


def declared_ids_for(credit_id: str) -> set[str]:
    rendered = Path("data").joinpath("dev", "rendered")
    if not rendered.is_dir():
        return set()
    from residual_zero.ingest.settlement_report import load_settlement_report
    from residual_zero.ingest.source_root import SourceRoot

    return {row.item_id for row in load_settlement_report(SourceRoot(rendered)) if row.credit_id == credit_id}


def call_tool(
    name: str,
    arguments: Mapping[str, Any] | None = None,
    ids: set[str] | None = None,
) -> dict[str, Any]:
    tool = str(name or "").strip()
    args = dict(arguments or {})
    if tool in REFUSED_TOOLS:
        raise ValueError(
            f"MCP tool {tool!r} writes or captures. Residual Zero is read-only settlement recon."
        )
    member_ids = ids if ids is not None else ledger_ids()
    if tool in ALLOWED_TOOLS:
        result = SettlementMcp.from_config().invoke(tool, args, ledger_ids=member_ids)
        credit_id = str(args.get("credit_id") or "")
        if credit_id:
            result = match_recon_to_ledger(result, member_ids, declared_ids_for(credit_id))
            utr = str(args.get("utr") or "")
            if utr:
                result = match_settlements_to_credit(result, utr)
        return result
    if tool == "desk_status":
        return _desk_status()
    if tool == "lookup_credit":
        return _lookup(str(args.get("q") or ""))
    if tool == "credit_proof":
        return credit_preview(str(args.get("credit_id") or ""), member_ids)
    if tool == "match_recon":
        payload = args.get("payload")
        if not isinstance(payload, dict):
            raise ValueError("match_recon needs a JSON object payload")
        return _match_payload(payload, member_ids)
    if tool == "ask_controller":
        from residual_zero.qa.controller import answer as controller_answer

        return controller_answer(str(args.get("question") or ""), str(args.get("credit_id") or ""))
    if tool == "finance_tool":
        from residual_zero.qa.finance_tools import call_finance_tool

        inner = args.get("arguments")
        payload = inner if isinstance(inner, dict) else {}
        return call_finance_tool(str(args.get("name") or ""), payload)
    if tool == "close_ops":
        payload = _console_json("/api/ops")
        if payload is None:
            return {"ok": False, "error": "ops_unwired", "writes_cleared": False}
        payload["writes_cleared"] = False
        return payload
    if tool == "standup":
        text = _console_text("/standup.md")
        if text is None:
            return {"ok": False, "error": "standup_unwired", "writes_cleared": False}
        return {"ok": True, "markdown": text, "writes_cleared": False}
    raise ValueError(
        f"MCP tool {tool!r} is not wired. Allowed: "
        f"{', '.join(sorted(ALLOWED_TOOLS | DESK_TOOLS))}."
    )


def _match_payload(payload: Mapping[str, Any], ids: set[str]) -> dict[str, Any]:
    parsed = parse_recon_combined(payload)
    rows = [
        {
            "settlement": row.settlement_id,
            "item": row.item_id,
            "kind": row.kind.value,
            "amount": format_rupees(row.amount_paise),
            "type": row.type_raw,
        }
        for row in parsed
    ]
    result = {"ok": True, "n": len(rows), "rows": rows, "written": False, "cleared": 0}
    return match_recon_to_ledger(result, ids)


def _desk_status() -> dict[str, Any]:
    from residual_zero.console.app import _honesty_now, _overlay, _split
    from residual_zero.ingest.mcp_settlements import load_adapter_flags

    overlay = _overlay()
    split = _split()
    n_posted = len(split[1]) if split is not None else 0
    n_gate = overlay.n_ok if overlay is not None else 0
    n_journal = overlay.n_journalable if overlay is not None else 0
    n_human = n_posted - n_gate if n_posted >= n_gate else 0
    enabled, _key, _secret = load_adapter_flags()
    return {
        "ok": True,
        "cleared": 0,
        "gate_a": n_gate,
        "journalable": n_journal,
        "mismatch": overlay.n_mismatch if overlay is not None else 0,
        "human": n_human,
        "posted": n_posted,
        "demo_credit": DEMO_CREDIT,
        "honesty": _honesty_now(n_human),
        "writes_cleared": False,
        "mcp_live": enabled,
        "stdio": "python -m residual_zero.mcp",
        "allowed": sorted(ALLOWED_TOOLS | DESK_TOOLS),
        "refused": sorted(REFUSED_TOOLS),
    }


def _lookup(needle: str) -> dict[str, Any]:
    from residual_zero.console.app import _credit_lookup, _overlay
    from residual_zero.money import format_rupees as rupees

    q = needle.strip().casefold()
    lookup = _credit_lookup()
    overlay = _overlay()
    ranked: list[dict[str, str]] = []
    rest: list[dict[str, str]] = []
    for cid, credit in lookup.items():
        gate = overlay.by_id.get(cid) if overlay is not None else None
        blob = " ".join((cid, credit.account_id)).casefold()
        row = {
            "id": cid,
            "amount": rupees(credit.amount_paise),
            "account": credit.account_id,
            "date": credit.value_date.isoformat(),
            "gate": "GATE_A" if gate is not None and gate.ok else "REFUSED",
            "href": "/credit/" + cid,
        }
        if not q:
            rest.append(row)
        elif cid.casefold() == q or cid.casefold().startswith(q):
            ranked.append(row)
        elif q in blob:
            rest.append(row)
    rows = (ranked + rest)[:40]
    return {"ok": True, "n": len(rows), "rows": rows, "written": False, "cleared": 0}


def credit_preview(credit_id: str, ids: set[str] | None = None) -> dict[str, Any]:
    """Desk proof plus MCP recon overlap for one credit. Never writes CLEARED."""
    from residual_zero.console.app import _credit_lookup, _overlay
    from residual_zero.money import format_rupees as rupees

    cid = str(credit_id or "").strip()
    if not cid:
        raise ValueError("credit_id is required")
    lookup = _credit_lookup()
    credit = lookup.get(cid)
    overlay = _overlay()
    gate = overlay.by_id.get(cid) if overlay is not None else None
    member_ids = ids if ids is not None else ledger_ids()
    declared = declared_ids_for(cid)
    recon = SettlementMcp.from_config().invoke(
        "fetch_settlement_recon_details",
        {"year": 2025, "month": 1},
        ledger_ids=member_ids,
    )
    recon = match_recon_to_ledger(recon, member_ids, declared)
    listing = SettlementMcp.from_config().invoke("fetch_all_settlements", {"count": 10})
    utr = credit.utr if credit is not None else ""
    listing = match_settlements_to_credit(listing, utr or "")
    journalable = overlay is not None and cid in overlay.journalable
    return {
        "ok": credit is not None or gate is not None,
        "id": cid,
        "amount": rupees(credit.amount_paise) if credit is not None else "",
        "account": credit.account_id if credit is not None else "",
        "date": credit.value_date.isoformat() if credit is not None else "",
        "utr": utr or "",
        "gate_a_ok": bool(gate is not None and gate.ok),
        "residual_paise": gate.residual_paise if gate is not None else None,
        "journalable": journalable,
        "writes_cleared": False,
        "cleared": 0,
        "mcp": {
            "source": recon.get("source"),
            "n": recon.get("n"),
            "ledger_hits": recon.get("ledger_hits"),
            "credit_hits": recon.get("credit_hits"),
            "utr_hits": listing.get("utr_hits"),
            "written": False,
            "rows": recon.get("rows") or [],
            "settlements": listing.get("settlements") or [],
        },
    }
