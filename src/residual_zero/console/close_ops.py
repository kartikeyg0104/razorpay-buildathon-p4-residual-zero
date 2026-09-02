"""Read-only month-end close pack. Never writes CLEARED.

Bidirectional unmatched, GST/TDS mismatch, SLA aging, four-way identity evidence,
F51 autonomy rungs, and a close checklist. Overlay and search remain the only
clearing authorities; this module does not pick a member set.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Mapping, NamedTuple, Sequence

from residual_zero.console.ops import GateA, Overlay
from residual_zero.models import BankCredit, Kind, LedgerItem
from residual_zero.money import format_rupees
from residual_zero.runtime.degrade import Rung, policy_for

RATE_TAX_KINDS = frozenset({Kind.FEE, Kind.TAX_GST, Kind.TAX_WITHHOLDING})
CAUSAL_ORDER = (
    Kind.PAYMENT,
    Kind.FEE,
    Kind.TAX_GST,
    Kind.TAX_WITHHOLDING,
    Kind.RESERVE_HOLD,
)
_SAMPLE = 24
_SLA = (
    ("0-1", 0, 1),
    ("2-7", 2, 7),
    ("8-14", 8, 14),
    ("15+", 15, None),
)


class ClosePack(NamedTuple):
    as_of: str
    n_bank_uncovered: int
    n_ledger_orphans: int
    n_tax_mismatch: int
    n_human: int
    n_four_way_full: int
    bank_uncovered: tuple[dict[str, Any], ...]
    ledger_orphans: tuple[dict[str, Any], ...]
    tax_mismatch: tuple[dict[str, Any], ...]
    sla: tuple[dict[str, Any], ...]
    autonomy: tuple[dict[str, Any], ...]
    checklist: tuple[dict[str, Any], ...]
    writes_cleared: bool


def corpus_as_of(credits: Sequence[BankCredit]) -> date | None:
    if not credits:
        return None
    return max(c.value_date for c in credits)


def sla_age_days(value_date: date, as_of: date) -> int:
    delta = as_of - value_date
    return delta.days if delta.days >= 0 else 0


def sla_bucket_name(age_days: int) -> str:
    for name, lo, hi in _SLA:
        if hi is None:
            if age_days >= lo:
                return name
        elif lo <= age_days <= hi:
            return name
    return "15+"


def gate_refused(gate: GateA | None) -> bool:
    return gate is None or not gate.ok


def is_tax_mismatch(gate: GateA | None, declared: Sequence[Any]) -> bool:
    """Gate A present, failed, rate-line deltas, and a fee/GST/withholding member."""
    if gate is None or gate.ok or gate.n_deltas <= 0:
        return False
    return any(getattr(row, "kind", None) in RATE_TAX_KINDS for row in declared)


def four_way_identity(
    credit: BankCredit,
    declared: Sequence[Any],
    ledger: Mapping[str, LedgerItem],
    residual_paise: int | None,
) -> dict[str, Any]:
    """UTR / settlement / named ledger / residual 0. Display only — never a clear gate."""
    named = tuple(r.item_id for r in declared if getattr(r, "item_id", None) in ledger)
    residual_zero = residual_paise == 0
    checks = (
        ("utr", bool(credit.utr), credit.utr or ""),
        ("settlement", bool(declared), str(len(declared))),
        ("named_ledger", bool(named), str(len(named))),
        ("residual_zero", residual_zero, format_rupees(residual_paise or 0)),
    )
    hits = tuple(name for name, ok, _detail in checks if ok)
    return {
        "transaction_id": credit.id,
        "utr": bool(credit.utr),
        "settlement": bool(declared),
        "named_ledger": bool(named),
        "residual_zero": residual_zero,
        "n_hit": len(hits),
        "hits": hits,
        "details": {name: detail for name, _ok, detail in checks},
        "clears": False,
        "writes_cleared": False,
        "note": "Four-way identity is evidence. UNIQUE + FULL + threshold is the only auto-clear.",
    }


def causal_chain(declared: Sequence[Any]) -> tuple[str, ...]:
    """PAYMENT → FEE → GST → withholding → reserve → BANK. Missing kinds omitted."""
    present = {row.kind for row in declared if getattr(row, "kind", None) is not None}
    ordered = tuple(k.value for k in CAUSAL_ORDER if k in present)
    return ordered + ("BANK_CREDIT",)


def _row(credit: BankCredit, why: str, extra: Mapping[str, Any] | None = None) -> dict[str, Any]:
    blob: dict[str, Any] = {
        "transaction_id": credit.id,
        "amount_display": format_rupees(credit.amount_paise),
        "value_date": credit.value_date.isoformat(),
        "account_id": credit.account_id,
        "why": why,
        "href": "/credit/" + credit.id,
        "writes_cleared": False,
    }
    if extra:
        blob.update(extra)
    return blob


def bidirectional_unmatched(
    credits: Sequence[BankCredit],
    ledger: Mapping[str, LedgerItem],
    by_credit: Mapping[str, Sequence[Any]],
    overlay: Overlay | None,
) -> tuple[tuple[dict[str, Any], ...], tuple[dict[str, Any], ...]]:
    bank: list[dict[str, Any]] = []
    named: set[str] = set()
    for credit in credits:
        declared = tuple(by_credit.get(credit.id) or ())
        for row in declared:
            item_id = getattr(row, "item_id", None)
            if item_id:
                named.add(str(item_id))
        gate = overlay.by_id.get(credit.id) if overlay is not None else None
        if not declared:
            bank.append(_row(credit, "no settlement rows"))
        elif gate_refused(gate):
            bank.append(_row(credit, "gate A refused"))
    orphans: list[dict[str, Any]] = []
    for item_id, item in ledger.items():
        if item_id in named:
            continue
        orphans.append(
            {
                "item_id": item_id,
                "kind": item.kind.value,
                "amount_display": format_rupees(item.amount_paise),
                "account_id": item.account_id,
                "why": "never named by a settlement row",
                "writes_cleared": False,
            }
        )
    return tuple(bank), tuple(orphans)


def tax_mismatch_rows(
    credits: Sequence[BankCredit],
    by_credit: Mapping[str, Sequence[Any]],
    overlay: Overlay | None,
    audits: Mapping[str, Mapping[str, Any]] | None = None,
) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    if overlay is None:
        return ()
    for credit in credits:
        declared = tuple(by_credit.get(credit.id) or ())
        gate = overlay.by_id.get(credit.id)
        if not is_tax_mismatch(gate, declared):
            continue
        uniqueness = str((audits or {}).get(credit.id, {}).get("uniqueness") or "AMBIGUOUS")
        if uniqueness == "UNIQUE":
            uniqueness = "AMBIGUOUS"
        rows.append(
            _row(
                credit,
                f"rate re-derive failed · {gate.n_deltas} line deltas",
                {
                    "n_deltas": gate.n_deltas,
                    "residual_display": format_rupees(gate.residual_paise),
                    "uniqueness": uniqueness,
                    "clears": False,
                },
            )
        )
    return tuple(rows)


def sla_buckets(
    credits: Sequence[BankCredit],
    overlay: Overlay | None,
    as_of: date,
) -> tuple[tuple[dict[str, Any], ...], int]:
    human: list[tuple[int, BankCredit]] = []
    for credit in credits:
        gate = overlay.by_id.get(credit.id) if overlay is not None else None
        if not gate_refused(gate):
            continue
        human.append((sla_age_days(credit.value_date, as_of), credit))
    buckets: list[dict[str, Any]] = []
    for name, lo, hi in _SLA:
        if hi is None:
            members = [(age, c) for age, c in human if age >= lo]
        else:
            members = [(age, c) for age, c in human if lo <= age <= hi]
        sample = [
            _row(c, f"age {age}d · {name}", {"age_days": age, "bucket": name})
            for age, c in members[:8]
        ]
        buckets.append(
            {
                "name": name,
                "n": len(members),
                "paise": sum(c.amount_paise for _age, c in members),
                "amount_display": format_rupees(sum(c.amount_paise for _age, c in members)),
                "rows": sample,
            }
        )
    return tuple(buckets), len(human)


def autonomy_rungs() -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    for rung in (Rung.NORMAL, Rung.NO_MODEL, Rung.NO_SEARCH, Rung.READ_ONLY, Rung.HALTED):
        pol = policy_for(rung)
        rows.append(
            {
                "name": rung.value,
                "allow_model": pol.allow_model,
                "allow_search": pol.allow_search,
                "allow_writes": pol.allow_writes,
                "process_credits": pol.process_credits,
                "auto_clear": 0,
                "coverage": "0/239",
            }
        )
    return tuple(rows)


def close_checklist(
    *,
    books_hold: bool,
    journal_balanced: bool,
    control_ok: bool,
    chain_ok: bool,
    n_auto_cleared: int,
    n_double_claimed: int,
) -> tuple[dict[str, Any], ...]:
    items = (
        ("books identity", books_hold, "Gate A conservation holds on every account"),
        ("journal balanced", journal_balanced, "debits equal credits at paise"),
        ("bank control residual 0", control_ok, "posted bank equals credits"),
        ("audit chain intact", chain_ok, "hash chain verifies"),
        ("search auto-clear 0", n_auto_cleared == 0, "UNIQUE + FULL + threshold still refuse-all"),
        ("double-claimed 0", n_double_claimed == 0, "no ledger item in two journalable stacks"),
    )
    return tuple(
        {"name": name, "ok": ok, "detail": detail, "writes_cleared": False}
        for name, ok, detail in items
    )


def build_close_pack(
    credits: Sequence[BankCredit],
    ledger: Mapping[str, LedgerItem],
    by_credit: Mapping[str, Sequence[Any]],
    overlay: Overlay | None,
    audits: Mapping[str, Mapping[str, Any]] | None = None,
    *,
    books_hold: bool = False,
    journal_balanced: bool = False,
    control_ok: bool = False,
    chain_ok: bool = False,
    n_auto_cleared: int = 0,
) -> ClosePack:
    as_of = corpus_as_of(credits) or date(2025, 1, 1)
    bank, orphans = bidirectional_unmatched(credits, ledger, by_credit, overlay)
    tax = tax_mismatch_rows(credits, by_credit, overlay, audits)
    sla, n_human = sla_buckets(credits, overlay, as_of)
    n_four = 0
    for credit in credits:
        declared = tuple(by_credit.get(credit.id) or ())
        gate = overlay.by_id.get(credit.id) if overlay is not None else None
        residual = gate.residual_paise if gate is not None else None
        ident = four_way_identity(credit, declared, ledger, residual)
        if ident["n_hit"] == 4:
            n_four += 1
    double_n = len(overlay.double_claimed) if overlay is not None else 0
    return ClosePack(
        as_of=as_of.isoformat(),
        n_bank_uncovered=len(bank),
        n_ledger_orphans=len(orphans),
        n_tax_mismatch=len(tax),
        n_human=n_human,
        n_four_way_full=n_four,
        bank_uncovered=bank[:_SAMPLE],
        ledger_orphans=orphans[:_SAMPLE],
        tax_mismatch=tax[:_SAMPLE],
        sla=sla,
        autonomy=autonomy_rungs(),
        checklist=close_checklist(
            books_hold=books_hold,
            journal_balanced=journal_balanced,
            control_ok=control_ok,
            chain_ok=chain_ok,
            n_auto_cleared=n_auto_cleared,
            n_double_claimed=double_n,
        ),
        writes_cleared=False,
    )


def pack_as_json(pack: ClosePack) -> dict[str, Any]:
    return {
        "as_of": pack.as_of,
        "n_bank_uncovered": pack.n_bank_uncovered,
        "n_ledger_orphans": pack.n_ledger_orphans,
        "n_tax_mismatch": pack.n_tax_mismatch,
        "n_human": pack.n_human,
        "n_four_way_full": pack.n_four_way_full,
        "bank_uncovered": list(pack.bank_uncovered),
        "ledger_orphans": list(pack.ledger_orphans),
        "tax_mismatch": list(pack.tax_mismatch),
        "sla": list(pack.sla),
        "autonomy": list(pack.autonomy),
        "checklist": list(pack.checklist),
        "writes_cleared": False,
        "auto_clear": 0,
        "note": "Close pack is read-only. Overlay does not write CLEARED.",
    }
