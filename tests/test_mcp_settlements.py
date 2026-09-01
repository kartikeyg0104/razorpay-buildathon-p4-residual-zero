"""Read-only Razorpay MCP settlement fetches. Write tools stay refused."""

from __future__ import annotations

import json
from pathlib import Path

from residual_zero.ingest.mcp_settlements import (
    ALLOWED_TOOLS,
    MCP_RECON_TOOL,
    REFUSED_TOOLS,
    SettlementMcp,
    live_url,
    load_adapter_flags,
    tool_path,
)
from residual_zero.ingest.razorpay import parse_recon_combined


def test_adapter_flags_default_cut():
    enabled, _key_id, _key_secret = load_adapter_flags()
    assert enabled is False


def test_fixture_recon_invoke_does_not_write():
    client = SettlementMcp(enabled=False)
    got = client.invoke(MCP_RECON_TOOL, {"year": 2025, "month": 1})
    assert got["ok"] is True
    assert got["source"] == "fixture"
    assert got["written"] is False
    assert got["n"] == 3
    assert got["rows"][0]["settlement"] == "setl_sample_01"
    assert got["url"] == ""
    assert got["cleared"] == 0
    assert got["ledger_hits"] == 0
    assert got["rows"][0]["in_ledger"] is False


def test_fixture_settlement_list_and_detail():
    client = SettlementMcp(enabled=False)
    listing = client.invoke("fetch_all_settlements", {"count": 10})
    assert listing["settlements"][0]["id"] == "setl_sample_01"
    detail = client.invoke("fetch_settlement_with_id", {"settlement_id": "setl_sample_01"})
    assert detail["settlements"][0]["utr"] == "RZPSAMPLE01"


def test_write_tools_are_refused():
    client = SettlementMcp(enabled=False)
    for name in ("capture_payment", "create_instant_settlement", "create_refund"):
        try:
            client.invoke(name, {})
        except ValueError as exc:
            assert "read-only" in str(exc) or "writes" in str(exc)
        else:
            raise AssertionError(name)


def test_live_path_is_get_only_and_uses_injected_getter():
    seen: list[str] = []

    def fake_get(url: str, key_id: str, key_secret: str) -> dict:
        seen.append(url)
        assert key_id == "rk"
        return json.loads(Path("fixtures/recon/combined_sample.json").read_text(encoding="utf-8"))

    client = SettlementMcp(enabled=True, key_id="rk", key_secret="rs", get_json=fake_get)
    got = client.invoke(MCP_RECON_TOOL, {"year": 2025, "month": 1, "day": 9})
    assert got["source"] == "live"
    assert seen[0].startswith("https://api.razorpay.com/v1/settlements/recon/combined")
    assert "year=2025" in seen[0]
    assert got["written"] is False


def test_cut_adapter_never_calls_network():
    def boom(url: str, key_id: str, key_secret: str) -> dict:
        raise AssertionError("network " + url)

    client = SettlementMcp(enabled=False, key_id="rk", key_secret="rs", get_json=boom)
    got = client.invoke("fetch_all_settlements", {})
    assert got["source"] == "fixture"


def test_tool_path_rejects_bad_settlement_id():
    try:
        tool_path("fetch_settlement_with_id", {"settlement_id": "../secrets"})
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_live_url_stays_on_settlements():
    path, query = tool_path("fetch_all_settlements", {"count": 2})
    url = live_url(path, query)
    assert url.startswith("https://api.razorpay.com/v1/settlements")
    assert ALLOWED_TOOLS == {
        "fetch_all_settlements",
        "fetch_settlement_with_id",
        "fetch_settlement_recon_details",
        "fetch_all_instant_settlements",
        "fetch_instant_settlement_with_id",
    }
    assert "create_instant_settlement" in REFUSED_TOOLS


def test_fixture_instant_settlements_are_read_only():
    client = SettlementMcp(enabled=False)
    listing = client.invoke("fetch_all_instant_settlements", {"count": 10})
    assert listing["settlements"][0]["id"] == "setlod_sample_01"
    assert listing["written"] is False
    assert listing["cleared"] == 0
    detail = client.invoke("fetch_instant_settlement_with_id", {"settlement_id": "setlod_sample_01"})
    assert detail["path"] == "/v1/settlements/ondemand/setlod_sample_01"
    path, _query = tool_path("fetch_all_instant_settlements", {})
    assert live_url(path, {}) == "https://api.razorpay.com/v1/settlements/ondemand"


def test_match_recon_to_ledger_never_clears():
    from residual_zero.ingest.mcp_settlements import match_recon_to_ledger

    got = match_recon_to_ledger(
        {"rows": [{"item": "pay_x"}, {"item": "pay_y"}], "n": 2},
        {"pay_x"},
        {"pay_x"},
    )
    assert got["ledger_hits"] == 1
    assert got["ledger_misses"] == 1
    assert got["credit_hits"] == 1
    assert got["rows"][0]["in_credit"] is True
    assert got["rows"][1]["in_credit"] is False
    assert got["cleared"] == 0
    assert got["written"] is False


def test_mcp_envelope_still_parses():
    payload = json.loads(
        Path("fixtures/recon/mcp_fetch_settlement_recon_details.json").read_text(encoding="utf-8")
    )
    rows = parse_recon_combined(payload)
    assert len(rows) == 3
