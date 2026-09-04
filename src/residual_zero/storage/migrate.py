"""Reproducible SQL migrations for the PostgreSQL backend.

Two ledgers, because there are two kinds of schema:

* ``migrations/shared`` runs once, in the shared identity schema.
* ``migrations/org`` runs once per organisation, inside that organisation's own schema.

Each applied version is recorded with the checksum of the file that produced it. A file
edited after it was applied is a hard error rather than a silent divergence between what the
repository says the schema is and what the database actually has.

Every migration is written to be idempotent (``CREATE TABLE IF NOT EXISTS``), so a partially
applied run can simply be re-run. Nothing here transforms a financial value; data migration
is a separate, verified step (``scripts/migrate_corpus.py``).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from residual_zero.storage.dialect import split_script

SHARED_SCHEMA_ENV = "RZ_SHARED_SCHEMA"
DEFAULT_SHARED_SCHEMA = "rz_shared"


def migrations_root() -> Path:
    """Repository ``migrations/`` directory, found from this file or the working directory."""
    here = Path(__file__).resolve().parents[3].joinpath("migrations")
    if here.is_dir():
        return here
    cwd = Path("migrations")
    if cwd.is_dir():
        return cwd
    raise FileNotFoundError("migrations/ not found")


@dataclass(frozen=True)
class Migration:
    version: str
    path: Path
    sql: str

    @property
    def checksum(self) -> str:
        return hashlib.sha256(self.sql.encode("utf-8")).hexdigest()


def load_migrations(kind: str) -> tuple[Migration, ...]:
    """Load ``migrations/<kind>/*.sql`` in filename order."""
    folder = migrations_root().joinpath(kind)
    if not folder.is_dir():
        raise FileNotFoundError(f"migrations/{kind} not found")
    out = []
    for path in sorted(folder.glob("*.sql")):
        out.append(Migration(version=path.stem, path=path, sql=path.read_text(encoding="utf-8")))
    if not out:
        raise FileNotFoundError(f"migrations/{kind} contains no .sql files")
    return tuple(out)


class MigrationChecksumMismatch(RuntimeError):
    """An already-applied migration file changed on disk. Add a new file instead."""


def _applied(conn) -> dict[str, str]:
    try:
        rows = list(conn.execute("SELECT version, checksum FROM schema_migration"))
    except Exception:
        # First run: schema_migration is itself created by migration 0001.
        conn.rollback()
        return {}
    return {str(v): str(c) for v, c in rows}


def apply_migrations(conn, kind: str) -> list[str]:
    """Apply every unapplied migration of ``kind`` to ``conn``. Returns versions applied.

    Each migration runs in its own transaction: a failure leaves the versions before it
    applied and recorded, and re-running resumes from there.
    """
    applied = _applied(conn)
    done: list[str] = []
    for migration in load_migrations(kind):
        known = applied.get(migration.version)
        if known is not None:
            if known != migration.checksum:
                raise MigrationChecksumMismatch(
                    f"{migration.path} was edited after it was applied "
                    f"(recorded {known[:12]}, on disk {migration.checksum[:12]}). "
                    "Add a new numbered migration rather than changing history."
                )
            continue
        for statement in split_script(migration.sql):
            conn.execute(statement)
        conn.execute(
            "INSERT OR REPLACE INTO schema_migration (version, checksum) VALUES (?, ?)",
            (migration.version, migration.checksum),
        )
        conn.commit()
        done.append(migration.version)
    return done


def pending(conn, kind: str) -> list[str]:
    """Versions of ``kind`` not yet applied to ``conn``."""
    applied = _applied(conn)
    return [m.version for m in load_migrations(kind) if m.version not in applied]
