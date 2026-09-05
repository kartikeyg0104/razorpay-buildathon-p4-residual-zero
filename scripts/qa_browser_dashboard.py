"""Verify the live dashboard in a real browser, not with curl.

An API returning the right JSON does not prove the page a person sees renders it. This
logs in, reads the KPI cards out of the DOM, hard-refreshes, logs out and back in, and
reports whether the values moved. It also records what the page itself logs to the
console, which is the only way to tell the application's own messages from a browser
extension's.

    RZ_QA_PASSWORD=... python scripts/qa_browser_dashboard.py \
        --url https://... --email you@example.com --shots ./shots

Read-only: it signs in and looks. It changes nothing.
"""

from __future__ import annotations

import argparse
import os
import sys

CARDS = (
    "search", "unique explanation", "ambiguous", "auto-cleared",
    "human review queue", "verified & accepted", "journal-ready",
)


def _cards(page) -> dict[str, str]:
    out: dict[str, str] = {}
    for article in page.query_selector_all("article.kpi"):
        label, value = article.query_selector(".lbl"), article.query_selector(".val")
        if label and value:
            out[label.inner_text().strip().lower()] = " ".join(value.inner_text().split())
    return out


def _banner(page) -> str:
    element = page.query_selector(".status")
    return " ".join(element.inner_text().split()) if element else "?"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--shots", default="", help="directory for screenshots")
    args = parser.parse_args(argv)

    password = os.environ.get("RZ_QA_PASSWORD") or ""
    if not password:
        print("set RZ_QA_PASSWORD (never pass a password on a command line)", file=sys.stderr)
        return 2

    from playwright.sync_api import sync_playwright

    def sign_in(page):
        page.goto(args.url + "/login", wait_until="networkidle")
        page.fill("#email", args.email)
        page.fill("#password", password)
        page.click("button[type=submit]")
        page.wait_for_load_state("networkidle")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport={"width": 1500, "height": 1150})
        page = context.new_page()
        console: list[tuple[str, str]] = []
        page.on("console", lambda m: console.append((m.type, m.text[:200])))
        page.on("pageerror", lambda e: console.append(("pageerror", str(e)[:200])))

        try:
            sign_in(page)
            first = _cards(page)
            print("banner:", _banner(page))
            for card in CARDS:
                print(f"  {card:22s} {first.get(card, '<missing>')}")
            if args.shots:
                os.makedirs(args.shots, exist_ok=True)
                page.screenshot(path=os.path.join(args.shots, "dashboard.png"))

            page.reload(wait_until="networkidle")
            after_refresh = _cards(page)
            page.goto(args.url + "/logout", wait_until="networkidle")
            sign_in(page)
            after_relogin = _cards(page)

            print("identical after hard refresh :", first == after_refresh)
            print("identical after logout/login :", first == after_relogin)
            print("console messages from the page:", console or "none")
            ok = first == after_refresh == after_relogin
        finally:
            browser.close()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
