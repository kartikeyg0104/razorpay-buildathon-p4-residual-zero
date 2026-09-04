"""The two-backend storage layer: translation, isolation, migrations, concurrency.

The SQL in this codebase is written in one dialect and translated for PostgreSQL, rather
than rewritten at ~60 call sites. That is a deliberate trade — a smaller diff through
financial code, at the cost of needing the translator to be exactly right. These tests are
that cost being paid.

The PostgreSQL half runs only when ``RZ_TEST_POSTGRES_URL`` names a server, so a clone with
no database still runs the whole suite.
"""

from __future__ import annotations

import os
import sqlite3

import pytest

from residual_zero.storage.config import (
    Backend,
    StorageConfigError,
    parse_database_url,
)
from residual_zero.storage.dialect import (
    PRIMARY_KEYS,
    UnsupportedStatement,
    scan,
    split_script,
    translate,
)

PG_URL = os.environ.get("RZ_TEST_POSTGRES_URL", "")
requires_pg = pytest.mark.skipif(
    not PG_URL, reason="set RZ_TEST_POSTGRES_URL to run the PostgreSQL suite",
)


def _cleared_decomposition(credit_id: str, members: tuple[str, ...]):
    """A gate-passing decomposition: residual 0, UNIQUE, FULL pool.

    Built by hand rather than solved, because what is under test is the storage path, not
    the solver — and the values here are exactly the ones the gate requires, so the write
    is the legitimate case.
    """
    from residual_zero.models import (
        Decomposition, PoolScope, ProofLine, ProofRecord, Regime, Uniqueness,
    )

    proof = ProofRecord(
        bank_credit_id=credit_id,
        lines=(ProofLine(label="PAYMENT", detail="x", amount_paise=100,
                         member_ids=members, derived_from="LEDGER"),),
        computed_total_paise=100,
        residual_paise=0,
        regime=Regime.A_DECLARED,
        uniqueness=Uniqueness.UNIQUE,
        alternate_count=1,
        pool_size=len(members),
        pool_scope=PoolScope.FULL,
        rate_config_digest="ab" * 32,
    )
    return Decomposition(
        bank_credit_id=credit_id,
        member_ids=tuple(sorted(members)),
        claimed_total_paise=100,
        residual_paise=0,
        regime=Regime.A_DECLARED,
        uniqueness=Uniqueness.UNIQUE,
        alternate_count=1,
        pool_scope=PoolScope.FULL,
        ordering_score=1.0,
        proof=proof,
    )


# ---------------------------------------------------------------- URL parsing


@pytest.mark.parametrize("url,backend", [
    (None, Backend.SQLITE),
    ("", Backend.SQLITE),
    ("   ", Backend.SQLITE),
    ("sqlite:///x.db", Backend.SQLITE),
    ("postgres://u@h/db", Backend.POSTGRES),
    ("postgresql://u@h/db", Backend.POSTGRES),
    ("postgresql+psycopg://u@h/db", Backend.POSTGRES),
])
def test_a_url_resolves_to_the_right_backend(url, backend):
    assert parse_database_url(url).backend is backend


def test_an_unknown_scheme_is_an_error_not_a_silent_downgrade():
    """A typo in production must stop the process, not quietly use a local file."""
    for bad in ("mysql://h/db", "http://h/db", "redis://h", "postgres//h/db"):
        with pytest.raises(StorageConfigError):
            parse_database_url(bad)


def test_the_password_is_never_rendered():
    config = parse_database_url("postgresql://user:sup3rs3cret@host:5432/db?sslmode=require")
    rendered = config.safe_dsn()
    assert "sup3rs3cret" not in rendered
    assert "user" in rendered and "host" in rendered
    assert rendered == "postgresql://user:***@host:5432/db"


# ---------------------------------------------------------------- translation


def test_placeholders_are_translated_outside_string_literals():
    assert translate("SELECT a FROM t WHERE b = ?") == "SELECT a FROM t WHERE b = %s"
    # A ? inside a literal is data, not a placeholder.
    assert translate("SELECT a FROM t WHERE b = 'why?' AND c = ?") == (
        "SELECT a FROM t WHERE b = 'why?' AND c = %s"
    )


def test_a_semicolon_in_a_comment_does_not_end_a_statement():
    """This truncated a migration mid-CHECK-constraint the first time it was applied."""
    script = """
    -- a comment with ; in it
    CREATE TABLE a (x TEXT DEFAULT ';');
    /* block ; comment */
    CREATE TABLE b (y INT);
    """
    statements = split_script(script)
    assert len(statements) == 2
    assert statements[0].count("CREATE TABLE") == 1
    assert "CREATE TABLE b" in statements[1]


