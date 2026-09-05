"""Proof-centric credit page and Proof Explorer in a real browser."""

from __future__ import annotations

import pytest

from tests.e2e.conftest import shot_dir

pytestmark = pytest.mark.e2e

TWINS = "crd_mix_ambiguous_twins"


def test_credit_page_financial_truth(page, console):
    page.goto(console + f"/credit/{TWINS}", wait_until="domcontentloaded", timeout=30000)
    body = page.inner_text("body")
    for needle in (
        "BANK AMOUNT",
        "RESIDUAL",
        "EXPLANATIONS FOUND",   # was "SOLUTION COUNT" (relabelled 2026-09)
        "UNIQUENESS",
        "VERIFICATION",
        "SETTLEMENT VERIFIED",  # Gate A relabelled for non-specialists (2026-09)
        "MATCHED RECORDS",
        "WHY NOT CLEARED",
        "PROOF EXPLORER",
        "CANDIDATE EQUATIONS",
        "SOURCE COMPARISON",
        "AI INVESTIGATION",
        "INVESTIGATE WITH AI",
        "human decision",
    ):
        assert needle.lower() in body.lower(), needle
    assert "AMBIGUOUS" in body
    assert "does not write CLEARED" in body or "Overlay does not write CLEARED" in body
    # Mixed twins are not UNIQUE / CLEARED as a financial state.
    assert "Eval would clear" in body or "REFUSE" in body
    assert "94%" not in body
    assert "likely winner" not in body.casefold()


def test_proof_explorer_two_solutions(page, console):
    page.goto(console + f"/proof/{TWINS}", wait_until="domcontentloaded", timeout=30000)
    body = page.inner_text("body")
    for needle in (
        # F36's side-by-side diff, relabelled 2026-09: SOLUTION A/B -> Explanation A/B,
        # "common records" -> "shared records", "only A" -> "only in A".
        "Explanation A",
        "Explanation B",
        "shared records",
        "only in A",
        "only in B",
        "distinguishing evidence",
        "Both explanations satisfy the financial equation",
        "Human review is required",
    ):
        assert needle.lower() in body.lower() or needle in body, needle
    assert "94%" not in body
    assert "AI confidence" not in body
    assert "best candidate" not in body.casefold()
    art = shot_dir()
    art.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(art / "proof-explorer.png"))
