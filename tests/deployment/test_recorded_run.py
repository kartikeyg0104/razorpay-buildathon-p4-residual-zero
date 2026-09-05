"""Recording a deterministic run into PostgreSQL.

The per-credit results always persisted: audit_entry carries the uniqueness, residual and
disposition the engine decided, on either backend. What was missing was the *run* — the
record that a deterministic execution happened, over which dataset, under which
configuration, and whether it finished. Without it a reader cannot tell "searched and
found nothing" from "never searched", and the dashboard was right to refuse to guess.

These tests are about that record and the safety around it. Nothing here asserts a
financial value the engine did not produce.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

PG_URL = os.environ.get("RZ_TEST_POSTGRES_URL", "")
requires_pg = pytest.mark.skipif(
    not PG_URL, reason="set RZ_TEST_POSTGRES_URL to run the PostgreSQL suite",
)

SCHEMAS = ("rz_shared_run_test", "org_runa", "org_runb")


def _drop():
    import psycopg

    with psycopg.connect(PG_URL, autocommit=True) as conn, conn.cursor() as cur:
        for schema in SCHEMAS:
            cur.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')


@pytest.fixture()
def orgs(monkeypatch):
    """Two organisations on a real PostgreSQL, each with its own schema."""
    monkeypatch.setenv("RZ_DATABASE_URL", PG_URL)
    monkeypatch.setenv("RZ_SHARED_SCHEMA", "rz_shared_run_test")
    monkeypatch.delenv("RZ_ENV", raising=False)
    _drop()
    from residual_zero.storage.engine import bootstrap_shared, bootstrap_tenant
    from residual_zero.tenancy import Tenant

    bootstrap_shared()
    a = Tenant(org_id="runa", slug="runa", db_schema="org_runa",
               dataset_kind="files", dataset_root="data/dev/rendered")
    b = Tenant(org_id="runb", slug="runb", db_schema="org_runb",
               dataset_kind="files", dataset_root="data/dev/rendered")
    for t in (a, b):
        bootstrap_tenant(t)
    yield a, b
    _drop()


def _rows(schema: str, sql: str):
    import psycopg

    with psycopg.connect(PG_URL) as conn, conn.cursor() as cur:
        cur.execute(f'SET search_path TO "{schema}"')
        cur.execute(sql)
        return cur.fetchall()


# ---------------------------------------------------------------- 1-4: create and retrieve


@requires_pg
def test_a_run_is_created_and_completed_in_postgres(orgs):
    from residual_zero.runner import record_run

    a, _b = orgs
    result = record_run(tenant=a, split="dev", limit=6)

    assert result.engine_ok, "the engine did not finish"
    assert result.persisted, "the run was not recorded"
    assert result.recorded
    assert result.backend == "postgres", "a production-shaped run must not use SQLite"
    assert result.n_processed == 6

    rows = _rows("org_runa", "SELECT run_id, status, n_processed FROM reconciliation_run")
    assert rows == [(result.run_id, "COMPLETED", 6)]


@requires_pg
def test_per_credit_deterministic_results_are_persisted(orgs):
    from residual_zero.runner import record_run

    a, _b = orgs
    result = record_run(tenant=a, split="dev", limit=6)

    linked = _rows("org_runa", "SELECT COUNT(*), COUNT(run_id) FROM audit_entry")
    assert linked == [(6, 6)], "every entry must name the run that produced it"
    owned = _rows(
        "org_runa", f"SELECT COUNT(*) FROM audit_entry WHERE run_id = '{result.run_id}'"
    )
    assert owned == [(6,)]


@requires_pg
def test_the_run_can_be_retrieved_after_the_writing_process_is_gone(orgs):
    """A fresh connection, as a later request or a restarted container would make."""
    from residual_zero.audit import latest_completed_run, open_audit
    from residual_zero.runner import record_run
    from residual_zero.tenancy import use_tenant

    a, _b = orgs
    result = record_run(tenant=a, split="dev", limit=5)

    with use_tenant(a):
        conn = open_audit()
        try:
            found = latest_completed_run(conn)
        finally:
            conn.close()
    assert found is not None
    assert found["run_id"] == result.run_id
    assert found["status"] == "COMPLETED"
    assert found["n_processed"] == 5


# ---------------------------------------------------------------- 5-9: the recorded states


@requires_pg
def test_search_uniqueness_and_ambiguity_come_from_the_run(orgs):
    """The states the dashboard reports must be the engine's, not a default."""
    from residual_zero.runner import record_run

    a, _b = orgs
    record_run(tenant=a, split="dev", limit=12)

    buckets = dict(_rows(
        "org_runa",
        "SELECT payload::jsonb ->> 'uniqueness' AS u, COUNT(*) FROM audit_entry GROUP BY u",
    ))
    assert buckets, "no uniqueness state was persisted"
    assert set(buckets) <= {"UNIQUE", "AMBIGUOUS", "NONE_FOUND", "BUDGET_EXCEEDED"}
    assert sum(buckets.values()) == 12, "every processed credit needs a uniqueness state"


