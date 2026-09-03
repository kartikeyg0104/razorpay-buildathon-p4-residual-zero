#!/usr/bin/env python3
"""Probe live provider tool-calling and record the result honestly.

The architecture under test is application-owned orchestration:

    model proposes a tool -> application validates it against the read-only allowlist
    -> application executes it -> result returns to the model -> next tool or final answer

The model never executes anything itself and never writes financial state. This script
proves the loop ran, or records why it did not. It never prints the API key.

Writes `artifacts/qa/live_tool_loop.json`. Exit 0 even when the provider is unavailable:
unavailability is a legitimate recorded outcome, not a failure of this check.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from residual_zero.runtime.envfile import load_env_file

load_env_file()

from residual_zero.qa.agent_loop import MAX_TOOLS, run_agent
from residual_zero.qa.finance_intents import FinanceIntent
from residual_zero.qa.finance_tools import TOOL_NAMES
from residual_zero.semantic import provider

QA = ROOT / "artifacts" / "qa"
DB = ROOT / "artifacts" / "dev" / "ledger.sqlite"
DEMO = "crd_001_acc_01_2025-01-09"


def recon_rows() -> int:
    if not DB.is_file():
        return -1
    conn = sqlite3.connect(f"file:{DB.resolve()}?mode=ro", uri=True)
    try:
        return int(conn.execute("SELECT COUNT(*) FROM reconciliation").fetchone()[0])
    except sqlite3.OperationalError:
        return 0
    finally:
        conn.close()


def main() -> int:
    QA.mkdir(parents=True, exist_ok=True)
    out: dict = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "provider": provider.ai_provider(),
        "endpoint": provider.provider_url(),
        "model": provider.provider_model(),
        "key_present": provider._key_looks_valid(),
        "live_enabled": provider.live_enabled(),
        "timeout_s": provider._timeout_s(),
        "allowlist_size": len(TOOL_NAMES),
        "architecture": (
            "model proposes -> application validates against allowlist -> application "
            "executes read-only tool -> result to model"
        ),
    }

    if not provider.live_enabled():
        out["LIVE_TOOL_CALLING"] = "NOT TESTABLE"
        out["reason"] = "live provider disabled (no valid key, stub provider, or under pytest)"
        out["pass"] = True
        (QA / "live_tool_loop.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({k: out[k] for k in ("provider", "LIVE_TOOL_CALLING", "reason")}, indent=2))
        return 0

    # 1. a single next-tool pick, validated against the allowlist
    t0 = time.perf_counter()
    pick, err = provider.select_next_tool(
        "Why are there two valid explanations for this credit?",
        ["get_transaction", "get_reconciliation"],
        sorted(TOOL_NAMES),
        DEMO,
    )
    out["next_tool"] = {
        "latency_s": round(time.perf_counter() - t0, 2),
        "pick": pick or {},
        "error": err or None,
        "tool_in_allowlist": bool(pick) and pick.get("tool") in TOOL_NAMES,
    }

    # 2. the full loop, then confirm nothing financial moved
    before = recon_rows()
    t0 = time.perf_counter()
    got = run_agent("Investigate why this was not reconciled.", DEMO, FinanceIntent.INVESTIGATE)
    after = recon_rows()
    executed = [t["tool"] for t in got["tools"]]
    out["agent_loop"] = {
        "latency_s": round(time.perf_counter() - t0, 2),
        "tools_executed": executed,
        "sources": sorted({t["source"] for t in got["tools"]}),
        "llm_picks": got["llm_picks"],
        "rejected_tools": got["rejected_tools"],
        "stopped": got["stopped"],
        "within_tool_cap": len(executed) <= MAX_TOOLS,
        "every_executed_tool_allowlisted": all(t in TOOL_NAMES for t in executed),
        "writes_cleared": got["writes_cleared"],
    }
    out["reconciliation_rows_before"] = before
    out["reconciliation_rows_after"] = after
    out["financial_state_unchanged"] = before == after

    status = provider.desk_ai_status()
    out["LIVE_PROVIDER"] = status["LIVE_PROVIDER"]
    out["LIVE_TOOL_CALLING"] = "YES" if got["llm_picks"] else "UNAVAILABLE"
    out["provider_error"] = status.get("error") or None

    failures = []
    if not out["agent_loop"]["every_executed_tool_allowlisted"]:
        failures.append("non_allowlisted_tool_executed")
    if not out["agent_loop"]["within_tool_cap"]:
        failures.append("tool_cap_exceeded")
    if out["agent_loop"]["writes_cleared"] is not False:
        failures.append("loop_reported_write")
    if not out["financial_state_unchanged"]:
        failures.append("financial_state_changed")
    out["failures"] = failures
    out["pass"] = not failures

    (QA / "live_tool_loop.json").write_text(json.dumps(out, indent=2, default=str) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "provider": out["provider"],
                "model": out["model"],
                "LIVE_PROVIDER": out["LIVE_PROVIDER"],
                "LIVE_TOOL_CALLING": out["LIVE_TOOL_CALLING"],
                "llm_picks": out["agent_loop"]["llm_picks"],
                "tools_executed": len(out["agent_loop"]["tools_executed"]),
                "every_executed_tool_allowlisted": out["agent_loop"]["every_executed_tool_allowlisted"],
                "financial_state_unchanged": out["financial_state_unchanged"],
                "failures": failures,
                "pass": out["pass"],
            },
            indent=2,
        )
    )
    return 0 if out["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
