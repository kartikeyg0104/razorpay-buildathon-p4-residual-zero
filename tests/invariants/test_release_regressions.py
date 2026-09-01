"""Regression tests for defects actually found during hardening.

Each test names the defect it protects against. These are the tests that would have
failed at the moment the bug existed.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src"

OFFICIAL_NUMBERS = [
    "159/239",
    "521/800",
    "148/239",
    "129/239",
    "501/800",
    "464/800",
    "142/239",
    "800/800",
    "1,44,25,758.19",
]


# ------------------------------------------------------------------------------
# Defect: the whole test suite was skipped by the e2e conftest hook, so `pytest -q`
# and therefore `make test` in CI reported success while running nothing.
# ------------------------------------------------------------------------------


def test_e2e_skip_hook_only_targets_browser_items():
    """`pytest_collection_modifyitems` receives every item in the session."""
    sys.path.insert(0, str(REPO / "tests" / "e2e"))
    import conftest as e2e_conftest  # noqa: PLC0415

    class FakeItem:
        def __init__(self, path, marker=False):
            self.path = path
            self._marker = marker
            self.markers = []

        def get_closest_marker(self, name):
            return object() if (self._marker and name == "e2e") else None

        def add_marker(self, marker):
            self.markers.append(marker)

    browser = FakeItem(REPO / "tests" / "e2e" / "test_smoke.py", marker=True)
    browser_unmarked = FakeItem(REPO / "tests" / "e2e" / "test_new.py", marker=False)
    unit = FakeItem(REPO / "tests" / "test_money.py", marker=False)
    invariant = FakeItem(REPO / "tests" / "invariants" / "test_money_invariants.py", marker=False)

    items = [browser, browser_unmarked, unit, invariant]
    env_before = os.environ.pop("RZ_E2E", None)
    try:
        e2e_conftest.pytest_collection_modifyitems(config=None, items=items)
    finally:
        if env_before is not None:
            os.environ["RZ_E2E"] = env_before

    assert browser.markers, "browser item should be skipped without RZ_E2E=1"
    assert browser_unmarked.markers, "e2e item without a marker should still be gated by path"
    assert unit.markers == [], "unit test must not be skipped by the e2e hook"
    assert invariant.markers == [], "invariant test must not be skipped by the e2e hook"


def test_default_pytest_invocation_actually_executes_tests():
    """`pytest -q` must run the suite, not skip it. Guards the CI regression."""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--collect-only", "tests"],
        cwd=REPO,
        capture_output=True,
        text=True,
        env={**os.environ, "RZ_E2E": ""},
    )
    collected = len(re.findall(r"^tests/\S+::\S+", proc.stdout, re.M))
    e2e = len(re.findall(r"^tests/e2e/\S+::\S+", proc.stdout, re.M))
    assert collected > e2e > 0, "expected non-browser tests to be collected"
    # More than a handful of non-browser tests must exist and be runnable.
    assert collected - e2e > 100


def test_makefile_test_target_is_not_a_no_op():
    """`make test` is the CI entrypoint; it must invoke pytest over the suite."""
    makefile = (REPO / "Makefile").read_text(encoding="utf-8")
    m = re.search(r"^test:\s*\n\t(.+)$", makefile, re.M)
    assert m, "no `test:` target in Makefile"
    assert "pytest" in m.group(1)


# ------------------------------------------------------------------------------
# Defect: `honesty_line` / `track04_snapshot` emitted official match rates as
# literals, so a missing artifact displayed metrics that were never computed.
# ------------------------------------------------------------------------------


def _render_metrics_without_artifacts() -> str:
    """Render every metric surface, console and AI, with no artifacts present."""
    probe = (
        "import json\n"
        "from residual_zero.console.facts import honesty_line, track04_snapshot, t04_view\n"
        "snap = track04_snapshot()\n"
        "print(honesty_line(0, 0, 0, 0))\n"
        "print(' '.join(str(v) for v in snap))\n"
        "print(json.dumps(t04_view('dev')))\n"
        "print(json.dumps(t04_view('test')))\n"
        "from residual_zero.qa.desk_tools import batch_prose\n"
        "print(batch_prose())\n"
        "from residual_zero.qa.corpus import load_documents\n"
        "print(' '.join(d.body for d in load_documents()))\n"
    )
    with tempfile.TemporaryDirectory() as tmp:
        proc = subprocess.run(
            [sys.executable, "-c", probe],
            cwd=tmp,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": str(SRC)},
        )
        assert proc.returncode == 0, proc.stderr
        return proc.stdout


@pytest.mark.parametrize("number", OFFICIAL_NUMBERS)
def test_no_official_metric_is_fabricated_without_its_artifact(number: str):
    assert number not in _render_metrics_without_artifacts(), (
        f"{number} was rendered with no artifacts present, so it is a hardcoded literal"
    )


def test_missing_official_card_degrades_to_a_dash():
    out = _render_metrics_without_artifacts()
    assert "—" in out, "expected the safe placeholder when the official card is absent"


def test_official_metrics_are_still_correct_when_the_artifacts_exist():
    """The fix must not have broken the real values."""
    from residual_zero.console.facts import honesty_line, t04_view

    if not (REPO / "artifacts" / "dev" / "t04.md").is_file():
        pytest.skip("committed dev card not present in this checkout")
    line = honesty_line(248, 142, 123, 106)
    assert t04_view("dev")["residual_zero"] in line
    assert t04_view("test")["residual_zero"] in line


@pytest.mark.parametrize(
    "module",
    [
        "console/facts.py",
        "qa/corpus.py",
        "qa/desk_tools.py",
        "qa/finance_templates.py",
        "qa/finance_tools.py",
    ],
)
def test_no_official_metric_appears_anywhere_in_production_python(module: str):
    """Catches bare literals and f-string interpolations alike."""
    path = SRC / "residual_zero" / module
    if not path.is_file():
        pytest.skip(f"{module} not present")
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.lstrip().startswith("#"):
            continue
        for number in OFFICIAL_NUMBERS:
            assert number not in line, f"{module}:{i} hardcodes {number}: {line.strip()}"


def test_ai_answer_surfaces_still_report_sourced_values():
    """The fix must not have blanked the real AI-facing metrics."""
    from residual_zero.console.facts import t04_fields
    from residual_zero.qa.desk_tools import batch_prose

    if not (REPO / "artifacts" / "dev" / "t04.md").is_file():
        pytest.skip("committed dev card not present")
    prose = batch_prose()
    assert t04_fields("dev")["residual-zero"] in prose
    assert t04_fields("test")["residual-zero"] in prose


# ------------------------------------------------------------------------------
# Defect: `/` returned 500 and the browser suite could not diagnose it because the
# server log was discarded. Guard the diagnostics and forbid blanket suppression.
# ------------------------------------------------------------------------------


def test_browser_smoke_asserts_absence_of_tracebacks():
    text = (REPO / "tests" / "e2e" / "test_smoke.py").read_text(encoding="utf-8")
    assert 'assert "Traceback" not in body' in text
    assert "page_errors" in text


def test_e2e_conftest_captures_the_console_server_log():
    """A 500 must be diagnosable after the run."""
    text = (REPO / "tests" / "e2e" / "conftest.py").read_text(encoding="utf-8")
    assert "console_server.log" in text
    assert "stdout=subprocess.DEVNULL" not in text


def test_dashboard_handler_does_not_swallow_exceptions_wholesale():
    """The `/` route must fail loudly rather than render partial financial state."""
    app = (SRC / "residual_zero" / "console" / "app.py").read_text(encoding="utf-8")
    m = re.search(r"@app\.get\(\"/\", response_class=HTMLResponse\)\ndef batch\(\):(.*?)\n@app\.", app, re.S)
    assert m, "batch handler not found"
    body = m.group(1)
    assert "except Exception:  # noqa" not in body
    # The only tolerated suppressions are the two narrative helpers, which have
    # explicit empty-string fallbacks and carry no financial value.
    assert body.count("except Exception:") <= 2


def test_no_bare_except_in_the_console_package():
    for module in (SRC / "residual_zero" / "console").rglob("*.py"):
        if "__pycache__" in module.parts:
            continue
        assert not re.search(r"except\s*:", module.read_text(encoding="utf-8")), module


# ------------------------------------------------------------------------------
# Defect: ambiguity investigation stopped early instead of running the multi-step
# playbook, and refused tool requests left no audit trace.
# ------------------------------------------------------------------------------


def test_ambiguity_investigation_with_a_credit_runs_multiple_tools():
    from residual_zero.qa.agent_loop import run_agent
    from residual_zero.qa.finance_intents import FinanceIntent

    got = run_agent(
        "Why are there two valid explanations?",
        "crd_001_acc_01_2025-01-09",
        FinanceIntent.AMBIGUITY_ANALYSIS,
    )
    tools = [t["tool"] for t in got["tools"]]
    assert len(tools) >= 2, f"expected a multi-step investigation, got {tools}"
    assert "compare_solutions" in tools or "get_proof_explorer" in tools
    assert got["writes_cleared"] is False


def test_refused_tool_requests_are_recorded_for_audit():
    from residual_zero.qa import agent_loop
    from residual_zero.qa.finance_intents import FinanceIntent

    original = agent_loop.playbook
    agent_loop.playbook = lambda *a, **k: [("write_cleared", {}), ("get_transaction", {"transaction_id": "crd_001_acc_01_2025-01-09"})]
    try:
        got = agent_loop.run_agent("investigate", "crd_001_acc_01_2025-01-09", FinanceIntent.INVESTIGATE)
    finally:
        agent_loop.playbook = original
    assert "write_cleared" not in [t["tool"] for t in got["tools"]]
    assert [r["tool"] for r in got["rejected_tools"]] == ["write_cleared"]
    assert got["rejected_tools"][0]["executed"] is False


# ------------------------------------------------------------------------------
# Defect: browser assertions were case-sensitive against display copy.
# ------------------------------------------------------------------------------


def test_browser_assertions_are_case_insensitive_on_display_copy():
    smoke = (REPO / "tests" / "e2e" / "test_smoke.py").read_text(encoding="utf-8")
    assert ".lower()" in smoke or ".casefold()" in smoke
    dashboard = (REPO / "tests" / "e2e" / "test_dashboard.py").read_text(encoding="utf-8")
    assert ".casefold()" in dashboard or ".lower()" in dashboard


# ------------------------------------------------------------------------------
# Defect: the certification terminal block printed Playwright as `passed / passed`.
# ------------------------------------------------------------------------------


def test_certification_reports_playwright_against_the_collected_total():
    text = (REPO / "scripts" / "release_certify.py").read_text(encoding="utf-8")
    assert "e.get('suite_total')" in text
    assert "{e.get('passed')} / {e.get('passed')}" not in text