def test_a_question_mark_in_a_comment_is_not_a_placeholder():
    assert translate("SELECT a FROM t -- is ? a placeholder", has_params=False) == (
        "SELECT a FROM t -- is ? a placeholder"
    )


def test_percent_is_escaped_only_when_parameters_are_passed():
    """psycopg interpolates only when parameters are supplied."""
    assert translate("SELECT COUNT(*) FROM t", has_params=False) == "SELECT COUNT(*) FROM t"
    assert "%%" in translate("SELECT a FROM t WHERE b LIKE 'x%' AND c = ?", has_params=True)


def test_upsert_is_translated_using_the_declared_primary_key():
    out = translate(
        "INSERT OR REPLACE INTO exception_work "
        "(bank_credit_id, assignee, note, status) VALUES (?, ?, ?, ?)"
    )
    assert out.startswith("INSERT INTO exception_work")
    assert "ON CONFLICT (bank_credit_id) DO UPDATE SET" in out
    assert "assignee = EXCLUDED.assignee" in out
    # The key column must not be in the SET list.
    assert "bank_credit_id = EXCLUDED" not in out


def test_an_upsert_whose_columns_are_all_key_becomes_do_nothing():
    out = translate(
        "INSERT OR REPLACE INTO decomposition_member (bank_credit_id, item_id) VALUES (?, ?)"
    )
    assert "ON CONFLICT (bank_credit_id, item_id) DO NOTHING" in out


def test_insert_or_ignore_becomes_do_nothing():
    out = translate("INSERT OR IGNORE INTO stream_pool(item_id, occurred_on) VALUES (?,?)")
    assert out.endswith("ON CONFLICT DO NOTHING")


def test_an_upsert_on_an_undeclared_table_refuses_rather_than_guessing():
    """Guessing which columns identify a financial row is not an acceptable failure mode."""
    with pytest.raises(UnsupportedStatement):
        translate("INSERT OR REPLACE INTO not_a_declared_table (a, b) VALUES (?, ?)")


def test_pragma_is_skipped():
    assert translate("PRAGMA journal_mode=WAL") is None
    assert translate("PRAGMA query_only = ON") is None


def test_json_extract_is_translated():
    """SQLite-only function used by two audit-trail queries."""
    out = translate(
        "SELECT payload FROM audit_entry "
        "WHERE json_extract(payload, '$.bank_credit_id') = ? ORDER BY seq"
    )
    assert "json_extract" not in out
    assert "(payload::jsonb ->> 'bank_credit_id') = %s" in out


def test_a_nested_json_path_refuses_rather_than_approximating():
    with pytest.raises(UnsupportedStatement):
        translate("SELECT json_extract(payload, '$.a.b') FROM audit_entry")


def test_every_upsert_target_in_the_source_has_a_declared_primary_key():
    """A new INSERT OR REPLACE must come with the columns that identify its row."""
    import re
    from pathlib import Path

    missing = []
    for path in Path("src/residual_zero").rglob("*.py"):
        if path.name == "dialect.py":
            # The translator's own docstring documents the syntax it rewrites.
            continue
        for match in re.finditer(
            r"INSERT OR REPLACE INTO\s+([A-Za-z_][A-Za-z0-9_]*)",
            path.read_text(encoding="utf-8"), re.IGNORECASE,
        ):
            if match.group(1) not in PRIMARY_KEYS:
                missing.append(f"{path}: {match.group(1)}")
    assert not missing, missing


def test_the_scanner_labels_code_strings_and_comments():
    runs = scan("SELECT 'a' -- c\nFROM t")
    kinds = {kind for _text, kind in runs}
    assert kinds == {"code", "string", "comment"}


# ---------------------------------------------------------------- SQLite isolation


