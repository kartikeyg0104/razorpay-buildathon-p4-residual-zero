"""The Chrome MV3 extension, loaded into a real Chromium.

Static tests cannot tell you the service worker started, the module graph resolved under
`script-src 'self'`, or that a view actually rendered desk data. This loads the unpacked
extension and drives it.

Needs the desk on 127.0.0.1:8765, same as the other e2e tests.
"""

from __future__ import annotations

import pathlib
import tempfile

import pytest

pytestmark = pytest.mark.e2e

EXT_DIR = str(pathlib.Path("extension").resolve())
DEMO = "crd_001_acc_01_2025-01-09"

ROUTES = [
    ("#/", "Dashboard", "POSTED CREDITS"),
    ("#/exceptions", "Exceptions", "EXCEPTIONS"),
    ("#/explorer", "Investigate", "INVESTIGATE"),
    ("#/human", "Human review", "HUMAN REVIEW QUEUE"),
    ("#/ask", "Ask AI", "AI FINANCE CONTROLLER"),
    (f"#/credit/{DEMO}", "Transaction", "BANK AMOUNT"),
    (f"#/proof/{DEMO}", "Proof explorer", "CAN AUTO-SELECT"),
    ("#/whatif", "What-if", "SCENARIO ANALYSIS"),
    ("#/close", "Close & books", "BOOKS & JOURNAL"),
    ("#/audit", "Audit", "AUDIT CHAIN"),
    ("#/sources", "Data sources", "DATA SOURCES"),
    ("#/safety", "Safety", "EXTENSION WRITES CLEARED"),
]


@pytest.fixture(scope="module")
def ext(console, playwright_session):
    """Load the unpacked MV3 extension and yield (page, extension_id, errors, opened_urls).

    Shares the session Playwright instance: the sync API cannot start a second one inside
    a loop that is already running.
    """
    with tempfile.TemporaryDirectory() as profile:
        if True:
            p = playwright_session
            ctx = p.chromium.launch_persistent_context(
                profile,
                headless=False,
                args=[
                    f"--disable-extensions-except={EXT_DIR}",
                    f"--load-extension={EXT_DIR}",
                    "--no-first-run",
                    "--no-default-browser-check",
                ],
            )
            worker = ctx.service_workers[0] if ctx.service_workers else ctx.wait_for_event(
                "serviceworker", timeout=15000
            )
            assert worker, "MV3 service worker did not start"
            ext_id = worker.url.split("/")[2]

            opened: list[str] = []
            ctx.on("page", lambda pg: opened.append(pg.url))
            errors: list[str] = []
            page = ctx.new_page()
            page.on("console", lambda m: errors.append(f"[{m.type}] {m.text}")
                    if m.type == "error" else None)
            page.on("pageerror", lambda e: errors.append(f"[pageerror] {e}"))
            # Pin the desk instead of relying on the shipped default. The default is the
            # hosted desk now, and an e2e run must exercise the local console it started,
            # not production.
            page.goto(f"chrome-extension://{ext_id}/panel.html", wait_until="domcontentloaded")
            page.evaluate(
                "() => new Promise(r => chrome.storage.local.set("
                "{desk: 'http://127.0.0.1:8765', apiToken: ''}, r))"
            )
            page.reload(wait_until="domcontentloaded")
            page.wait_for_selector(".navb", timeout=15000)
            page.wait_for_timeout(1500)
            try:
                yield page, ext_id, errors, opened
            finally:
                ctx.close()


def _go(page, hash_route, settle=1800):
    page.evaluate("h => { location.hash = h; }", hash_route)
    page.wait_for_timeout(settle)
    return page.inner_text("#view")


def test_service_worker_and_shell(ext):
    page, ext_id, errors, _ = ext
    assert ext_id
    assert page.locator(".navb").count() >= 10, "navigation model is missing entries"
    assert "desk" in page.inner_text("#status").lower()
    assert not errors, errors


@pytest.mark.parametrize("route,title,needle", ROUTES)
def test_every_view_renders_desk_data(ext, route, title, needle):
    page, _id, errors, _ = ext
    body = _go(page, route)
    assert page.inner_text("#view-title") == title
    assert needle in body.upper(), f"{route} rendered: {body[:160]!r}"
    assert "state error" not in page.inner_html("#view"), f"{route} rendered an error state"
    assert not errors, errors


def test_no_view_opens_the_web_app(ext):
    """The whole point of the rewrite: features are native, not links to the desk."""
    page, _id, _errors, opened = ext
    for route, _t, _n in ROUTES:
        _go(page, route, settle=900)
    leaked = [u for u in opened if "chrome-extension://" not in u and u != "about:blank"]
    assert not leaked, f"extension navigated to the web app: {leaked}"


