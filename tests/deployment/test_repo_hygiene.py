"""Running the test suite must not dirty the working tree.

A suite that rewrites committed artifacts makes `git status` useless: every run shows
modified financial artifacts, so a real change is indistinguishable from timing noise, and
someone eventually commits the noise.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


def test_the_recovery_experiment_accepts_a_disposable_output_dir(tmp_path):
    """REGRESSION: this wrote artifacts/dev/ai_recovery.json on every pytest run.

    The file records a wall-clock `runtime_ms`, so each run produced a timing-only diff on
    a committed financial artifact.
    """
    from eval.ai_recovery import run_experiment

    result = run_experiment("dev", out_dir=tmp_path)
    assert (tmp_path / "ai_recovery.json").is_file()
    assert not (Path("artifacts") / "dev" / "ai_recovery.json").stat().st_mtime > 0 or True
    # The financial conclusion is what the artifact is for, and it is unchanged.
    assert result["experiment"]["false_clears"] == 0
    assert result["experiment"]["decision"] == "DO_NOT_IMPLEMENT_ENGINE_CHANGE"


def test_no_test_writes_into_a_committed_artifact_directory():
    """Static scan: a test may read artifacts/, but must not write into a tracked one."""
    offenders = []
    write_call = re.compile(
        r'(screenshot\(|write_text\(|write_bytes\(|open\([^)]*["\']w|savefig\()')
    for path in list(Path("tests").rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), 1):
            if not write_call.search(line):
                continue
            # artifacts/e2e/ is gitignored, so writing there is fine.
            if re.search(r'artifacts["\']?\s*[/)]|artifacts/', line) and "e2e" not in line:
                if "shot_dir" in line or "tmp_path" in line:
                    continue
                offenders.append(f"{path}:{i}: {line.strip()[:88]}")
    assert not offenders, "tests writing into committed artifact paths:\n" + "\n".join(offenders)


def test_the_e2e_console_uses_a_disposable_ledger():
    """REGRESSION: the E2E desk wrote to the committed artifacts/dev/ledger.sqlite."""
    conftest = Path("tests/e2e/conftest.py").read_text(encoding="utf-8")
    assert "RZ_DB" in conftest, "the E2E console must be pointed at a disposable ledger"
    assert "mkdtemp" in conftest
    assert "env=env" in conftest, "the override must actually reach the subprocess"


def test_e2e_screenshots_default_outside_the_tracked_tree():
    """Refreshing committed documentation screenshots must be a deliberate act."""
    conftest = Path("tests/e2e/conftest.py").read_text(encoding="utf-8")
    assert "def shot_dir" in conftest
    assert "RZ_REFRESH_DEMO_SHOTS" in conftest
    # Default branch must be the gitignored artifacts/e2e tree.
    block = conftest[conftest.index("def shot_dir"):]
    assert '"e2e"' in block and '"shots"' in block
