"""Authentication: an unauthenticated request cannot read anybody's financial data.

Before this work the console had no authentication at all — every route, including the
journal CSV, the audit log and the close-pack ZIP, answered 200 to any caller. These tests
pin the replacement, and pin it as a *default*: the check is that anything not on a short
public list needs a credential, so a route added later is protected without anybody
remembering to protect it.
"""

from __future__ import annotations

import pytest

from residual_zero.console.security import PUBLIC_EXACT, PUBLIC_PREFIXES, is_public

# Every financial surface the console exposes, JSON and HTML alike.
FINANCIAL_GET = [
    "/", "/audit", "/exceptions", "/books", "/journal", "/close", "/clusters", "/whatif",
    "/controller", "/asof", "/evidence", "/human", "/explorer", "/safety", "/alts",
    "/mixed", "/recon", "/demo", "/metrics", "/standup.md", "/close.md",
    "/api/desk", "/api/credits", "/api/health", "/api/ops", "/api/close", "/api/journal",
    "/api/t04", "/api/lookup", "/api/whatif", "/api/mcp/tools", "/mcp",
    "/journal.csv", "/journal.tally", "/exceptions.csv", "/close.zip",
    "/api/credit/crd_001_acc_01_2025-01-09",
    "/api/finance/evidence?credit_id=crd_001_acc_01_2025-01-09",
    "/api/finance/proof?credit_id=crd_001_acc_01_2025-01-09",
    "/proof/crd_001_acc_01_2025-01-09",
    "/credit/crd_001_acc_01_2025-01-09",
]

FINANCIAL_POST = [
    "/api/ask", "/api/finance/tool", "/api/recon", "/api/mcp/tool", "/mcp", "/recon",
    "/exceptions/crd_001_acc_01_2025-01-09/resolve?resolution=accept",
    "/exceptions/crd_001_acc_01_2025-01-09/work?status=open",
]


@pytest.mark.parametrize("path", FINANCIAL_GET)
def test_every_financial_get_needs_a_credential(deployment, path):
    response = deployment.anon().get(path, follow_redirects=False)
    assert response.status_code in (401, 303), (
        f"{path} answered {response.status_code} to an unauthenticated caller"
    )
    if response.status_code == 303:
        assert response.headers["location"].startswith("/login")


@pytest.mark.parametrize("path", FINANCIAL_POST)
def test_every_write_or_ai_post_needs_a_credential(deployment, path):
    response = deployment.anon().post(path, content="{}", follow_redirects=False)
    assert response.status_code in (401, 303), (
        f"{path} answered {response.status_code} to an unauthenticated caller"
    )


def test_the_public_list_is_short_and_carries_nothing_financial():
    """A route is public only if it reports nothing about anybody's money."""
    assert PUBLIC_EXACT == {
        "/login", "/signup", "/logout", "/healthz", "/readyz", "/favicon.ico", "/robots.txt",
    }
    assert PUBLIC_PREFIXES == ("/static/",)
    # /api/health reports credit counts and gate totals, so it must NOT be public. /healthz
    # is the probe that exists precisely so a load balancer never needs /api/health.
    assert not is_public("/api/health")
    assert is_public("/healthz")


def test_liveness_and_readiness_answer_without_a_credential(deployment):
    live = deployment.anon().get("/healthz")
    assert live.status_code == 200
    body = live.json()
    assert body == {"ok": True, "service": "residual-zero"}
    # Nothing financial, no organisation, no configuration values.
    assert "credit" not in live.text.casefold()

    ready = deployment.anon().get("/readyz")
    assert ready.status_code == 200
    assert ready.json()["ready"] is True


def test_a_valid_session_reads_its_own_organisation(deployment):
    client = deployment.login("owner@alpha.test")
    body = client.get("/api/desk").json()
    assert body["ok"] is True
    assert body["posted"] == 248, "alpha reads the committed dev corpus"
    assert body["writes_cleared"] is False


def test_the_session_cookie_is_httponly_and_samesite(deployment):
    client = deployment.client()
    response = client.post(
        "/login",
        data={"email": "owner@alpha.test", "password": "alpha owner passphrase"},
        follow_redirects=False,
    )
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie, "script must not be able to read the session"
    assert "SameSite=lax" in cookie.replace("samesite", "SameSite")
    assert "Path=/" in cookie
    # No Secure flag here because the test origin is http://. The production check that it
    # IS set lives in test_production_config.py.
    assert "Secure" not in cookie


