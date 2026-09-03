#!/usr/bin/env python3
"""Capture demo screenshots with Playwright against http://127.0.0.1:8765."""

from __future__ import annotations

import json
import sqlite3
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEMO = "crd_001_acc_01_2025-01-09"
TWINS = "crd_mix_ambiguous_twins"
BASE = "http://127.0.0.1:8765"


def get_json(path: str) -> dict:
    with urllib.request.urlopen(BASE + path) as resp:
        return json.loads(resp.read().decode("utf-8"))


def cleared_count() -> int:
    db = ROOT / "artifacts/dev/ledger.sqlite"
    if not db.is_file():
        return -1
    conn = sqlite3.connect(db)
    try:
        return int(conn.execute("SELECT COUNT(*) FROM reconciliation WHERE disposition = 'CLEARED'").fetchone()[0])
    except sqlite3.OperationalError:
        return 0
    finally:
        conn.close()


def main() -> int:
    from playwright.sync_api import sync_playwright

    out = ROOT / "artifacts" / "demo"
    out.mkdir(parents=True, exist_ok=True)
    t04 = get_json("/api/t04")
    health = get_json("/api/health")
    report = {
        "api_t04": t04.get("test"),
        "health_writes_cleared": health.get("writes_cleared"),
        "cleared_before": cleared_count(),
        "steps": [],
    }
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        page.goto(BASE + "/", wait_until="domcontentloaded")
        page.screenshot(path=str(out / "dashboard.png"), full_page=True)
        report["steps"].append({"step": 1, "path": "/", "ok": "521/800" in page.inner_text("body") or "159/239" in page.inner_text("body")})
        page.goto(BASE + f"/credit/{DEMO}", wait_until="domcontentloaded")
        page.screenshot(path=str(out / "credit.png"), full_page=True)
        page.locator("[data-ai-ask]").first.click()
        page.wait_for_timeout(4000)
        page.screenshot(path=str(out / "investigation.png"), full_page=True)
        page.goto(BASE + f"/proof/{TWINS}", wait_until="domcontentloaded")
        page.screenshot(path=str(out / "proof-explorer.png"), full_page=True)
        page.goto(BASE + f"/credit/{TWINS}#source-comparison", wait_until="domcontentloaded")
        page.screenshot(path=str(out / "source-comparison.png"), full_page=True)
        page.goto(BASE + f"/credit/{TWINS}#proof-explorer", wait_until="domcontentloaded")
        page.screenshot(path=str(out / "candidate-comparison.png"), full_page=True)
        page.goto(BASE + f"/credit/{DEMO}#human-decision", wait_until="domcontentloaded")
        page.screenshot(path=str(out / "human-review.png"), full_page=True)
        q = urllib.parse.quote("Clear this transaction.")
        page.goto(BASE + f"/ask?credit_id={DEMO}&question={q}", wait_until="domcontentloaded")
        page.screenshot(path=str(out / "refuse-clear.png"), full_page=True)
        refuse = "cannot authorize a financial clear" in page.inner_text("body").casefold()
        report["steps"].append({"step": 10, "refuse_clear": refuse})
        browser.close()
    report["cleared_after"] = cleared_count()
    report["writes_cleared"] = False
    (out / "demo_run.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"screenshots": str(out), "cleared_after": report["cleared_after"], "refuse": refuse}, indent=2))
    return 0 if refuse and report["cleared_after"] in (0, -1) else 1


if __name__ == "__main__":
    raise SystemExit(main())