def test_two_sqlite_tenants_use_different_files_and_cannot_see_each_other(tmp_path, monkeypatch):
    monkeypatch.setenv("RZ_TENANT_ROOT", str(tmp_path))
    monkeypatch.delenv("RZ_DATABASE_URL", raising=False)
    from residual_zero.db import open_readonly
    from residual_zero.exceptions import open_exceptions, write_exception
    from residual_zero.models import ExceptionClass
    from residual_zero.storage.engine import bootstrap_tenant
    from residual_zero.tenancy import Tenant, use_tenant

    one = Tenant(org_id="one", slug="one", db_schema="org_one")
    two = Tenant(org_id="two", slug="two", db_schema="org_two")
    for tenant in (one, two):
        bootstrap_tenant(tenant)

    with use_tenant(one):
        conn = open_exceptions(None)
        try:
            write_exception(conn, "crd_only_in_one", ExceptionClass.MISSING_RECORD)
        finally:
            conn.close()

    with use_tenant(two):
        conn = open_readonly()
        try:
            assert list(conn.execute("SELECT * FROM exception")) == []
        finally:
            conn.close()

    with use_tenant(one):
        conn = open_readonly()
        try:
            rows = list(conn.execute("SELECT bank_credit_id FROM exception"))
        finally:
            conn.close()
    assert rows == [("crd_only_in_one",)]
    assert one.sqlite_path != two.sqlite_path
    assert one.sqlite_path.is_file() and two.sqlite_path.is_file()


def test_a_sqlite_readonly_connection_refuses_a_write(tmp_path, monkeypatch):
    monkeypatch.setenv("RZ_TENANT_ROOT", str(tmp_path))
    monkeypatch.delenv("RZ_DATABASE_URL", raising=False)
    from residual_zero.db import open_readonly
    from residual_zero.storage.engine import bootstrap_tenant
    from residual_zero.tenancy import Tenant, use_tenant

    tenant = Tenant(org_id="ro", slug="ro", db_schema="org_ro")
    bootstrap_tenant(tenant)
    with use_tenant(tenant):
        conn = open_readonly()
        try:
            with pytest.raises(sqlite3.OperationalError):
                conn.execute(
                    "INSERT INTO exception (bank_credit_id, exception_class) "
                    "VALUES ('x', 'MISSING_RECORD')"
                )
        finally:
            conn.close()


def test_the_owner_check_still_gates_a_write_connection(tmp_path, monkeypatch):
    monkeypatch.setenv("RZ_TENANT_ROOT", str(tmp_path))
    monkeypatch.delenv("RZ_DATABASE_URL", raising=False)
    from residual_zero.storage.engine import open_tenant_readwrite

    with pytest.raises(ValueError, match="unknown db owner"):
        open_tenant_readwrite("not_an_owner")


def test_the_privileged_entry_points_are_only_used_by_the_three_owners():
    """Extends the original least-privilege scan to the new engine-level function name.

    `db._open_readwrite` was the only privileged entry point when that invariant was
    written. `storage.engine.open_tenant_readwrite` is now a second one, so the scan has to
    cover it too or the boundary is only half checked.
    """
    from pathlib import Path

    from residual_zero.db import TABLE_OWNERS

    allowed_modules = {"verify", "audit", "exceptions", "investigation_log"}
    importers = set()
    for path in Path("src/residual_zero").rglob("*.py"):
        if path.name in {"db.py", "engine.py"} or path.parent.name == "storage":
            continue
        text = path.read_text(encoding="utf-8")
        if "open_tenant_readwrite" in text or "_open_readwrite" in text:
            importers.add(path.parent.name if path.name == "__init__.py" else path.stem)
    # `console/app.py` and `console/extra.py` reach writes only through open_exceptions.
    assert importers <= allowed_modules, sorted(importers - allowed_modules)
    assert set(TABLE_OWNERS) == {"verify", "audit", "exceptions"}


# ---------------------------------------------------------------- PostgreSQL


@pytest.fixture()
def pg(monkeypatch):
    """A fresh set of schemas on the configured PostgreSQL server."""
    monkeypatch.setenv("RZ_DATABASE_URL", PG_URL)
    monkeypatch.setenv("RZ_SHARED_SCHEMA", "rz_shared_test")
    import psycopg

    with psycopg.connect(PG_URL, autocommit=True) as conn, conn.cursor() as cur:
        for schema in ("rz_shared_test", "org_pgone", "org_pgtwo"):
            cur.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
    from residual_zero.storage.engine import bootstrap_shared, bootstrap_tenant
    from residual_zero.tenancy import Tenant

    bootstrap_shared()
    one = Tenant(org_id="pgone", slug="pgone", db_schema="org_pgone")
    two = Tenant(org_id="pgtwo", slug="pgtwo", db_schema="org_pgtwo")
    for tenant in (one, two):
        bootstrap_tenant(tenant)
    yield one, two
    with psycopg.connect(PG_URL, autocommit=True) as conn, conn.cursor() as cur:
        for schema in ("rz_shared_test", "org_pgone", "org_pgtwo"):
            cur.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')


