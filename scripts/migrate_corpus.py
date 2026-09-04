#!/usr/bin/env python3
"""Move a rendered CSV corpus into an organisation's database, and prove it arrived intact.

This is the data half of the migration. The schema half is ``scripts/migrate.py``.

Nothing here converts a money value. ``amount_paise`` is read out of the canonical objects
the existing CSV adapters already produced and written as the same integer, so a rupee
string is parsed exactly once — by the adapter that always parsed it — and never again.

Verification is the point of the script, not a courtesy. Before writing it records the row
count and the signed paise total of each source; after writing it reads them back out of
the database and refuses (exit 1, nothing committed as verified) unless every pair matches.
A migration that changed a financial aggregate is a failed migration.

    # into the demo organisation of a Postgres deployment
    RZ_DATABASE_URL=postgresql://... python scripts/migrate_corpus.py \
        --org demo --source data/dev/rendered

    # dry run: report what would move, write nothing
    python scripts/migrate_corpus.py --org demo --source data/dev/rendered --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO.joinpath("src")) not in sys.path:
    sys.path.insert(0, str(REPO.joinpath("src")))


def corpus_aggregates(credits, items, declared) -> dict[str, int]:
    """Row counts and signed paise totals read from the canonical objects."""
    return {
        "n_bank_credits": len(credits),
        "sum_bank_credit_paise": sum(c.amount_paise for c in credits),
        "n_ledger_items": len(items),
        "sum_ledger_item_paise": sum(i.amount_paise for i in items),
        "n_settlement_lines": len(declared),
        "sum_settlement_paise": sum(d.amount_paise for d in declared),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--org", required=True, help="organisation slug to load into")
    parser.add_argument(
        "--source", default="data/dev/rendered",
        help="rendered-source directory holding bank.csv / ledger.csv / settlement.csv",
    )
    parser.add_argument("--dry-run", action="store_true", help="report only, write nothing")
    parser.add_argument(
        "--create-org", action="store_true",
        help="create the organisation if it does not exist",
    )
    parser.add_argument("--json", action="store_true", help="machine-readable report")
    args = parser.parse_args(argv)

    from residual_zero import obs
    from residual_zero.identity.store import AuthError, IdentityStore
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
    from residual_zero.runtime.envfile import load_env_file
    from residual_zero.storage.engine import open_tenant_readonly, open_tenant_readwrite
    from residual_zero.tenancy import use_tenant

    load_env_file()
    obs.configure_logging()

    source = Path(args.source)
    if not source.is_dir():
        print(f"source directory not found: {source}", file=sys.stderr)
        return 2

    root = SourceRoot(source)
    items = load_ledger_items(root)
    credits = load_bank_credits(root)
    declared = load_settlement_report(root)
    before = corpus_aggregates(credits, items, declared)

    store = IdentityStore()
    tenant = store.find_organization(args.org)
    if tenant is None:
        if not args.create_org:
            print(
                f"organisation {args.org!r} does not exist; pass --create-org to create it",
                file=sys.stderr,
            )
            return 2
        try:
            tenant = store.create_organization(
                args.org, args.org, dataset_kind="sql",
            )
        except AuthError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    if args.dry_run:
        report = {"org": tenant.org_id, "schema": tenant.db_schema,
                  "dry_run": True, "source": before}
        print(json.dumps(report, indent=2) if args.json else _human(report, None))
        return 0

    with use_tenant(tenant):
        conn = open_tenant_readwrite("verify")
        try:
            n_credits = write_bank_credits(conn, credits)
            n_items = write_ledger_items(conn, items)
            n_lines = write_settlement_lines(conn, declared)
        finally:
            conn.close()

        # Read the aggregates back through a read-only connection, so the check cannot be
        # satisfied by anything still sitting in the writer's transaction.
        check = open_tenant_readonly()
        try:
            after = source_aggregates(check)
        finally:
            check.close()

    mismatches = {
        key: {"before": before[key], "after": after.get(key)}
        for key in before
        if before[key] != after.get(key)
    }
    report = {
        "org": tenant.org_id,
        "schema": tenant.db_schema,
        "written": {"bank_credits": n_credits, "ledger_items": n_items,
                    "settlement_lines": n_lines},
        "source": before,
        "database": after,
        "verified": not mismatches,
        "mismatches": mismatches,
    }
    print(json.dumps(report, indent=2) if args.json else _human(report, mismatches))
    if mismatches:
        obs.warn("corpus_migration.mismatch", org=tenant.org_id, keys=sorted(mismatches))
        return 1
    obs.event("corpus_migration.verified", org=tenant.org_id, **before)
    return 0


def _human(report: dict, mismatches: dict | None) -> str:
    lines = [f"organisation {report['org']}  schema {report['schema']}"]
    src = report["source"]
    db = report.get("database")
    lines.append("")
    lines.append(f"{'aggregate':28s} {'source':>18s} {'database':>18s}")
    for key in src:
        after = "—" if db is None else f"{db.get(key, 0):,}"
        lines.append(f"{key:28s} {src[key]:>18,} {after:>18s}")
    lines.append("")
    if report.get("dry_run"):
        lines.append("dry run: nothing was written")
    elif mismatches:
        lines.append("MISMATCH — the migration did not preserve these aggregates:")
        for key, pair in mismatches.items():
            lines.append(f"  {key}: source {pair['before']} vs database {pair['after']}")
    else:
        lines.append("verified: every row count and signed paise total matches the source")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
