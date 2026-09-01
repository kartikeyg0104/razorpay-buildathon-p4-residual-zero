"""The extension is a product, not a launcher.

v1 rendered three KPIs and a lookup box; every other "feature" was a button that called
`chrome.tabs.create` with a desk URL. These tests pin the properties that make v2 a real
extension: features are implemented against the read-only desk APIs, navigation stays
inside the extension, and nothing it can do writes financial state.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from residual_zero.console.app import app
from residual_zero.console.ext_api import DEMO_CREDIT

EXT = Path("extension")
JS = sorted(list(EXT.glob("*.js")) + list(EXT.glob("lib/*.js")))
HTML = sorted(EXT.glob("*.html"))
SOURCE = "\n".join(p.read_text(encoding="utf-8") for p in JS + HTML)


def _code_only(text: str) -> str:
    """Strip comments so a test cannot be satisfied or broken by prose about the rule."""
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    text = re.sub(r"^\s*//.*$", " ", text, flags=re.M)
    text = re.sub(r"\{#.*?#\}", " ", text, flags=re.S)
    return text


CODE = _code_only(SOURCE)
JS_CODE = _code_only("\n".join(p.read_text(encoding="utf-8") for p in JS))


def _route(path: str, method: str = "GET"):
    for route in app.routes:
        if getattr(route, "path", "") == path and method in getattr(route, "methods", set()):
            return route
    raise AssertionError(f"missing route {method} {path}")


# --------------------------------------------------------------------- no redirects

# Desk routes a v1 button used to open. None of these may appear as a navigation target.
WEB_ROUTES = [
    "/credit/", "/exceptions", "/explorer", "/ask", "/proof/", "/whatif", "/close",
    "/books", "/journal", "/audit", "/human", "/recon", "/safety", "/mixed", "/alts",
    "/clusters", "/controller", "/asof", "/challenge", "/demo", "/evidence",
]


def test_no_extension_code_navigates_to_a_web_app_route():
    """The whole point: a feature button must not be a link to the website."""
    offenders = []
    for path in JS + HTML:
        text = path.read_text(encoding="utf-8")
        for route in WEB_ROUTES:
            # A desk route inside a quoted string is how the old redirects were written.
            for m in re.finditer(r"""["'`](%s[^"'`]*)["'`]""" % re.escape(route), text):
                offenders.append(f"{path}: {m.group(1)}")
    assert not offenders, "extension still points at web-app routes:\n  " + "\n  ".join(offenders)


def test_tabs_create_only_opens_the_extensions_own_page():
    for path in JS:
        text = path.read_text(encoding="utf-8")
        for m in re.finditer(r"chrome\.tabs\.create\(\{[^}]*\}", text):
            assert "chrome.runtime.getURL" in m.group(0), f"{path}: {m.group(0)[:90]}"


def test_no_window_open_or_location_redirects():
    """Hash routing is fine; whole-page navigation away from the extension is not."""
    assert "window.open" not in SOURCE
    assert not re.search(r"location\.(href|assign|replace)\s*=", SOURCE)
    assert not re.search(r"location\.(assign|replace)\(", SOURCE)


def test_content_script_chips_open_the_extension_not_the_desk():
    js = EXT.joinpath("content.js").read_text(encoding="utf-8")
    assert "open-credit" in js and "open-settlement" in js
    assert "/credit/" not in js
    assert "/recon" not in js


# --------------------------------------------------------------------- feature parity

# Every view the extension implements natively, and the desk API that feeds it.
PARITY = {
    "dashboardView": "/api/desk",
    "exceptionsView": "get_exceptions",
    "creditView": "/api/credit/",
    "proofView": "/api/finance/proof",
    "askView": "/api/ask",
    "explorerView": "explorer_query",
    "humanView": "get_exposure_queue",
    "whatifView": "/api/whatif",
    "closeView": "/api/close",
    "auditView": "get_audit_trail",
    "safetyView": "/api/mcp/tools",
    "sourcesView": "/api/recon",
    "searchView": "/api/lookup",
}


@pytest.mark.parametrize("view", sorted(PARITY))
def test_each_view_exists(view):
    views = EXT.joinpath("lib", "views.js").read_text(encoding="utf-8")
    assert f"function {view}" in views or f"export async function {view}" in views


@pytest.mark.parametrize("endpoint", sorted(set(PARITY.values())))
def test_each_view_is_backed_by_a_real_desk_surface(endpoint):
    """Either a mounted HTTP route, or a name on the read-only finance-tool allowlist."""
    if endpoint.startswith("/"):
        paths = {getattr(r, "path", "") for r in app.routes}
        assert any(p.startswith(endpoint.rstrip("/")) for p in paths), endpoint
    else:
        from residual_zero.qa.finance_tools import TOOL_NAMES

        assert endpoint in TOOL_NAMES, endpoint


def test_every_tool_the_extension_calls_is_on_the_allowlist():
    from residual_zero.qa.finance_tools import TOOL_NAMES

    views = EXT.joinpath("lib", "views.js").read_text(encoding="utf-8")
    called = set(re.findall(r"""api\.tool\(\s*["']([a-z_]+)["']""", views))
    assert called, "expected the extension to drive views through allowlisted tools"
    assert called <= set(TOOL_NAMES), sorted(called - set(TOOL_NAMES))


def test_navigation_model_covers_the_operational_surface():
    app_js = EXT.joinpath("app.js").read_text(encoding="utf-8")
    for route in ["#/exceptions", "#/explorer", "#/human", "#/ask", "#/proof",
                  "#/whatif", "#/close", "#/audit", "#/sources", "#/safety"]:
        assert route in app_js, route


# --------------------------------------------------------------------- safety

def test_extension_never_writes_cleared():
    """No write verb, and no route that could record a clear or an exception decision."""
    assert "write_cleared" not in CODE
    # The desk's only browser-reachable writes are /exceptions/{id}/resolve and /work.
    assert "/resolve" not in CODE
    assert "/work" not in CODE
    for verb in ('"PUT"', '"DELETE"', '"PATCH"', "'PUT'", "'DELETE'", "'PATCH'"):
        assert verb not in CODE, verb
    # Only these two POSTs exist, and both are server-side allowlisted read-only tools.
    posts = set(re.findall(r'postJson\(\s*"([^"]+)"', CODE))
    assert posts <= {"/api/ask", "/api/finance/tool", "/api/mcp/tool", "/api/recon"}, sorted(posts)


def test_extension_asserts_the_read_only_invariant_on_every_payload():
    api_js = EXT.joinpath("lib", "api.js").read_text(encoding="utf-8")
    assert "assertReadOnly" in api_js
    assert "writes_cleared" in api_js
    views = EXT.joinpath("lib", "views.js").read_text(encoding="utf-8")
    assert views.count("assertReadOnly") >= 8


def test_extension_does_no_financial_arithmetic():
    """Amounts are rendered by the backend; the extension must not do money maths."""
    views = EXT.joinpath("lib", "views.js").read_text(encoding="utf-8")
    ui = EXT.joinpath("lib", "ui.js").read_text(encoding="utf-8")
    for blob in (views, ui):
        assert "paise /" not in blob
        assert "/ 100" not in blob
        assert "toFixed" not in blob
        assert "parseFloat" not in blob


def test_no_secrets_or_remote_code_in_the_extension():
    """No credential VALUE is bundled, and no code arrives from anywhere but this package.

    The extension does now send an ``Authorization: Bearer`` header, because a deployed desk
    authenticates every request. That header carries a token the *user* minted for
    themselves on the desk and pasted into the options page — so what this test has to
    establish is not "the word authorization never appears" but the thing that actually
    matters: no credential literal ships inside the extension.
    """
    assert not re.search(r"(gsk_|nvapi-|sk-[A-Za-z0-9]{16}|rzp_(live|test)_)", SOURCE)
    # A hardcoded personal access token would be a bundled secret.
    assert not re.search(r"rz_pat_[A-Za-z0-9_\-]{8,}", SOURCE)
    assert "api_key" not in SOURCE.casefold()
    # The header may be SET, but never from a literal: the value must come from storage.
    for match in re.finditer(r'(?i)authorization"?\]?\s*[:=]\s*(.{0,40})', CODE):
        assigned = match.group(1)
        assert "token" in assigned.casefold(), (
            f"Authorization is built from something other than the stored token: {assigned!r}"
        )
    assert "eval(" not in CODE
    assert "new Function" not in CODE
    assert "innerHTML" not in CODE, "build DOM with textContent so desk strings stay inert"
    assert "outerHTML" not in CODE
    assert "insertAdjacentHTML" not in CODE
    # Scanned over the JAVASCRIPT only, because JavaScript is what can fetch. The options
    # page's prose and its input placeholder legitimately show an example https URL now
    # that the desk is configurable, and neither is an endpoint.
    external = set(re.findall(r"https?://[^\s\"'`)]+", JS_CODE))
    allowed = {"http://127.0.0.1:8765", "http://localhost:8765"}
    assert external <= allowed, sorted(external - allowed)
    # The HTML must still not pull code or styling from anywhere off-package.
    for path in HTML:
        markup = path.read_text(encoding="utf-8")
        assert not re.search(r'<script[^>]+src=["\']https?://', markup), path
        assert not re.search(r'<link[^>]+href=["\']https?://', markup), path


