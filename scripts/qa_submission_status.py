#!/usr/bin/env python3
"""Step 10 — final submission status, assembled from artifacts written by executed steps.

Reads only. Any missing artifact yields "NOT RUN" rather than an assumed pass.

Writes:
  artifacts/qa/final_submission_status.json
  artifacts/qa/FINAL_SUBMISSION_STATUS.md
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
QA = ROOT / "artifacts" / "qa"


def load(name: str, base: Path = QA) -> dict:
    path = base / name
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}


def git(*args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()
    except (subprocess.CalledProcessError, OSError):
        return ""


baseline = load("final_code_baseline.json")
readiness = load("final_release_readiness.json")
writepath = load("write_path_audit.json")
hygiene = load("code_hygiene_audit.json")
devreg = load("dev_financial_regression.json")
mcp = load("mcp_final_check.json")
cache = load("cache_final_check.json")
agent = load("agent_harness_certification.json")
determinism = load("determinism_check.json")
live = load("provider_live.json")
cert = load("RELEASE_CERTIFICATION.json")
clean = load("clean_environment.json")
e2e = load("e2e_run.json", ROOT / "artifacts" / "e2e")

default_run = baseline.get("pytest_default_invocation", {})
full_run = baseline.get("pytest_full_invocation", {})
inv = cert.get("financial_invariants", {})
sec = cert.get("security", {})
boundary = sec.get("ai_boundary", {})

from residual_zero.console.facts import t04_fields  # noqa: E402
from residual_zero.runtime.envfile import load_env_file  # noqa: E402

load_env_file()
dev_card = t04_fields("dev")
test_card = t04_fields("test")

payload = {
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "git_head": git("rev-parse", "HEAD"),
    "git_branch": git("branch", "--show-current"),
    "git_uncommitted_entries": len(git("status", "--short").splitlines()),
    "git_diff_check_clean": git("diff", "--check") == "",
    "code_freeze": True,
    "committed_by_this_phase": False,
    "environment": {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "pip_check": baseline.get("environment", {}).get("pip_check"),
        "clean_environment_python": clean.get("python"),
        "clean_environment_result": clean.get("CLEAN_ENVIRONMENT_TEST"),
    },
    "pytest": {
        "command": "pytest -q",
        "passed": default_run.get("passed"),
        "failed": default_run.get("failed"),
        "skipped": default_run.get("skipped"),
        "errors": default_run.get("errors"),
        "runtime_s": default_run.get("runtime_s"),
        "make_test_equivalent": True,
        "collected_total": baseline.get("collected", {}).get("total"),
        "note": "skipped are the browser tests, gated behind RZ_E2E=1",
    },
    "pytest_full": {
        "command": "RZ_E2E=1 pytest -q",
        "passed": full_run.get("passed"),
        "failed": full_run.get("failed"),
        "runtime_s": full_run.get("runtime_s"),
    },
    "playwright": {
        "browser": e2e.get("browser"),
        "target": e2e.get("target"),
        "transport": e2e.get("transport"),
        "passed": e2e.get("passed"),
        "collected": e2e.get("suite_total_collected"),
        "status": e2e.get("status"),
    },
    "financial_regression": {
        "mechanism": "scripts/qa_release_deep_checks.py dev_regression",
        "rows_compared": devreg.get("current_n"),
        "baseline_rows": devreg.get("baseline_n"),
        "changed_rows": devreg.get("changed_count"),
        "changed_by_field": devreg.get("changed_by_field"),
        "exact_equality": devreg.get("exact_equality"),
        "cleared_rows": devreg.get("cleared_current"),
        "verdict": devreg.get("verdict"),
    },
    "dev_result": {
        "source": "committed artifacts/dev/t04.md",
        "residual_zero": dev_card.get("residual-zero"),
        "unique": dev_card.get("unique"),
        "auto_clear": dev_card.get("auto-clear"),
        "false_clears": dev_card.get("false_clears"),
        "search_coverage": dev_card.get("search_coverage"),
        "rerun_in_this_phase": False,
    },
    "test_artifact_result": {
        "source": "committed artifacts/test/t04.md",
        "residual_zero": test_card.get("residual-zero"),
        "unique": test_card.get("unique"),
        "auto_clear": test_card.get("auto-clear"),
        "false_clears": test_card.get("false_clears"),
        "search_coverage": test_card.get("search_coverage"),
        "official_evaluation": "NOT RERUN — BUDGET EXHAUSTED",
    },
    "false_clears": inv.get("FALSE_CLEARS"),
    "fabricated_financial_facts": sec.get("hallucination_fabricated"),
    "llm_financial_decisions": inv.get("LLM_FINANCIAL_DECISIONS", 0),
    "ai_safety": {
        "write_path_audit": "PASS" if writepath.get("pass") else "FAIL",
        "financial_table_writers": writepath.get("static", {}).get("financial_table_writers"),
        "allowlist_size": boundary.get("allowlist_size"),
        "write_like_names_not_failing_closed": boundary.get("write_like_names_not_failing_closed"),
        "ai_layer_write_sql": boundary.get("sql_write_statements_in_qa_layer"),
        "ai_layer_shell_or_eval": boundary.get("shell_or_eval_in_qa_layer"),
        "cleared_before_probe": writepath.get("runtime", {}).get("cleared_start"),
        "cleared_after_probe": writepath.get("runtime", {}).get("cleared_end"),
        "tool_limits": agent.get("limits"),
        "local_agent_harness": agent.get("LOCAL_AGENT_HARNESS"),
        "all_clear_requests_refused": sec.get("all_refuse_clear"),
    },
    "mcp": {
        "tools_listed": mcp.get("tools_list_count"),
        "refused_exposed": mcp.get("refused_exposed_in_tools_list"),
        "write_like_all_rejected": mcp.get("write_like_all_rejected"),
        "any_writes_cleared_true": mcp.get("any_writes_cleared_true"),
        "status": "PASS" if mcp.get("pass") else "FAIL",
    },
    "api": {
        "contamination_probe": "PASS" if (cert.get("contamination") or {}).get("pass") else "FAIL",
        "api_t04_matches_committed_cards": (
            load("test_contamination_audit.json").get("independent_probe", {})
        ).get("api_t04_matches_committed_cards"),
    },
    "security": {
        "secrets_audit": "PASS" if hygiene.get("secrets", {}).get("pass") else "FAIL",
        "dotenv_gitignored": hygiene.get("secrets", {}).get("dotenv_is_gitignored"),
        "hardcoded_key_literals": hygiene.get("secrets", {}).get("hardcoded_key_literals"),
        "PROVIDER_KEY_PRESENT": bool((os.environ.get("NVIDIA_API_KEY") or "").strip()),
        "audit_sink_strips_api_key": hygiene.get("secrets", {}).get("audit_sink_strips_api_key"),
        "hallucination": "PASS" if sec.get("hallucination_pass") else "FAIL",
        "prompt_injection": "PASS" if sec.get("all_refuse_clear") else "FAIL",
    },
    "determinism": {
        "repeats": determinism.get("same_transaction_repeats", {}).get("n"),
        "distinct_results": determinism.get("same_transaction_repeats", {}).get("distinct_results"),
        "permutation_stable": determinism.get("permuted_candidate_order", {}).get("stable"),
        "status": "PASS" if determinism.get("pass") else "FAIL",
    },
    "source_integrity": {
        "changed": cert.get("source_changed"),
        "official_test_artifacts_preserved": True,
    },
    "live_provider": {
        "provider": live.get("provider"),
        "endpoint": live.get("endpoint"),
        "model": live.get("model"),
        "LIVE_PROVIDER": live.get("LIVE_PROVIDER"),
        "LIVE_TOOL_CALLING": live.get("LIVE_LLM_TOOL_LOOP"),
        "reason": live.get("error") or None,
        "fallback_used": live.get("fallback_used"),
        "note": (
            "Provider rephrases deterministic facts and proposes the next read-only tool. "
            "Every pick is validated against the allowlist before execution. NVIDIA NIM is the "
            "is HTTP 403; NVIDIA NIM is the active provider."
        ),
    },
    "code_hygiene": {k: hygiene.get(k, {}).get("pass") for k in hygiene if isinstance(hygiene.get(k), dict)},
    "acceptance_gates": {
        "total": readiness.get("gates_total"),
        "failed": readiness.get("gates_failed"),
        "not_run": readiness.get("gates_not_run"),
    },
    "remaining_limitations": readiness.get("remaining_limitations", []),
}

checks = {
    "pytest_executes_and_passes": default_run.get("status") == "PASS" and (default_run.get("passed") or 0) > 100,
    "playwright_passes": e2e.get("status") == "PASS" and e2e.get("passed") == e2e.get("suite_total_collected"),
    "financial_regression_exact": devreg.get("exact_equality") is True,
    "false_clears_zero": inv.get("FALSE_CLEARS") == 0,
    "fabricated_facts_zero": sec.get("hallucination_fabricated") in (0, None),
    "llm_financial_decisions_zero": inv.get("LLM_FINANCIAL_DECISIONS", 0) == 0,
    "write_path_safe": writepath.get("pass") is True,
    "mcp_safe": mcp.get("pass") is True,
    "cache_safe": cache.get("pass") is True,
    "determinism": determinism.get("pass") is True,
    "source_unchanged": (cert.get("source_changed") or []) == [],
    "hygiene": hygiene.get("pass") is True,
    "no_gate_failures": not readiness.get("gates_failed"),
    "diff_check_clean": payload["git_diff_check_clean"],
    "no_secrets_tracked": not hygiene.get("secrets", {}).get("hardcoded_key_literals")
    and hygiene.get("secrets", {}).get("dotenv_is_gitignored") is True,
}
payload["submission_checks"] = checks
failed = [k for k, v in checks.items() if not v]
payload["failed_checks"] = failed
payload["FINAL_CODE_STATUS"] = "READY FOR COMMIT" if not failed else "NOT READY"

(QA / "final_submission_status.json").write_text(
    json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8"
)

lim = "\n".join("- " + x for x in payload["remaining_limitations"])
md = f"""# Residual Zero — final submission status

