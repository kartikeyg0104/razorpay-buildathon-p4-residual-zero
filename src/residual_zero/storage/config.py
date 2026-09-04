"""Which persistence backend this process uses, and where it lives.

One environment variable decides: ``RZ_DATABASE_URL``. Absent, the process is on SQLite and
behaves exactly as it did before Postgres existed — that is what keeps the CLI, the eval
harness and the test suite unchanged. Present and ``postgresql://``, the process is on the
production backend.

Nothing here renders a secret: :meth:`StorageConfig.safe_dsn` is the only printable form of
the URL and it removes the password.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


class Backend(str, Enum):
    SQLITE = "sqlite"
    POSTGRES = "postgres"


POSTGRES_SCHEMES = frozenset({"postgres", "postgresql", "postgresql+psycopg"})
SQLITE_SCHEMES = frozenset({"sqlite", "sqlite3", "file"})

# Environment variable name, kept in one place so the audit script and the docs agree.
URL_ENV = "RZ_DATABASE_URL"


class StorageConfigError(ValueError):
    """A database URL this build cannot honour. Never contains the password."""


@dataclass(frozen=True)
class StorageConfig:
    """Resolved persistence configuration for this process."""

    backend: Backend
    dsn: str = ""
    """Connection string for Postgres. Empty on SQLite."""

    @property
    def is_postgres(self) -> bool:
        return self.backend is Backend.POSTGRES

    def safe_dsn(self) -> str:
        """The DSN with the password removed. The only form that may be logged."""
        if not self.dsn:
            return ""
        parts = urlsplit(self.dsn)
        netloc = parts.netloc
        if "@" in netloc:
            userinfo, _, host = netloc.rpartition("@")
            user, _, _password = userinfo.partition(":")
            netloc = (user + ":***@" if user else "") + host
        return urlunsplit((parts.scheme, netloc, parts.path, "", ""))


def _normalise_pg(raw: str) -> str:
    """psycopg accepts ``postgresql://``. Rewrite the SQLAlchemy-style aliases onto it."""
    scheme, _, rest = raw.partition("://")
    return "postgresql://" + rest if scheme != "postgresql" else raw


def parse_database_url(raw: str | None) -> StorageConfig:
    """Resolve a database URL into a :class:`StorageConfig`.

    An empty or missing URL means SQLite, which is the local-development default. An
    unrecognised scheme is an error rather than a silent fallback: a typo in production
    must stop the process, not quietly downgrade the authoritative store to a local file.
    """
    text = (raw or "").strip()
    if not text:
        return StorageConfig(backend=Backend.SQLITE)
    scheme = text.partition("://")[0].casefold()
    if scheme in POSTGRES_SCHEMES:
        return StorageConfig(backend=Backend.POSTGRES, dsn=_normalise_pg(text))
    if scheme in SQLITE_SCHEMES:
        return StorageConfig(backend=Backend.SQLITE)
    raise StorageConfigError(
        f"{URL_ENV} has unsupported scheme {scheme!r}; "
        f"expected one of {sorted(POSTGRES_SCHEMES | SQLITE_SCHEMES)}"
    )


def storage_config() -> StorageConfig:
    """Read :data:`URL_ENV` from the environment on every call.

    Deliberately uncached: tests and the migration runner point one process at more than
    one database, and a cached global would silently keep the first.
    """
    return parse_database_url(os.environ.get(URL_ENV))


def sqlite_default_path() -> Path:
    """The legacy single-tenant ledger location. Unchanged from before Postgres."""
    env_path = os.environ.get("RZ_DB")
    if env_path:
        return Path(env_path)
    primary = Path("artifacts").joinpath("dev", "ledger.sqlite")
    if primary.is_file():
        return primary
    return Path("artifacts").joinpath("dev", "cp5", "ledger.sqlite")
