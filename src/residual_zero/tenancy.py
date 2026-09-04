"""Which organisation the current request is acting for.

Isolation here is **structural**. A tenant does not get a shared table plus a ``WHERE
org_id = ?`` that some future query might forget; it gets its own storage namespace, and
its connections cannot name anything outside it:

* **PostgreSQL** — one schema per organisation. The connection sets
  ``search_path`` to that schema alone, with no ``public`` fallback, so an unqualified
  table name resolves inside the tenant or not at all.
* **SQLite** — one database file per organisation, under ``RZ_TENANT_ROOT``. A file the
  connection was not opened on is not reachable by any SQL it can run.

The organisation travels in a :class:`~contextvars.ContextVar` rather than a parameter on
every function. That is deliberate: roughly a hundred call sites read the desk's data
through four accessors (``_split``, ``_overlay``, ``_credit_lookup``, ``_db``), and
threading an argument through all of them would have meant editing financial code to add
tenancy. A ContextVar is also per-task, so two concurrent requests never observe each
other's tenant.

``current_tenant()`` returning ``None`` is the legacy single-tenant mode: the CLI, the eval
harness, ``make demo`` and the test suite all run with no tenant and therefore behave
exactly as they did before multi-tenancy existed.
"""

from __future__ import annotations

import os
import re
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Literal

DatasetKind = Literal["files", "sql"]

SCHEMA_PREFIX = "org_"
# A schema name is interpolated into DDL (it cannot be a bind parameter), so the character
# set is restricted at construction and every route into a Tenant goes through it.
_SAFE_NAME = re.compile(r"^[a-z][a-z0-9_]{0,54}$")

TENANT_ROOT_ENV = "RZ_TENANT_ROOT"
DEFAULT_TENANT_ROOT = "var/tenants"


class TenancyError(ValueError):
    """An organisation identifier this build will not turn into a storage namespace."""


def safe_namespace(raw: str) -> str:
    """Validate a storage namespace. Raises rather than sanitising.

    Sanitising would be the wrong move: two different organisation slugs must never
    collapse onto the same namespace, and silently rewriting one into a legal name is how
    that happens.
    """
    name = (raw or "").strip()
    if not _SAFE_NAME.match(name):
        raise TenancyError(
            f"unsafe storage namespace {raw!r}; expected {_SAFE_NAME.pattern}"
        )
    return name


def namespace_for_org(org_id: str) -> str:
    """Postgres schema name for an organisation id."""
    return safe_namespace(SCHEMA_PREFIX + re.sub(r"[^a-z0-9_]", "_", org_id.casefold()))


def tenant_root() -> Path:
    """Directory holding per-organisation SQLite files in local multi-tenant mode."""
    return Path(os.environ.get(TENANT_ROOT_ENV) or DEFAULT_TENANT_ROOT)


@dataclass(frozen=True)
class Tenant:
    """One organisation's storage namespace and dataset locator."""

    org_id: str
    slug: str
    db_schema: str
    dataset_kind: DatasetKind = "sql"
    dataset_root: str = ""

    def __post_init__(self) -> None:
        safe_namespace(self.db_schema)
        if self.dataset_kind not in ("files", "sql"):
            raise TenancyError(f"unknown dataset_kind {self.dataset_kind!r}")

    @property
    def sqlite_path(self) -> Path:
        """This organisation's SQLite ledger, when the backend is SQLite."""
        return tenant_root().joinpath(self.db_schema, "ledger.sqlite")

    def files_root(self) -> Path | None:
        """Rendered-source directory when this organisation reads a file corpus."""
        if self.dataset_kind != "files" or not self.dataset_root:
            return None
        return Path(self.dataset_root)

    def cache_key(self) -> str:
        """Stable key for per-tenant memoisation of loaded source data."""
        return f"{self.db_schema}|{self.dataset_kind}|{self.dataset_root}"


_CURRENT: ContextVar[Tenant | None] = ContextVar("rz_current_tenant", default=None)


def current_tenant() -> Tenant | None:
    """The organisation this request acts for, or ``None`` in single-tenant mode."""
    return _CURRENT.get()


def require_tenant() -> Tenant:
    """The current organisation, or raise. Used where a tenant is not optional."""
    tenant = _CURRENT.get()
    if tenant is None:
        raise TenancyError("no organisation is bound to this request")
    return tenant


@contextmanager
def use_tenant(tenant: Tenant | None) -> Iterator[Tenant | None]:
    """Bind ``tenant`` for the duration of the block. Restores the previous value."""
    token = _CURRENT.set(tenant)
    try:
        yield tenant
    finally:
        _CURRENT.reset(token)


def legacy_tenant_key() -> str:
    """Cache key used when no tenant is bound, so caches never mix modes."""
    return "__single_tenant__"


def cache_key() -> str:
    """Cache key for the current tenant, or the single-tenant key."""
    tenant = _CURRENT.get()
    return tenant.cache_key() if tenant is not None else legacy_tenant_key()
