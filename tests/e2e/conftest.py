"""Live browser E2E. Requires RZ_E2E=1 and a console on 127.0.0.1:8765."""

from __future__ import annotations

import os
import socket
import subprocess
import time
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.filterwarnings("ignore::DeprecationWarning"),
    pytest.mark.filterwarnings("ignore::ResourceWarning"),
]

BASE = "http://127.0.0.1:8765"
TWINS = "crd_mix_ambiguous_twins"
DEMO = "crd_001_acc_01_2025-01-09"
ART = Path("artifacts").joinpath("e2e")


def _port_open() -> bool:
    sock = socket.socket()
    sock.settimeout(0.4)
    try:
        sock.connect(("127.0.0.1", 8765))
        return True
    except OSError:
        return False
    finally:
        sock.close()


_E2E_DIR = Path(__file__).resolve().parent


def _is_e2e_item(item) -> bool:
    """True only for browser E2E items.

    This hook is handed every item in the session, not just the ones under this
    directory, so it must filter. Both the path and the `e2e` marker are checked so a
    new module that forgets `pytestmark` is still gated.
    """
    if item.get_closest_marker("e2e") is not None:
        return True
    path = getattr(item, "path", None) or getattr(item, "fspath", None)
    if path is None:
        return False
    try:
        return _E2E_DIR in Path(str(path)).resolve().parents
    except OSError:
        return False


def pytest_collection_modifyitems(config, items):
    if os.environ.get("RZ_E2E") == "1":
        return
    skip = pytest.mark.skip(reason="set RZ_E2E=1 to run browser E2E against :8765")
    for item in items:
        if _is_e2e_item(item):
            item.add_marker(skip)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    setattr(item, "rep_" + rep.when, rep)


@pytest.fixture(scope="session")
def console():
    pytest.importorskip("playwright")
    started = False
    proc = None
    log_handle = None
    if not _port_open():
        # Keep the server log: a 500 from a page is otherwise undiagnosable after the run.
        ART.mkdir(parents=True, exist_ok=True)
        log_handle = (ART / "console_server.log").open("w", encoding="utf-8")
        proc = subprocess.Popen(
            [".venv/bin/python", "-m", "residual_zero.console"],
            cwd=str(Path.cwd()),
            stdout=log_handle,
            stderr=subprocess.STDOUT,
        )
        started = True
        for _ in range(80):
            if _port_open():
                break
            time.sleep(0.25)
        else:
            proc.kill()
            pytest.fail("console did not bind 8765")
    yield BASE
    if started and proc is not None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    if log_handle is not None:
        log_handle.close()


@pytest.fixture(scope="session")
def playwright_session():
    """One Playwright instance for the whole session.

    The sync API refuses to start a second instance inside a running loop, so every e2e
    fixture that needs a browser — including the MV3 extension one, which launches its own
    persistent context — has to share this.
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        yield pw


@pytest.fixture(scope="session")
def browser_page(console, playwright_session):
    pw = playwright_session
    ART.mkdir(parents=True, exist_ok=True)
    if True:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1400, "height": 900})
        page = context.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda err: errors.append(str(err)))
        page.on(
            "console",
            lambda msg: errors.append(msg.text)
            if msg.type == "error" and "favicon" not in (msg.text or "")
            else None,
        )
        yield page, errors, context
        context.close()
        browser.close()


@pytest.fixture
def page(browser_page, request):
    pg, errors, ctx = browser_page
    errors.clear()
    ART.mkdir(parents=True, exist_ok=True)
    ctx.tracing.start(screenshots=True, snapshots=True, sources=True)
    yield pg
    failed = getattr(request.node, "rep_call", None)
    dest = ART / f"trace_{request.node.name}.zip"
    shot = ART / f"fail_{request.node.name}.png"
    if failed is not None and failed.failed:
        ctx.tracing.stop(path=str(dest))
        try:
            pg.screenshot(path=str(shot), full_page=True)
        except Exception:
            pass
        log = ART / f"console_{request.node.name}.txt"
        log.write_text("\n".join(errors) + "\n", encoding="utf-8")
    else:
        try:
            ctx.tracing.stop()
        except Exception:
            pass


@pytest.fixture
def page_errors(browser_page):
    return browser_page[1]
