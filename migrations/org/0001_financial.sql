-- Per-organisation financial schema. Applied inside each organisation's own Postgres
-- schema, so isolation does not depend on any query remembering a WHERE clause.
--
-- Money is INTEGER PAISE everywhere, exactly as in the canonical Python model
-- (residual_zero.models, NN-1). There is no NUMERIC, no float, and no computed column: the
-- deterministic engine calculates residual and uniqueness in Python and hands this schema a
-- finished result. Nothing in this file performs financial arithmetic.

CREATE TABLE IF NOT EXISTS schema_migration (
    version     TEXT        PRIMARY KEY,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    checksum    TEXT        NOT NULL
);

-- ---------------------------------------------------------------- source financial data

-- A credit landing in the merchant's bank account: the thing to be decomposed.
CREATE TABLE IF NOT EXISTS bank_credit (
    credit_id     TEXT    PRIMARY KEY,
    amount_paise  BIGINT  NOT NULL,
    value_date    DATE    NOT NULL,
    account_id    TEXT    NOT NULL,
    currency      CHAR(3) NOT NULL,
    narration_raw TEXT    NOT NULL,
    narration_norm TEXT   NOT NULL,
    utr           TEXT,
    ingested_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Mirrors BankCredit's own validator: a credit is a positive inflow.
    CONSTRAINT bank_credit_amount_positive CHECK (amount_paise > 0),
    CONSTRAINT bank_credit_currency_upper  CHECK (currency = upper(currency))
);
CREATE INDEX IF NOT EXISTS bank_credit_account_date_idx ON bank_credit (account_id, value_date);
CREATE INDEX IF NOT EXISTS bank_credit_utr_idx          ON bank_credit (utr);

-- One line of the deduction stack: payments, refunds, chargebacks, fees, GST, withholding,
-- reserve holds and releases, adjustments and bank charges. One table, because that is the
-- canonical model's own shape (residual_zero.models.Kind) — amount_paise is SIGNED and a
-- single signed universe is exactly what lets one solver handle every kind uniformly.
-- Splitting fees/taxes/refunds into separate tables would contradict the model the
-- verifier re-derives from.
CREATE TABLE IF NOT EXISTS ledger_item (
    item_id        TEXT        PRIMARY KEY,
    kind           TEXT        NOT NULL,
    amount_paise   BIGINT      NOT NULL,
    occurred_at    TIMESTAMPTZ NOT NULL,
    account_id     TEXT        NOT NULL,
    currency       CHAR(3)     NOT NULL,
    instrument     TEXT,
    order_id       TEXT,
    parent_id      TEXT,
    narration_raw  TEXT        NOT NULL,
    narration_norm TEXT        NOT NULL,
    counterparty_raw TEXT,
    counterparty_id  TEXT,
    source         TEXT        NOT NULL,
    ingested_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- A zero-value ledger item is a defect, matching LedgerItem's validator.
    CONSTRAINT ledger_item_amount_nonzero CHECK (amount_paise <> 0),
    CONSTRAINT ledger_item_kind_valid CHECK (kind IN (
        'PAYMENT', 'REFUND', 'CHARGEBACK', 'REPRESENTMENT', 'FEE', 'TAX_GST',
        'TAX_WITHHOLDING', 'RESERVE_HOLD', 'RESERVE_RELEASE', 'ADJUSTMENT', 'BANK_CHARGE'
    )),
    CONSTRAINT ledger_item_instrument_valid CHECK (
        instrument IS NULL OR instrument IN ('CARD', 'UPI', 'NETBANKING', 'WALLET', 'EMI')
    ),
    CONSTRAINT ledger_item_source_valid CHECK (source IN (
        'SETTLEMENT_REPORT', 'INTERNAL_LEDGER', 'BANK_STATEMENT', 'API'
    ))
);
CREATE INDEX IF NOT EXISTS ledger_item_account_time_idx ON ledger_item (account_id, occurred_at);
CREATE INDEX IF NOT EXISTS ledger_item_order_idx        ON ledger_item (order_id);
CREATE INDEX IF NOT EXISTS ledger_item_parent_idx       ON ledger_item (parent_id);
CREATE INDEX IF NOT EXISTS ledger_item_kind_idx         ON ledger_item (kind);

-- The settlement report's DECLARED composition. Each row names a ledger item that already
-- exists, so this is not a second item universe — duplicating members here would break
-- conservation (see residual_zero.ingest.settlement_report).
CREATE TABLE IF NOT EXISTS settlement_line (
    credit_id     TEXT   NOT NULL,
    item_id       TEXT   NOT NULL,
    kind          TEXT   NOT NULL,
    amount_paise  BIGINT NOT NULL,
    instrument    TEXT,
    order_id      TEXT,
    settlement_id TEXT,
    PRIMARY KEY (credit_id, item_id),
    CONSTRAINT settlement_line_amount_nonzero CHECK (amount_paise <> 0)
);
CREATE INDEX IF NOT EXISTS settlement_line_credit_idx     ON settlement_line (credit_id);
CREATE INDEX IF NOT EXISTS settlement_line_item_idx       ON settlement_line (item_id);
CREATE INDEX IF NOT EXISTS settlement_line_settlement_idx ON settlement_line (settlement_id);

