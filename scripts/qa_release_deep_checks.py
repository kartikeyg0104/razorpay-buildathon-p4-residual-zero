#!/usr/bin/env python3
"""Release-candidate deep checks that the aggregate certification does not cover.

Five checks, each writing its own artifact under `artifacts/qa/`:

  contamination  → test_contamination_audit.json (independent_probe key)
  agent          → agent_harness_certification.json
  dev_regression → dev_financial_regression.json
  cache          → cache_final_check.json
  mcp            → mcp_final_check.json

Every value is measured. Nothing here writes financial state; the reconciliation row count
is asserted unchanged where a check could plausibly touch it. Requires a console on
127.0.0.1:8765 for the contamination probe only.

Usage:
    python scripts/qa_release_deep_checks.py [check ...]     # default: all
"""

from __future__ import annotations

import importlib.util
import inspect
import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

QA = ROOT / "artifacts" / "qa"
DB = ROOT / "artifacts" / "dev" / "ledger.sqlite"
BASE = "http://127.0.0.1:8765"
DEMO = "crd_001_acc_01_2025-01-09"


def recon_rows() -> int:
    if not DB.is_file():
        return -1
    conn = sqlite3.connect(DB)
    try:
        return int(conn.execute("SELECT COUNT(*) FROM reconciliation").fetchone()[0])
    except sqlite3.OperationalError:
        return 0
    finally:
        conn.close()


def get(path: str) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(BASE + path, timeout=90) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")
    except OSError as exc:
        return 0, f"unreachable: {exc}"


# --------------------------------------------------------------------------- contamination


