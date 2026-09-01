"""JSON contracts for desk APIs. Types, not just HTTP 200."""

from __future__ import annotations

import json

from residual_zero.console.app import app
from residual_zero.qa.finance_tools import get_reconciliation

DEMO = "crd_001_acc_01_2025-01-09"


def _get(path: str):
    route = next(r for r in app.routes if getattr(r, "path", "") == path)
    return route.endpoint()


def test_health_contract_is_honest_about_the_provider():
    body = json.loads(_get("/api/health").body)
    assert body["ok"] is True
    assert body["writes_cleared"] is False
    assert body["auto_clear"] == 0
    assert body["LIVE_PROVIDER"] in {"YES", "UNAVAILABLE", "OFF"}
    assert body["LIVE_LLM_TOOL_LOOP"] in {"YES", "UNAVAILABLE"}
    assert body["DETERMINISTIC_CONTROLLER"] == "PASS"
    if body["LIVE_PROVIDER"] == "YES":
        assert not body.get("provider_error")


def test_ops_contract():
    body = json.loads(_get("/api/ops").body)
    assert body["ok"] is True
    assert body["writes_cleared"] is False
    assert body["plugged"] is False
    assert isinstance(body["exposure"]["n"], int)
    assert isinstance(body["duplicate_utr"]["n"], int)


def test_reconciliation_schema_types():
    got = get_reconciliation(DEMO)
    assert got["found"] is True
    assert isinstance(got["residual_paise"], int)
    assert got["uniqueness"] in {"UNIQUE", "AMBIGUOUS", "NONE_FOUND", "BUDGET_EXCEEDED"}
    assert got["writes_cleared"] is False
    decision = got["auto_clear_decision"]
    assert decision["final"] == "REFUSE"
    assert decision["writes_cleared"] is False
    assert isinstance(decision["residual_paise"], int)