-- ---------------------------------------------------------------- reconciliation results

-- The authoritative outcome for one bank credit, as produced by the deterministic engine.
CREATE TABLE IF NOT EXISTS reconciliation (
    bank_credit_id      TEXT   PRIMARY KEY,
    claimed_total_paise BIGINT NOT NULL,
    residual_paise      BIGINT NOT NULL,
    uniqueness          TEXT   NOT NULL,
    pool_scope          TEXT   NOT NULL,
    disposition         TEXT   NOT NULL,
    decided_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- The closed sets from residual_zero.models. A disposition outside them cannot be
    -- stored at all, so no code path — application, migration or manual — can invent a
    -- fourth outcome.
    CONSTRAINT reconciliation_uniqueness_valid CHECK (uniqueness IN (
        'UNIQUE', 'AMBIGUOUS', 'NONE_FOUND', 'BUDGET_EXCEEDED'
    )),
    CONSTRAINT reconciliation_pool_scope_valid CHECK (pool_scope IN ('FULL', 'REDUCED')),
    CONSTRAINT reconciliation_disposition_valid CHECK (disposition IN (
        'CLEARED', 'FLAGGED', 'BUDGET_EXCEEDED'
    )),
    -- The auto-clear gate, restated as a storage constraint. CLEARED requires a zero-paise
    -- residual, UNIQUE, and a search that saw the FULL pool. The engine already enforces
    -- this (residual_zero.orchestrator, residual_zero.verify); the constraint means a bug,
    -- a migration or a hand-written UPDATE cannot persist a clear that fails the gate.
    CONSTRAINT reconciliation_cleared_requires_gate CHECK (
        disposition <> 'CLEARED'
        OR (residual_paise = 0 AND uniqueness = 'UNIQUE' AND pool_scope = 'FULL')
    )
);
CREATE INDEX IF NOT EXISTS reconciliation_disposition_idx ON reconciliation (disposition);
CREATE INDEX IF NOT EXISTS reconciliation_uniqueness_idx  ON reconciliation (uniqueness);

