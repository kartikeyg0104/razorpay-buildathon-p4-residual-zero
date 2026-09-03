"""Regression: /evidence derives its numbers and renders the test-split card it computed.

Two defects, one page. `evidence()` passed `t04_test=t04_view("test")` into a template that
never referenced it, so the held-out card (settlement-linked, residual-zero, and the
`800/800` search coverage) was computed on every request and thrown away. And two KPI values
— A0 exact and A2 cleared — were literals baked into the template, so they could not follow
`artifacts/dev/headline.md` the way facts.py deliberately does.
"""

from __future__ import annotations

from pathlib import Path

from residual_zero.console.app import app
from residual_zero.console.extra import _arm_cell
from residual_zero.console.facts import t04_view

TEMPLATE = Path("src/residual_zero/console/templates/evidence.html")


def _evidence_body() -> str:
    route = next(r for r in app.routes if getattr(r, "path", "") == "/evidence")
    return route.endpoint().body.decode()


def test_arm_cell_reads_the_committed_card():
    rows = [["a0", "239", "0/239", "—", "0/5973", "0", "—", "—"],
            ["a2", "239", "0/239", "x", "y", "147", "92", "0"]]
    assert _arm_cell(rows, "a0", 2) == "0/239"
    assert _arm_cell(rows, "a2", 5) == "147"


def test_arm_cell_renders_a_dash_rather_than_inventing_a_number():
    """Same discipline as facts.py: a missing card must never render as a plausible value."""
    assert _arm_cell([], "a0", 2) == "—"
    assert _arm_cell([["a0", "239"]], "a0", 5) == "—"
    assert _arm_cell([["a3", "239", "148/239"]], "a0", 2) == "—"


def test_the_kpi_numbers_are_not_literals_in_the_template():
    text = TEMPLATE.read_text(encoding="utf-8")
    assert "0/239" not in text
    assert ">147<" not in text
    assert "a0_exact" in text
    assert "a2_cleared" in text


def test_the_held_out_card_is_actually_rendered():
    body = _evidence_body()
    card = t04_view("test")
    assert card, "artifacts/test/t04.md must be committed for this page to be honest"
    for key in ("identified", "residual_zero", "search_coverage"):
        value = card[key]
        assert value, f"t04_view('test')[{key!r}] is empty"
        assert value in body, f"{key}={value} computed but not rendered"


def test_search_coverage_is_not_presented_as_auto_clear():
    """800/800 search completed sits next to auto-clear 0; the page must not conflate them."""
    body = _evidence_body().lower()
    assert "search completed" in body
    assert "auto-clear" in body
    assert "uniqueness still refuses" in body