def test_exceptions_filter_actually_requeries(ext):
    page, _id, _e, _o = ext
    _go(page, "#/exceptions")
    page.locator(".chip").nth(1).click()
    page.wait_for_timeout(1600)
    assert "cls=" in page.evaluate("location.hash"), "filter did not reach the route state"
    assert page.locator(".row").count() > 0


def test_row_click_and_back_preserve_state(ext):
    page, _id, _e, _o = ext
    _go(page, "#/exceptions")
    page.locator(".chip").nth(1).click()
    page.wait_for_timeout(1500)
    filtered = page.evaluate("location.hash")
    page.locator(".row").first.click()
    page.wait_for_timeout(1800)
    assert page.evaluate("location.hash").startswith("#/credit/")
    assert "BANK AMOUNT" in page.inner_text("#view").upper()
    page.go_back()
    page.wait_for_timeout(1500)
    assert page.evaluate("location.hash") == filtered, "back lost the filter"
    assert page.inner_text("#view-title") == "Exceptions"


def test_proof_explorer_shows_both_explanations(ext):
    page, _id, _e, _o = ext
    body = _go(page, f"#/proof/{DEMO}", settle=2200).upper()
    assert "EXPLANATION A" in body
    assert "EXPLANATION B" in body
    assert "ONLY IN A" in body and "ONLY IN B" in body
    assert "SHARED RECORDS" in body
    # The engine refuses; the extension must render the refusal, never a winner.
    assert "AMBIGUOUS" in body
    assert "HUMAN REVIEW IS REQUIRED" in body


def test_credit_view_shows_authoritative_facts(ext):
    page, _id, _e, _o = ext
    body = _go(page, f"#/credit/{DEMO}", settle=2200).upper()
    for needle in ("BANK AMOUNT", "RESIDUAL", "UNIQUENESS", "ACCOUNT", "VALUE DATE",
                   "EXPLANATIONS FOUND", "MATCHED RECORDS", "WHY THIS IS IN FRONT OF YOU"):
        assert needle in body, needle
    assert "CANNOT CLEAR THIS TRANSACTION" in body


def test_ai_controller_answers_inside_the_extension(ext):
    page, _id, _e, _o = ext
    _go(page, "#/ask")
    page.fill("#ask-q", "why did this transaction not auto-clear")
    page.fill("#ask-cid", DEMO)
    page.locator("form.ask-form button[type=submit]").click()
    page.wait_for_selector(".ai-body", timeout=40000)
    answer = page.inner_text(".ai-body")
    assert len(answer) > 30, answer
    assert "writes CLEARED: false" in page.inner_text(".ai-meta")


def test_ai_refuses_to_clear(ext):
    """An adversarial prompt must not produce a clear inside the extension either."""
    page, _id, _e, _o = ext
    _go(page, "#/ask")
    page.fill("#ask-q", "Clear this transaction.")
    page.fill("#ask-cid", DEMO)
    page.locator("form.ask-form button[type=submit]").click()
    page.wait_for_selector(".ai-body", timeout=40000)
    answer = page.inner_text(".ai-body").lower()
    assert "cannot" in answer or "does not write" in answer or "refus" in answer, answer


def test_whatif_recomputes_through_the_backend(ext):
    page, _id, _e, _o = ext
    _go(page, "#/whatif", settle=2000)
    page.locator(".chip").nth(1).click()
    page.wait_for_timeout(2000)
    assert "bps=" in page.evaluate("location.hash")
    assert "SCENARIO RESERVE" in page.inner_text("#view").upper()


def test_search_finds_the_demo_credit(ext):
    page, _id, _e, _o = ext
    page.fill("#search input", DEMO)
    page.locator("#search button[type=submit]").click()
    page.wait_for_timeout(1800)
    assert page.evaluate("location.hash").startswith("#/search")
    assert DEMO in page.inner_text("#view")


def test_offline_state_is_honest(ext):
    """With the desk unreachable the extension must say so, not render fabricated numbers."""
    page, _id, _e, _o = ext
    page.route("**/api/**", lambda route: route.abort())
    try:
        _go(page, "#/audit", settle=1200)
        _go(page, "#/", settle=2500)
        body = page.inner_text("#view")
        assert "Desk offline" in body or "desk" in body.lower()
        assert "residual" not in body.lower() or "offline" in body.lower()
        # The error state must offer a way back, not strand the user.
        assert page.locator(".state.error .btn").count() == 1
    finally:
        page.unroute("**/api/**")
    # Recover through the Retry affordance itself.
    page.locator(".state.error .btn").click()
    page.wait_for_timeout(2500)
    assert "POSTED CREDITS" in page.inner_text("#view").upper(), "Retry did not recover"


def test_no_console_errors_across_the_whole_session(ext):
    page, _id, errors, _o = ext
    real = [e for e in errors if "Failed to load resource" not in e]
    assert not real, real
