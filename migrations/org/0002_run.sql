-- A recorded reconciliation run.
--
-- The per-credit deterministic results already persisted here: audit_entry carries the
-- uniqueness, residual and disposition the engine decided, and the hash chain links them.
-- What was missing was the run itself — the fact that a deterministic execution happened,
-- over which dataset, under which configuration, and whether it finished. Without that
-- there is no way to tell "searched and found nothing" from "never searched", which is
-- exactly what the dashboard could not say.
--
-- This file adds no financial arithmetic and no financial state. A run row is metadata
-- about an execution. The engine decides; this records that it ran.
--
-- Isolation is the schema, as everywhere else: this table is created inside the
-- organisation's own schema, so a run cannot be seen by another organisation without
-- crossing a search_path that is never set to more than one.

CREATE TABLE IF NOT EXISTS reconciliation_run (
    run_id          TEXT        PRIMARY KEY,
    org_id          TEXT        NOT NULL,
    split           TEXT        NOT NULL,
    dataset_root    TEXT        NOT NULL,
    dataset_digest  TEXT        NOT NULL,
    config_digest   TEXT        NOT NULL,
    engine_version  TEXT        NOT NULL,
    -- RUNNING until the engine finishes and the results are written. Only COMPLETED runs
    -- are a claim that anything was evaluated; a reader that counts RUNNING or FAILED rows
    -- would resurrect the bug this table exists to fix.
    status          TEXT        NOT NULL DEFAULT 'RUNNING',
    n_credits       INTEGER     NOT NULL DEFAULT 0,
    n_processed     INTEGER     NOT NULL DEFAULT 0,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at     TIMESTAMPTZ,
    error           TEXT        NOT NULL DEFAULT '',
    CONSTRAINT reconciliation_run_status_valid
        CHECK (status IN ('RUNNING', 'COMPLETED', 'FAILED')),
    -- Counts are populations, never money. Money stays in the paise columns of the
    -- financial tables, which this table does not touch.
    CONSTRAINT reconciliation_run_counts_sane
        CHECK (n_credits >= 0 AND n_processed >= 0)
);

CREATE INDEX IF NOT EXISTS reconciliation_run_status_idx
    ON reconciliation_run (status, started_at DESC);

-- Which run produced a given audit entry. Nullable on purpose: entries written before
-- runs were recorded are real deterministic results and are not rewritten to fit a new
-- column. NULL means "no run row recorded", not "no result".
--
-- The column sits outside the hashed payload, so entry_hash is unchanged and an existing
-- chain still verifies. Adding it does not re-hash history.
ALTER TABLE audit_entry ADD COLUMN IF NOT EXISTS run_id TEXT;

CREATE INDEX IF NOT EXISTS audit_entry_run_idx ON audit_entry (run_id);