def test_the_desk_url_must_be_https_or_loopback():
    """A deployed desk is configurable, but never over plain HTTP.

    This replaces an assertion that the origin was pinned to a fixed loopback pair. Pinning
    stopped being expressible once the desk could be any deployment; the invariant that
    still holds — and is what protects the user's token on the wire — is that anything other
    than a loopback development desk has to be https://.
    """
    api_js = EXT.joinpath("lib", "api.js").read_text(encoding="utf-8")
    assert "normaliseDesk" in api_js
    assert "export const LOOPBACK" in api_js
    assert 'parsed.protocol !== "https:"' in api_js, (
        "normaliseDesk must reject a non-HTTPS deployed desk"
    )
    # The token is a credential: it must not be replicated across the user's machines by
    # being written to chrome.storage.sync.
    api_code = _code_only(api_js)
    assert "chrome.storage.sync" not in api_code
    assert "chrome.storage.local" in api_code


def test_service_worker_validates_message_sender_and_shape():
    bg = EXT.joinpath("background.js").read_text(encoding="utf-8")
    assert "sender.id !== chrome.runtime.id" in bg
    assert 'typeof msg.op !== "string"' in bg
    assert "CREDIT_RE" in bg and "SETTLEMENT_RE" in bg
    assert "unknown op" in bg


