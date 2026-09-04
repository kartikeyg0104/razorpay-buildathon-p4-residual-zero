"""Point an existing organisation at the committed corpus, or back at its own rows.

A self-service signup starts on ``sql`` with no records, so a freshly deployed desk shows
zeros everywhere. That is correct behaviour — one tenant's books are never another
tenant's starting point — but the demonstration organisation is meant to read the
committed synthetic corpus. ``bootstrap_admin.py --dataset files`` does this at creation
time; this does it afterwards, without touching the password.

    RZ_DATABASE_URL=postgresql://... python scripts/set_org_dataset.py --org demo --dataset files

Idempotent: re-running with the same values changes nothing and exits 0, so it is safe as
a pre-deploy command. It reads and writes one row of the identity schema. It does not
touch the ledger, and it cannot clear anything.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO.joinpath("src")) not in sys.path:
    sys.path.insert(0, str(REPO.joinpath("src")))

from residual_zero.identity.store import AuthError, IdentityStore  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--org", required=True, help="organisation slug")
    parser.add_argument("--dataset", choices=("sql", "files"), required=True)
    parser.add_argument(
        "--dataset-root", default="data/dev/rendered",
        help="rendered-source directory when --dataset files",
    )
    args = parser.parse_args(argv)

    store = IdentityStore()
    try:
        before = store.find_organization(args.org)
        if before is None:
            print(f"unknown organisation {args.org!r}", file=sys.stderr)
            return 2
        current = store.tenant_for_org(before.org_id)
        root = args.dataset_root if args.dataset == "files" else ""
        if (current.dataset_kind, current.dataset_root) == (args.dataset, root):
            print(f"organisation {current.slug} already reads {args.dataset}; nothing to do")
            return 0
        tenant = store.set_organization_dataset(args.org, args.dataset, root)
    except AuthError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    where = tenant.dataset_root or "its own ingested rows"
    print(
        f"organisation {tenant.slug} now reads {tenant.dataset_kind} ({where}); "
        f"was {current.dataset_kind}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