@requires_pg
def test_the_dashboard_stops_saying_not_run_once_a_run_exists(orgs):
    """The truthful "not evaluated" state must flip on real data, and only on real data."""
    from residual_zero.console import app as console_app
    from residual_zero.runner import record_run
    from residual_zero.tenancy import use_tenant

    a, b = orgs
    console_app.reset_caches()
    with use_tenant(b):
        assert console_app._db() is None, "an unrun organisation must read as no ledger"

    record_run(tenant=a, split="dev", limit=8)
    console_app.reset_caches()
    with use_tenant(a):
        conn = console_app._db()
        assert conn is not None, "a recorded run must resurface the ledger"
        try:
            audits = console_app._load_audits(conn)
        finally:
            conn.close()
    assert len(audits) == 8
    # ...and org B, which never ran, still reads as not evaluated.
    with use_tenant(b):
        assert console_app._db() is None


# ---------------------------------------------------------------- 10-12: audit, rollback, idempotency


@requires_pg
def test_the_audit_chain_is_persisted_and_verifies(orgs):
    from residual_zero.audit import open_audit, verify_chain
    from residual_zero.runner import record_run
    from residual_zero.tenancy import use_tenant

    a, _b = orgs
    record_run(tenant=a, split="dev", limit=7)
    with use_tenant(a):
        conn = open_audit()
        try:
            ok, broken, head = verify_chain(conn)
        finally:
            conn.close()
    assert ok, f"chain broken at {broken}"
    assert head and head != "0" * 64


@requires_pg
def test_a_failed_run_leaves_no_results_behind(orgs):
    """A partial run is not a smaller run. Counting its rows would report a search."""
    import residual_zero.runner as runner_module
    from residual_zero.runner import record_run

    a, _b = orgs

    def explode(*_args, **_kwargs):
        raise RuntimeError("engine exploded")

    original = runner_module.run_split if hasattr(runner_module, "run_split") else None
    import residual_zero.orchestrator as orch

    real = orch.run_split
    orch.run_split = explode
    try:
        with pytest.raises(RuntimeError, match="engine exploded"):
            record_run(tenant=a, split="dev", limit=4)
    finally:
        orch.run_split = real
        if original is not None:  # pragma: no cover - defensive
            runner_module.run_split = original

    runs = _rows("org_runa", "SELECT status FROM reconciliation_run")
    assert runs == [("FAILED",)], "a failed run must be visible as failed, not absent"
    assert _rows("org_runa", "SELECT COUNT(*) FROM audit_entry") == [(0,)]

    from residual_zero.audit import latest_completed_run, open_audit
    from residual_zero.tenancy import use_tenant

    with use_tenant(a):
        conn = open_audit()
        try:
            assert latest_completed_run(conn) is None, "a failed run must not read as a result"
        finally:
            conn.close()


@requires_pg
def test_rerunning_the_same_dataset_does_not_duplicate_results(orgs):
    from residual_zero.runner import record_run

    a, _b = orgs
    first = record_run(tenant=a, split="dev", limit=6)
    second = record_run(tenant=a, split="dev", limit=6)

    assert second.run_id == first.run_id, "identity must not depend on the clock"
    assert second.reused, "the second execution must reuse the recorded run"
    assert _rows("org_runa", "SELECT COUNT(*) FROM reconciliation_run") == [(1,)]
    assert _rows("org_runa", "SELECT COUNT(*) FROM audit_entry") == [(6,)]