def test_manifest_is_mv3_and_still_narrow():
    manifest = json.loads(EXT.joinpath("manifest.json").read_text(encoding="utf-8"))
    assert manifest["manifest_version"] == 3
    assert manifest["background"]["type"] == "module"
    assert set(manifest["host_permissions"]) == {
        "http://127.0.0.1:8765/*",
        "http://localhost:8765/*",
        "https://dashboard.razorpay.com/*",
    }
    forbidden = {"cookies", "webRequest", "webRequestBlocking", "debugger", "history",
                 "clipboardRead", "downloads", "<all_urls>", "tabs", "scripting"}
    assert not (forbidden & set(manifest["permissions"]))
    assert "<all_urls>" not in json.dumps(manifest)
    assert manifest["content_security_policy"]["extension_pages"].startswith("script-src 'self'")


def test_every_referenced_asset_exists():
    for page in HTML:
        text = page.read_text(encoding="utf-8")
        for ref in re.findall(r'(?:src|href)="([^"#:]+)"', text):
            assert EXT.joinpath(ref).is_file(), f"{page.name} -> missing {ref}"
    manifest = json.loads(EXT.joinpath("manifest.json").read_text(encoding="utf-8"))
    for rel in [manifest["background"]["service_worker"], manifest["options_page"],
                manifest["action"]["default_popup"]]:
        assert EXT.joinpath(rel).is_file(), rel


def test_extension_zip_ships_the_module_tree():
    import io
    import zipfile

    from residual_zero.console.ext_api import pack_extension_zip

    names = zipfile.ZipFile(io.BytesIO(pack_extension_zip())).namelist()
    for rel in ("manifest.json", "popup.html", "panel.html", "app.js", "app.css",
                "options.html", "lib/api.js", "lib/ui.js", "lib/views.js"):
        assert f"residual-zero-extension/{rel}" in names, rel


# --------------------------------------------------------------------- new read-only APIs

def test_api_whatif_uses_the_authoritative_recompute():
    body = json.loads(_route("/api/whatif").endpoint().body)
    assert body["ok"] is True
    assert body["writes_cleared"] is False
    assert body["baseline"]["residual_paise"] == 0
    shifted = json.loads(_route("/api/whatif").endpoint(reserve_bps=300).body)
    assert shifted["scenario"]["bps"] == 300
    assert shifted["scenario"]["same"] is False, "300 bps must not equal the 500 bps baseline"
    assert shifted["scenario"]["residual_paise"] != 0


def test_api_whatif_refuses_to_invent_a_member_set():
    unknown = json.loads(_route("/api/whatif").endpoint(credit_id="crd_not_real").body)
    assert unknown["ok"] is False
    assert unknown["error"] == "unknown_credit"
    assert unknown["writes_cleared"] is False


def test_api_journal_matches_the_books_identity():
    body = json.loads(_route("/api/journal").endpoint().body)
    assert body["ok"] is True
    assert body["writes_cleared"] is False
    assert body["balanced"] is True, "debits must equal credits at paise"
    assert body["debits_paise"] == body["credits_paise"]
    assert body["control_residual_paise"] == 0


def test_the_new_apis_are_read_only():
    """Neither endpoint may mutate a ledger."""
    import glob
    import hashlib

    def digests():
        return {p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
                for p in sorted(glob.glob("artifacts/**/*.sqlite", recursive=True))}

    before = digests()
    _route("/api/whatif").endpoint(reserve_bps=700)
    _route("/api/journal").endpoint()
    assert digests() == before


def test_demo_credit_is_reachable_for_the_extension():
    body = json.loads(_route("/api/credit/{credit_id}").endpoint(DEMO_CREDIT).body)
    assert body["ok"] is True
    assert body["writes_cleared"] is False