def check_contamination() -> dict:
    from residual_zero.console.facts import t04_fields
    from residual_zero.qa import evidence_extract, finance_audit
    from residual_zero.qa.finance_tools import get_reconciliation_statistics

    out: dict[str, object] = {}
    status, body = get("/api/t04")
    if status != 200:
        return {"pass": False, "failures": ["console_unreachable"], "api_t04_status": status}
    api = json.loads(body)
    drift = []
    for split, api_key in (("dev", "dev"), ("test", "test")):
        committed = t04_fields(split)
        served = api.get(api_key) or {}
        for field, value in committed.items():
            if field in served and str(served[field]) != str(value):
                drift.append(
                    {"split": split, "field": field, "committed": value, "api": served[field]}
                )
    out["api_t04_matches_committed_cards"] = not drift
    out["api_t04_drift"] = drift

    markers = ["crd_mix_", "fixture", "mock", "dummy", "sample_", "lorem", "test_credit", "fake"]
    metric_endpoints = ["/api/t04", "/api/ops", "/api/credits", "/api/health"]
    scan = {}
    for endpoint in metric_endpoints:
        code, text = get(endpoint)
        scan[endpoint] = {
            "status": code,
            "markers": sorted({m for m in markers if m in text.casefold()}),
        }
    out["metric_endpoint_marker_scan"] = scan

    stats = get_reconciliation_statistics()
    out["stats_contains_mixed_desk_ids"] = "crd_mix_" in json.dumps(stats, default=str)
    out["stats_residual_zero"] = stats.get("residual_zero")
    out["stats_writes_cleared"] = stats.get("writes_cleared")

    code, mixed = get("/mixed")
    out["mixed_desk_declares_non_official"] = (
        "not official" in mixed.casefold() or "constructed pool" in mixed.casefold()
    )
    out["audit_sink_test_guarded"] = "PYTEST_CURRENT_TEST" in inspect.getsource(
        finance_audit.record_audit
    )
    out["extract_cache_test_guarded"] = "PYTEST_CURRENT_TEST" in inspect.getsource(
        evidence_extract._cache_put
    )

    failures = []
    if drift:
        failures.append("api_t04_drift_from_committed_cards")
    if out["stats_contains_mixed_desk_ids"]:
        failures.append("mixed_desk_ids_in_official_stats")
    if scan["/api/t04"]["markers"]:
        failures.append("fixture_markers_in_api_t04")
    if not (out["audit_sink_test_guarded"] and out["extract_cache_test_guarded"]):
        failures.append("append_only_sink_not_test_guarded")
    out["failures"] = failures
    out["pass"] = not failures
    out["note"] = (
        "Official cards are parsed from committed artifacts/{split}/t04.md. The mixed/demo "
        "desk (crd_mix_*) is a constructed teaching pool excluded from official statistics; "
        "it appears in HTML only as navigation. The AI audit log and extract cache are "
        "suppressed under pytest unless explicitly opted in."
    )

    dest = QA / "test_contamination_audit.json"
    prev = json.loads(dest.read_text()) if dest.is_file() else {}
    dest.write_text(
        json.dumps({**prev, "independent_probe": out}, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    return out


# ----------------------------------------------------------------------------------- agent


def check_agent() -> dict:
    from residual_zero.qa import agent_loop
    from residual_zero.qa.agent_loop import MAX_NS, MAX_REPEAT, MAX_TOOLS, run_agent
    from residual_zero.qa.finance_intents import FinanceIntent
    from residual_zero.qa.finance_tools import call_finance_tool
    from residual_zero.semantic.provider import live_enabled

    cheap = [
        "get_transaction",
        "get_reconciliation",
        "get_match_candidates",
        "compare_sources",
        "get_candidate_equations",
        "get_tax_breakdown",
        "get_audit_trail",
        "get_transaction_evidence",
        "get_transaction_timeline",
    ]
    original = agent_loop.playbook
    real_call = agent_loop.call_finance_tool

    def force(steps):
        agent_loop.playbook = lambda *a, **k: list(steps)

    out: dict[str, object] = {
        "provider_live_enabled": bool(live_enabled()),
        "limits": {"MAX_TOOLS": MAX_TOOLS, "MAX_REPEAT": MAX_REPEAT, "MAX_NS": MAX_NS},
    }
    try:
        force([("get_transaction", {"transaction_id": DEMO})])
        r = run_agent("look this up", DEMO, FinanceIntent.TRANSACTION_LOOKUP)
        out["single_tool"] = {
            "n_tools": len(r["tools"]),
            "tool": r["tools"][0]["tool"],
            "pass": len(r["tools"]) == 1 and bool(r["tools"][0]["output"]),
        }

        agent_loop.playbook = original
        r = run_agent("Can you investigate why this wasn't reconciled?", DEMO, FinanceIntent.INVESTIGATE)
        seq = [t["tool"] for t in r["tools"]]
        out["multi_tool"] = {
            "sequence": seq,
            "n_tools": len(seq),
            "evidence_aggregated": sorted(r["evidence"])[:10],
            "writes_cleared": r["writes_cleared"],
            "pass": len(seq) >= 2 and r["writes_cleared"] is False,
        }

        force([(n, {"transaction_id": DEMO}) for n in cheap[:9]])
        r = run_agent("investigate", DEMO, FinanceIntent.INVESTIGATE)
        out["eight_tools_then_ninth_rejected"] = {
            "requested": 9,
            "executed": len(r["tools"]),
            "stopped": r["stopped"],
            "pass": len(r["tools"]) == MAX_TOOLS and r["stopped"] == "tool_limit",
        }

        force([("get_transaction", {"transaction_id": DEMO})] * 3)
        r = run_agent("investigate", DEMO, FinanceIntent.INVESTIGATE)
        out["duplicate_then_third_rejected"] = {
            "requested": 3,
            "executed": len(r["tools"]),
            "max_repeat": MAX_REPEAT,
            "pass": len(r["tools"]) == MAX_REPEAT,
        }

        missing = call_finance_tool("get_transaction", {"transaction_id": "does_not_exist_zzz"})
        empty = call_finance_tool("get_transaction", {})
        out["invalid_arguments"] = {
            "unknown_id_found": missing.get("found"),
            "empty_args_found": empty.get("found"),
            "writes_cleared": missing.get("writes_cleared"),
            "pass": missing.get("found") is False and missing.get("writes_cleared") is False,
        }

        unknown = call_finance_tool("clear_everything", {})
        out["unknown_tool"] = {
            "ok": unknown.get("ok"),
            "error": unknown.get("error"),
            "pass": unknown.get("ok") is False and unknown.get("error") == "unknown_tool",
        }

        def boom(name, arguments=None):
            raise RuntimeError("injected tool failure")

        agent_loop.call_finance_tool = boom
        force([("get_transaction", {"transaction_id": DEMO})])
        loop_exc = None
        try:
            run_agent("investigate", DEMO, FinanceIntent.INVESTIGATE)
        except Exception as exc:  # noqa: BLE001
            loop_exc = f"{type(exc).__name__}: {exc}"
        ctrl_exc, answer = None, ""
        try:
            from residual_zero.qa.finance_controller import finance_ask

            got = finance_ask("Why was this not reconciled?", DEMO)
            answer = str(got.get("answer") or "")[:160]
        except Exception as exc:  # noqa: BLE001
            ctrl_exc = f"{type(exc).__name__}: {exc}"
        agent_loop.call_finance_tool = real_call
        out["tool_exception"] = {
            "propagated_out_of_agent_loop": loop_exc,
            "contained_by_controller": ctrl_exc is None,
            "controller_answer_prefix": answer,
            "note": (
                "agent_loop intentionally does not swallow tool exceptions; finance_ask is the "
                "containment boundary and degrades to deterministic engine output"
            ),
            "pass": ctrl_exc is None,
        }

        saved = agent_loop.MAX_NS
        agent_loop.MAX_NS = 1
        force([(n, {"transaction_id": DEMO}) for n in cheap[:8]])
        r = run_agent("investigate", DEMO, FinanceIntent.INVESTIGATE)
        agent_loop.MAX_NS = saved
        out["timeout"] = {
            "ns_budget": 1,
            "executed": len(r["tools"]),
            "stopped": r["stopped"],
            "pass": r["stopped"] == "time_limit" and len(r["tools"]) <= 1,
        }
    finally:
        agent_loop.playbook = original
        agent_loop.call_finance_tool = real_call

    checks = {k: v["pass"] for k, v in out.items() if isinstance(v, dict) and "pass" in v}
    out["checks"] = checks
    out["failures"] = [k for k, v in checks.items() if v is False]
    out["LOCAL_AGENT_HARNESS"] = "PASS" if not out["failures"] else "FAIL"
    out["pass"] = not out["failures"]
    out["writes_cleared"] = False
    (QA / "agent_harness_certification.json").write_text(
        json.dumps(out, indent=2, default=str) + "\n", encoding="utf-8"
    )
    return out


# -------------------------------------------------------------------------- dev regression

FIELDS = (
    "status",
    "residual",
    "solution_count",
    "matched_ids",
    "search_status",
    "verification",
    "uniqueness",
)


def check_dev_regression() -> dict:
    spec = importlib.util.spec_from_file_location("hb", ROOT / "scripts" / "hardening_baseline.py")
    hb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hb)

    baseline_path = QA / "financial_regression_baseline.json"
    if not baseline_path.is_file():
        return {"pass": False, "failures": ["baseline_missing"]}
    baseline = json.loads(baseline_path.read_text())
    base_rows = baseline["rows"]
    now_rows = hb.snapshot_sqlite(DB)

    def norm(row: dict) -> dict:
        out = {}
        for field in FIELDS:
            value = row.get(field)
            if field == "matched_ids":
                if isinstance(value, str):
                    value = [p.strip() for p in value.split(",") if p.strip()]
                value = sorted(str(x).strip() for x in (value or []))
            elif isinstance(value, str):
                value = value.strip()
            out[field] = value
        return out

    base = {str(r["transaction_id"]).strip(): norm(r) for r in base_rows}
    now = {str(r["transaction_id"]).strip(): norm(r) for r in now_rows}
    missing = sorted(set(base) - set(now))
    added = sorted(set(now) - set(base))
    changed = [
        {
            "transaction_id": tid,
            "fields": {f: {"baseline": base[tid][f], "current": now[tid][f]} for f in FIELDS if base[tid][f] != now[tid][f]},
        }
        for tid in sorted(set(base) & set(now))
        if base[tid] != now[tid]
    ]
    out = {
        "baseline_n": len(base),
        "current_n": len(now),
        "ids_missing_from_current": missing,
        "ids_added_in_current": added,
        "changed_count": len(changed),
        "changed_rows": changed[:25],
        "changed_by_field": {f: sum(1 for c in changed if f in c["fields"]) for f in FIELDS},
        "cleared_baseline": sum(1 for r in base_rows if r.get("status") == "CLEARED"),
        "cleared_current": sum(1 for r in now_rows if r.get("status") == "CLEARED"),
    }
    out["exact_equality"] = not missing and not added and not changed
    out["pass"] = bool(out["exact_equality"]) and out["cleared_current"] == 0
    out["verdict"] = "PRESERVED" if out["pass"] else "REVIEW_REQUIRED"
    out["failures"] = [] if out["pass"] else ["dev_financial_results_changed"]
    (QA / "dev_financial_regression.json").write_text(
        json.dumps(out, indent=2, default=str) + "\n", encoding="utf-8"
    )
    return out


# ----------------------------------------------------------------------------------- cache


def check_cache() -> dict:
    probe_cache = ROOT / "artifacts" / "qa" / "_probe_extract_cache.jsonl"
    probe_cache.unlink(missing_ok=True)
    # RZ_EXTRACT_CACHE is a path override, so the committed cache is never touched here.
    os.environ["RZ_EXTRACT_CACHE"] = str(probe_cache)
    try:
        from residual_zero.qa.evidence_extract import PROMPT_VERSION, extract_for_credit, text_hash
        from residual_zero.qa.finance_tools import get_reconciliation

        narration = "NEFT SETTL RZPX0099 INV-2201 MBR-77 20250109"
        first = extract_for_credit(DEMO, narration)
        repeat = extract_for_credit(DEMO, narration)

        def key(tid: str, text: str, prompt: str, method: str = "deterministic") -> str:
            return "|".join((tid, text_hash(text), prompt, method))

        base_key = key(DEMO, narration, PROMPT_VERSION)
        variants = {
            "change_source_text": key(DEMO, narration + " AMENDED", PROMPT_VERSION),
            "change_dataset_transaction": key("crd_002_acc_01_2025-01-09", narration, PROMPT_VERSION),
            "change_prompt_version": key(DEMO, narration, "extract-v2"),
            "change_model_method": key(DEMO, narration, PROMPT_VERSION, "nvidia-openai/gpt-oss-20b"),
        }
        out: dict[str, object] = {
            "isolated_cache_file": str(probe_cache.relative_to(ROOT)),
            "request_A_first_cache_hit": first["cache_hit"],
            "request_A_repeat_cache_hit": repeat["cache_hit"],
            "repeat_identical_fields": first["fields"] == repeat["fields"],
            "key_changes": {name: value != base_key for name, value in variants.items()},
            "question_not_part_of_key": "question" not in base_key,
        }
        out["all_variants_distinct_keys"] = all(out["key_changes"].values()) and len(
            set(variants.values())
        ) == len(variants)
        out["changed_source_text_is_miss"] = (
            extract_for_credit(DEMO, narration + " AMENDED")["cache_hit"] is False
        )

        financial_keys = [
            "status", "residual", "residual_paise", "uniqueness", "verification",
            "verified", "matched_ids", "disposition", "cleared", "solution_count",
        ]
        rows = [
            json.loads(line)
            for line in (probe_cache.read_text(encoding="utf-8").splitlines() if probe_cache.is_file() else [])
            if line.strip()
        ]
        offending = []
        for row in rows:
            bad = sorted(set(row) & set(financial_keys))
            if bad:
                offending.append({"key": str(row.get("key"))[:40], "top_level": bad})
            for field in row.get("fields") or []:
                if str(field.get("field") or "") in financial_keys:
                    offending.append({"key": str(row.get("key"))[:40], "field": field.get("field")})
        out["cached_row_count"] = len(rows)
        out["cached_top_level_keys"] = sorted({k for r in rows for k in r})
        out["cached_payload_financial_leak"] = offending[:10]
        out["cached_payload_is_candidate_only"] = not offending
        out["result_candidate_only"] = first.get("candidate_only") is True
        out["result_writes_cleared"] = first.get("writes_cleared")

        watched = ("status", "residual_paise", "uniqueness", "verification", "matched_ids", "solution_count", "disposition")
        before = get_reconciliation(DEMO)
        extract_for_credit(DEMO, narration + " TOTALLY DIFFERENT NARRATION RZPX9999")
        after = get_reconciliation(DEMO)
        drift = {
            f: {"before": before.get(f), "after": after.get(f)}
            for f in watched
            if before.get(f) != after.get(f)
        }
        out["engine_drift_after_cache_write"] = drift
        out["engine_unaffected_by_cache"] = not drift
    finally:
        os.environ.pop("RZ_EXTRACT_CACHE", None)
        probe_cache.unlink(missing_ok=True)

    failures = []
    if out["request_A_repeat_cache_hit"] is not True:
        failures.append("repeat_request_not_cached")
    if not out["all_variants_distinct_keys"]:
        failures.append("cache_key_not_sensitive")
    if not out["changed_source_text_is_miss"]:
        failures.append("changed_source_text_served_stale")
    if not out["cached_payload_is_candidate_only"]:
        failures.append("cached_payload_carries_financial_state")
    if not out["engine_unaffected_by_cache"]:
        failures.append("cache_mutated_engine_truth")
    if out["result_writes_cleared"] is not False:
        failures.append("cache_result_writes_cleared")
    out["failures"] = failures
    out["pass"] = not failures
    (QA / "cache_final_check.json").write_text(
        json.dumps(out, indent=2, default=str) + "\n", encoding="utf-8"
    )
    return out


# ------------------------------------------------------------------------------------- mcp


def check_mcp() -> dict:
    from residual_zero.ingest.mcp_settlements import ALLOWED_TOOLS, REFUSED_TOOLS
    from residual_zero.mcp.registry import call_tool, list_tools

    before = recon_rows()
    listed = sorted(t["name"] for t in list_tools())
    out: dict[str, object] = {
        "tools_list_count": len(listed),
        "tools_list": listed,
        "allowlist_declared": sorted(ALLOWED_TOOLS),
        "refused_declared": sorted(REFUSED_TOOLS),
        "refused_exposed_in_tools_list": sorted(set(listed) & set(REFUSED_TOOLS)),
    }

    refused_probe = {}
    for name in sorted(REFUSED_TOOLS):
        try:
            result = call_tool(name, {"transaction_id": DEMO})
            refused_probe[name] = {"rejected": isinstance(result, dict) and result.get("ok") is False}
        except Exception as exc:  # noqa: BLE001
            refused_probe[name] = {"rejected": True, "error": type(exc).__name__}
    out["declared_refused_probe"] = refused_probe
    out["declared_refused_all_rejected"] = all(v["rejected"] for v in refused_probe.values())

    write_like = [
        "clear_transaction", "mark_cleared", "set_disposition", "write_ledger",
        "update_reconciliation", "delete_transaction", "insert_settlement",
        "execute_sql", "run_sql", "write_file", "shell", "post_journal",
        "approve_clear", "override_gate", "force_clear", "commit_reconciliation",
        "mutate_state", "auto_clear", "resolve_exception", "settle",
    ]
    extra = {}
    for name in write_like:
        try:
            result = call_tool(name, {"transaction_id": DEMO})
            extra[name] = {"rejected": isinstance(result, dict) and result.get("ok") is False}
        except Exception as exc:  # noqa: BLE001
            extra[name] = {"rejected": True, "error": type(exc).__name__}
    out["write_like_probe"] = extra
    out["write_like_all_rejected"] = all(v["rejected"] for v in extra.values())

    leaks = {}
    for name in listed:
        try:
            result = call_tool(
                name,
                {"transaction_id": DEMO, "name": "get_transaction", "arguments": {"transaction_id": DEMO}},
            )
        except Exception as exc:  # noqa: BLE001
            leaks[name] = f"raised:{type(exc).__name__}"
            continue
        if '"writes_cleared": true' in json.dumps(result, default=str).casefold():
            leaks[name] = "TRUE_LEAK"
        else:
            leaks[name] = result.get("writes_cleared", "absent") if isinstance(result, dict) else "non_dict"
    out["writes_cleared_per_tool"] = leaks
    out["any_writes_cleared_true"] = any(v == "TRUE_LEAK" for v in leaks.values())

    after = recon_rows()
    out["reconciliation_rows_before"] = before
    out["reconciliation_rows_after"] = after
    out["db_unchanged"] = before == after

    failures = []
    if out["refused_exposed_in_tools_list"]:
        failures.append("refused_tool_exposed_in_tools_list")
    if not out["declared_refused_all_rejected"]:
        failures.append("declared_refused_tool_not_rejected")
    if not out["write_like_all_rejected"]:
        failures.append("write_like_operation_accepted")
    if out["any_writes_cleared_true"]:
        failures.append("writes_cleared_true_leak")
    if not out["db_unchanged"]:
        failures.append("db_mutated")
    out["failures"] = failures
    out["pass"] = not failures
    (QA / "mcp_final_check.json").write_text(
        json.dumps(out, indent=2, default=str) + "\n", encoding="utf-8"
    )
    return out


CHECKS = {
    "contamination": check_contamination,
    "agent": check_agent,
    "dev_regression": check_dev_regression,
    "cache": check_cache,
    "mcp": check_mcp,
}


def main(argv: list[str]) -> int:
    QA.mkdir(parents=True, exist_ok=True)
    wanted = [a for a in argv[1:] if not a.startswith("-")] or list(CHECKS)
    unknown = [w for w in wanted if w not in CHECKS]
    if unknown:
        print(f"unknown check(s): {unknown}; known: {sorted(CHECKS)}", file=sys.stderr)
        return 2

    before = recon_rows()
    summary: dict[str, object] = {}
    started = time.perf_counter()
    for name in wanted:
        result = CHECKS[name]()
        summary[name] = {"pass": result.get("pass"), "failures": result.get("failures") or []}
        print(f"{name:<15} {'PASS' if result.get('pass') else 'FAIL'} {result.get('failures') or ''}")
    after = recon_rows()

    failures = sorted(
        {f for info in summary.values() for f in (info.get("failures") or [])}
        | ({"reconciliation_rows_changed"} if before != after else set())
    )
    payload = {
        "checks": summary,
        "reconciliation_rows_before": before,
        "reconciliation_rows_after": after,
        "cleared_rows": after,
        "elapsed_s": round(time.perf_counter() - started, 3),
        "failures": failures,
        "pass": not failures,
    }
    (QA / "release_deep_checks.json").write_text(
        json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8"
    )
    print(f"\nDEEP CHECKS: {'PASS' if payload['pass'] else 'FAIL'}  reconciliation rows {before} -> {after}")
    return 0 if payload["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
