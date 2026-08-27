"""Challenge fixtures reach a terminal disposition."""

from __future__ import annotations

from pathlib import Path

from residual_zero.challenge import run_challenge
from residual_zero.models import Disposition

ROOT = Path("fixtures/challenges")


def test_three_challenge_files_run():
    for name in ("solvable_aggregate.json", "ambiguous_refused.json", "unsolvable_missing_record.json"):
        disp = run_challenge(ROOT.joinpath(name))
        assert disp in Disposition


def test_the_unsolvable_challenge_is_refused():
    disp = run_challenge(ROOT.joinpath("unsolvable_missing_record.json"))
    assert disp != Disposition.CLEARED
