#!/usr/bin/env python3
"""Create the first organisation and its owner, without putting a password on a command line.

An argument is visible in the process table and in shell history, so the password is read
from a prompt or from ``RZ_ADMIN_PASSWORD``, never from ``--password``.

    RZ_DATABASE_URL=postgresql://... python scripts/bootstrap_admin.py \
        --email ops@example.com --org demo

Add ``--dataset files`` to point the organisation at the committed synthetic dev corpus
instead of its own ingested rows — that is what makes the deployed demo show numbers
immediately. Any other organisation should stay on ``sql`` and ingest its own data; the demo
corpus is synthetic and shared, and it is not a starting point for somebody's real books.
"""

from __future__ import annotations

import argparse
import getpass
import os
import secrets
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO.joinpath("src")) not in sys.path:
    sys.path.insert(0, str(REPO.joinpath("src")))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    parser.add_argument("--org", required=True, help="organisation slug")
    parser.add_argument("--name", default="", help="organisation display name")
    parser.add_argument(
        "--dataset", choices=("sql", "files"), default="sql",
        help="'files' reads the committed synthetic dev corpus; 'sql' reads this "
             "organisation's own ingested rows",
    )
    parser.add_argument(
        "--dataset-root", default="data/dev/rendered",
        help="rendered-source directory when --dataset files",
    )
    parser.add_argument(
        "--role", choices=("owner", "analyst", "viewer"), default="owner",
    )
    parser.add_argument(
        "--generate-password", action="store_true",
        help="print a generated password instead of prompting",
    )
    args = parser.parse_args(argv)

    from residual_zero import obs
    from residual_zero.identity.store import AuthError, IdentityStore, Role
    from residual_zero.runtime.envfile import load_env_file
    from residual_zero.storage.engine import bootstrap_shared

    load_env_file()
    obs.configure_logging()
    bootstrap_shared()

    generated = ""
    if args.generate_password:
        generated = secrets.token_urlsafe(18)
        password = generated
    else:
        password = os.environ.get("RZ_ADMIN_PASSWORD") or ""
        if not password:
            password = getpass.getpass("password (12+ chars): ")
            if password != getpass.getpass("repeat: "):
                print("passwords did not match", file=sys.stderr)
                return 2

    store = IdentityStore()
    tenant = store.find_organization(args.org)
    try:
        if tenant is None:
            tenant = store.create_organization(
                args.org, args.name or args.org,
                dataset_kind=args.dataset,
                dataset_root=args.dataset_root if args.dataset == "files" else "",
            )
            print(f"created organisation {tenant.org_id} (schema {tenant.db_schema}, "
                  f"dataset {tenant.dataset_kind})")
        else:
            print(f"organisation {tenant.org_id} already exists "
                  f"(schema {tenant.db_schema}, dataset {tenant.dataset_kind})")
        principal = store.create_user(args.email, password, tenant.org_id, Role(args.role))
    except AuthError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    store.log_event(
        "bootstrap_admin", "ok", user_id=principal.user_id, org_id=principal.org_id,
    )
    print(f"created user {principal.email} with role {principal.role.value}")
    if generated:
        print(f"\ngenerated password (shown once): {generated}\n")
    print("sign in at <your public origin>/login")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