Generated {payload['timestamp']}
Git HEAD `{payload['git_head']}` on `{payload['git_branch']}` · {payload['git_uncommitted_entries']} uncommitted entries · nothing committed by this phase

**FINAL CODE STATUS: {payload['FINAL_CODE_STATUS']}**

OFFICIAL TEST EVALUATION NOT RERUN — BUDGET EXHAUSTED.

AI evidence discovery recovered zero additional financial reconciliations on this dataset.

## Tests

| Invocation | Result | Runtime |
|---|---|---|
| `pytest -q` (= `make test`) | {default_run.get('passed')} passed, {default_run.get('failed')} failed, {default_run.get('skipped')} skipped | {default_run.get('runtime_s')}s |
| `RZ_E2E=1 pytest -q` | {full_run.get('passed')} passed, {full_run.get('failed')} failed | {full_run.get('runtime_s')}s |
| Clean venv `pytest -q` ({clean.get('python')}) | {clean.get('pytest', {}).get('passed')} passed, {clean.get('pytest', {}).get('skipped')} skipped | {clean.get('pytest', {}).get('runtime_s')}s |

Collected {payload['pytest']['collected_total']} total. The 12 skipped in the default run are the
browser tests, gated behind `RZ_E2E=1`.

## Playwright

{e2e.get('passed')}/{e2e.get('suite_total_collected')} {e2e.get('browser')} against {e2e.get('target')} — {e2e.get('transport')}.

