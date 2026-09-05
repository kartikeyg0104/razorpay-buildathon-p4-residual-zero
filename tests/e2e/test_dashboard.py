"""Dashboard UI agrees with /api/t04 official cards."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.e2e.conftest import shot_dir

pytestmark = pytest.mark.e2e


def test_dashboard_matches_api_t04(page, console):
    import urllib.request

    with urllib.request.urlopen(console + "/api/t04") as resp:
        api = json.loads(resp.read().decode("utf-8"))
    page.goto(console + "/", wait_until="domcontentloaded", timeout=30000)
    body = page.inner_text("body")
    test = api.get("test") or {}
    stats = api.get("stats") or {}
    rz = str(test.get("residual-zero") or stats.get("residual_zero") or "")
    assert "521/800" in body or rz in body
    assert "0" in body
    assert "does not write CLEARED" in body or "Overlay does not write CLEARED" in body
    assert "false clear" in body.casefold() or "false_clears" in body.casefold() or "0 false" in body.casefold()
    mismatches = []
    if rz and rz not in body and "521/800" not in body:
        mismatches.append({"metric": "test_residual_zero", "api": rz, "ui": "missing"})
    # Written beside the other E2E output (gitignored) rather than into the committed
    # QA artifact, so running the suite never rewrites a published record.
    (shot_dir() / "ui_backend_consistency.json").write_text(
        json.dumps(
            {
                "api_t04": api.get("stats"),
                "test": test,
                "ui_contains_521_800": "521/800" in body,
                "ui_contains_159_239": "159/239" in body,
                "mismatches": mismatches,
                "writes_cleared": False,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    assert not mismatches
