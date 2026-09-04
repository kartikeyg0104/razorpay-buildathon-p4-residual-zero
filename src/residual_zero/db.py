"""Least-privilege connections. The privilege boundary is readable in one screen.

Two backends stand behind these three functions (see :mod:`residual_zero.storage`):
SQLite for local development, the CLI, the eval harness and the tests; PostgreSQL as the
authoritative production store. The signatures, the owner check and the SQLite behaviour
are unchanged from the single-backend version — a caller that passes a path still gets a
file, which is what keeps ``make demo``, ``make eval`` and the suite identical.

``TABLE_OWNERS`` and ``SCHEMA`` describe the *SQLite* shape. The production shape, with its
foreign keys, indexes and financial CHECK constraints, is ``migrations/org/*.sql``; the two
are held together by ``tests/test_schema_parity.py``.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

TABLE_OWNERS: dict[str, frozenset[str]] = {
    "verify":     frozenset({"reconciliation", "decomposition_member"}),
    "audit":      frozenset({"audit_entry"}),
    "exceptions": frozenset({"exception", "exception_resolution", "exception_work"}),
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS reconciliation (
    bank_credit_id TEXT PRIMARY KEY,
    claimed_total_paise INTEGER NOT NULL,
    residual_paise INTEGER NOT NULL,
    uniqueness TEXT NOT NULL,
    pool_scope TEXT NOT NULL,
    disposition TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS decomposition_member (
    bank_credit_id TEXT NOT NULL,
    item_id TEXT NOT NULL,
    PRIMARY KEY (bank_credit_id, item_id)
);
CREATE TABLE IF NOT EXISTS audit_entry (
    seq INTEGER PRIMARY KEY,
    payload TEXT NOT NULL,
    metrics TEXT NOT NULL,
    prev_hash TEXT NOT NULL,
    entry_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS exception (
    bank_credit_id TEXT PRIMARY KEY,
    exception_class TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS exception_resolution (
    bank_credit_id TEXT PRIMARY KEY,
    resolution TEXT NOT NULL,
    decided_by TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS exception_work (
    bank_credit_id TEXT PRIMARY KEY,
    assignee TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'open',
    updated_by TEXT NOT NULL DEFAULT ''
);
"""


# ---------------------------------------------------------------- SQLite primitives
# The original implementations, unchanged. `storage.engine` calls these for the SQLite
# backend, so there is exactly one definition of what a SQLite connection is.


def _sqlite_readonly(path: Path) -> sqlite3.Connection:
    """sqlite3.connect('file:...?mode=ro', uri=True). Writes are rejected by the driver."""
    uri = "file:" + str(path.resolve()) + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.execute("PRAGMA query_only = ON")
    return conn


# Columns added to the SQLite schema after ledgers already existed on disk. `CREATE TABLE
# IF NOT EXISTS` cannot add a column to a table it finds, so an already-committed
# artifacts/dev/ledger.sqlite would keep the old shape and every insert naming a new column
# would fail (found the first time the review actor was recorded). Each entry is additive
# and nullable-with-a-default, so applying it never rewrites or reinterprets an existing
# financial value.
ADDED_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("exception_resolution", "decided_by", "TEXT NOT NULL DEFAULT ''"),
    ("exception_work", "updated_by", "TEXT NOT NULL DEFAULT ''"),
)


def _add_missing_columns(conn: sqlite3.Connection) -> None:
    for table, column, ddl in ADDED_COLUMNS:
        existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        if existing and column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
    conn.commit()


def _sqlite_readwrite(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    _add_missing_columns(conn)
    return conn


# ---------------------------------------------------------------- public API


def open_readonly(path: Path | None = None):
    """A connection the backend refuses writes on.

    On SQLite that is ``mode=ro`` plus ``query_only``; on PostgreSQL it is a read-only
    transaction. Both refuse below the application, where a coding mistake cannot argue.
    """
    from residual_zero.storage.engine import open_tenant_readonly

    return open_tenant_readonly(path)


def _open_readwrite(path: Path | None, owner: str):
    """Module-private. ``owner`` must be one of the three declared table owners."""
    from residual_zero.storage.engine import open_tenant_readwrite

    return open_tenant_readwrite(owner, path)


def init_db(path: Path | None = None) -> None:
    """Create the operational schema for this backend and organisation."""
    from residual_zero.storage.config import Backend, storage_config
    from residual_zero.storage.engine import _sqlite_path

    if storage_config().backend is Backend.SQLITE:
        resolved = _sqlite_path(path)
        conn = _sqlite_readwrite(resolved)
        conn.close()
        return
    from residual_zero.storage.engine import bootstrap_tenant
    from residual_zero.tenancy import Tenant, current_tenant

    tenant = current_tenant()
    if tenant is None:
        from residual_zero.storage.engine import _tenant_schema

        tenant = Tenant(org_id="default", slug="default", db_schema=_tenant_schema(None))
    bootstrap_tenant(tenant)
