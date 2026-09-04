"""Organisations, users, sessions and personal access tokens.

Storage lives in the shared schema (:func:`residual_zero.storage.engine.open_shared`),
because a login happens before the organisation is known. Everything financial lives in a
per-organisation namespace that a tenant connection cannot see out of, so this is the one
place with cross-organisation reach — and it stores no financial value at all.

Three credential rules are worth naming:

1. **Passwords** are scrypt-hashed with a per-user salt. The plaintext is never stored,
   never logged, and never returned.
2. **Session cookies** and **API tokens** are stored only as SHA-256 digests. A database
   dump therefore does not hand anybody a live session. Lookup is by digest, so it is a
   single indexed read rather than a scan-and-compare.
3. **Comparisons** go through :func:`hmac.compare_digest`.

The extension uses an API token rather than a cookie. That keeps the shipped extension free
of any secret — the token is one the user minted for themselves — and a bearer credential
is not a CSRF vector, so the extension needs no ``SameSite=None`` relaxation.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from residual_zero.tenancy import Tenant, namespace_for_org

TOKEN_PREFIX = "rz_pat_"
SESSION_COOKIE = "rz_session"
SESSION_TTL_HOURS_ENV = "RZ_SESSION_TTL_HOURS"
DEFAULT_SESSION_TTL_HOURS = 12

# scrypt parameters. n=2**15 costs ~32 MiB and tens of milliseconds per verification, which
# is the point: it is what makes an offline attack on a leaked hash expensive.
_SCRYPT_N = 2 ** 15
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 32


class Role(str, Enum):
    """What a user may do. No role can authorise a financial clear."""

    VIEWER = "viewer"
    ANALYST = "analyst"
    OWNER = "owner"

    def rank(self) -> int:
        return {"viewer": 0, "analyst": 1, "owner": 2}[self.value]

    def can(self, permission: str) -> bool:
        return permission in PERMISSIONS.get(self, frozenset())


# The complete permission set. `clear` is deliberately absent: authorising CLEARED is the
# deterministic engine's decision (UNIQUE + residual 0 + FULL pool + derived threshold) and
# granting it to a role would create a second, ungated path to a financial clear.
PERMISSIONS: dict[Role, frozenset[str]] = {
    Role.VIEWER: frozenset({"read_financial", "read_ai"}),
    Role.ANALYST: frozenset({"read_financial", "read_ai", "review_exception", "export"}),
    Role.OWNER: frozenset(
        {"read_financial", "read_ai", "review_exception", "export", "administer"}
    ),
}


class AuthError(RuntimeError):
    """Authentication or registration failed. The message is safe to show a user."""


@dataclass(frozen=True)
class Principal:
    """The authenticated caller, and the organisation their request is confined to."""

    user_id: str
    email: str
    org_id: str
    role: Role
    tenant: Tenant
    credential: str = "session"
    """``"session"`` (browser cookie) or ``"token"`` (extension bearer token)."""

    def can(self, permission: str) -> bool:
        return self.role.can(permission)

    @property
    def is_bearer(self) -> bool:
        return self.credential == "token"


# ---------------------------------------------------------------- password hashing


def hash_password(plaintext: str) -> str:
    """scrypt with a fresh 16-byte salt, encoded with its own parameters.

    The parameters travel with the hash so raising the cost later does not invalidate
    existing users: an old hash still verifies against the parameters it was made with.
    """
    if not plaintext or len(plaintext) < 12:
        raise AuthError("password must be at least 12 characters")
    if len(plaintext) > 1024:
        raise AuthError("password is too long")
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        plaintext.encode("utf-8"), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P,
        dklen=_SCRYPT_DKLEN, maxmem=64 * 1024 * 1024,
    )
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salt.hex()}${digest.hex()}"


def verify_password(plaintext: str, encoded: str) -> bool:
    """Constant-time verification. A malformed stored hash verifies as False, never True."""
    try:
        algorithm, n_s, r_s, p_s, salt_hex, digest_hex = encoded.split("$")
        if algorithm != "scrypt":
            return False
        candidate = hashlib.scrypt(
            (plaintext or "").encode("utf-8"),
            salt=bytes.fromhex(salt_hex),
            n=int(n_s), r=int(r_s), p=int(p_s),
            dklen=len(bytes.fromhex(digest_hex)),
            maxmem=64 * 1024 * 1024,
        )
    except (ValueError, TypeError, MemoryError):
        return False
    return hmac.compare_digest(candidate, bytes.fromhex(digest_hex))


def _token_digest(raw: str) -> str:
    return hashlib.sha256((raw or "").encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def session_ttl() -> timedelta:
    raw = (os.environ.get(SESSION_TTL_HOURS_ENV) or "").strip()
    hours = int(raw) if raw.isdigit() and int(raw) > 0 else DEFAULT_SESSION_TTL_HOURS
    return timedelta(hours=min(hours, 24 * 30))


def normalise_email(raw: str) -> str:
    email = (raw or "").strip().casefold()
    if "@" not in email or len(email) < 3 or len(email) > 320:
        raise AuthError("that is not a usable email address")
    return email


def slug_from_email(email: str) -> str:
    """A default organisation slug for a self-service signup."""
    import re

    local = email.partition("@")[0]
    base = re.sub(r"[^a-z0-9]+", "", local.casefold())[:24] or "org"
    if not base[0].isalpha():
        base = "o" + base
    return base


# ---------------------------------------------------------------- SQLite fallback schema

# Local development and the test suite run identity on SQLite so authentication can be
# exercised without a Postgres server. This is the same shape as
# migrations/shared/0001_identity.sql, in SQLite's dialect.
SQLITE_IDENTITY_SCHEMA = """
CREATE TABLE IF NOT EXISTS organization (
    org_id TEXT PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    db_schema TEXT NOT NULL UNIQUE,
    dataset_kind TEXT NOT NULL DEFAULT 'sql',
    dataset_root TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS app_user (
    user_id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    org_id TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'analyst',
    created_at TEXT NOT NULL DEFAULT '',
    disabled_at TEXT
);
CREATE TABLE IF NOT EXISTS user_session (
    session_id TEXT PRIMARY KEY,
    token_hash TEXT NOT NULL UNIQUE,
    user_id TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT '',
    expires_at TEXT NOT NULL,
    revoked_at TEXT
);
CREATE TABLE IF NOT EXISTS api_token (
    token_id TEXT PRIMARY KEY,
    token_hash TEXT NOT NULL UNIQUE,
    user_id TEXT NOT NULL,
    label TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT '',
    expires_at TEXT,
    revoked_at TEXT,
    last_used_at TEXT
);
CREATE TABLE IF NOT EXISTS system_audit_event (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    occurred_at TEXT NOT NULL DEFAULT '',
    kind TEXT NOT NULL,
    user_id TEXT,
    org_id TEXT,
    outcome TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT ''
);
"""


def sqlite_identity_path() -> Path:
    """Where the SQLite identity database lives. Never inside the financial ledger file."""
    from residual_zero.tenancy import tenant_root

    override = os.environ.get("RZ_IDENTITY_DB")
    return Path(override) if override else tenant_root().joinpath("identity.sqlite")


def ensure_sqlite_identity() -> Path:
    import sqlite3

    path = sqlite_identity_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(SQLITE_IDENTITY_SCHEMA)
        conn.commit()
    finally:
        conn.close()
    return path


class IdentityStore:
    """Read and write identity. One instance per operation; connections are not pooled here."""

    def __init__(self) -> None:
        from residual_zero.storage.config import Backend, storage_config

        self._is_postgres = storage_config().backend is Backend.POSTGRES

    def _connect(self, readonly: bool = False):
        from residual_zero.storage.engine import open_shared

        if not self._is_postgres:
            ensure_sqlite_identity()
            import sqlite3

            path = sqlite_identity_path()
            if readonly:
                conn = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
                conn.execute("PRAGMA query_only = ON")
                return conn
            return sqlite3.connect(str(path))
        return open_shared(readonly=readonly)

    # ------------------------------------------------------------ organisations

    def create_organization(
        self,
        slug: str,
        display_name: str = "",
        *,
        dataset_kind: str = "sql",
        dataset_root: str = "",
        org_id: str | None = None,
    ) -> Tenant:
        """Create an organisation and bring its storage namespace up to date."""
        from residual_zero.storage.engine import bootstrap_tenant

        clean_slug = _clean_slug(slug)
        oid = org_id or clean_slug
        schema = namespace_for_org(oid)
        tenant = Tenant(
            org_id=oid, slug=clean_slug, db_schema=schema,
            dataset_kind=dataset_kind, dataset_root=dataset_root,
        )
        conn = self._connect()
        try:
            existing = conn.execute(
                "SELECT org_id FROM organization WHERE slug = ?", (clean_slug,)
            ).fetchone()
            if existing is not None:
                raise AuthError(f"organisation {clean_slug!r} already exists")
            conn.execute(
                "INSERT INTO organization "
                "(org_id, slug, display_name, db_schema, dataset_kind, dataset_root, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (oid, clean_slug, display_name or clean_slug, schema,
                 dataset_kind, dataset_root, _now().isoformat()),
            )
            conn.commit()
        finally:
            conn.close()
        bootstrap_tenant(tenant)
        return tenant

    def set_organization_dataset(
        self, slug: str, dataset_kind: str, dataset_root: str = ""
    ) -> Tenant:
        """Repoint an existing organisation at a different source of records.

        ``files`` reads the committed synthetic corpus; ``sql`` reads the organisation's
        own ingested rows. A self-service signup starts on ``sql`` and therefore starts
        empty, which is correct — another tenant's records are never a starting point —
        but it leaves the deployed demo with nothing to show. This is the supported way to
        say "this organisation is the demo".

        Never point an organisation holding real books at the file corpus: the corpus is
        synthetic and shared, and the desk would then report figures that are not that
        organisation's. Nothing here writes to the ledger, and nothing here clears
        anything; it only changes which source the read-only overlay loads.
        """
        clean_slug = _clean_slug(slug)
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT org_id, slug, db_schema FROM organization WHERE slug = ?",
                (clean_slug,),
            ).fetchone()
            if row is None:
                raise AuthError(f"unknown organisation {clean_slug!r}")
            # Constructed before the write so an unknown kind is rejected by the same
            # validation the request path uses, rather than stored and failing later.
            tenant = Tenant(
                org_id=str(row[0]), slug=str(row[1]), db_schema=str(row[2]),
                dataset_kind=dataset_kind,
                dataset_root=dataset_root if dataset_kind == "files" else "",
            )
            conn.execute(
                "UPDATE organization SET dataset_kind = ?, dataset_root = ? WHERE org_id = ?",
                (tenant.dataset_kind, tenant.dataset_root, tenant.org_id),
            )
            conn.commit()
        finally:
            conn.close()
        return tenant

    def tenant_for_org(self, org_id: str) -> Tenant:
        conn = self._connect(readonly=True)
        try:
            row = conn.execute(
                "SELECT org_id, slug, db_schema, dataset_kind, dataset_root "
                "FROM organization WHERE org_id = ?",
                (org_id,),
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            raise AuthError("unknown organisation")
        return Tenant(
            org_id=str(row[0]), slug=str(row[1]), db_schema=str(row[2]),
            dataset_kind=str(row[3]), dataset_root=str(row[4] or ""),
        )

    def find_organization(self, slug: str) -> Tenant | None:
        conn = self._connect(readonly=True)
        try:
            row = conn.execute(
                "SELECT org_id FROM organization WHERE slug = ?", (_clean_slug(slug),)
            ).fetchone()
        finally:
            conn.close()
        return self.tenant_for_org(str(row[0])) if row is not None else None

    # ------------------------------------------------------------ users

    def create_user(
        self, email: str, password: str, org_id: str, role: Role = Role.ANALYST,
    ) -> Principal:
        clean = normalise_email(email)
        encoded = hash_password(password)
        tenant = self.tenant_for_org(org_id)
        user_id = "usr_" + secrets.token_hex(12)
        conn = self._connect()
        try:
            existing = conn.execute(
                "SELECT user_id FROM app_user WHERE email = ?", (clean,)
            ).fetchone()
            if existing is not None:
                raise AuthError("an account with that email already exists")
            conn.execute(
                "INSERT INTO app_user (user_id, email, password_hash, org_id, role, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, clean, encoded, org_id, role.value, _now().isoformat()),
            )
            conn.commit()
        finally:
            conn.close()
        return Principal(
            user_id=user_id, email=clean, org_id=org_id, role=role, tenant=tenant,
        )

    def authenticate(self, email: str, password: str) -> Principal:
        """Verify a password. Raises :class:`AuthError` with one message for every failure.

        One message on purpose: distinguishing "no such account" from "wrong password"
        turns the login form into an account-existence oracle.
        """
        try:
            clean = normalise_email(email)
        except AuthError:
            clean = ""
        conn = self._connect(readonly=True)
        try:
            row = conn.execute(
                "SELECT user_id, email, password_hash, org_id, role, disabled_at "
                "FROM app_user WHERE email = ?",
                (clean,),
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            # Spend comparable time on an unknown account so the response time does not
            # reveal whether the email exists.
            verify_password(password, hash_password("x" * 16))
            raise AuthError("email or password is incorrect")
        if row[5]:
            raise AuthError("this account is disabled")
        if not verify_password(password, str(row[2])):
            raise AuthError("email or password is incorrect")
        return Principal(
            user_id=str(row[0]), email=str(row[1]), org_id=str(row[3]),
            role=Role(str(row[4])), tenant=self.tenant_for_org(str(row[3])),
        )

    def count_users(self) -> int:
        conn = self._connect(readonly=True)
        try:
            row = conn.execute("SELECT COUNT(*) FROM app_user").fetchone()
        finally:
            conn.close()
        return int(row[0]) if row else 0

    # ------------------------------------------------------------ sessions

    def create_session(self, principal: Principal) -> str:
        """Mint a session and return the raw cookie value. Only the digest is stored."""
        raw = secrets.token_urlsafe(32)
        conn = self._connect()
        try:
            conn.execute(
                "INSERT INTO user_session (session_id, token_hash, user_id, created_at, expires_at) "
                "VALUES (?, ?, ?, ?, ?)",
                ("ses_" + secrets.token_hex(12), _token_digest(raw), principal.user_id,
                 _now().isoformat(), (_now() + session_ttl()).isoformat()),
            )
            conn.commit()
        finally:
            conn.close()
        return raw

    def resolve_session(self, raw: str) -> Principal | None:
        if not raw:
            return None
        conn = self._connect(readonly=True)
        try:
            row = conn.execute(
                "SELECT s.expires_at, s.revoked_at, u.user_id, u.email, u.org_id, u.role, "
                "u.disabled_at FROM user_session s JOIN app_user u ON u.user_id = s.user_id "
                "WHERE s.token_hash = ?",
                (_token_digest(raw),),
            ).fetchone()
        finally:
            conn.close()
        if row is None or row[1] or row[6]:
            return None
        if _expired(row[0]):
            return None
        return Principal(
            user_id=str(row[2]), email=str(row[3]), org_id=str(row[4]),
            role=Role(str(row[5])), tenant=self.tenant_for_org(str(row[4])),
            credential="session",
        )

    def revoke_session(self, raw: str) -> None:
        if not raw:
            return
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE user_session SET revoked_at = ? WHERE token_hash = ?",
                (_now().isoformat(), _token_digest(raw)),
            )
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------ API tokens

    def create_api_token(self, principal: Principal, label: str = "") -> str:
        """Mint a personal access token. Returned once; only its digest is stored."""
        raw = TOKEN_PREFIX + secrets.token_urlsafe(32)
        conn = self._connect()
        try:
            conn.execute(
                "INSERT INTO api_token (token_id, token_hash, user_id, label, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                ("tok_" + secrets.token_hex(12), _token_digest(raw), principal.user_id,
                 (label or "")[:120], _now().isoformat()),
            )
            conn.commit()
        finally:
            conn.close()
        return raw

    def resolve_api_token(self, raw: str) -> Principal | None:
        if not raw or not raw.startswith(TOKEN_PREFIX):
            return None
        conn = self._connect(readonly=True)
        try:
            row = conn.execute(
                "SELECT t.expires_at, t.revoked_at, u.user_id, u.email, u.org_id, u.role, "
                "u.disabled_at FROM api_token t JOIN app_user u ON u.user_id = t.user_id "
                "WHERE t.token_hash = ?",
                (_token_digest(raw),),
            ).fetchone()
        finally:
            conn.close()
        if row is None or row[1] or row[6]:
            return None
        if row[0] and _expired(row[0]):
            return None
        return Principal(
            user_id=str(row[2]), email=str(row[3]), org_id=str(row[4]),
            role=Role(str(row[5])), tenant=self.tenant_for_org(str(row[4])),
            credential="token",
        )

    def list_api_tokens(self, principal: Principal) -> list[dict[str, Any]]:
        conn = self._connect(readonly=True)
        try:
            rows = list(conn.execute(
                "SELECT token_id, label, created_at, revoked_at FROM api_token "
                "WHERE user_id = ? ORDER BY created_at DESC",
                (principal.user_id,),
            ))
        finally:
            conn.close()
        return [
            {"token_id": str(r[0]), "label": str(r[1] or ""),
             "created_at": str(r[2] or ""), "revoked": bool(r[3])}
            for r in rows
        ]

    def revoke_api_token(self, principal: Principal, token_id: str) -> bool:
        """Revoke one of *this user's* tokens. A token belonging to anyone else is not found."""
        conn = self._connect()
        try:
            found = conn.execute(
                "SELECT token_id FROM api_token WHERE token_id = ? AND user_id = ?",
                (token_id, principal.user_id),
            ).fetchone()
            if found is None:
                return False
            conn.execute(
                "UPDATE api_token SET revoked_at = ? WHERE token_id = ? AND user_id = ?",
                (_now().isoformat(), token_id, principal.user_id),
            )
            conn.commit()
        finally:
            conn.close()
        return True

    # ------------------------------------------------------------ system audit

    def log_event(
        self, kind: str, outcome: str, *,
        user_id: str | None = None, org_id: str | None = None, detail: str = "",
    ) -> None:
        """Record a non-financial event. ``detail`` must never carry a credential."""
        conn = self._connect()
        try:
            conn.execute(
                "INSERT INTO system_audit_event (occurred_at, kind, user_id, org_id, outcome, detail) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (_now().isoformat(), kind[:64], user_id, org_id, outcome[:32], detail[:500]),
            )
            conn.commit()
        finally:
            conn.close()


def _expired(raw: Any) -> bool:
    if isinstance(raw, datetime):
        moment = raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    else:
        try:
            moment = datetime.fromisoformat(str(raw))
        except ValueError:
            return True
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
    return moment <= _now()


def _clean_slug(raw: str) -> str:
    import re

    slug = re.sub(r"[^a-z0-9-]+", "-", (raw or "").strip().casefold()).strip("-")
    if not slug or len(slug) > 48:
        raise AuthError("organisation slug must be 1-48 characters of a-z, 0-9 or '-'")
    return slug