-- The member set of a decomposition: the candidate/member relationship.
CREATE TABLE IF NOT EXISTS decomposition_member (
    bank_credit_id TEXT NOT NULL,
    item_id        TEXT NOT NULL,
    PRIMARY KEY (bank_credit_id, item_id),
    CONSTRAINT decomposition_member_recon_fk FOREIGN KEY (bank_credit_id)
        REFERENCES reconciliation (bank_credit_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS decomposition_member_item_idx ON decomposition_member (item_id);

-- ---------------------------------------------------------------- financial audit chain

-- Hash-chained financial audit log. entry_hash = sha256(canonical_json(payload) || 0x00 ||
-- prev_hash). The chain is verified in Python (residual_zero.audit.verify_chain); this table
-- only has to store it without letting a race fork it, which is why seq is the primary key
-- and prev_hash is unique.
CREATE TABLE IF NOT EXISTS audit_entry (
    seq        BIGINT PRIMARY KEY,
    payload    TEXT   NOT NULL,
    metrics    TEXT   NOT NULL,
    prev_hash  TEXT   NOT NULL,
    entry_hash TEXT   NOT NULL,
    -- A fork would need two entries claiming the same predecessor. Both uniques make that
    -- a constraint violation rather than a silently branched chain.
    CONSTRAINT audit_entry_hash_unique      UNIQUE (entry_hash),
    CONSTRAINT audit_entry_prev_hash_unique UNIQUE (prev_hash)
);

-- ---------------------------------------------------------------- exceptions and review

CREATE TABLE IF NOT EXISTS exception (
    bank_credit_id  TEXT PRIMARY KEY,
    exception_class TEXT NOT NULL,
    raised_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT exception_class_valid CHECK (exception_class IN (
        'AMBIGUOUS_DECOMPOSITION', 'MISSING_RECORD', 'DUPLICATE_CREDIT',
        'SUSPECTED_WITHHOLDING', 'UNITEMISED_FEE', 'ROUNDING_RESIDUE',
        'CROSS_WINDOW_UNRESOLVED', 'SIGN_REVERSAL', 'ENTITY_UNRESOLVED',
        'BUDGET_EXCEEDED', 'RATE_MISMATCH', 'STRUCTURALLY_INFEASIBLE'
    ))
);
CREATE INDEX IF NOT EXISTS exception_class_idx ON exception (exception_class);

-- A human's decision on an exception. 'cleared' is deliberately absent from the allowed
-- set: recording a clear here would be a second, ungated path to a financial clear.
CREATE TABLE IF NOT EXISTS exception_resolution (
    bank_credit_id TEXT PRIMARY KEY,
    resolution     TEXT NOT NULL,
    decided_by     TEXT,
    decided_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Exactly residual_zero.console.ops_pack.RESOLUTIONS. 'cleared' is not in the set and
    -- normalise_resolution() refuses it by name, so a human note can never become a clear.
    CONSTRAINT exception_resolution_valid CHECK (resolution IN (
        'accept', 'correct', 'escalate'
    )),
    CONSTRAINT exception_resolution_exception_fk FOREIGN KEY (bank_credit_id)
        REFERENCES exception (bank_credit_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS exception_work (
    bank_credit_id TEXT NOT NULL PRIMARY KEY,
    assignee       TEXT NOT NULL DEFAULT '',
    note           TEXT NOT NULL DEFAULT '',
    status         TEXT NOT NULL DEFAULT 'open',
    updated_by     TEXT,
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Exactly residual_zero.console.ops_pack.WORK_STATUSES.
    CONSTRAINT exception_work_status_valid CHECK (status IN (
        'open', 'investigating', 'resolved', 'written_off'
    )),
    CONSTRAINT exception_work_exception_fk FOREIGN KEY (bank_credit_id)
        REFERENCES exception (bank_credit_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS exception_work_status_idx ON exception_work (status);

-- ---------------------------------------------------------------- evidence and AI

-- Evidence graph: an edge from a bank credit to the record that explains part of it, with
-- the provenance of the claim. 'derived_from' is the same discipline as ProofLine: an edge
-- that cannot name where it came from is not evidence.
CREATE TABLE IF NOT EXISTS evidence_edge (
    edge_id      BIGSERIAL PRIMARY KEY,
    credit_id    TEXT NOT NULL,
    node_kind    TEXT NOT NULL,
    node_id      TEXT NOT NULL,
    relation     TEXT NOT NULL,
    derived_from TEXT NOT NULL,
    amount_paise BIGINT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT evidence_edge_unique UNIQUE (credit_id, node_kind, node_id, relation)
);
CREATE INDEX IF NOT EXISTS evidence_edge_credit_idx ON evidence_edge (credit_id);
CREATE INDEX IF NOT EXISTS evidence_edge_node_idx   ON evidence_edge (node_kind, node_id);

-- What the model was asked, which read-only tools it ran, and what it said. This is an
-- investigation record, not a decision record: 'outcome' cannot be CLEARED, and there is no
-- column through which this table could influence reconciliation.
CREATE TABLE IF NOT EXISTS ai_investigation (
    investigation_id TEXT PRIMARY KEY,
    credit_id        TEXT,
    user_id          TEXT,
    question         TEXT NOT NULL DEFAULT '',
    tools_called     TEXT NOT NULL DEFAULT '',
    provider         TEXT NOT NULL DEFAULT '',
    model            TEXT NOT NULL DEFAULT '',
    outcome          TEXT NOT NULL DEFAULT 'ANSWERED',
    provider_error   TEXT NOT NULL DEFAULT '',
    fell_back        BOOLEAN NOT NULL DEFAULT false,
    prompt_tokens    INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    duration_ms      BIGINT  NOT NULL DEFAULT 0,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- The AI authority boundary as a storage constraint: no AI investigation row can claim
    -- to have cleared anything.
    CONSTRAINT ai_investigation_never_clears CHECK (
        outcome IN ('ANSWERED', 'INSUFFICIENT_EVIDENCE', 'PROVIDER_FAILED',
                    'BUDGET_EXCEEDED', 'REFUSED', 'TEMPLATE_FALLBACK')
    ),
    CONSTRAINT ai_investigation_tokens_nonneg CHECK (
        prompt_tokens >= 0 AND completion_tokens >= 0
    )
);
CREATE INDEX IF NOT EXISTS ai_investigation_credit_idx ON ai_investigation (credit_id);
CREATE INDEX IF NOT EXISTS ai_investigation_time_idx   ON ai_investigation (created_at);

-- ---------------------------------------------------------------- idempotency

-- Replay protection for write requests that carry an Idempotency-Key. The unique primary
-- key is the whole mechanism: a duplicate submission collides instead of writing twice.
CREATE TABLE IF NOT EXISTS idempotency_record (
    scope           TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_digest  TEXT NOT NULL,
    response_body   TEXT NOT NULL DEFAULT '',
    status_code     INTEGER NOT NULL DEFAULT 200,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (scope, idempotency_key)
);
CREATE INDEX IF NOT EXISTS idempotency_created_idx ON idempotency_record (created_at);
