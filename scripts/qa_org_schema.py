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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--org", required=True, help="organisation slug")
    args = parser.parse_args(argv)

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