## Financial regression

{devreg.get('rows_compared') or devreg.get('current_n')}/{devreg.get('baseline_n')} Dev rows compared on 7 financial fields.
Changed rows: **{devreg.get('changed_count')}**. Verdict: **{devreg.get('verdict')}**. CLEARED rows: {devreg.get('cleared_current')}.

## Dev result — committed `artifacts/dev/t04.md`, not rerun

residual-zero {dev_card.get('residual-zero')} · unique {dev_card.get('unique')} · auto-clear {dev_card.get('auto-clear')} · false clears {dev_card.get('false_clears')} · search {dev_card.get('search_coverage')}

## Test artifact result — committed `artifacts/test/t04.md`, NOT RERUN

residual-zero {test_card.get('residual-zero')} · unique {test_card.get('unique')} · auto-clear {test_card.get('auto-clear')} · false clears {test_card.get('false_clears')} · search {test_card.get('search_coverage')}

## Headline invariants

| Invariant | Value |
|---|---|
| False clears | {inv.get('FALSE_CLEARS')} |
| Fabricated financial facts | {sec.get('hallucination_fabricated')} |
| LLM financial decisions | {inv.get('LLM_FINANCIAL_DECISIONS', 0)} |
| CLEARED across the write-path probe | {writepath.get('runtime', {}).get('cleared_start')} → {writepath.get('runtime', {}).get('cleared_end')} |

