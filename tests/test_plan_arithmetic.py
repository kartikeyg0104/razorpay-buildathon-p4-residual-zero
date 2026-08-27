"""The plan's own arithmetic reconciles.

Spec §9.8 asks for this in passing and it is worth honouring: a wrong number in your own schedule
is a smaller problem than a wrong number in your results only because nobody else reads it. A plan
whose totals disagree is a plan you stop trusting halfway through, and then abandon.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


def test_third_wave_group_hours_sum_to_the_wave_total():
    """§6.2: Group A 39 + B 50 + C 33 + D 23 + E 26 == 171h of third-wave work."""
    assert 39 + 50 + 33 + 23 + 26 == 171


def test_post_phase1_queue_reconciles():
    """§6.2: 171h, minus F56's 5h which moves into Phase 1, plus the 26h second-wave carry."""
    assert 171 - 5 + 26 == 192


def test_phase_totals_match_the_queue():
    """§11: Phase 2 71h + Phase 3 69h + Phase 4 52h == the same 192h, ordered differently."""
    assert 71 + 69 + 52 == 192


def test_phase1_ladder_sums_to_the_stated_build_time():
    """§11: Day 0 at 8h, Days 1-8 at 16h, Day 9 at 10h == 146h of own build time.

    F56 adds ~5h that is mostly the raters' time, which is why the phase heading reads ~151h and
    the days read 146. That is the one place the two figures differ and it is stated, not hidden.
    """
    assert 8 + 16 * 8 + 10 == 146
    assert 146 + 5 == 151


def test_plan_ladder_estimates_match_the_stated_total():
    """The estimates written into PLAN-P1.md's CP headings actually sum to 146."""
    plan = Path("PLAN-P1.md")
    if not plan.exists():
        pytest.skip("PLAN-P1.md not present")
    hours = [int(h) for h in re.findall(r"^### CP\d+ · .+? · (\d+)h · trip-wire", plan.read_text(encoding="utf-8"), re.M)]
    assert len(hours) == 10, f"expected 10 checkpoint headings, found {len(hours)}"
    assert sum(hours) == 146, f"ladder sums to {sum(hours)}h, not 146h"


def test_makefile_targets_match_the_documented_list():
    """A target named in a document and absent from the repo is the cheapest way to look careless.

    The list must stay identical across spec §7, spec §10 and CLAUDE.md.
    """
    expected = {
        "demo", "eval", "test", "verify-audit", "verify-books",
        "reproduce", "challenge", "evidence", "eval-diff",
    }
    makefile = Path("Makefile").read_text(encoding="utf-8")
    declared = set(re.findall(r"^\.PHONY:(.*)$", makefile, re.M)[0].split())
    assert declared == expected, f"missing {expected - declared}, unexpected {declared - expected}"
    for target in expected:
        assert re.search(rf"^{re.escape(target)}:", makefile, re.M), f"no rule for '{target}'"