@requires_pg
def test_a_different_dataset_or_configuration_is_a_different_run(orgs):
    """Identity is the inputs. A different limit is a different execution."""
    from residual_zero.runner import record_run

    a, _b = orgs
    first = record_run(tenant=a, split="dev", limit=4)
    second = record_run(tenant=a, split="dev", limit=9)
    assert first.run_id != second.run_id
    assert _rows("org_runa", "SELECT COUNT(*) FROM reconciliation_run") == [(2,)]


# ---------------------------------------------------------------- 13: isolation


@requires_pg
def test_one_organisations_run_is_invisible_to_another(orgs):
    from residual_zero.runner import record_run

    a, b = orgs
    result_a = record_run(tenant=a, split="dev", limit=5)

    assert _rows("org_runb", "SELECT COUNT(*) FROM reconciliation_run") == [(0,)]
    assert _rows("org_runb", "SELECT COUNT(*) FROM audit_entry") == [(0,)]

    result_b = record_run(tenant=b, split="dev", limit=5)
    a_runs = _rows("org_runa", "SELECT run_id FROM reconciliation_run")
    b_runs = _rows("org_runb", "SELECT run_id FROM reconciliation_run")
    assert a_runs == [(result_a.run_id,)]
    assert b_runs == [(result_b.run_id,)]
    assert _rows("org_runa", "SELECT COUNT(*) FROM audit_entry") == [(5,)]
    assert _rows("org_runb", "SELECT COUNT(*) FROM audit_entry") == [(5,)]


@requires_pg
def test_a_run_reader_cannot_reach_across_organisations(orgs):
    """The reader is scoped by search_path, not by remembering a WHERE clause."""
    from residual_zero.audit import latest_completed_run, open_audit
    from residual_zero.runner import record_run
    from residual_zero.tenancy import use_tenant

    a, b = orgs
    record_run(tenant=a, split="dev", limit=5)

    with use_tenant(b):
        conn = open_audit()
        try:
            assert latest_completed_run(conn) is None, "org B saw org A's run"
        finally:
            conn.close()


# ---------------------------------------------------------------- 14-16: backend and arithmetic


@requires_pg
def test_production_refuses_to_record_a_run_without_postgres(monkeypatch):
    """No silent fallback: a production run into a local file is not a run."""
    from residual_zero.runner import PersistenceError, require_production_database

    monkeypatch.setenv("RZ_ENV", "production")
    monkeypatch.setenv("RZ_AUTH_MODE", "required")
    monkeypatch.setenv("RZ_SESSION_SECRET", "s" * 40)
    monkeypatch.setenv("RZ_PUBLIC_ORIGIN", "https://rz.example")
    monkeypatch.delenv("RZ_DATABASE_URL", raising=False)

    with pytest.raises(PersistenceError, match="PostgreSQL"):
        require_production_database()


@requires_pg
def test_production_with_postgres_is_allowed(monkeypatch):
    from residual_zero.runner import require_production_database

    monkeypatch.setenv("RZ_ENV", "production")
    monkeypatch.setenv("RZ_AUTH_MODE", "required")
    monkeypatch.setenv("RZ_SESSION_SECRET", "s" * 40)
    monkeypatch.setenv("RZ_PUBLIC_ORIGIN", "https://rz.example")
    monkeypatch.setenv("RZ_DATABASE_URL", PG_URL)
    require_production_database()  # must not raise


@requires_pg
def test_paise_survive_the_roundtrip_exactly(orgs):
    """Integers in, the same integers out. No float ever touches the value."""
    import json

    from residual_zero.runner import record_run

    a, _b = orgs
    record_run(tenant=a, split="dev", limit=10)
    rows = _rows("org_runa", "SELECT payload FROM audit_entry ORDER BY seq")
    for (payload,) in rows:
        value = json.loads(payload)["residual_paise"]
        assert isinstance(value, int), f"residual_paise came back as {type(value).__name__}"
        assert value == int(value)


# ---------------------------------------------------------------- 17: the local path


