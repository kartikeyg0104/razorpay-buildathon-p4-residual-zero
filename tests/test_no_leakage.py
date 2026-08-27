"""NN-6: ground truth is physically unreachable from the system under test."""

from __future__ import annotations

from pathlib import Path

import pytest

from residual_zero.ingest import SourceRoot, SourceRootError


SRC_ROOT = Path("src/residual_zero")


def test_source_root_cannot_escape(tmp_path: Path):
    """SourceRoot.open cannot reach truth.jsonl by relative path, absolute path or symlink."""
    rendered = tmp_path / "rendered"
    rendered.mkdir()
    (rendered / "bank.csv").write_text("id\n", encoding="utf-8")
    truth = tmp_path / "truth.jsonl"
    truth.write_text("{}\n", encoding="utf-8")
    root = SourceRoot(rendered)

    with pytest.raises(SourceRootError):
        root.open("../truth.jsonl")
    with pytest.raises(SourceRootError):
        root.open("/etc/passwd")

    escape = rendered / "escape.csv"
    escape.symlink_to(truth)
    with pytest.raises(SourceRootError):
        root.open("escape.csv")


def test_src_never_references_truth():
    """No module under src/residual_zero/ can name truth.jsonl.

    PLAN-P1 also asked this test to grep for the substrings ``truth`` and ``member_ids``.
    That literal reading is unsatisfiable: ``models.py`` carries ``member_ids`` on
    Decomposition, which is the system's own output, not the answer key. The invariant
    NN-6 actually requires is that the online path cannot open the answer-key file, so
    that is what is asserted. Recorded as a CP1 deviation in PROGRESS.md.
    """
    hits: list[str] = []
    for path in SRC_ROOT.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "truth.jsonl" in text:
            hits.append(str(path))
        if "load_truth" in text:
            hits.append(f"{path}:load_truth")
    assert hits == [], f"src/ references the answer key: {hits}"


def test_rendered_views_carry_no_class_labels(tmp_path: Path):
    """No column in any rendered view is a 1:1 stand-in for an applied corruption class."""
    from residual_zero.config import load_fees, load_profile, load_tax_rates
    from generator.corrupt import apply_corruptions, phase1_dev_plan
    from generator.render import render
    from generator.scenario import build_scenario
    from generator.truth import build_truth
    from random import Random

    profile = load_profile(Path("config/profiles/phase1.yaml"))
    truth = build_truth(build_scenario(profile, seed=1), load_tax_rates(), load_fees())
    views, _records = apply_corruptions(render(truth), truth, phase1_dev_plan(), Random(1))
    forbidden = {"class", "corruption", "corruption_class", "class_id", "cause"}
    for rows, name in (
        (views.bank_rows, "bank"),
        (views.ledger_rows, "ledger"),
        (views.settlement_rows, "settlement"),
    ):
        if not rows:
            continue
        columns = {c.lower() for c in rows[0].keys()}
        assert not (columns & forbidden), f"{name} carries a class-label column: {columns & forbidden}"
