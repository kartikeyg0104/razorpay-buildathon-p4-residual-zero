"""Report what an organisation's schema actually contains.

`migrate.py --status` reports what the migration ledger *claims*. This reports what is
there. The two disagreed once — every migration recorded as applied, and a table the
first one creates missing — and there was no way to see that from outside the database.

    RZ_DATABASE_URL=postgresql://... python scripts/qa_org_schema.py --org demo

Read-only. Prints table names and row counts; never a financial value, never a credential.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO.joinpath("src")) not in sys.path:
    sys.path.insert(0, str(REPO.joinpath("src")))


def _list_all() -> int:
    """Every organisation, who signs in to it, and whether it has a recorded run.

    The question this answers is "which organisation does that browser session land in",
    which is not answerable from a dashboard that is correctly organisation-scoped.
    """
    from residual_zero.audit import latest_completed_run, open_audit
    from residual_zero.identity.store import IdentityStore
    from residual_zero.storage.engine import open_shared
    from residual_zero.tenancy import use_tenant

    store = IdentityStore()
    conn = open_shared(readonly=True)
    try:
        orgs = list(conn.execute(
            "SELECT org_id, slug, db_schema, dataset_kind FROM organization ORDER BY slug"
        ))
        users = list(conn.execute("SELECT email, org_id, role FROM app_user ORDER BY email"))
    finally:
        conn.close()

    by_org: dict[str, list[str]] = {}
    for email, org_id, role in users:
        by_org.setdefault(str(org_id), []).append(f"{email} ({role})")

    for org_id, slug, schema, kind in orgs:
        tenant = store.tenant_for_org(str(org_id))
        with use_tenant(tenant):
            audit = open_audit()
            try:
                run = latest_completed_run(audit)
                entries = list(audit.execute(
                    "SELECT COUNT(DISTINCT json_extract(payload, '$.bank_credit_id')) "
                    "FROM audit_entry"
                ))[0][0]
            except Exception as exc:  # noqa: BLE001 - a schema may predate the run table
                run, entries = None, f"unreadable: {type(exc).__name__}"
            finally:
                audit.close()
        print(f"org {slug!r} schema={schema} dataset={kind}")
        print(f"    users: {by_org.get(str(org_id)) or 'none'}")
        if run is None:
            print("    recorded run: NONE  -> dashboard correctly says NOT RUN")
        else:
            print(f"    recorded run: {run['run_id']} {run['status']} "
                  f"{run['n_persisted']}/{run['n_credits']} complete={run['complete']}")
        print(f"    distinct credits with results: {entries}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--org", help="organisation slug")
    parser.add_argument("--all", action="store_true",
                        help="list every organisation, its users, and its recorded run")
    args = parser.parse_args(argv)
    if args.all:
        return _list_all()
    if not args.org:
        parser.error("--org or --all is required")

    from residual_zero.identity.store import IdentityStore
    from residual_zero.storage.engine import open_tenant_readonly
    from residual_zero.tenancy import use_tenant

    store = IdentityStore()
    found = store.find_organization(args.org)
    if found is None:
        print(f"unknown organisation {args.org!r}", file=sys.stderr)
        return 2
    tenant = store.tenant_for_org(found.org_id)
    print(f"org {tenant.slug} schema {tenant.db_schema} dataset {tenant.dataset_kind}")

    with use_tenant(tenant):
        conn = open_tenant_readonly(None)
        try:
            print("current_schema", [r[0] for r in conn.execute("SELECT current_schema()")])
            tables = sorted(
                r[0]
                for r in conn.execute(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = current_schema()"
                )
            )
            print(f"tables ({len(tables)}): {tables}")
            versions = [
                r[0] for r in conn.execute("SELECT version FROM schema_migration ORDER BY version")
            ]
            print("recorded migrations:", versions)
            if "audit_entry" in tables:
                rows = list(conn.execute(
                    "SELECT COUNT(*), COUNT(DISTINCT json_extract(payload, '$.bank_credit_id')) "
                    "FROM audit_entry"
                ))[0]
                print(f"  audit entries {rows[0]} over {rows[1]} distinct credits")
                dupes = list(conn.execute(
                    "SELECT json_extract(payload, '$.bank_credit_id') AS cid, COUNT(*) c "
                    "FROM audit_entry GROUP BY cid HAVING COUNT(*) > 1 ORDER BY c DESC"
                ))
                print(f"  credits with more than one entry: {len(dupes)}")
                if dupes:
                    print(f"    worst: {dupes[0][0]} x{dupes[0][1]}")
            if "reconciliation_run" in tables:
                for r in conn.execute(
                    "SELECT run_id, status, n_credits, n_computed, n_reused, n_persisted "
                    "FROM reconciliation_run ORDER BY started_at"
                ):
                    print(f"  run {r[0]} {r[1]} credits={r[2]} computed={r[3]} "
                          f"reused={r[4]} persisted={r[5]}")
                    n = list(conn.execute(
                        "SELECT COUNT(*), COUNT(DISTINCT json_extract(payload, "
                        "'$.bank_credit_id')) FROM audit_entry WHERE run_id = ?", (r[0],)
                    ))[0]
                    print(f"    entries {n[0]} over {n[1]} distinct credits")
            for name in ("audit_entry", "exception", "reconciliation", "reconciliation_run"):
                if name in tables:
                    n = list(conn.execute(f"SELECT COUNT(*) FROM {name}"))[0][0]
                    print(f"  {name:22s} {n} rows")
                else:
                    print(f"  {name:22s} MISSING")
        finally:
            conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
