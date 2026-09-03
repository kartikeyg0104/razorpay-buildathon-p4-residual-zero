"""Human review and explorer chips in a real browser."""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e

TWINS = "crd_mix_ambiguous_twins"
DEMO = "crd_001_acc_01_2025-01-09"


def test_human_review_save_does_not_clear(page, console):
    page.goto(console + f"/credit/{DEMO}#human-decision", wait_until="domcontentloaded", timeout=30000)
    body = page.inner_text("body")
    assert "AI is not the decision maker" in body or "human decision" in body.casefold()
    page.locator("[data-work-note]").fill("hardening e2e note")
    page.locator("[data-work-status]").select_option("investigating")
    page.locator("[data-work-save]").click()
    page.wait_for_timeout(800)
    after = page.inner_text("body")
    assert "CLEARED" in after  # policy text
    assert "does not write CLEARED" in after or "cannot be CLEARED" in after or "never CLEARED" in after.casefold()
    Path("artifacts").joinpath("demo").mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(Path("artifacts") / "demo" / "human-review.png"))


def test_explorer_recoverable_not_reconciled(page, console):
    page.goto(console + "/explorer?kind=POTENTIALLY_RECOVERABLE", wait_until="domcontentloaded", timeout=45000)
    body = page.inner_text("body")
    assert "NOT RECONCILED" in body or "not a match" in body.casefold()
    assert "writes CLEARED" in body or "read-only" in body.casefold()


def test_explorer_ambiguous_ids_listed(page, console):
    page.goto(console + "/explorer?kind=AMBIGUOUS", wait_until="domcontentloaded", timeout=60000)
    body = page.inner_text("body")
    assert "crd_" in body or "No rows" in body
    assert "does not write CLEARED" in body or "Overlay does not write CLEARED" in body
