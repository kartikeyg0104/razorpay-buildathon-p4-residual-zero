"""MCP JSON-RPC stdio server. Read-only. Capture/refund stay refused."""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

from residual_zero.mcp.protocol import encode_message, handle_rpc, read_message, serve
from residual_zero.mcp.registry import call_tool, list_tools


def test_initialize_and_tools_list():
    listed = {row["name"] for row in list_tools()}
    assert "fetch_settlement_recon_details" in listed
    assert "desk_status" in listed
    assert "close_ops" in listed
    assert "standup" in listed
    assert "ask_controller" in listed
    assert "credit_proof" in listed
    assert "capture_payment" not in listed
    reply = handle_rpc(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "t"}},
        }
    )
    assert reply is not None
    assert reply["result"]["protocolVersion"] == "2025-03-26"
    assert reply["result"]["serverInfo"]["name"] == "residual-zero"
    assert "does not write CLEARED" in reply["result"]["instructions"]


def test_tools_call_recon_is_fixture_and_writes_nothing():
    reply = handle_rpc(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "fetch_settlement_recon_details",
                "arguments": {"year": 2025, "month": 1},
            },
        }
    )
    assert reply is not None
    assert reply["result"]["isError"] is False
    payload = json.loads(reply["result"]["content"][0]["text"])
    assert payload["ok"] is True
    assert payload["source"] == "fixture"
    assert payload["n"] == 3
    assert payload["written"] is False
    assert payload["cleared"] == 0
    assert payload["ledger_hits"] == 0


def test_tools_call_refuses_capture():
    reply = handle_rpc(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "capture_payment", "arguments": {}},
        }
    )
    assert reply is not None
    assert reply["result"]["isError"] is True
    payload = json.loads(reply["result"]["content"][0]["text"])
    assert payload["written"] is False
    assert "capture_payment" in payload["error"]


def test_credit_proof_does_not_clear():
    got = call_tool("credit_proof", {"credit_id": "crd_001_acc_01_2025-01-09"})
    assert got["id"] == "crd_001_acc_01_2025-01-09"
    assert got["writes_cleared"] is False
    assert got["cleared"] == 0
    assert got["mcp"]["credit_hits"] == 0
    assert got["mcp"]["written"] is False


def test_desk_status_stdio_line():
    got = call_tool("desk_status", {})
    assert got["cleared"] == 0
    assert got["writes_cleared"] is False
    assert got["stdio"] == "python -m residual_zero.mcp"
    assert "desk_status" in got["allowed"]
    assert "close_ops" in got["allowed"]
    ops = call_tool("close_ops", {})
    assert ops["writes_cleared"] is False
    assert ops.get("plugged") is False
    standup = call_tool("standup", {})
    assert standup["writes_cleared"] is False
    assert "Residual Zero standup" in standup["markdown"]


def test_content_length_roundtrip():
    incoming = BytesIO(
        encode_message({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    )
    outgoing = BytesIO()
    serve(incoming, outgoing)
    outgoing.seek(0)
    reply = read_message(outgoing)
    assert reply is not None
    assert reply["id"] == 1
    assert reply["result"]["serverInfo"]["name"] == "residual-zero"


def test_ask_controller_tool_does_not_clear():
    got = call_tool("ask_controller", {"question": "why is search auto-clear 0"})
    assert got["writes_cleared"] is False
    assert got["trained"] is True
    assert "does not write CLEARED" in got["answer"]

    root = Path("src/residual_zero/mcp")
    blob = "\n".join(p.read_text(encoding="utf-8") for p in root.rglob("*.py"))
    assert "open_verify" not in blob
    assert "write_cleared" not in blob
