#!/usr/bin/env python3
"""Apply schema migrations. Reproducible, idempotent, and safe to re-run.

    # bring the shared identity schema up to date
    RZ_DATABASE_URL=postgresql://... python scripts/migrate.py --shared

    # bring one organisation's financial schema up to date
    RZ_DATABASE_URL=postgresql://... python scripts/migrate.py --org demo

    # every organisation the identity store knows about
    RZ_DATABASE_URL=postgresql://... python scripts/migrate.py --all

    # report without applying
    RZ_DATABASE_URL=postgresql://... python scripts/migrate.py --status
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO.joinpath("src")) not in sys.path:
    sys.path.insert(0, str(REPO.joinpath("src")))


def _org_slugs() -> list[str]:
    from residual_zero.storage.engine import open_shared

    conn = open_shared(readonly=True)
    try:
        return [str(r[0]) for r in conn.execute("SELECT slug FROM organization ORDER BY slug")]
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shared", action="store_true", help="apply the shared identity schema")
    parser.add_argument("--org", default="", help="apply one organisation's financial schema")
    parser.add_argument("--all", action="store_true", help="shared plus every organisation")
    parser.add_argument("--status", action="store_true", help="report pending versions only")
    args = parser.parse_args(argv)

    from residual_zero import obs
    from residual_zero.runtime.envfile import load_env_file

    load_env_file()
    obs.configure_logging()

    from residual_zero.storage.config import Backend, storage_config

    cfg = storage_config()
    print(f"backend {cfg.backend.value}  {cfg.safe_dsn() or '(local files)'}")
    if cfg.backend is Backend.SQLITE:
        # SQLite creates its schema on connect, so there is nothing to version. Saying so
        # is better than reporting a vacuous success.
        print("sqlite: schema is created on connect; no migration ledger is kept")
        from residual_zero.storage.engine import bootstrap_shared

        bootstrap_shared()
        print("sqlite: identity tables ensured")
        return 0

    from residual_zero.identity.store import IdentityStore
    from residual_zero.storage.engine import bootstrap_shared, bootstrap_tenant, open_shared
    from residual_zero.storage.migrate import pending

    if args.status:
        conn = open_shared(readonly=True)
        try:
            print("shared pending:", pending(conn, "shared") or "none")
        finally:
            conn.close()
        for slug in _org_slugs():
            tenant = IdentityStore().find_organization(slug)
            from residual_zero.storage.pg import PgConnection

            conn = PgConnection(cfg.dsn, schema=tenant.db_schema, readonly=True)
            try:
                print(f"org {slug} ({tenant.db_schema}) pending:",
                      pending(conn, "org") or "none")
            finally:
                conn.close()
        return 0

    if args.shared or args.all:
        applied = bootstrap_shared()
        print("shared applied:", applied or "already up to date")

    slugs: list[str] = []
    if args.org:
        slugs = [args.org]
    elif args.all:
        slugs = _org_slugs()
    for slug in slugs:
        tenant = IdentityStore().find_organization(slug)
        if tenant is None:
            print(f"org {slug}: unknown", file=sys.stderr)
            return 2
        applied = bootstrap_tenant(tenant)
        print(f"org {slug} ({tenant.db_schema}) applied:", applied or "already up to date")

    if not (args.shared or args.all or slugs):
        parser.print_help()
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
