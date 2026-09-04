"""The process must refuse to serve financial data unsafely.

The dangerous failure for a public finance console is not a crash. It is starting
*successfully* with authentication off — nobody notices, and the data is readable by the
internet. So the checks are collected in one place and applied before the server binds.
"""

from __future__ import annotations

import pytest

from residual_zero.appconfig import (
    AuthMode,
    ConfigError,
    Env,
    config_errors,
    load_config,
    validate_for_startup,
)

PROD = {
    "RZ_ENV": "production",
    "RZ_AUTH_MODE": "required",
    "RZ_SESSION_SECRET": "s" * 40,
    "RZ_PUBLIC_ORIGIN": "https://rz.example",
    "RZ_DATABASE_URL": "postgresql://u:p@h/db",
}


@pytest.fixture()
def prod(monkeypatch):
    for key, value in PROD.items():
        monkeypatch.setenv(key, value)
    return monkeypatch


def test_a_complete_production_configuration_starts(prod):
    config = validate_for_startup()
    assert config.is_production
    assert config.auth_required
    assert config.https_only
    assert config.trust_proxy is True, "a production deployment is behind a TLS proxy"


def test_local_is_the_default_and_needs_no_secrets(monkeypatch):
    for key in PROD:
        monkeypatch.delenv(key, raising=False)
    config = validate_for_startup()
    assert config.env is Env.LOCAL
    assert config.auth_mode is AuthMode.OFF
    assert config.public_origin == "http://127.0.0.1:8765"
    assert config.https_only is False
    assert config.trust_proxy is False


def test_production_refuses_to_start_with_authentication_off(prod):
    prod.setenv("RZ_AUTH_MODE", "off")
    with pytest.raises(ConfigError, match="without authentication"):
        validate_for_startup()


@pytest.mark.parametrize("value", ["", "short", "x" * 31])
def test_production_refuses_a_missing_or_weak_session_secret(prod, value):
    prod.setenv("RZ_SESSION_SECRET", value)
    with pytest.raises(ConfigError, match="RZ_SESSION_SECRET"):
        validate_for_startup()


def test_production_refuses_a_missing_public_origin(prod):
    prod.delenv("RZ_PUBLIC_ORIGIN")
    with pytest.raises(ConfigError, match="RZ_PUBLIC_ORIGIN"):
        validate_for_startup()


@pytest.mark.parametrize("origin", ["http://rz.example", "ftp://rz.example", "rz.example"])
def test_production_refuses_a_non_https_origin(prod, origin):
    prod.setenv("RZ_PUBLIC_ORIGIN", origin)
    with pytest.raises(ConfigError, match="https"):
        validate_for_startup()


def test_production_refuses_sqlite(prod):
    """SQLite is a development backend. Production persistence is PostgreSQL."""
    prod.delenv("RZ_DATABASE_URL")
    with pytest.raises(ConfigError, match="PostgreSQL"):
        validate_for_startup()
    prod.setenv("RZ_DATABASE_URL", "sqlite:///local.db")
    with pytest.raises(ConfigError, match="PostgreSQL"):
        validate_for_startup()


def test_every_missing_variable_is_reported_at_once(monkeypatch):
    """One restart per missing variable would be a miserable deployment loop."""
    monkeypatch.setenv("RZ_ENV", "production")
    for key in ("RZ_AUTH_MODE", "RZ_SESSION_SECRET", "RZ_PUBLIC_ORIGIN", "RZ_DATABASE_URL"):
        monkeypatch.delenv(key, raising=False)
    problems = config_errors()
    assert len(problems) == 4
    joined = " ".join(problems)
    for name in ("RZ_AUTH_MODE", "RZ_SESSION_SECRET", "RZ_PUBLIC_ORIGIN", "RZ_DATABASE_URL"):
        assert name in joined


def test_the_configuration_summary_never_renders_a_secret(prod):
    prod.setenv("RZ_DATABASE_URL", "postgresql://user:sup3rs3cret@host/db")
    summary = load_config().redacted_summary()
    rendered = repr(summary)
    assert "sup3rs3cret" not in rendered
    assert "s" * 40 not in rendered
    assert summary["session_secret_present"] is True
    assert summary["database"] == "postgresql://user:***@host/db"


