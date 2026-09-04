-- Shared (cross-organisation) schema: identity and the migration ledger.
--
-- These tables live in one schema because a login happens BEFORE the organisation is
-- known. Everything financial lives in a per-organisation schema instead (migrations/org),
-- so a query issued on a tenant connection cannot name a row here or in another tenant.
--
-- No financial value is stored in this file. Nothing here computes anything.

CREATE TABLE IF NOT EXISTS schema_migration (
    version     TEXT        PRIMARY KEY,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    checksum    TEXT        NOT NULL
);

CREATE TABLE IF NOT EXISTS organization (
    org_id       TEXT        PRIMARY KEY,
    slug         TEXT        NOT NULL,
    display_name TEXT        NOT NULL,
    -- The schema holding this organisation's financial rows. Structural isolation: a
    -- tenant connection sets search_path to exactly this value and nothing else.
    db_schema    TEXT        NOT NULL,
    -- 'files' keeps the committed synthetic demo corpus on disk (read-only, shared,
    -- public in the repository). 'sql' reads this organisation's own ingested rows.
    dataset_kind TEXT        NOT NULL DEFAULT 'sql',
    dataset_root TEXT        NOT NULL DEFAULT '',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT organization_slug_unique      UNIQUE (slug),
    CONSTRAINT organization_db_schema_unique UNIQUE (db_schema),
    CONSTRAINT organization_dataset_kind_valid CHECK (dataset_kind IN ('files', 'sql'))
);

CREATE TABLE IF NOT EXISTS app_user (
    user_id       TEXT        PRIMARY KEY,
    email         TEXT        NOT NULL,
    -- scrypt, stored as an algorithm-tagged string. Never a plaintext password, and never
    -- a reversible encoding of one.
    password_hash TEXT        NOT NULL,
    org_id        TEXT        NOT NULL,
    -- viewer: read financial data. analyst: additionally record human review decisions.
    -- owner: additionally administer the organisation. No role can authorise CLEARED —
    -- that gate is the deterministic engine's and is not expressible as a role.
    role          TEXT        NOT NULL DEFAULT 'analyst',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    disabled_at   TIMESTAMPTZ,
    CONSTRAINT app_user_email_unique UNIQUE (email),
    CONSTRAINT app_user_role_valid   CHECK (role IN ('viewer', 'analyst', 'owner')),
    CONSTRAINT app_user_org_fk FOREIGN KEY (org_id)
        REFERENCES organization (org_id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS app_user_org_idx ON app_user (org_id);

CREATE TABLE IF NOT EXISTS user_session (
    session_id  TEXT        PRIMARY KEY,
    -- sha256 of the cookie value. The cookie itself is never stored, so a database dump
    -- does not hand anybody a live session.
    token_hash  TEXT        NOT NULL,
    user_id     TEXT        NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at  TIMESTAMPTZ NOT NULL,
    revoked_at  TIMESTAMPTZ,
    CONSTRAINT user_session_token_unique UNIQUE (token_hash),
    CONSTRAINT user_session_user_fk FOREIGN KEY (user_id)
        REFERENCES app_user (user_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS user_session_user_idx    ON user_session (user_id);
CREATE INDEX IF NOT EXISTS user_session_expires_idx ON user_session (expires_at);

-- Personal access tokens. The browser extension authenticates with one of these instead of
-- a cookie: the extension holds a credential the USER minted for themselves, so no secret
-- is bundled into the shipped code, and a bearer token is not a CSRF vector.
CREATE TABLE IF NOT EXISTS api_token (
    token_id    TEXT        PRIMARY KEY,
    token_hash  TEXT        NOT NULL,
    user_id     TEXT        NOT NULL,
    label       TEXT        NOT NULL DEFAULT '',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at  TIMESTAMPTZ,
    revoked_at  TIMESTAMPTZ,
    last_used_at TIMESTAMPTZ,
    CONSTRAINT api_token_hash_unique UNIQUE (token_hash),
    CONSTRAINT api_token_user_fk FOREIGN KEY (user_id)
        REFERENCES app_user (user_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS api_token_user_idx ON api_token (user_id);

-- System (non-financial) audit: authentication and administration events. The hash-chained
-- FINANCIAL audit log is a different table, per organisation, in migrations/org.
CREATE TABLE IF NOT EXISTS system_audit_event (
    event_id    BIGSERIAL   PRIMARY KEY,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    kind        TEXT        NOT NULL,
    user_id     TEXT,
    org_id      TEXT,
    outcome     TEXT        NOT NULL,
    detail      TEXT        NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS system_audit_kind_idx ON system_audit_event (kind, occurred_at);
CREATE INDEX IF NOT EXISTS system_audit_user_idx ON system_audit_event (user_id, occurred_at);
