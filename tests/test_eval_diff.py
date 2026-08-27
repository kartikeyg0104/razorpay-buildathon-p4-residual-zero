"""F54 eval-diff."""

from __future__ import annotations

import json
from pathlib import Path

from eval.diff import diff_maps, main, render_md


def test_identical_runs_have_empty_diff(tmp_path: Path):
    payload = {"c1": "FLAGGED", "c2": "BUDGET_EXCEEDED"}
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir(); b.mkdir()
    (a / "dispositions.json").write_text(json.dumps(payload), encoding="utf-8")
    (b / "dispositions.json").write_text(json.dumps(payload), encoding="utf-8")
    rows = diff_maps(payload, payload)
    assert rows == []
    assert "0 disposition" in render_md(rows, "a", "b")
    assert main(["--a", str(a), "--b", str(b)]) == 0


def test_direction_is_recorded(tmp_path: Path):
    a = {"c1": "FLAGGED"}
    b = {"c1": "CLEARED"}
    rows = diff_maps(a, b)
    assert rows == [{"credit_id": "c1", "from": "FLAGGED", "to": "CLEARED"}]


def test_missing_run_exits_nonzero(tmp_path: Path):
    assert main(["--a", str(tmp_path / "missing"), "--b", str(tmp_path / "missing")]) == 1
