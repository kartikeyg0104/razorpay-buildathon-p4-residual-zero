"""F44: account-scoped members vs credit.account_id. Class 25 is a mispost, two MIDs are not."""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Mapping, Sequence

from residual_zero.models import BankCredit, LedgerItem


def members_cross_account(credit: BankCredit, members: Sequence[LedgerItem]) -> bool:
    """True iff any known member was posted on a different account than the credit."""
    return any(m.account_id != credit.account_id for m in members)


def detect_credit(
    credit: BankCredit,
    member_ids: Sequence[str],
    ledger: Mapping[str, LedgerItem],
) -> bool:
    items = tuple(ledger[mid] for mid in member_ids if mid in ledger)
    if not items:
        return False
    return members_cross_account(credit, items)


def false_positives(
    credits: Sequence[BankCredit],
    members_by_credit: Mapping[str, Sequence[str]],
    ledger: Mapping[str, LedgerItem],
) -> tuple[str, ...]:
    """Credit ids that fire on a legitimate (unmutated) batch."""
    fired = [
        credit.id
        for credit in credits
        if detect_credit(credit, members_by_credit.get(credit.id, ()), ledger)
    ]
    return tuple(sorted(fired))


def consolidated_view(credits: Iterable[BankCredit]) -> dict[str, tuple[str, ...]]:
    """Credits grouped by account_id, ids sorted. The cross-account surface, not a merged pool."""
    groups: dict[str, list[str]] = defaultdict(list)
    for credit in credits:
        groups[credit.account_id].append(credit.id)
    return {account: tuple(sorted(ids)) for account, ids in sorted(groups.items())}
