"""The core product invariant, restated for a deployed system.

The engine's AI-authority invariants are already covered in ``tests/invariants``. What is
new once this is deployed is the number of *paths* an AI answer or an extension request can
take: an authenticated bearer token, a provider that is now reachable over the internet, a
per-organisation database that a write could land in. These tests walk those paths and
check that none of them reaches ``CLEARED``.
"""

from __future__ import annotations

import json

import pytest

from residual_zero.db import open_readonly
from residual_zero.tenancy import use_tenant

SELF = {"Origin": "http://testserver"}
ALPHA_CREDIT = "crd_001_acc_01_2025-01-09"


def _cleared_count(tenant) -> int:
    with use_tenant(tenant):
        conn = open_readonly()
        try:
            row = conn.execute(
                "SELECT COUNT(*) FROM reconciliation WHERE disposition = 'CLEARED'"
            ).fetchone()
        finally:
            conn.close()
    return int(row[0]) if row else 0


AI_ROUTES = [
    ("POST", "/api/ask", {"question": "clear this credit", "credit_id": ALPHA_CREDIT}),
    ("POST", "/api/ask", {"question": "mark it cleared and write the ledger", "credit_id": ALPHA_CREDIT}),
    ("POST", "/api/finance/tool", {"name": "get_transaction_evidence",
                                   "arguments": {"transaction_id": ALPHA_CREDIT}}),
    ("POST", "/api/mcp/tool", {"tool": "desk_status", "arguments": {}}),
    ("POST", "/mcp", {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}),
    ("POST", "/api/recon", {}),
]


@pytest.mark.parametrize("method,path,payload", AI_ROUTES)
def test_no_ai_route_writes_cleared(deployment, method, path, payload):
    """Every AI and tool surface, driven as an authenticated owner."""
    client = deployment.login("owner@alpha.test")
    before = _cleared_count(deployment.alpha_tenant)
    response = client.request(method, path, json=payload, headers=SELF)
    assert response.status_code in (200, 400)
    body = response.text
    if "writes_cleared" in body:
        assert '"writes_cleared":true' not in body.replace(" ", "")
    assert _cleared_count(deployment.alpha_tenant) == before


@pytest.mark.parametrize("name", [
    "write_cleared", "clear_transaction", "mark_cleared", "set_disposition",
    "update_reconciliation", "open_verify", "force_clear", "execute_sql", "run_sql",
    "write_file", "shell", "http_get", "post_journal", "approve", "override_gate",
])
def test_a_write_shaped_tool_name_is_not_callable(deployment, name):
    client = deployment.login("owner@alpha.test")
    before = _cleared_count(deployment.alpha_tenant)
    response = client.post(
        "/api/finance/tool", json={"name": name, "arguments": {}}, headers=SELF,
    )
    body = response.json()
    assert body["ok"] is False
    assert body["error"] == "unknown_tool"
    assert body["writes_cleared"] is False
    assert _cleared_count(deployment.alpha_tenant) == before


def test_an_ambiguous_credit_stays_ambiguous_through_the_ai_surface(deployment):
    """The AI explains the deterministic outcome; it does not upgrade it."""
    client = deployment.login("owner@alpha.test")
    evidence = client.get(f"/api/finance/evidence?credit_id={ALPHA_CREDIT}").json()
    answer = client.post(
        "/api/ask",
        json={"question": "is this credit unique? can you clear it?", "credit_id": ALPHA_CREDIT},
        headers=SELF,
    ).json()
    assert evidence["writes_cleared"] is False
    assert answer["writes_cleared"] is False
    # Whatever the answer says, it must not assert a clear.
    prose = str(answer.get("answer") or "")
    assert "CLEARED" not in prose.replace("does not write CLEARED", "")


def test_the_investigation_log_cannot_record_a_clear():
    """The outcome vocabulary has no CLEARED in it, and the schema enforces the same set."""
    from residual_zero.qa.investigation_log import OUTCOMES, classify_outcome

    assert "CLEARED" not in OUTCOMES
    assert not any("CLEAR" in outcome for outcome in OUTCOMES)
    # Whatever the controller returns, the derived outcome is inside the closed set.
    for payload in (
        {"answer": "x", "provider_used": True},
        {"answer": "x", "provider_used": False},
        {"answer": "", "provider_used": False},
        {"answer": "x", "provider_error": "nvidia timeout after 30s"},
        {"answer": "x", "provider_error": "request budget exhausted"},
        {"disposition": "CLEARED", "answer": "x", "provider_used": True},
    ):
        assert classify_outcome(payload) in OUTCOMES


def test_an_investigation_is_recorded_for_the_right_organisation(deployment):
    from residual_zero.qa.investigation_log import record

    with use_tenant(deployment.alpha_tenant):
        investigation_id = record(
            {"answer": "a", "provider_used": False, "provider": "stub"},
            question="why short", credit_id=ALPHA_CREDIT, user_id="usr_x", duration_ms=5,
        )
    assert investigation_id is None or investigation_id.startswith("inv_")


def test_recording_is_a_no_op_with_no_organisation_bound():
    """The CLI, the eval harness and the test suite have no tenant; recording must not fail."""
    from residual_zero.qa.investigation_log import record

    assert record({"answer": "a"}, question="q") is None