def test_a_wrong_password_is_refused_and_says_nothing_about_the_account(deployment):
    client = deployment.client()
    response = client.post(
        "/login",
        data={"email": "owner@alpha.test", "password": "not the passphrase"},
        follow_redirects=False,
    )
    assert response.status_code == 200  # the form is re-rendered, not a redirect
    assert "incorrect" in response.text
    # An unknown address must produce the SAME message, or the form is an account oracle.
    unknown = client.post(
        "/login",
        data={"email": "nobody@nowhere.test", "password": "not the passphrase"},
        follow_redirects=False,
    )
    assert "incorrect" in unknown.text
    assert "no such" not in unknown.text.casefold()
    assert "unknown" not in unknown.text.casefold()


def test_logout_revokes_the_session_server_side(deployment):
    client = deployment.login("owner@alpha.test")
    assert client.get("/api/desk").status_code == 200
    client.get("/logout", follow_redirects=False)
    # A stale copy of the cookie must not work either: revocation is recorded in the
    # database, not just dropped from the browser.
    fresh = deployment.client()
    fresh.cookies.update(client.cookies)
    assert fresh.get("/api/desk", follow_redirects=False).status_code in (401, 303)


def test_a_bearer_token_authenticates_the_extension(deployment):
    token = deployment.token("analyst@alpha.test")
    client = deployment.client()
    response = client.get("/api/desk", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    session = client.get("/api/session", headers={"Authorization": f"Bearer {token}"}).json()
    assert session["credential"] == "token"
    assert session["org_id"] == "alpha"
    assert session["can_clear"] is False


@pytest.mark.parametrize("header", [
    "Bearer rz_pat_not_a_real_token",
    "Bearer xyz",
    "Basic dXNlcjpwYXNz",
    "rz_pat_missing_the_scheme",
    "Bearer ",
])
def test_an_unusable_authorization_header_is_refused(deployment, header):
    response = deployment.anon().get(
        "/api/desk", headers={"Authorization": header}, follow_redirects=False,
    )
    assert response.status_code in (401, 303)


def test_an_explicit_bad_token_does_not_fall_back_to_a_cookie(deployment):
    """A caller that presents a token means it; a stale cookie must not rescue it.

    Otherwise a request with a revoked token would silently succeed as whoever last logged
    in on that browser, which is a different principal than the caller asked to be.
    """
    client = deployment.login("owner@alpha.test")
    assert client.get("/api/desk").status_code == 200
    refused = client.get(
        "/api/desk",
        headers={"Authorization": "Bearer rz_pat_revoked"},
        follow_redirects=False,
    )
    assert refused.status_code in (401, 303)


def test_a_revoked_token_stops_working(deployment):
    token = deployment.token("analyst@alpha.test")
    client = deployment.client()
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/desk", headers=headers).status_code == 200
    principal = deployment.principal("analyst@alpha.test")
    token_id = deployment.store.list_api_tokens(principal)[0]["token_id"]
    assert deployment.store.revoke_api_token(principal, token_id) is True
    assert client.get("/api/desk", headers=headers, follow_redirects=False).status_code in (401, 303)


def test_a_minted_token_is_never_put_in_a_url(deployment):
    """A credential in a URL lands in browser history and in access logs.

    The token page therefore renders a new token in the response BODY of the POST, rather
    than redirecting to `?created=<token>`.
    """
    client = deployment.login("owner@alpha.test")
    response = client.post(
        "/tokens", data={"label": "my laptop"}, headers={"Origin": "http://testserver"},
        follow_redirects=False,
    )
    assert response.status_code == 200, "minting must answer with the page, not a redirect"
    assert "location" not in {k.lower() for k in response.headers}
    import re

    shown = re.findall(r"rz_pat_[A-Za-z0-9_\-]+", response.text)
    assert shown, "the token was not shown to the user at all"
    # And it does not come back on the next page load.
    again = client.get("/tokens")
    assert not re.findall(r"rz_pat_[A-Za-z0-9_\-]{20,}", again.text)


def test_the_token_page_source_does_not_redirect_with_a_credential():
    from pathlib import Path

    source = Path("src/residual_zero/console/auth_routes.py").read_text(encoding="utf-8")
    assert "?created=" not in source
    assert 'RedirectResponse("/tokens?created' not in source
