"""An authenticated HTML form POST must work in a real browser.

REGRESSION: every authenticated form POST on the deployed console returned 403
"That origin may not write to this desk." The desk sent `Referrer-Policy: no-referrer`,
and under that policy the Fetch spec serialises the `Origin` header as `null` on form
submissions — so our own CSRF check refused our own forms. Minting an extension token was
impossible, and so was recording a human review decision.

curl never showed it, because curl sends whatever Origin you hand it. Only a browser does
what a browser does, so this test drives one and runs its own authenticated console.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(os.environ.get("RZ_E2E") != "1", reason="set RZ_E2E=1"),
]

EMAIL = "forms@test.local"
PASSWORD = "forms browser test passphrase"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture()
def authed_console(tmp_path):
    """A console with authentication required, on its own port and its own storage."""
    port = _free_port()
    env = dict(os.environ)
    env.pop("RZ_DATABASE_URL", None)
    env.update(
        RZ_TENANT_ROOT=str(tmp_path / "tenants"),
        RZ_IDENTITY_DB=str(tmp_path / "identity.sqlite"),
        RZ_AUTH_MODE="required",
        RZ_SESSION_SECRET="e2e-form-post-secret-long-enough-0000000",
        RZ_PUBLIC_ORIGIN=f"http://127.0.0.1:{port}",
        RZ_HOST="127.0.0.1",
        RZ_PORT=str(port),
        RZ_LLM="0",
        PYTHONPATH="src",
    )
    subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, 'src');"
         "from residual_zero.identity.store import IdentityStore, Role;"
         "s = IdentityStore();"
         "t = s.create_organization('forms', 'Forms', dataset_kind='files',"
         " dataset_root='data/dev/rendered');"
         f"s.create_user({EMAIL!r}, {PASSWORD!r}, t.org_id, Role.OWNER)"],
        env=env, check=True, capture_output=True,
    )
    # A file, not a PIPE: nothing reads this console's output, and an unread pipe both
    # leaks a handle at teardown and can block the child once its buffer fills.
    log = (tmp_path / "console.log").open("wb")
    proc = subprocess.Popen(
        [sys.executable, "-m", "residual_zero.console"],
        env=env, stdout=log, stderr=subprocess.STDOUT,
    )
    base = f"http://127.0.0.1:{port}"
    for _ in range(120):
        with socket.socket() as probe:
            probe.settimeout(0.4)
            try:
                probe.connect(("127.0.0.1", port))
                break
            except OSError:
                time.sleep(0.25)
    else:  # pragma: no cover - the console failed to start
        proc.kill()
        log.close()
        pytest.fail("authenticated console did not start")
    try:
        yield base
    finally:
        proc.terminate()
        proc.wait(timeout=20)
        log.close()


def _sign_in(page, base: str) -> None:
    page.goto(base + "/login", wait_until="networkidle")
    page.fill("#email", EMAIL)
    page.fill("#password", PASSWORD)
    page.click("button[type=submit]")
    page.wait_for_load_state("networkidle")


def test_an_authenticated_form_post_is_accepted(authed_console):
    """Minting an extension token: a cookie-authenticated, same-origin form POST."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_context().new_page()
        origins: list[str] = []
        page.on(
            "request",
            lambda r: origins.append(r.headers.get("origin", "<none>"))
            if r.method == "POST" else None,
        )
        try:
            _sign_in(page, authed_console)
            page.goto(authed_console + "/tokens", wait_until="networkidle")
            page.fill("#label", "browser regression")
            page.click("button[type=submit]")
            page.wait_for_load_state("networkidle")
            body = " ".join(page.inner_text("body").split())
        finally:
            browser.close()

    assert "That origin may not write" not in body, (
        "the desk refused its own form; check Referrer-Policy, which nullifies Origin "
        "on form submissions when set to no-referrer"
    )
    assert "rz_pat_" in body, f"no token was minted; page said: {body[:200]}"
    assert origins, "no POST was observed"
    assert "null" not in origins, (
        f"the browser sent Origin: null on a form POST ({origins}); a strict CSRF check "
        "cannot accept that, so the header policy must not cause it"
    )
