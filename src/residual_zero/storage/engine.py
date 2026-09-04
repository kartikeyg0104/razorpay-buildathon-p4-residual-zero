"""Open a connection for the current backend and the current organisation.

This is the one place that decides *where* a row goes. Callers keep asking for "the
read-only ledger" or "the audit writer" exactly as they did before Postgres or tenancy
existed; the answer now depends on :func:`residual_zero.storage.config.storage_config` and
:func:`residual_zero.tenancy.current_tenant`.

The least-privilege boundary from the original SQLite design is preserved on both backends:
a read path gets a connection the *server* refuses writes on, and a write path must name
which of the three table owners it is.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from residual_zero.storage.config import Backend, storage_config
from residual_zero.tenancy import Tenant, current_tenant

# Kept in sync with residual_zero.db.TABLE_OWNERS; imported lazily to avoid a cycle.


def _shared_schema() -> str:
    import os

    from residual_zero.storage.migrate import DEFAULT_SHARED_SCHEMA, SHARED_SCHEMA_ENV

    from residual_zero.tenancy import safe_namespace

    return safe_namespace(os.environ.get(SHARED_SCHEMA_ENV) or DEFAULT_SHARED_SCHEMA)


def _tenant_schema(tenant: Tenant | None) -> str:
    """Postgres schema for this request.

    With no tenant bound the process is in single-tenant mode and uses the shared schema's
    sibling default. A production request always has a tenant, because authentication
    binds one before any route runs.
    """
    if tenant is not None:
        return tenant.db_schema
    import os

    from residual_zero.tenancy import safe_namespace

    return safe_namespace(os.environ.get("RZ_DEFAULT_SCHEMA") or "org_default")


def open_tenant_readonly(path: Path | None = None):
    """A connection the backend rejects writes on, scoped to the current organisation."""
    cfg = storage_config()
    if cfg.backend is Backend.SQLITE:
        from residual_zero.db import _sqlite_readonly

        return _sqlite_readonly(_sqlite_path(path))
    from residual_zero.storage.pg import PgConnection

    return PgConnection(
        cfg.dsn,
        schema=_tenant_schema(current_tenant()),
        readonly=True,
        application_name="residual-zero-read",
    )


def open_tenant_readwrite(owner: str, path: Path | None = None):
    """A write connection for one declared table owner, scoped to the organisation."""
    from residual_zero.db import TABLE_OWNERS

    if owner not in TABLE_OWNERS:
        raise ValueError(
            f"unknown db owner {owner!r}; declared owners: {sorted(TABLE_OWNERS)}"
        )
    cfg = storage_config()
    if cfg.backend is Backend.SQLITE:
        from residual_zero.db import _sqlite_readwrite

        return _sqlite_readwrite(_sqlite_path(path))
    from residual_zero.storage.pg import PgConnection

    return PgConnection(
        cfg.dsn,
        schema=_tenant_schema(current_tenant()),
        readonly=False,
        application_name=f"residual-zero-{owner}",
    )


def open_shared(readonly: bool = False):
    """Connection to the shared identity schema. Postgres only.

    Identity is cross-organisation by nature — a login happens before the organisation is
    known — so it is the one schema a tenant connection can never reach.
    """
    cfg = storage_config()
    if cfg.backend is Backend.SQLITE:
        from residual_zero.identity.store import sqlite_identity_path
        from residual_zero.db import _sqlite_readonly, _sqlite_readwrite

        path = sqlite_identity_path()
        return _sqlite_readonly(path) if readonly else _sqlite_readwrite(path)
    from residual_zero.storage.pg import PgConnection

    return PgConnection(
        cfg.dsn,
        schema=_shared_schema(),
        readonly=readonly,
        create_schema=not readonly,
        application_name="residual-zero-identity",
    )


def _sqlite_path(explicit: Path | None) -> Path:
    """Where the SQLite ledger lives for this request.

    An explicit path always wins: the CLI, the eval harness and every test that passes a
    ``tmp_path`` rely on that, and none of them are multi-tenant. Otherwise a bound tenant
    picks its own file and the legacy default is used when there is none.
    """
    if explicit is not None:
        return explicit
    tenant = current_tenant()
    if tenant is not None:
        return tenant.sqlite_path
    from residual_zero.storage.config import sqlite_default_path

    return sqlite_default_path()


def bootstrap_tenant(tenant: Tenant) -> list[str]:
    """Create this organisation's storage namespace and bring its schema up to date."""
    cfg = storage_config()
    from residual_zero.storage.migrate import apply_migrations

    if cfg.backend is Backend.SQLITE:
        from residual_zero.db import _sqlite_readwrite
        from residual_zero.ingest.sql_source import SQLITE_SOURCE_SCHEMA

        conn = _sqlite_readwrite(tenant.sqlite_path)
        try:
            # The operational tables come from db.SCHEMA; the source tables do not, because
            # folding them in would change the shape of the committed single-tenant
            # artifacts/dev/ledger.sqlite. A new organisation needs both, empty, or its
            # first read fails on a missing table instead of reporting "no data yet".
            conn.executescript(SQLITE_SOURCE_SCHEMA)
            conn.commit()
            return []
        finally:
            conn.close()
    from residual_zero.storage.pg import PgConnection

    conn = PgConnection(cfg.dsn, schema=tenant.db_schema, create_schema=True)
    try:
        return apply_migrations(conn, "org")
    finally:
        conn.close()


def bootstrap_shared() -> list[str]:
    """Create the shared identity schema and bring it up to date."""
    cfg = storage_config()
    if cfg.backend is Backend.SQLITE:
        from residual_zero.identity.store import ensure_sqlite_identity

        ensure_sqlite_identity()
        return []
    from residual_zero.storage.migrate import apply_migrations

    conn = open_shared()
    try:
        return apply_migrations(conn, "shared")
    finally:
        conn.close()


__all__ = [
    "bootstrap_shared",
    "bootstrap_tenant",
    "open_shared",
    "open_tenant_readonly",
    "open_tenant_readwrite",
]
