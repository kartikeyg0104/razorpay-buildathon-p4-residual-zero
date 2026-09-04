"""CORS, CSRF, security headers, HTTPS and error bodies.

The deployment-specific hazards, each with the reason it is a hazard:

* **CORS** used to admit ``chrome-extension://[a-z]+`` by regex — every extension installed
  in the operator's browser. On a public deployment that is any extension reading this
  organisation's financial JSON.
* **CSRF**: a cookie rides along on a cross-site POST, and CORS does not stop the request,
  only the response. Origin enforcement is the check that matches the threat.
* **Headers**: a finance console that can be framed, sniffed or referrer-leaked is a
  finance console with an avoidable problem.
* **Error bodies**: a reconciliation traceback names tables, paths and query text.
"""

from __future__ import annotations

import pytest

from residual_zero.appconfig import AppConfig, AuthMode, Env, load_config
from residual_zero.console.security import origin_allowed

SELF = {"Origin": "http://testserver"}
ALPHA_CREDIT = "crd_001_acc_01_2025-01-09"

REQUIRED_HEADERS = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
}


@pytest.mark.parametrize("path", ["/api/desk", "/", "/login", "/healthz"])
def test_security_headers_are_on_every_response(deployment, path):
    client = deployment.login("owner@alpha.test")
    response = client.get(path, follow_redirects=False)
    for header, value in REQUIRED_HEADERS.items():
        assert response.headers.get(header) == value, f"{path} is missing {header}"
    csp = response.headers.get("content-security-policy") or ""
    assert "script-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "object-src 'none'" in csp
    # 'unsafe-inline' is allowed for STYLE only. Allowing it for script would make the
    # whole policy decorative.
    assert "'unsafe-inline'" not in csp.split("style-src")[0]
    assert "script-src 'self';" in csp + ";"
    assert response.headers.get("cache-control") == "no-store"


def test_the_csp_allows_exactly_the_external_hosts_the_templates_use():
    """A CSP that blocks the console's own stylesheet is a regression, not a tightening."""
    import re
    from pathlib import Path

    from residual_zero.console.security import CSP

    used = set()
    for path in Path("src/residual_zero/console/templates").glob("*.html"):
        markup = path.read_text(encoding="utf-8")
        for match in re.finditer(r'<link[^>]+href="(https://[^"]+)"', markup):
            used.add(match.group(1).split("/")[2])
    assert used, "no external stylesheet hosts found; the scan is broken"
    for host in used:
        assert host in CSP, f"templates load from {host}, which the CSP blocks"


def test_hsts_is_absent_on_a_plain_http_origin(deployment):
    """Pinning HSTS from a local desk would make 127.0.0.1 unreachable afterwards."""
    client = deployment.login("owner@alpha.test")
    assert "strict-transport-security" not in client.get("/api/desk").headers


def test_hsts_is_present_when_the_public_origin_is_https(monkeypatch, deployment):
    monkeypatch.setenv("RZ_PUBLIC_ORIGIN", "https://rz.example")
    client = deployment.client()
    response = client.get("/healthz")
    assert response.headers.get("strict-transport-security") == (
        "max-age=31536000; includeSubDomains"
    )


def test_the_cookie_is_marked_secure_when_the_origin_is_https(monkeypatch, deployment):
    monkeypatch.setenv("RZ_PUBLIC_ORIGIN", "https://rz.example")
    client = deployment.client()
    response = client.post(
        "/login",
        data={"email": "owner@alpha.test", "password": "alpha owner passphrase"},
        follow_redirects=False,
    )
    cookie = response.headers["set-cookie"]
    assert "Secure" in cookie
    assert "HttpOnly" in cookie


# ---------------------------------------------------------------- CSRF


@pytest.mark.parametrize("origin", [
    "https://evil.example",
    "http://127.0.0.1:9999",
    "https://dashboard.razorpay.com",
    "null",
    "http://testserver.evil.example",
])
def test_a_foreign_origin_cannot_write_with_a_cookie(deployment, origin):
    client = deployment.login("analyst@alpha.test")
    response = client.post(
        f"/exceptions/{ALPHA_CREDIT}/resolve?resolution=accept",
        headers={"Origin": origin, "Content-Type": "application/x-www-form-urlencoded"},
        content="",
    )
    assert response.status_code == 403
    assert "may not write" in response.text


def test_a_missing_origin_cannot_write_with_a_cookie_when_auth_is_required(deployment):
    """The local-mode inference "no Origin means curl" is withdrawn in a deployment.

    Locally it is a fair reading: nobody else can reach a loopback desk. Publicly, the
    header is caller-controlled, so a cookie write has to prove which origin it came from.
    A non-browser client uses a bearer token instead, which needs no Origin at all.
    """
    client = deployment.login("analyst@alpha.test")
    response = client.post(
        f"/exceptions/{ALPHA_CREDIT}/resolve?resolution=accept", content="",
    )
    assert response.status_code == 403


def test_a_bearer_write_needs_no_origin(deployment):
    """A bearer token is not a CSRF vector: a browser will not attach it cross-site."""
    from residual_zero.exceptions import open_exceptions, write_exception
    from residual_zero.models import ExceptionClass
    from residual_zero.tenancy import use_tenant

    with use_tenant(deployment.alpha_tenant):
        conn = open_exceptions(None)
        try:
            write_exception(conn, ALPHA_CREDIT, ExceptionClass.MISSING_RECORD)
        finally:
            conn.close()
    deployment.module.reset_caches()

    token = deployment.token("analyst@alpha.test")
    response = deployment.client().post(
        f"/exceptions/{ALPHA_CREDIT}/resolve?resolution=accept",
        headers={"Authorization": f"Bearer {token}"}, content="",
    )
    assert response.status_code == 200


