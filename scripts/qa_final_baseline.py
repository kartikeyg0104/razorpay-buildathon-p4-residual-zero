#!/usr/bin/env python3
"""Capture the final code-hardening baseline from actual execution.

Writes `artifacts/qa/final_code_baseline.json`. Runs the suite three ways because the
three invocations are not equivalent:

  pytest -q                 unit + integration, browser gated off
  RZ_E2E=1 pytest -q        whole suite including browser
  pytest -q --collect-only  collected totals, so counts are never hardcoded
"""

from __future__ import annotations

import json
import os
import platform
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QA = ROOT / "artifacts" / "qa"
PY = ROOT / ".venv" / "bin" / "python"
if not PY.exists():
    PY = Path(sys.executable)


def run(cmd: list[str], env: dict | None = None) -> tuple[int, str, float]:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    started = time.perf_counter()
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, env=merged)
    return proc.returncode, ((proc.stdout or "") + (proc.stderr or "")).strip(), round(
        time.perf_counter() - started, 3
    )


def parse(text: str) -> dict:
    def grab(word: str) -> int:
        m = re.search(rf"(\d+) {word}", text)
        return int(m.group(1)) if m else 0

    passed, failed = grab("passed"), grab("failed")
    errors, skipped = grab("error"), grab("skipped")
    return {
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "errors": errors,
        "status": "PASS" if passed and not failed and not errors else ("FAIL" if failed or errors else "NOT RUN"),
        "tail": text.splitlines()[-1:] if text else [],
    }


def git(*args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()
    except (subprocess.CalledProcessError, OSError):
        return ""


def main() -> int:
    QA.mkdir(parents=True, exist_ok=True)

    code_unit, out_unit, secs_unit = run([str(PY), "-m", "pytest", "-q", "--tb=line"])
    unit = parse(out_unit)
    unit["runtime_s"] = secs_unit
    unit["exit_code"] = code_unit

    code_all, out_all, secs_all = run(
        [str(PY), "-m", "pytest", "-q", "--tb=line"], env={"RZ_E2E": "1"}
    )
    full = parse(out_all)
    full["runtime_s"] = secs_all
    full["exit_code"] = code_all

    _, collected, _ = run([str(PY), "-m", "pytest", "-q", "--collect-only"], env={"RZ_E2E": "1"})
    total_collected = len(re.findall(r"^tests/\S+::\S+", collected, re.M)) or None
    e2e_collected = len(re.findall(r"^tests/e2e/\S+::\S+", collected, re.M)) or None

    _, pipcheck, _ = run([str(PY), "-m", "pip", "check"])
    _, freeze, _ = run([str(PY), "-m", "pip", "freeze"])

    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "git_commit": git("rev-parse", "HEAD"),
        "git_branch": git("branch", "--show-current"),
        "git_status_short_lines": len(git("status", "--short").splitlines()),
        "git_diff_stat_tail": git("diff", "--stat").splitlines()[-1:],
        "environment": {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "interpreter": str(PY),
            "pip_check": pipcheck,
            "installed_package_count": len([l for l in freeze.splitlines() if l.strip()]),
        },
        "pytest_default_invocation": {
            "command": "pytest -q",
            "note": "browser E2E gated off unless RZ_E2E=1",
            **unit,
        },
        "pytest_full_invocation": {
            "command": "RZ_E2E=1 pytest -q",
            "note": "whole suite including Chromium browser tests",
            **full,
        },
        "collected": {
            "total": total_collected,
            "e2e": e2e_collected,
            "unit_and_integration": (total_collected - e2e_collected)
            if (total_collected and e2e_collected)
            else None,
        },
        "consistency": {
            "default_passed_plus_skipped_equals_collected": (
                (unit["passed"] + unit["skipped"]) == total_collected if total_collected else None
            ),
            "full_passed_equals_collected": (
                full["passed"] == total_collected if total_collected else None
            ),
            "default_skipped_equals_e2e_collected": (
                unit["skipped"] == e2e_collected if e2e_collected else None
            ),
        },
    }
    payload["pass"] = (
        unit["status"] == "PASS"
        and full["status"] == "PASS"
        and all(v is not False for v in payload["consistency"].values())
    )
    (QA / "final_code_baseline.json").write_text(
        json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8"
    )
    print(json.dumps(
        {
            "default": {k: unit[k] for k in ("passed", "failed", "skipped", "errors", "status", "runtime_s")},
            "full_with_e2e": {k: full[k] for k in ("passed", "failed", "skipped", "errors", "status", "runtime_s")},
            "collected": payload["collected"],
            "consistency": payload["consistency"],
            "pass": payload["pass"],
        },
        indent=2,
    ))
    return 0 if payload["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
