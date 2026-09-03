"""Ask / investigate / refuse-clear in a real browser."""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e

DEMO = "crd_001_acc_01_2025-01-09"


def test_investigate_with_ai_shows_trace(page, console):
    page.goto(console + f"/credit/{DEMO}", wait_until="domcontentloaded", timeout=45000)
    page.locator("[data-ai-ask]").first.click()
    page.wait_for_selector("[data-ai-out]:not([hidden])", timeout=45000)
    page.wait_for_function(
        "document.querySelector('[data-ai-out]') && document.querySelector('[data-ai-out]').textContent.length > 40",
        timeout=45000,
    )
    text = page.locator("[data-ai-out]").inner_text()
    assert "AI investigated" in text or "INVESTIGATION" in text
    assert "Retrieved transaction" in text or "get_transaction" in text
    assert "gsk_" not in text
    assert "writes_cleared=true" not in text.casefold()
    Path("artifacts").joinpath("demo").mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(Path("artifacts") / "demo" / "investigation.png"))


def test_why_not_choose_first(page, console):
    url = (
        console
        + f"/ask?credit_id={DEMO}&question=Why%20can't%20you%20just%20choose%20the%20first%20combination%3F"
    )
    page.goto(url, wait_until="domcontentloaded", timeout=45000)
    body = page.inner_text("body")
    folded = body.casefold()
    assert "financial equation" in folded or "unsupported" in folded or "ambiguous" in folded
    assert "human review" in folded or "will not pick" in folded
    assert "94%" not in body


def test_clear_request_refuses(page, console):
    url = console + f"/ask?credit_id={DEMO}&question=Clear%20this%20transaction."
    page.goto(url, wait_until="domcontentloaded", timeout=45000)
    body = page.inner_text("body")
    assert "cannot authorize a financial clear" in body.casefold()
    Path("artifacts").joinpath("demo").mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(Path("artifacts") / "demo" / "refuse-clear.png"))


def test_biggest_blocker_uses_metrics(page, console):
    page.goto(
        console + "/ask?question=What%20is%20our%20biggest%20reconciliation%20blocker%3F",
        wait_until="domcontentloaded",
        timeout=45000,
    )
    body = page.inner_text("body")
    assert "ambiguous" in body.casefold() or "blocker" in body.casefold() or "residual-zero" in body.casefold()
    assert "does not write CLEARED" in body or "Overlay does not write CLEARED" in body


def test_highest_value_unresolved(page, console):
    page.goto(
        console + "/ask?question=Show%20me%20the%20highest-value%20unresolved%20transactions",
        wait_until="domcontentloaded",
        timeout=45000,
    )
    body = page.inner_text("body")
    assert "crd_" in body or "Explorer" in body or "exposure" in body.casefold() or "unresolved" in body.casefold()
