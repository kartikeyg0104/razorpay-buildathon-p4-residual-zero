-- Run accounting: four numbers that were one.
--
-- `n_processed` held whatever the engine loop counted during a single invocation, which
-- is not coverage. Per-credit idempotency means a retry legitimately skips work already
-- persisted, so an interrupted-then-retried run reported 231 while 248 credits carried
-- results. The number was right about what it measured and wrong about what its name
-- implied, sitting next to an `n_credits` that was never populated at all.
--
-- The four are genuinely different questions:
--
--   n_credits    how many credits the run was asked to cover (the dataset, capped by
--                any --limit). The denominator.
--   n_computed   how many this invocation actually computed. Invocation-local by
--                definition, and renamed so it cannot be read as coverage.
--   n_reused     how many were already persisted and correctly skipped rather than
--                recomputed. Evidence that idempotency did its job.
--   n_persisted  how many credits carry a persisted result for this run. Coverage.
--                Derived by counting rows in audit_entry, never accumulated in Python:
--                a counter can drift from the rows, a COUNT cannot.
--
-- Completeness is n_persisted = n_credits, and nothing else. A run that finished its
-- loop without covering the dataset is PARTIAL, which is a real outcome and not a
-- failure: its results are genuine and a retry completes it.

ALTER TABLE reconciliation_run RENAME COLUMN n_processed TO n_computed;

ALTER TABLE reconciliation_run ADD COLUMN IF NOT EXISTS n_reused    INTEGER NOT NULL DEFAULT 0;
ALTER TABLE reconciliation_run ADD COLUMN IF NOT EXISTS n_persisted INTEGER NOT NULL DEFAULT 0;

-- PARTIAL joins the vocabulary. A reader that treats it as COMPLETED resurrects exactly
-- the bug this migration exists to fix.
ALTER TABLE reconciliation_run DROP CONSTRAINT IF EXISTS reconciliation_run_status_valid;
ALTER TABLE reconciliation_run ADD CONSTRAINT reconciliation_run_status_valid
    CHECK (status IN ('RUNNING', 'COMPLETED', 'PARTIAL', 'FAILED'));

ALTER TABLE reconciliation_run DROP CONSTRAINT IF EXISTS reconciliation_run_counts_sane;
ALTER TABLE reconciliation_run ADD CONSTRAINT reconciliation_run_counts_sane
    CHECK (n_credits >= 0 AND n_computed >= 0 AND n_reused >= 0 AND n_persisted >= 0);

-- COMPLETED is a claim about coverage, so the database refuses to store one that is not
-- true. This is the same move as reconciliation_cleared_requires_gate: the invariant is
-- restated where it cannot be forgotten by a caller.
ALTER TABLE reconciliation_run DROP CONSTRAINT IF EXISTS reconciliation_run_completed_is_covered;
ALTER TABLE reconciliation_run ADD CONSTRAINT reconciliation_run_completed_is_covered
    CHECK (status <> 'COMPLETED' OR n_persisted = n_credits);
