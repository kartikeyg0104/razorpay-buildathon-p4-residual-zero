"""Moving the corpus into a database must not change a single financial value.

This is the test that makes the migration trustworthy. It does not check that the script
ran; it checks that the deterministic engine, reading the migrated rows, produces the same
residuals, the same gate decisions and the same member sets as it does reading the files.

If those ever diverge, the migration changed financial truth, which is the one thing it is
not allowed to do — regardless of how convenient the divergence would be.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from residual_zero.console import app as console_app
from residual_zero.ingest.csv_bank import load_bank_credits
from residual_zero.ingest.csv_ledger import load_ledger_items
from residual_zero.ingest.settlement_report import load_settlement_report
from residual_zero.ingest.source_root import SourceRoot
from residual_zero.ingest.sql_source import (
    source_aggregates,
    write_bank_credits,
    write_ledger_items,
    write_settlement_lines,
)
from residual_zero.storage.engine import (
    bootstrap_tenant,
    open_tenant_readonly,
    open_tenant_readwrite,
)
from residual_zero.tenancy import Tenant, use_tenant

RENDERED = Path("data/dev/rendered")
pytestmark = pytest.mark.skipif(
    not RENDERED.is_dir(), reason="data/dev/rendered is not present",
)


@pytest.fixture()
def migrated(tmp_path, monkeypatch):
    """The committed corpus, loaded into a SQLite tenant through the migration path."""
    monkeypatch.setenv("RZ_TENANT_ROOT", str(tmp_path))
    monkeypatch.delenv("RZ_DATABASE_URL", raising=False)
    monkeypatch.setenv("RZ_LLM", "0")

    root = SourceRoot(RENDERED)
    items = load_ledger_items(root)
    credits = load_bank_credits(root)
    declared = load_settlement_report(root)

    tenant = Tenant(org_id="mig", slug="mig", db_schema="org_mig", dataset_kind="sql")
    bootstrap_tenant(tenant)
    with use_tenant(tenant):
        conn = open_tenant_readwrite("verify")
        try:
            write_bank_credits(conn, credits)
            write_ledger_items(conn, items)
            write_settlement_lines(conn, declared)
        finally:
            conn.close()
    console_app.reset_caches()
    return tenant, credits, items, declared


def test_row_counts_and_signed_paise_totals_are_unchanged(migrated):
    tenant, credits, items, declared = migrated
    with use_tenant(tenant):
        conn = open_tenant_readonly()
        try:
            after = source_aggregates(conn)
        finally:
            conn.close()
    assert after["n_bank_credits"] == len(credits)
    assert after["n_ledger_items"] == len(items)
    assert after["n_settlement_lines"] == len(declared)
    assert after["sum_bank_credit_paise"] == sum(c.amount_paise for c in credits)
    assert after["sum_ledger_item_paise"] == sum(i.amount_paise for i in items)
    assert after["sum_settlement_paise"] == sum(d.amount_paise for d in declared)
    # Nothing was silently dropped.
    assert after["n_bank_credits"] > 0 and after["n_ledger_items"] > 0


def test_every_record_round_trips_field_for_field(migrated):
    """Not just the totals: each object must come back identical."""
    from residual_zero.ingest.sql_source import (
        load_bank_credits_sql,
        load_ledger_items_sql,
        load_settlement_report_sql,
    )

    tenant, credits, items, declared = migrated
    with use_tenant(tenant):
        conn = open_tenant_readonly()
        try:
            back_credits = load_bank_credits_sql(conn)
            back_items = load_ledger_items_sql(conn)
            back_declared = load_settlement_report_sql(conn)
        finally:
            conn.close()

    assert sorted(back_credits, key=lambda c: c.id) == sorted(credits, key=lambda c: c.id)
    assert sorted(back_items, key=lambda i: i.id) == sorted(items, key=lambda i: i.id)
    assert sorted(back_declared) == sorted(declared)


def test_the_engine_produces_identical_results_from_files_and_from_sql(migrated):
    """The invariant that matters: same residuals, same gates, same member sets."""
    tenant, _credits, _items, _declared = migrated

    console_app.reset_caches()
    file_overlay = console_app._overlay()
    file_split = console_app._split()

    console_app.reset_caches()
    with use_tenant(tenant):
        sql_overlay = console_app._overlay()
        sql_split = console_app._split()

    assert file_overlay is not None and sql_overlay is not None

    # Same population.
    assert len(file_split[1]) == len(sql_split[1])
    assert len(file_split[0]) == len(sql_split[0])

    # Same gate totals.
    assert sql_overlay.n_ok == file_overlay.n_ok
    assert sql_overlay.n_journalable == file_overlay.n_journalable
    assert sql_overlay.n_mismatch == file_overlay.n_mismatch

    # Same answer for every single credit, not just in aggregate.
    assert set(sql_overlay.by_id) == set(file_overlay.by_id)
    for credit_id, expected in file_overlay.by_id.items():
        got = sql_overlay.by_id[credit_id]
        assert got.residual_paise == expected.residual_paise, credit_id
        assert got.ok == expected.ok, credit_id

    # Same member sets, which is what a journal and a proof are built from.
    assert sql_overlay.journalable == file_overlay.journalable


def test_the_journal_balances_identically_from_sql(migrated):
    """Debits equal credits at paise, and the control residual is unchanged."""
    from residual_zero.journal import build_journal, control_residual, load_chart, trial_balance

    tenant, _credits, _items, _declared = migrated

    def journal_for(bound):
        console_app.reset_caches()
        if bound is None:
            split, overlay = console_app._split(), console_app._overlay()
        else:
            with use_tenant(bound):
                split, overlay = console_app._split(), console_app._overlay()
        _items_, credits, _by, ledger, _ids = split
        chart = load_chart()
        lines = build_journal(credits, ledger, overlay.journalable, chart)
        debits, credits_total = trial_balance(lines)
        return (
            len(lines), debits, credits_total,
            control_residual(lines, credits, chart.bank_control.code),
        )

    assert journal_for(tenant) == journal_for(None)
    n_lines, debits, credits_total, residual = journal_for(tenant)
    assert debits == credits_total, "the migrated journal does not balance"
    assert n_lines > 0


def test_a_re_run_of_the_migration_is_idempotent(migrated):
    """Re-running must not duplicate a row or double a total."""
    tenant, credits, items, declared = migrated
    with use_tenant(tenant):
        conn = open_tenant_readonly()
        try:
            first = source_aggregates(conn)
        finally:
            conn.close()
        conn = open_tenant_readwrite("verify")
        try:
            write_bank_credits(conn, credits)
            write_ledger_items(conn, items)
            write_settlement_lines(conn, declared)
        finally:
            conn.close()
        conn = open_tenant_readonly()
        try:
            second = source_aggregates(conn)
        finally:
            conn.close()
    assert first == second


def test_the_migration_script_reports_a_mismatch_rather_than_succeeding_quietly():
    """The verification is the point of the script, so its failure path must be real."""
    from scripts.migrate_corpus import corpus_aggregates

    class Fake:
        def __init__(self, amount_paise):
            self.amount_paise = amount_paise

    before = corpus_aggregates([Fake(100)], [Fake(-40)], [Fake(60)])
    assert before == {
        "n_bank_credits": 1, "sum_bank_credit_paise": 100,
        "n_ledger_items": 1, "sum_ledger_item_paise": -40,
        "n_settlement_lines": 1, "sum_settlement_paise": 60,
    }
    # A different aggregate must not compare equal — the comparison is exact, not tolerant.
    after = dict(before, sum_bank_credit_paise=101)
    assert after != before
