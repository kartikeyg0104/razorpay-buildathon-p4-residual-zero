"""The production database path, and the ways it could silently stop being PostgreSQL.

The failure this file exists to prevent: a production process that comes up successfully
and serves the committed development SQLite ledger as if it were production data. That is
worse than a crash, because nothing looks wrong - the console renders, the numbers are
plausible, and they belong to a different database.
"""

from __future__ import annotations

import pytest

from residual_zero.appconfig import ConfigError, enforce_import_time, load_config
from residual_zero.storage.config import Backend, StorageConfigError, parse_database_url

PROD = {
    "RZ_ENV": "production",
    "RZ_AUTH_MODE": "required",
    "RZ_SESSION_SECRET": "s" * 40,
    "RZ_PUBLIC_ORIGIN": "https://rz.example",
    "RZ_DATABASE_URL": "postgresql://u:p@host/db",
}


@pytest.fixture()
def prod(monkeypatch):
    for k, v in PROD.items():
        monkeypatch.setenv(k, v)
    return monkeypatch


def test_a_complete_production_config_imports(prod):
    enforce_import_time()  # must not raise
    assert load_config().is_production


def test_importing_the_app_refuses_production_without_postgres(prod):
    """REGRESSION: `uvicorn residual_zero.console.app:app` bypassed the startup checks.

    validate_for_startup() runs only in __main__, so a process started with uvicorn or
    gunicorn - the default on most hosting platforms - imported the module and served the
    development SQLite ledger under RZ_ENV=production. Verified before the fix: 248 audit
    rows returned from artifacts/dev/ledger.sqlite. The guard now runs at import, where no
    start command can route around it.
    """
    prod.delenv("RZ_DATABASE_URL")
    with pytest.raises(ConfigError, match="PostgreSQL"):
        enforce_import_time()


@pytest.mark.parametrize("url", ["sqlite:///local.db", "sqlite://", "file:///x.db"])
def test_production_refuses_an_explicit_sqlite_url(prod, url):
    prod.setenv("RZ_DATABASE_URL", url)
    with pytest.raises(ConfigError, match="PostgreSQL"):
        enforce_import_time()


def test_local_mode_is_never_blocked_by_the_import_guard(monkeypatch):
    """Local development must stay zero-configuration."""
    for k in PROD:
        monkeypatch.delenv(k, raising=False)
    enforce_import_time()  # must not raise
    assert load_config().is_production is False
    assert parse_database_url(None).backend is Backend.SQLITE


def test_a_typo_in_the_database_url_is_an_error_not_a_downgrade():
    """A mistyped scheme must stop the process, never quietly use a local file."""
    for bad in ("postgres//host/db", "psql://host/db", "mysql://host/db", "http://host/db"):
        with pytest.raises(StorageConfigError):
            parse_database_url(bad)


def test_the_app_module_calls_the_guard_at_import():
    """Asserted on the source, so the call cannot be dropped without this failing."""
    from pathlib import Path

    src = Path("src/residual_zero/console/app.py").read_text(encoding="utf-8")
    assert "enforce_import_time()" in src
    # It must run before the app object is built, not inside a route.
    assert src.index("enforce_import_time()") < src.index("app.add_middleware")


def test_a_postgres_connection_failure_is_loud_not_a_fallback(monkeypatch):
    """An unreachable database must raise, never silently switch to SQLite."""
    monkeypatch.setenv("RZ_DATABASE_URL",
                       "postgresql://nobody:nothing@127.0.0.1:1/nope?connect_timeout=2")
    from residual_zero.storage.config import storage_config
    from residual_zero.storage.engine import open_tenant_readonly

    assert storage_config().backend is Backend.POSTGRES
    with pytest.raises(Exception) as exc:
        open_tenant_readonly()
    # Whatever it is, it must not be a quietly-returned SQLite connection.
    assert "sqlite" not in type(exc.value).__name__.casefold()
