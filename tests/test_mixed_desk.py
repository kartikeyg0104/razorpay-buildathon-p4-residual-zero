"""Constructed mixed uniqueness desk. Not official Track 04."""

from __future__ import annotations

from residual_zero.console.app import credit_view
from residual_zero.console.mixed_desk import mixed_counts, mixed_rows


def test_mixed_desk_has_all_three_outcomes():
    rows = mixed_rows()
    kinds = {row.uniqueness for row in rows}
    assert kinds == {"UNIQUE", "AMBIGUOUS", "NONE_FOUND"}
    for row in rows:
        assert row.uniqueness == row.expect
    counts = mixed_counts()
    assert counts["unique"] >= 1
    assert counts["ambiguous"] >= 1
    assert counts["none_found"] >= 1
    assert counts["eval_eligible"] == counts["unique"]
    assert counts["overlay_cleared"] == 0
    unique_rows = [row for row in rows if row.uniqueness == "UNIQUE"]
    assert unique_rows
    assert unique_rows[0].eval_label == "ELIGIBLE"
    assert unique_rows[0].console_write == "REFUSE"
    amb = next(row for row in rows if row.uniqueness == "AMBIGUOUS")
    assert amb.eval_label == "REFUSE"
    assert amb.residual == "0.00"


def test_mixed_credit_pages_render():
    unique = credit_view("crd_mix_unique_pair")
    assert unique.status_code == 200
    assert b"ELIGIBLE" in unique.body
    assert b"UNIQUE" in unique.body
    assert b"CONSTRUCTED_MIXED" in unique.body
    assert b"does not write CLEARED" in unique.body
    amb = credit_view("crd_mix_ambiguous_twins")
    assert amb.status_code == 200
    assert b"AMBIGUOUS" in amb.body
    assert b"Eval would clear" in amb.body
    none = credit_view("crd_mix_none")
    assert none.status_code == 200
    assert b"NONE_FOUND" in none.body


def test_mixed_route_mounted():
    from residual_zero.console.app import app

    paths = {getattr(route, "path", "") for route in app.routes}
    assert "/mixed" in paths
    page = next(r for r in app.routes if getattr(r, "path", "") == "/mixed")
    body = page.endpoint().body
    assert b"constructed search pools" in body.lower()
    assert b"crd_mix_unique_pair" in body
    assert b"not official Track 04" in body
    assert b"0/239" in body
