"""Fixtures for the deployment suite.

Every test here runs the console the way a deployment runs it — authentication on, more
than one organisation — while staying on SQLite so the suite needs no database server. The
PostgreSQL-specific behaviour has its own file and skips when no server is configured.
"""

from __future__ import annotations

import pytest


@pytest.fixture()
def deployment(tmp_path, monkeypatch):
    """A two-organisation deployment with authentication required.

    Returns an object exposing ``client()``, ``login()``, ``token()`` and the two tenants.
    Each test gets its own tenant root and identity database, so nothing leaks between
    tests and nothing touches ``artifacts/``.
    """
    monkeypatch.setenv("RZ_AUTH_MODE", "required")
    monkeypatch.setenv("RZ_SESSION_SECRET", "t" * 40)
    monkeypatch.setenv("RZ_PUBLIC_ORIGIN", "http://testserver")
    monkeypatch.setenv("RZ_TENANT_ROOT", str(tmp_path / "tenants"))
    monkeypatch.setenv("RZ_IDENTITY_DB", str(tmp_path / "identity.sqlite"))
    monkeypatch.setenv("RZ_LLM", "0")
    monkeypatch.delenv("RZ_DATABASE_URL", raising=False)

    from residual_zero.console import app as console_app
    from residual_zero.identity.store import IdentityStore, Role

    console_app.reset_caches()
    # Deliberately NOT reloading residual_zero.appconfig. `load_config()` reads the
    # environment on every call, so a reload buys nothing — and it replaces the AuthMode
    # and Env enum members, after which `self.auth_mode is AuthMode.REQUIRED` compares a
    # pre-reload member against a post-reload one and is False. That silently inverted an
    # authorisation check inside a test suite whose job is to verify authorisation.
    #
    # The CORS origin list IS fixed when the app module is imported. That matches a real
    # deployment, where middleware is installed once at startup, so a test that needs
    # different CORS origins asserts on `load_config().cors_origins()` instead.

    store = IdentityStore()
    # `alpha` reads the committed synthetic dev corpus, so it has records to look at.
    alpha = store.create_organization(
        "alpha", "Alpha Payments", dataset_kind="files", dataset_root="data/dev/rendered",
    )
    # `beta` reads its own (initially empty) rows, which is what a real new tenant does.
    beta = store.create_organization("beta", "Beta Retail", dataset_kind="sql")

    users = {
        "alpha_owner": store.create_user("owner@alpha.test", "alpha owner passphrase", alpha.org_id, Role.OWNER),
        "alpha_analyst": store.create_user("analyst@alpha.test", "alpha analyst passphrase", alpha.org_id, Role.ANALYST),
        "alpha_viewer": store.create_user("viewer@alpha.test", "alpha viewer passphrase", alpha.org_id, Role.VIEWER),
        "beta_owner": store.create_user("owner@beta.test", "beta owner passphrase", beta.org_id, Role.OWNER),
    }
    passwords = {
        "owner@alpha.test": "alpha owner passphrase",
        "analyst@alpha.test": "alpha analyst passphrase",
        "viewer@alpha.test": "alpha viewer passphrase",
        "owner@beta.test": "beta owner passphrase",
    }

    class Deployment:
        app = console_app.app
        module = console_app
        alpha_tenant = alpha
        beta_tenant = beta

        def client(self):
            from fastapi.testclient import TestClient

            return TestClient(console_app.app)

        def anon(self):
            return self.client()

        def login(self, email: str):
            client = self.client()
            response = client.post(
                "/login",
                data={"email": email, "password": passwords[email]},
                follow_redirects=False,
            )
            assert response.status_code == 303, response.text[:400]
            return client

        def token(self, email: str) -> str:
            principal = store.authenticate(email, passwords[email])
            return store.create_api_token(principal, "test")

        def principal(self, email: str):
            return store.authenticate(email, passwords[email])

    Deployment.store = store
    Deployment.users = users
    yield Deployment()
    console_app.reset_caches()


SELF = {"Origin": "http://testserver"}
FORM = {"Content-Type": "application/x-www-form-urlencoded"}