def test_the_sqlite_development_path_still_records_a_run(tmp_path, monkeypatch):
    """SQLite stays supported, and the run record works there too."""
    monkeypatch.delenv("RZ_DATABASE_URL", raising=False)
    monkeypatch.delenv("RZ_ENV", raising=False)
    monkeypatch.setenv("RZ_TENANT_ROOT", str(tmp_path / "tenants"))
    from residual_zero.audit import latest_completed_run, open_audit
    from residual_zero.runner import record_run
    from residual_zero.tenancy import Tenant, use_tenant

    local = Tenant(org_id="local", slug="local", db_schema="org_local",
                   dataset_kind="files", dataset_root="data/dev/rendered")
    result = record_run(tenant=local, split="dev", limit=3)
    assert result.backend == "sqlite"
    assert result.recorded
    with use_tenant(local):
        conn = open_audit()
        try:
            found = latest_completed_run(conn)
        finally:
            conn.close()
    assert found is not None and found["run_id"] == result.run_id
    # REGRESSION: the run must live in *this organisation's* ledger. An explicit path wins
    # in _sqlite_path, so a placeholder path sent the run to that file instead — and a test
    # that read back through the same placeholder called it a pass.
    assert local.sqlite_path.is_file(), f"{local.sqlite_path} was never written"
    assert not Path("unused").exists(), "a placeholder ledger path was used"
    import sqlite3

    conn = sqlite3.connect(str(local.sqlite_path))
    try:
        rows = list(conn.execute("SELECT run_id, status FROM reconciliation_run"))
    finally:
        conn.close()
    assert rows == [(result.run_id, "COMPLETED")]


# ---------------------------------------------------------------- 18-20: safety


@requires_pg
def test_a_recorded_run_clears_nothing(orgs):
    """CLEARED stays deterministically gated. Recording a run is not a clearance."""
    from residual_zero.runner import record_run

    a, _b = orgs
    record_run(tenant=a, split="dev", limit=20)

    assert _rows("org_runa", "SELECT COUNT(*) FROM reconciliation WHERE disposition = 'CLEARED'") == [(0,)]
    import json

    for (payload,) in _rows("org_runa", "SELECT payload FROM audit_entry"):
        assert json.loads(payload)["disposition"] != "CLEARED"


@requires_pg
def test_the_ai_tables_are_untouched_by_a_run(orgs):
    """A deterministic run writes deterministic tables. AI events stay separate."""
    from residual_zero.runner import record_run

    a, _b = orgs
    record_run(tenant=a, split="dev", limit=6)
    assert _rows("org_runa", "SELECT COUNT(*) FROM ai_investigation") == [(0,)]


@requires_pg
def test_an_organisation_without_a_run_keeps_its_existing_metrics(orgs):
    """Recording a run for A must not change what B reports."""
    from residual_zero.console import app as console_app
    from residual_zero.runner import record_run
    from residual_zero.tenancy import use_tenant

    a, b = orgs
    console_app.reset_caches()
    with use_tenant(b):
        before = console_app._split()
        n_before = len(before[1]) if before is not None else 0

    record_run(tenant=a, split="dev", limit=10)
    console_app.reset_caches()
    with use_tenant(b):
        after = console_app._split()
        n_after = len(after[1]) if after is not None else 0
        assert console_app._db() is None, "B gained a ledger it never ran"
    assert n_after == n_before