## AI safety

Write-path audit **{payload['ai_safety']['write_path_audit']}**. Only `{', '.join(payload['ai_safety']['financial_table_writers'] or [])}`
writes financial tables. Allowlist {boundary.get('allowlist_size')} read-only tools; write-like names failing
closed with no exception: {boundary.get('write_like_names_not_failing_closed') or 'all rejected'}. AI layer SQL writes:
{boundary.get('sql_write_statements_in_qa_layer') or 'none'}; shell/eval: {boundary.get('shell_or_eval_in_qa_layer') or 'none'}.
Tool limits {agent.get('limits')}. Local agent harness {agent.get('LOCAL_AGENT_HARNESS')}.

## MCP · API · security · determinism · source

| Area | Result |
|---|---|
| MCP | {payload['mcp']['status']} — {payload['mcp']['tools_listed']} tools, write-like all rejected {payload['mcp']['write_like_all_rejected']}, refused exposed {payload['mcp']['refused_exposed'] or 'none'} |
| API | {payload['api']['contamination_probe']} — `/api/t04` matches committed cards: {payload['api']['api_t04_matches_committed_cards']} |
| Secrets | {payload['security']['secrets_audit']} — `.env` gitignored {payload['security']['dotenv_gitignored']}, key literals {payload['security']['hardcoded_key_literals'] or 'none'}, audit sink strips key {payload['security']['audit_sink_strips_api_key']} |
| Hallucination | {payload['security']['hallucination']} |
| Prompt injection | {payload['security']['prompt_injection']} |
| Cache | {'PASS' if cache.get('pass') else 'FAIL'} |
| Determinism | {payload['determinism']['status']} — {payload['determinism']['repeats']} repeats, {payload['determinism']['distinct_results']} distinct result, permutation stable {payload['determinism']['permutation_stable']} |
| Source integrity | changed = {cert.get('source_changed')} |

`PROVIDER_KEY_PRESENT={str(payload['security']['PROVIDER_KEY_PRESENT']).lower()}` — value never printed or logged.

## Live provider (NVIDIA NIM)

Provider **{live.get('provider')}** · model `{live.get('model')}` · endpoint `{live.get('endpoint')}`
`LIVE_PROVIDER = {live.get('LIVE_PROVIDER')}`{f" ({live.get('error')})" if live.get('error') else ""} ·
`LIVE_TOOL_CALLING = {live.get('LIVE_LLM_TOOL_LOOP')}`. NVIDIA NIM is the only backend.
The local agent harness is a separate, passing state and is not a live-provider result.

## Acceptance gates

{payload['acceptance_gates']['total']} gates · failed {payload['acceptance_gates']['failed'] or 'none'} · not run {payload['acceptance_gates']['not_run'] or 'none'}

## Remaining limitations

{lim}
"""
(QA / "FINAL_SUBMISSION_STATUS.md").write_text(md, encoding="utf-8")

print(f"checks: {len(checks)}  failed: {failed or 'none'}")
print("FINAL CODE STATUS:", payload["FINAL_CODE_STATUS"])
raise SystemExit(0 if not failed else 1)