def test_the_write_origin_allowlist_is_configuration_not_a_literal(monkeypatch):
    """Behind a real domain, a hardcoded loopback pair would refuse the console itself."""
    monkeypatch.setenv("RZ_AUTH_MODE", "required")
    monkeypatch.setenv("RZ_PUBLIC_ORIGIN", "https://rz.example")
    monkeypatch.setenv("RZ_ALLOWED_ORIGINS", "https://ops.rz.example")
    config = load_config()
    assert config.write_origins() == {"https://rz.example", "https://ops.rz.example"}
    # With authentication off, the historical loopback allowlist is preserved exactly.
    monkeypatch.setenv("RZ_AUTH_MODE", "off")
    monkeypatch.delenv("RZ_PUBLIC_ORIGIN", raising=False)
    monkeypatch.delenv("RZ_ALLOWED_ORIGINS", raising=False)
    assert load_config().write_origins() == {
        "http://127.0.0.1:8765", "http://localhost:8765",
    }


def test_origin_allowed_ignores_origin_for_a_bearer_caller():
    from residual_zero.identity.store import Principal, Role
    from residual_zero.tenancy import Tenant

    tenant = Tenant(org_id="a", slug="a", db_schema="org_a")
    bearer = Principal("u", "u@x.test", "a", Role.ANALYST, tenant, credential="token")
    cookie = Principal("u", "u@x.test", "a", Role.ANALYST, tenant, credential="session")
    config = AppConfig(
        env=Env.PRODUCTION, auth_mode=AuthMode.REQUIRED,
        public_origin="https://rz.example", session_secret_present=True,
    )
    assert origin_allowed("https://evil.example", config, bearer) is True
    assert origin_allowed(None, config, bearer) is True
    assert origin_allowed("https://evil.example", config, cookie) is False
    assert origin_allowed(None, config, cookie) is False
    assert origin_allowed("https://rz.example", config, cookie) is True


# ---------------------------------------------------------------- CORS


def test_cors_does_not_admit_every_extension(monkeypatch):
    """The old regex matched any chrome-extension origin at all."""
    monkeypatch.setenv("RZ_PUBLIC_ORIGIN", "https://rz.example")
    monkeypatch.setenv("RZ_EXTENSION_IDS", "abcdefghijklmnopabcdefghijklmnop")
    origins = load_config().cors_origins()
    assert "https://rz.example" in origins
    assert "chrome-extension://abcdefghijklmnopabcdefghijklmnop" in origins
    # A different extension is not admitted.
    assert "chrome-extension://someotherextensionidentifier00" not in origins


def test_cors_source_no_longer_contains_a_wildcard_extension_regex():
    from pathlib import Path

    source = Path("src/residual_zero/console/app.py").read_text(encoding="utf-8")
    assert "allow_origin_regex" not in source
    assert "allow_origins=_CORS_ORIGINS" in source


def test_cors_does_not_allow_credentials(monkeypatch):
    """Cookies are never sent cross-origin, so SameSite=Lax can stay strict."""
    from pathlib import Path

    source = Path("src/residual_zero/console/app.py").read_text(encoding="utf-8")
    assert "allow_credentials=False" in source


# ---------------------------------------------------------------- error bodies


def test_an_unhandled_error_does_not_return_a_traceback(deployment, monkeypatch):
    """A reconciliation traceback names tables, paths and query text."""
    from residual_zero.console import app as console_app

    def explode():
        raise RuntimeError("residual_zero internals: SELECT * FROM reconciliation")

    monkeypatch.setattr(console_app, "_overlay", explode)
    client = deployment.login("owner@alpha.test")
    # raise_server_exceptions=False makes TestClient behave like a real server: return the
    # handler's response instead of re-raising into the test. What is under test is the
    # RESPONSE BODY a client would receive, which is only observable that way.
    from fastapi.testclient import TestClient

    client = TestClient(console_app.app, raise_server_exceptions=False)
    client.cookies.update(deployment.login("owner@alpha.test").cookies)
    response = client.get("/api/desk")
    assert response.status_code == 500
    body = response.text
    assert "Traceback" not in body
    assert "SELECT" not in body
    assert "residual_zero" not in body
    assert response.json()["error"] == "internal_error"
    assert response.json()["writes_cleared"] is False


def test_a_404_is_json_for_an_api_caller_and_html_for_a_browser(deployment):
    client = deployment.login("owner@alpha.test")
    api = client.get("/api/does-not-exist")
    assert api.status_code == 404
    assert api.headers["content-type"].startswith("application/json")
    page = client.get("/does-not-exist")
    assert page.status_code == 404
    assert page.headers["content-type"].startswith("text/html")


def test_the_login_next_parameter_cannot_be_an_open_redirect(deployment):
    client = deployment.client()
    for hostile in ("https://evil.example", "//evil.example", "\\\\evil.example"):
        response = client.post(
            "/login",
            data={"email": "owner@alpha.test", "password": "alpha owner passphrase",
                  "next": hostile},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/", (
            f"next={hostile!r} became {response.headers['location']!r}"
        )