@requires_pg
def test_the_org_schema_has_every_table_the_app_reads(pg):
    from residual_zero.db import SCHEMA
    import re

    one, _two = pg
    import psycopg

    with psycopg.connect(PG_URL) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = %s",
            (one.db_schema,),
        )
        present = {r[0] for r in cur.fetchall()}
    sqlite_tables = set(re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", SCHEMA))
    assert sqlite_tables <= present, sorted(sqlite_tables - present)
    # Plus the production-only tables.
    for extra in ("bank_credit", "ledger_item", "settlement_line", "evidence_edge",
                  "ai_investigation", "idempotency_record", "schema_migration"):
        assert extra in present


@requires_pg
def test_migrations_are_idempotent_and_record_a_checksum(pg):
    from residual_zero.storage.engine import bootstrap_tenant
    from residual_zero.storage.migrate import pending
    from residual_zero.storage.pg import PgConnection

    one, _two = pg
    assert bootstrap_tenant(one) == [], "a second run must apply nothing"
    conn = PgConnection(PG_URL, schema=one.db_schema, readonly=True)
    try:
        assert pending(conn, "org") == []
        rows = list(conn.execute("SELECT version, checksum FROM schema_migration"))
    finally:
        conn.close()
    assert rows
    assert all(len(checksum) == 64 for _version, checksum in rows)


@requires_pg
def test_an_edited_applied_migration_is_refused(pg):
    """History must not change silently under a database that already ran it."""
    from residual_zero.storage.migrate import (
        Migration,
        MigrationChecksumMismatch,
        apply_migrations,
    )
    from residual_zero.storage.pg import PgConnection
    import residual_zero.storage.migrate as migrate_module

    one, _two = pg
    real = migrate_module.load_migrations

    def tampered(kind: str):
        return tuple(
            Migration(version=m.version, path=m.path, sql=m.sql + "\n-- edited\n")
            for m in real(kind)
        )

    migrate_module.load_migrations = tampered
    try:
        conn = PgConnection(PG_URL, schema=one.db_schema)
        try:
            with pytest.raises(MigrationChecksumMismatch):
                apply_migrations(conn, "org")
        finally:
            conn.close()
    finally:
        migrate_module.load_migrations = real


@requires_pg
def test_a_tenant_connection_cannot_name_another_tenants_table(pg):
    """search_path is the isolation, and there is no `public` fallback to fall through to."""
    from residual_zero.exceptions import open_exceptions, write_exception
    from residual_zero.models import ExceptionClass
    from residual_zero.db import open_readonly
    from residual_zero.tenancy import use_tenant

    one, two = pg
    with use_tenant(one):
        conn = open_exceptions(None)
        try:
            write_exception(conn, "crd_only_in_one", ExceptionClass.MISSING_RECORD)
        finally:
            conn.close()
    with use_tenant(two):
        conn = open_readonly()
        try:
            assert list(conn.execute("SELECT bank_credit_id FROM exception")) == []
        finally:
            conn.close()
    with use_tenant(one):
        conn = open_readonly()
        try:
            assert list(conn.execute("SELECT bank_credit_id FROM exception")) == [
                ("crd_only_in_one",)
            ]
        finally:
            conn.close()


@requires_pg
def test_a_postgres_readonly_connection_is_refused_by_the_server(pg):
    from residual_zero.db import open_readonly
    from residual_zero.tenancy import use_tenant

    one, _two = pg
    with use_tenant(one):
        conn = open_readonly()
        try:
            with pytest.raises(Exception, match="read-only"):
                conn.execute(
                    "INSERT INTO exception (bank_credit_id, exception_class) "
                    "VALUES ('x', 'MISSING_RECORD')"
                )
        finally:
            try:
                conn.close()
            except Exception:
                pass


@requires_pg
@pytest.mark.parametrize("sql,why", [
    ("INSERT INTO reconciliation VALUES ('c',100,50,'UNIQUE','FULL','CLEARED')",
     "CLEARED with a non-zero residual"),
    ("INSERT INTO reconciliation VALUES ('c',100,0,'AMBIGUOUS','FULL','CLEARED')",
     "CLEARED while AMBIGUOUS"),
    ("INSERT INTO reconciliation VALUES ('c',100,0,'NONE_FOUND','FULL','CLEARED')",
     "CLEARED while NONE_FOUND"),
    ("INSERT INTO reconciliation VALUES ('c',100,0,'BUDGET_EXCEEDED','FULL','CLEARED')",
     "CLEARED while BUDGET_EXCEEDED"),
    ("INSERT INTO reconciliation VALUES ('c',100,0,'UNIQUE','REDUCED','CLEARED')",
     "CLEARED on a REDUCED pool"),
    ("INSERT INTO reconciliation VALUES ('c',100,0,'UNIQUE','FULL','APPROVED')",
     "an invented disposition"),
    ("INSERT INTO exception_resolution (bank_credit_id, resolution) VALUES ('c','cleared')",
     "a human resolution of 'cleared'"),
    ("INSERT INTO ai_investigation (investigation_id, outcome) VALUES ('i','CLEARED')",
     "an AI investigation claiming CLEARED"),
    ("INSERT INTO bank_credit (credit_id, amount_paise, value_date, account_id, currency, "
     "narration_raise, narration_norm) VALUES ('c',-1,'2025-01-01','a','INR','n','n')",
     "a negative bank credit"),
])
def test_the_database_refuses_an_illegal_financial_state(pg, sql, why):
    """The auto-clear gate restated as storage constraints.

    The engine already enforces this. The constraints mean a bug, a migration or a
    hand-written UPDATE cannot persist a clear that never passed the gate.
    """
    import psycopg

    one, _two = pg
    with psycopg.connect(PG_URL, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(f'SET search_path TO "{one.db_schema}"')
        with pytest.raises(psycopg.Error):
            cur.execute(sql)


@requires_pg
def test_a_legitimate_clear_is_accepted(pg):
    """The constraints must not be so tight that a real clear cannot be stored."""
    import psycopg

    one, _two = pg
    with psycopg.connect(PG_URL, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(f'SET search_path TO "{one.db_schema}"')
        cur.execute(
            "INSERT INTO reconciliation VALUES ('crd_ok',100,0,'UNIQUE','FULL','CLEARED')"
        )
        cur.execute("SELECT disposition FROM reconciliation WHERE bank_credit_id='crd_ok'")
        assert cur.fetchone()[0] == "CLEARED"


@requires_pg
def test_concurrent_audit_appends_do_not_fork_the_chain(pg):
    """A read-modify-write over the chain head, run from many writers at once."""
    import concurrent.futures as futures

    from residual_zero.audit import append_entry, verify_chain
    from residual_zero.db import open_readonly
    from residual_zero.storage.engine import open_tenant_readwrite
    from residual_zero.tenancy import use_tenant

    one, _two = pg
    n = 24

    def append(i: int) -> str:
        with use_tenant(one):
            conn = open_tenant_readwrite("audit")
            try:
                append_entry(conn, {"bank_credit_id": f"crd_{i}"}, {"i": i})
                return "ok"
            except Exception as exc:
                return type(exc).__name__
            finally:
                conn.close()

    with futures.ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(append, range(n)))
    assert results == ["ok"] * n, results

    with use_tenant(one):
        conn = open_readonly()
        try:
            ok, broken, _head = verify_chain(conn)
            count = conn.execute("SELECT COUNT(*) FROM audit_entry").fetchone()[0]
            seqs = [r[0] for r in conn.execute("SELECT seq FROM audit_entry ORDER BY seq")]
        finally:
            conn.close()
    assert ok is True and broken is None
    assert count == n
    assert seqs == list(range(n)), "the sequence has a gap or a duplicate"


@requires_pg
def test_idempotency_is_enforced_by_the_primary_key(pg):
    import psycopg

    one, _two = pg
    with psycopg.connect(PG_URL, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(f'SET search_path TO "{one.db_schema}"')
        cur.execute(
            "INSERT INTO idempotency_record (scope, idempotency_key, request_digest) "
            "VALUES ('resolve', 'k1', 'd1')"
        )
        with pytest.raises(psycopg.errors.UniqueViolation):
            cur.execute(
                "INSERT INTO idempotency_record (scope, idempotency_key, request_digest) "
                "VALUES ('resolve', 'k1', 'd2')"
            )


@requires_pg
def test_a_second_different_clear_for_one_credit_is_refused(pg):
    """Two different explanations of one bank credit cannot both be true."""
    from residual_zero.storage.engine import open_tenant_readwrite
    from residual_zero.tenancy import use_tenant
    from residual_zero.verify import ConflictingClearError, write_cleared

    one, _two = pg
    first = _cleared_decomposition("crd_conflict", ("itm_a", "itm_b"))
    second = _cleared_decomposition("crd_conflict", ("itm_c", "itm_d"))
    with use_tenant(one):
        conn = open_tenant_readwrite("verify")
        try:
            write_cleared(conn, first)
            # The same explanation again is a no-op, which is what makes replay safe.
            write_cleared(conn, first)
            with pytest.raises(ConflictingClearError):
                write_cleared(conn, second)
        finally:
            conn.close()
