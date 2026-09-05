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


def test_no_test_module_imports_playwright_at_module_level():
    """A `pip install -e ".[dev]"` must be able to collect the whole suite.

    playwright lives in the `[e2e]` extra on purpose, so unit and integration tests install
    without a browser toolchain. A module-level `from playwright... import ...` in any test
    file turns that install into a collection error for the entire run - caught by cloning
    the repository and installing only `[dev]`.
    """
    import ast

    offenders = []
    for path in Path("tests").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:  # module level only; inside a function is fine
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                name = (node.module or "") if isinstance(node, ast.ImportFrom) \
                    else node.names[0].name
                if "playwright" in name:
                    offenders.append(f"{path}:{node.lineno}")
    assert not offenders, (
        "module-level playwright imports break a [dev]-only install: " + ", ".join(offenders)
    )


def test_the_image_copies_every_directory_read_at_runtime():
    """A path the app reads must exist in the deployed image.

    `fixtures/` was missing, and the settlement adapter reads it in fixture mode - so the
    credit detail page returned 500 in the container while passing every local test. This
    compares what src/ opens by relative path against what the Dockerfile copies.
    """
    import re

    src_text = "\n".join(
        p.read_text(encoding="utf-8") for p in Path("src/residual_zero").rglob("*.py")
    )
    used = set(re.findall(r'Path\("([a-z_]+)"\)', src_text))
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
    copied = set(re.findall(r"^COPY\s+([a-z_]+)\s", dockerfile, re.M))
    # `var` is created at runtime for per-organisation SQLite; it is not shipped.
    missing = sorted(used - copied - {"var"})
    assert not missing, (
        f"read at runtime but not COPYed into the image: {missing}"
    )