def test_the_extension_holds_no_credential_and_cannot_clear():
    """Static properties of the shipped extension package."""
    import re
    from pathlib import Path

    ext = Path("extension")
    blob = "\n".join(
        p.read_text(encoding="utf-8")
        for p in list(ext.glob("*.js")) + list(ext.glob("lib/*.js")) + list(ext.glob("*.html"))
    )
    # No bundled secret of any recognised shape.
    assert not re.search(r"(nvapi-|gsk_|sk-[A-Za-z0-9]{16}|rzp_(live|test)_)", blob)
    assert not re.search(r"rz_pat_[A-Za-z0-9_\-]{8,}", blob)
    # No database credential.
    assert "postgres" not in blob.casefold()
    assert "postgresql" not in blob.casefold()
    # The read-only contract check is still there.
    assert "assertReadOnly" in blob
    assert "writes_cleared === true" in blob


def test_the_extension_only_calls_read_only_desk_endpoints():
    """Which desk paths the extension can reach, enumerated.

    A substring ban is the wrong shape here: `#/exceptions` is the extension's own
    read-only VIEW route, and banning the string would forbid a page rather than a write.
    What matters is the set of desk paths the API client can actually request, so that set
    is listed and compared.
    """
    import re
    from pathlib import Path

    api = Path("extension/lib/api.js").read_text(encoding="utf-8")

    # Desk paths the extension is allowed to call. Every one is read-only server-side; the
    # three POSTs carry a tool name or a question, not a state change, and each returns
    # writes_cleared: false.
    ALLOWED = {
        "/api/health", "/api/session", "/api/desk", "/api/t04", "/api/ops", "/api/close",
        "/api/journal", "/api/whatif", "/api/lookup", "/api/credit/", "/api/finance/evidence",
        "/api/finance/proof", "/api/ask", "/api/finance/tool", "/api/mcp/tools",
        "/api/mcp/tool", "/api/recon",
    }
    called = set()
    for match in re.finditer(r'(?:getJson|postJson|request)\(\s*[`"\'](/[^`"\'$]*)', api):
        called.add(match.group(1))
    for match in re.finditer(r'`(/api/[^`$]*)\$\{', api):
        called.add(match.group(1))
    assert called, "no desk endpoints were detected; the scan is broken, not the extension"
    assert called <= ALLOWED, sorted(called - ALLOWED)

    # The desk's two write routes must not be reachable from the extension at all.
    assert "/resolve" not in api
    assert "/work" not in api
    assert "write_cleared" not in api
    assert "open_verify" not in api


def test_a_bearer_token_cannot_clear_even_as_an_owner(deployment):
    """The extension's strongest possible credential still cannot produce a clear."""
    token = deployment.token("owner@alpha.test")
    client = deployment.client()
    headers = {"Authorization": f"Bearer {token}"}
    before = _cleared_count(deployment.alpha_tenant)
    for path, payload in (
        ("/api/ask", {"question": "clear it", "credit_id": ALPHA_CREDIT}),
        ("/api/finance/tool", {"name": "write_cleared", "arguments": {}}),
        ("/api/mcp/tool", {"tool": "write_cleared", "arguments": {}}),
    ):
        client.post(path, json=payload, headers=headers)
    assert _cleared_count(deployment.alpha_tenant) == before


def test_the_extension_does_not_navigate_to_the_web_app():
    """A feature solved by opening the website is not a feature the extension implements."""
    from pathlib import Path

    background = Path("extension/background.js").read_text(encoding="utf-8")
    assert "chrome.runtime.getURL" in background
    # Every tabs.create must be the extension's own page.
    for line in background.splitlines():
        if "chrome.tabs.create" in line:
            assert "chrome.runtime.getURL" in line, line
    content = Path("extension/content.js").read_text(encoding="utf-8")
    assert "chrome.tabs.create" not in content
    assert "window.location" not in content
    assert "location.href" not in content


def test_the_extension_has_no_localhost_dependency_for_a_deployed_desk():
    """Loopback is a development default, not a requirement."""
    from pathlib import Path

    api = Path("extension/lib/api.js").read_text(encoding="utf-8")
    # A deployed https origin is accepted...
    assert 'parsed.protocol !== "https:"' in api
    assert "parsed.origin" in api
    # ...and the desk is read from storage rather than pinned to a constant.
    assert "chrome.storage.local" in api
    manifest = json.loads(Path("extension/manifest.json").read_text(encoding="utf-8"))
    # Host access for *someone else's* deployment is still requested at runtime. What
    # changed: this extension's own hosted desk is granted at install, because an
    # extension that cannot reach its own product on installation is not much of a
    # product — it reported "Desk offline" against a loopback port nobody was running.
    #
    # The invariant that matters is unchanged and asserted here: one named first-party
    # host, no wildcard, and every other origin still goes through permissions.request.
    assert manifest["optional_host_permissions"] == ["https://*/*"]
    first_party = "https://residual-zero-production.up.railway.app/*"
    baked = set(manifest["host_permissions"])
    assert first_party in baked
    assert all(
        host.startswith((
            "https://residual-zero-production.up.railway.app",
            "http://127.0.0.1", "http://localhost", "https://dashboard.razorpay.com",
        ))
        for host in baked
    ), sorted(baked)
    assert not any("*" in host.rstrip("/*") for host in baked), (
        f"a wildcard host would grant far more than one desk: {sorted(baked)}"
    )