def test_an_unparseable_database_url_is_a_startup_error(prod):
    prod.setenv("RZ_DATABASE_URL", "mysql://h/db")
    with pytest.raises(ConfigError):
        validate_for_startup()


def test_readyz_reports_problems_without_their_values(prod, monkeypatch, tmp_path):
    """The readiness probe has to be diagnosable without becoming a disclosure."""
    monkeypatch.setenv("RZ_AUTH_MODE", "off")  # so the probe itself is reachable
    monkeypatch.setenv("RZ_TENANT_ROOT", str(tmp_path))
    from fastapi.testclient import TestClient

    from residual_zero.console.app import app

    response = TestClient(app).get("/readyz")
    assert response.status_code == 503
    body = response.json()
    assert body["ready"] is False
    assert any("RZ_AUTH_MODE" in p for p in body["problems"])
    assert "s" * 40 not in response.text
    assert "p@h" not in response.text


def test_the_bind_address_and_port_come_from_the_environment(monkeypatch):
    """A container needs 0.0.0.0, and most platforms inject PORT."""
    from residual_zero.console.__main__ import _host, _port

    for key in ("RZ_HOST", "RZ_PORT", "PORT"):
        monkeypatch.delenv(key, raising=False)
    assert _host() == "127.0.0.1", "the local default must not change"
    assert _port() == 8765

    monkeypatch.setenv("RZ_HOST", "0.0.0.0")
    monkeypatch.setenv("PORT", "8080")
    assert _host() == "0.0.0.0"
    assert _port() == 8080
    # An explicit RZ_PORT wins over the platform's PORT.
    monkeypatch.setenv("RZ_PORT", "9001")
    assert _port() == 9001
    # Nonsense falls back rather than crashing the boot.
    monkeypatch.setenv("RZ_PORT", "not-a-port")
    monkeypatch.delenv("PORT")
    assert _port() == 8765


def test_the_entrypoint_exits_rather_than_serving_a_bad_configuration(prod, monkeypatch):
    """`main()` must not reach uvicorn.run when the configuration is unsafe."""
    prod.setenv("RZ_AUTH_MODE", "off")
    served = []
    import uvicorn

    # Patch what main() actually calls. This test passed vacuously once already, when the
    # entrypoint moved off uvicorn.run() to hand over a pre-bound socket.
    monkeypatch.setattr(uvicorn.Server, "run", lambda *a, **k: served.append(True))
    from residual_zero.console.__main__ import main

    with pytest.raises(SystemExit) as exit_info:
        main()
    assert exit_info.value.code == 2
    assert served == [], "the server started despite an invalid configuration"


def test_the_ipv6_wildcard_still_answers_ipv4(monkeypatch):
    """`RZ_HOST=::` must mean every interface, not IPv6 only.

    asyncio sets IPV6_V6ONLY on any AF_INET6 socket it binds itself, so letting uvicorn
    bind `::` produces a server that logs a clean startup and refuses every IPv4
    connection. Railway's health probe dials IPv4; the deploy died on healthcheck timeout
    with no request in the log. Connect over IPv4 for real — asserting the sockopt alone
    would not have caught the original bug's symptom.
    """
    import socket

    from residual_zero.console.__main__ import _listen_socket

    sock = _listen_socket("::", 0)
    assert sock is not None, "the wildcard must be bound by us, not by uvicorn"
    try:
        if not sock.getsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY) == 0:
            pytest.skip("kernel refuses dual-stack sockets")
        sock.listen(8)
        port = sock.getsockname()[1]
        for family, address in ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")):
            client = socket.socket(family, socket.SOCK_STREAM)
            client.settimeout(5)
            try:
                client.connect((address, port))
            except OSError as exc:  # pragma: no cover - the bug this test exists for
                pytest.fail(f"{address} was refused by the wildcard bind: {exc}")
            finally:
                client.close()
    finally:
        sock.close()


def test_a_specific_bind_address_is_left_to_uvicorn(monkeypatch):
    """Only the wildcard is special-cased; picking an address picks a family on purpose."""
    from residual_zero.console.__main__ import _listen_socket

    for host in ("127.0.0.1", "0.0.0.0", "::1"):
        assert _listen_socket(host, 0) is None, host
