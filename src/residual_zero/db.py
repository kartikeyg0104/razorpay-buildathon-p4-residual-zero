"""Least-privilege SQLite connections. The privilege boundary is readable in one screen."""

from __future__ import annotations

import sqlite3
from pathlib import Path

TABLE_OWNERS: dict[str, frozenset[str]] = {
    "verify":     frozenset({"reconciliation", "decomposition_member"}),
    "audit":      frozenset({"audit_entry"}),
    "exceptions": frozenset({"exception", "exception_resolution"}),
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
    resolution TEXT NOT NULL
);
"""


def open_readonly(path: Path) -> sqlite3.Connection:
    """sqlite3.connect('file:...?mode=ro', uri=True). Writes are rejected by the driver."""
    uri = "file:" + str(path.resolve()) + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.execute("PRAGMA query_only = ON")
    return conn


def _open_readwrite(path: Path, owner: str) -> sqlite3.Connection:
    """Module-private. ``owner`` must be one of the three declared table owners."""
    if owner not in TABLE_OWNERS:
        raise ValueError(f"unknown db owner {owner!r}; declared owners: {sorted(TABLE_OWNERS)}")
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    return conn


def init_db(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    conn.close()