@requires_pg
def test_an_organisation_created_before_the_run_table_can_still_record(orgs):
    """REGRESSION: the first production run died with UndefinedTable.

    run_split bootstraps the tenant through init_db, but the idempotency check reads
    reconciliation_run before that ever happens. An organisation created before the table
    existed — the normal state of anything already deployed — failed on the first query.
    A run must bring its own schema up to date before reading or writing one.
    """
    import psycopg

    from residual_zero.runner import record_run

    a, _b = orgs
    # Wind org A back to the schema it would have had before the run table shipped.
    with psycopg.connect(PG_URL, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute('SET search_path TO "org_runa"')
        cur.execute("DROP TABLE IF EXISTS reconciliation_run CASCADE")
        cur.execute("ALTER TABLE audit_entry DROP COLUMN IF EXISTS run_id")
        cur.execute("DELETE FROM schema_migration WHERE version = '0002_run'")

    assert _rows(
        "org_runa",
        "SELECT COUNT(*) FROM information_schema.tables "
        "WHERE table_schema = 'org_runa' AND table_name = 'reconciliation_run'",
    ) == [(0,)], "the table should be gone for this test to mean anything"

    result = record_run(tenant=a, split="dev", limit=4)
    assert result.recorded
    assert _rows("org_runa", "SELECT status FROM reconciliation_run") == [("COMPLETED",)]


def test_production_without_postgres_writes_no_local_database(tmp_path, monkeypatch, capsys):
    """REGRESSION: it refused, but only after creating the database it must never create.

    require_production_database ran inside record_run, and the CLI resolved the
    organisation first. Opening the identity store under a production environment with no
    PostgreSQL created a local SQLite identity database, then reported "unknown
    organisation" — a loud failure for the wrong reason, with the forbidden file already
    on disk. Found by running the real image with RZ_DATABASE_URL unset.
    """
    from residual_zero.cli import main

    monkeypatch.setenv("RZ_ENV", "production")
    monkeypatch.setenv("RZ_AUTH_MODE", "required")
    monkeypatch.setenv("RZ_SESSION_SECRET", "s" * 40)
    monkeypatch.setenv("RZ_PUBLIC_ORIGIN", "https://rz.example")
    monkeypatch.setenv("RZ_TENANT_ROOT", str(tmp_path / "tenants"))
    monkeypatch.delenv("RZ_DATABASE_URL", raising=False)
    monkeypatch.delenv("RZ_IDENTITY_DB", raising=False)

    code = main(["run", "--org", "anything", "--limit", "1"])
    assert code == 4, "a production run without PostgreSQL must fail with the persistence code"
    assert "PostgreSQL" in capsys.readouterr().err

    created = list(tmp_path.rglob("*.sqlite"))
    assert created == [], f"a local production database was created: {created}"


@requires_pg
def test_entries_from_a_run_that_never_completed_are_not_read(orgs):
    """REGRESSION: the production desk reported 479 posted over a 248-credit corpus.

    A run died mid-way and its own cleanup failed — the read-only leak — so its entries
    stayed. A later completed run's entries were then read alongside them and the totals
    were simply added together. A partial run is not a smaller run.

    The rows are excluded on read, never deleted: audit_entry is a hash chain and removing
    rows from the middle of it would break the thing it exists to prove.
    """
    import psycopg

    from residual_zero.console import app as console_app
    from residual_zero.runner import record_run
    from residual_zero.tenancy import use_tenant

    a, _b = orgs
    result = record_run(tenant=a, split="dev", limit=6)

    # Forge the wreckage of a run whose cleanup failed: a FAILED row and its entries.
    with psycopg.connect(PG_URL, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute('SET search_path TO "org_runa"')
        cur.execute(
            "INSERT INTO reconciliation_run (run_id, org_id, split, dataset_root, "
            "dataset_digest, config_digest, engine_version, status) "
            "VALUES ('run_wreck', 'runa', 'dev', 'x', 'x', 'x', '0', 'FAILED')"
        )
        for seq in range(900, 905):
            cur.execute(
                "INSERT INTO audit_entry (seq, payload, metrics, prev_hash, entry_hash, run_id) "
                "VALUES (%s, %s, '{}', %s, %s, 'run_wreck')",
                (seq, '{"bank_credit_id": "wreck_%d", "uniqueness": "AMBIGUOUS"}' % seq,
                 f"p{seq}", f"h{seq}"),
            )

    total = _rows("org_runa", "SELECT COUNT(*) FROM audit_entry")[0][0]
    assert total == 11, "the fixture should have both runs' rows on disk"

    console_app.reset_caches()
    with use_tenant(a):
        conn = console_app._db()
        assert conn is not None
        try:
            audits = console_app._load_audits(conn)
        finally:
            conn.close()

    assert len(audits) == 6, f"read {len(audits)} entries; the failed run leaked in"
    assert not any(k.startswith("wreck_") for k in audits)
    # ...and the rows are still there, because the chain needs them.
    assert _rows("org_runa", "SELECT COUNT(*) FROM audit_entry")[0][0] == 11
    assert result.n_processed == 6
