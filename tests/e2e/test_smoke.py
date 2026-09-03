"""Browser smoke: real navigation, headings, no uncaught exceptions."""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e

PAGES = (
    ("/", "batch"),
    ("/demo", "Product Tour"),   # page renamed from "Demo" (2026-09)
    ("/explorer", "explorer"),
    ("/ask", "AI FINANCE CONTROLLER"),
    ("/evidence", "evidence"),
    ("/challenge", "Evaluation Lab"),   # page renamed from "Challenge" (2026-09)
    ("/safety", "safety"),
    ("/close", "month-end"),
    ("/exceptions", "Exceptions"),
    ("/audit", "audit"),
    ("/credit/crd_mix_ambiguous_twins", "crd_mix_ambiguous_twins"),
    ("/proof/crd_mix_ambiguous_twins", "crd_mix_ambiguous_twins"),
)


def test_smoke_pages(page, page_errors, console):
    """Visit every major page. Collect ALL failures rather than stopping at the first.

    Failing fast here hid later pages behind whichever one broke first, so a single stale
    heading made the rest of the sweep invisible (2026-09).
    """
    art = Path("artifacts").joinpath("e2e")
    art.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []
    for path, needle in PAGES:
        page.goto(console + path, wait_until="domcontentloaded", timeout=30000)
        body = page.inner_text("body")
        if not (needle.lower() in body.lower() or needle in page.title() or needle in body):
            failures.append(f"{path}: missing {needle!r}")
        # A rendered traceback is a hard stop: a 500 is not something to sweep past.
        assert "Traceback" not in body, path
        if page_errors:
            shot = art / f"fail_{path.strip('/').replace('/', '_') or 'home'}.png"
            page.screenshot(path=str(shot))
            failures.append(f"{path}: console/page errors: {list(page_errors)}")
            page_errors.clear()
    assert not failures, "\n".join(failures)
