"""Second-wave ops surfaces borrowed from Track 04 READMEs.

Cash bridge (Kosh), tax radar vs rate table (AegisPay/SuryaSK), SHA-256 batch
seal (AegisPay), playbooks + dispute draft (pk7007/finctrl), three-way desk
(Vouch/finctrl). None of this writes CLEARED or picks a member set.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from collections import Counter, defaultdict
from typing import Any, Mapping, Sequence

from residual_zero.config import FeeSchedule, TaxRates
from residual_zero.console.ops import Overlay
from residual_zero.models import BankCredit, Instrument, Kind, LedgerItem
from residual_zero.money import apply_bps, format_rupees

_BRIDGE_KINDS = (
    Kind.PAYMENT,
    Kind.REFUND,
    Kind.FEE,
    Kind.TAX_GST,
    Kind.TAX_WITHHOLDING,
    Kind.RESERVE_HOLD,
    Kind.RESERVE_RELEASE,
    Kind.CHARGEBACK,
    Kind.REPRESENTMENT,
    Kind.ADJUSTMENT,
    Kind.BANK_CHARGE,
)

PLAYBOOKS: dict[str, str] = {
    "AMBIGUOUS_DECOMPOSITION": "Review competing subsets. Do not pick Equation SEARCH. Leave flagged.",
    "MISSING_RECORD": "Locate the missing ledger or settlement row. Do not fabricate an amount.",
    "DUPLICATE_CREDIT": "Confirm the second NEFT with the bank. One credit is a duplicate until proven.",
    "SUSPECTED_WITHHOLDING": "Re-derive 194-O against GROSS_PAYMENTS at the rate table. Do not clear on a percentage guess.",
    "UNITEMISED_FEE": "Re-derive platform fee per instrument. A clean residual is not a clear.",
    "ROUNDING_RESIDUE": "Residual sits inside rounding. Do not plug. Escalate if it repeats.",
    "CROSS_WINDOW_UNRESOLVED": "An excluded window member equals the residual. Widen is a proposal, not a clear.",
    "SIGN_REVERSAL": "A debit posted as a credit. Correct the sign in the source, then re-run.",
    "ENTITY_UNRESOLVED": "Counterparty failed the closed registry. Do not invent an id.",
    "BUDGET_EXCEEDED": "Search did not finish. Not a match. Re-run with the same threshold.",
    "RATE_MISMATCH": "Declared fee/GST/withholding failed the rate table. Fix the report, do not override.",
    "STRUCTURALLY_INFEASIBLE": "Arithmetic subsets exist; constraints kill them. Data defect.",
    "NONE_FOUND": "Search found no residual-zero subset. Inspect missing refunds/settlement.",
    "AMBIGUOUS": "Two or more subsets fit. Human review. Overlay does not write CLEARED.",
}

WORK_STATUSES = frozenset({"open", "investigating", "resolved", "written_off"})
# The three buttons the credit page offers (templates/credit.html data-resolve).
RESOLUTIONS = frozenset({"accept", "correct", "escalate"})


def playbook_for(exception_class: str) -> str:
    wanted = (exception_class or "").strip().upper()
    return PLAYBOOKS.get(wanted, "Leave flagged. Overlay does not write CLEARED.")


def cash_bridge(
    credits: Sequence[BankCredit],
    ledger: Mapping[str, LedgerItem],
    overlay: Overlay | None = None,
) -> dict[str, Any]:
    """Kosh-style cash bridge from signed ledger kinds + bank credits. Residual unplugged."""
    by_kind: Counter[str] = Counter()
    for item in ledger.values():
        by_kind[item.kind.value] += item.amount_paise
    lines = []
    ledger_total = 0
    for kind in _BRIDGE_KINDS:
        paise = by_kind.get(kind.value, 0)
        ledger_total += paise
        lines.append(
            {
                "kind": kind.value,
                "paise": paise,
                "amount_display": format_rupees(paise),
            }
        )
    bank = sum(c.amount_paise for c in credits)
    by_id = {c.id: c for c in credits}
    journalable_paise = 0
    if overlay is not None:
        for cid in overlay.journalable:
            credit = by_id.get(cid)
            if credit is not None:
                journalable_paise += credit.amount_paise
    unreconciled = bank - journalable_paise
    residual = bank - ledger_total
    return {
        "lines": lines,
        "ledger_total_paise": ledger_total,
        "ledger_total_display": format_rupees(ledger_total),
        "bank_landed_paise": bank,
        "bank_landed_display": format_rupees(bank),
        "journalable_paise": journalable_paise,
        "journalable_display": format_rupees(journalable_paise),
        "unreconciled_paise": unreconciled,
        "unreconciled_display": format_rupees(unreconciled),
        "residual_paise": residual,
        "residual_display": format_rupees(residual),
        "plugged": False,
        "writes_cleared": False,
        "note": "Residual stays on the face of the report. Overlay does not write CLEARED.",
    }


def tax_radar(
    ledger: Mapping[str, LedgerItem],
    rates: TaxRates,
    fees: FeeSchedule,
) -> dict[str, Any]:
    """Posted GST/TDS vs rate-table recompute. Not Form 26AS. Not a clear."""
    posted: Counter[str] = Counter()
    payments_by_instrument: dict[Instrument, int] = {}
    for item in ledger.values():
        posted[item.kind.value] += item.amount_paise
        if item.kind == Kind.PAYMENT and item.instrument is not None:
            payments_by_instrument[item.instrument] = (
                payments_by_instrument.get(item.instrument, 0) + item.amount_paise
            )
    expected_fee = 0
    expected_gst = 0
    for instrument, gross in sorted(payments_by_instrument.items(), key=lambda kv: kv[0].value):
        fee = -apply_bps(gross, fees.per_instrument_bps[instrument].bps)
        expected_fee += fee
        expected_gst += apply_bps(fee, rates.gst_on_fee.bps) if fee != 0 else 0
    expected_tds = 0
    gross = posted.get(Kind.PAYMENT.value, 0)
    if gross > 0 and rates.withholding.bps > 0:
        if rates.withholding.base == "GROSS_PAYMENTS":
            expected_tds = -apply_bps(gross, rates.withholding.bps)
        else:
            fee_mag = -expected_fee if expected_fee < 0 else expected_fee
            expected_tds = -apply_bps(fee_mag, rates.withholding.bps)
    gst_delta = posted.get(Kind.TAX_GST.value, 0) - expected_gst
    tds_delta = posted.get(Kind.TAX_WITHHOLDING.value, 0) - expected_tds
    fee_delta = posted.get(Kind.FEE.value, 0) - expected_fee
    return {
        "gst_posted_display": format_rupees(posted.get(Kind.TAX_GST.value, 0)),
        "gst_expected_display": format_rupees(expected_gst),
        "gst_delta_display": format_rupees(gst_delta),
        "tds_posted_display": format_rupees(posted.get(Kind.TAX_WITHHOLDING.value, 0)),
        "tds_expected_display": format_rupees(expected_tds),
        "tds_delta_display": format_rupees(tds_delta),
        "fee_posted_display": format_rupees(posted.get(Kind.FEE.value, 0)),
        "fee_expected_display": format_rupees(expected_fee),
        "fee_delta_display": format_rupees(fee_delta),
        "gst_on_fee_not_gross": True,
        "section": "194-O on GROSS_PAYMENTS at the loaded rate table",
        "not_form_26as": True,
        "writes_cleared": False,
        "note": "ITC/194-O radar is posted vs rate table. It does not query GSTN or 26AS.",
    }


def three_way(
    credit: BankCredit,
    declared: Sequence[Any],
    ledger: Mapping[str, LedgerItem],
) -> dict[str, Any]:
    settlement = []
    ledger_rows = []
    for row in declared:
        settlement.append(
            {
                "item_id": row.item_id,
                "kind": row.kind.value,
                "amount_display": format_rupees(row.amount_paise),
                "order_id": getattr(row, "order_id", None) or "",
            }
        )
        item = ledger.get(row.item_id)
        if item is None:
            ledger_rows.append(
                {
                    "item_id": row.item_id,
                    "kind": row.kind.value,
                    "amount_display": "",
                    "status": "MISSING",
                }
            )
        else:
            ledger_rows.append(
                {
                    "item_id": item.id,
                    "kind": item.kind.value,
                    "amount_display": format_rupees(item.amount_paise),
                    "status": "PRESENT",
                }
            )
    return {
        "bank": {
            "id": credit.id,
            "amount_display": format_rupees(credit.amount_paise),
            "value_date": credit.value_date.isoformat(),
            "account_id": credit.account_id,
            "utr": credit.utr or "",
            "narration": credit.narration_raw,
        },
        "settlement": settlement,
        "ledger": ledger_rows,
        "n_settlement": len(settlement),
        "n_ledger_missing": sum(1 for r in ledger_rows if r["status"] == "MISSING"),
        "writes_cleared": False,
        "note": "Three-way evidence. Not a matcher. Overlay does not write CLEARED.",
    }


def dispute_draft(
    credit: BankCredit,
    uniqueness: str,
    residual_display: str,
    playbook: str,
) -> str:
    utr = credit.utr or "(no UTR on file)"
    return (
        f"To: Bank ops / Razorpay merchant support\n"
        f"Re: settlement credit {credit.id} · UTR {utr} · {format_rupees(credit.amount_paise)} {credit.currency}\n"
        f"Value date: {credit.value_date.isoformat()} · account {credit.account_id}\n"
        f"Narration: {credit.narration_raw}\n"
        f"Search uniqueness: {uniqueness or 'unknown'} — Residual Zero will not pick a subset.\n"
        f"Residual: {residual_display}\n"
        f"Requested action: {playbook}\n"
        f"This letter is a draft from deterministic evidence. It is not a clear.\n"
        f"Overlay does not write CLEARED.\n"
    )


def batch_certificate(
    *,
    audit_head: str,
    n_credits: int,
    n_gate_a: int,
    n_journalable: int,
    n_unique: int,
    n_ambiguous: int,
    n_none_found: int,
    n_auto_cleared: int,
    chain_ok: bool,
) -> dict[str, Any]:
    payload = {
        "audit_head": audit_head,
        "n_credits": n_credits,
        "n_gate_a": n_gate_a,
        "n_journalable": n_journalable,
        "n_unique": n_unique,
        "n_ambiguous": n_ambiguous,
        "n_none_found": n_none_found,
        "n_auto_cleared": n_auto_cleared,
        "chain_ok": chain_ok,
        "writes_cleared": False,
        "product": "Residual Zero",
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(blob.encode("utf-8")).hexdigest()
    return {
        **payload,
        "sha256": digest,
        "note": "Seal of overlay counts + audit head. Not a CLEARED certificate.",
    }


def exceptions_csv(rows: Sequence[Mapping[str, Any]]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "credit_id",
            "account",
            "value_date",
            "amount",
            "uniqueness",
            "gate",
            "exception_class",
            "playbook",
            "writes_cleared",
        ]
    )
    for row in rows:
        writer.writerow(
            [
                row.get("id") or "",
                row.get("account") or "",
                row.get("value_date") or "",
                row.get("amount") or "",
                row.get("uniqueness") or "",
                row.get("gate") or "",
                row.get("cls") or "",
                playbook_for(str(row.get("cls") or "")),
                "false",
            ]
        )
    return buf.getvalue()


def close_markdown(
    pack: Any,
    bridge: Mapping[str, Any],
    radar: Mapping[str, Any],
    cert: Mapping[str, Any],
) -> str:
    lines = [
        "# Residual Zero close pack",
        f"as_of: {pack.as_of}",
        "writes_cleared: false",
        f"sha256: {cert.get('sha256')}",
        "",
        "## Cash bridge",
        f"ledger {bridge['ledger_total_display']} · bank {bridge['bank_landed_display']} · residual {bridge['residual_display']} (unplugged)",
        f"journalable {bridge['journalable_display']} · unreconciled {bridge['unreconciled_display']}",
        "",
        "## Tax radar (rate table, not GSTN)",
        f"GST posted {radar['gst_posted_display']} expected {radar['gst_expected_display']} delta {radar['gst_delta_display']}",
        f"TDS posted {radar['tds_posted_display']} expected {radar['tds_expected_display']} delta {radar['tds_delta_display']}",
        "",
        "## Queue",
        f"bank uncovered {pack.n_bank_uncovered} · ledger orphans {pack.n_ledger_orphans} · tax mismatch {pack.n_tax_mismatch} · human {pack.n_human}",
        "",
        "Search auto-clear 0. Overlay does not write CLEARED.",
        "",
    ]
    return "\n".join(lines)


def prometheus_text(
    *,
    n_credits: int,
    n_gate_a: int,
    n_human: int,
    n_auto_cleared: int,
) -> str:
    return (
        "# HELP rz_auto_clear Search auto-clear count. Product is 0 when uniqueness is AMBIGUOUS.\n"
        "# TYPE rz_auto_clear gauge\n"
        f"rz_auto_clear {n_auto_cleared}\n"
        "# HELP rz_gate_a Gate A accepted declared stacks.\n"
        "# TYPE rz_gate_a gauge\n"
        f"rz_gate_a {n_gate_a}\n"
        "# HELP rz_human Human queue size.\n"
        "# TYPE rz_human gauge\n"
        f"rz_human {n_human}\n"
        "# HELP rz_credits Posted bank credits.\n"
        "# TYPE rz_credits gauge\n"
        f"rz_credits {n_credits}\n"
        "# HELP rz_writes_cleared Always 0 on the overlay.\n"
        "# TYPE rz_writes_cleared gauge\n"
        "rz_writes_cleared 0\n"
    )


def normalise_work_status(raw: str) -> str:
    wanted = (raw or "open").strip().casefold()
    if wanted == "cleared":
        raise ValueError("work status cannot be CLEARED")
    if wanted not in WORK_STATUSES:
        raise ValueError(f"unknown work status {raw!r}")
    return wanted


def normalise_resolution(raw: str) -> str:
    """Closed set, same shape as :func:`normalise_work_status`.

    The resolution is persisted and rendered back into the exception queue, so it is a closed
    vocabulary rather than free text. ``cleared`` is refused explicitly: a human note in the
    overlay is not a deterministic clear (ADR-11).
    """
    wanted = (raw or "escalate").strip().casefold()
    if wanted == "cleared":
        raise ValueError("resolution cannot be CLEARED; the overlay does not write CLEARED")
    if wanted not in RESOLUTIONS:
        raise ValueError(f"unknown resolution {raw!r}")
    return wanted


def exposure_queue(
    credits: Sequence[BankCredit],
    overlay: Overlay | None,
    as_of,
    limit: int = 8,
) -> dict[str, Any]:
    """Human queue ranked by |amount| × (age+1). Not a matcher. Age vs corpus as-of."""
    from residual_zero.console.close_ops import gate_refused, sla_age_days

    rows: list[dict[str, Any]] = []
    for credit in credits:
        gate = overlay.by_id.get(credit.id) if overlay is not None else None
        if not gate_refused(gate):
            continue
        age = sla_age_days(credit.value_date, as_of) if as_of is not None else 0
        mag = credit.amount_paise if credit.amount_paise >= 0 else -credit.amount_paise
        score = mag * (age + 1)
        rows.append(
            {
                "id": credit.id,
                "account": credit.account_id,
                "value_date": credit.value_date.isoformat(),
                "amount_display": format_rupees(credit.amount_paise),
                "age_days": age,
                "score": score,
                "href": "/credit/" + credit.id,
                "writes_cleared": False,
            }
        )
    rows.sort(key=lambda row: (-int(row["score"]), str(row["id"])))
    return {
        "n": len(rows),
        "rows": rows[:limit],
        "writes_cleared": False,
        "note": "Ranked |amount| × (age+1) on Gate A refused. Overlay does not write CLEARED.",
    }


def duplicate_utr_rows(credits: Sequence[BankCredit], limit: int = 12) -> dict[str, Any]:
    groups: dict[str, list[BankCredit]] = defaultdict(list)
    for credit in credits:
        if credit.utr:
            groups[credit.utr].append(credit)
    rows = []
    for utr, bucket in sorted(groups.items(), key=lambda kv: kv[0]):
        if len(bucket) < 2:
            continue
        total = 0
        for credit in bucket:
            total += credit.amount_paise
        rows.append(
            {
                "utr": utr,
                "n": len(bucket),
                "ids": [c.id for c in bucket],
                "amount_display": format_rupees(total),
                "href": "/credit/" + bucket[0].id,
                "writes_cleared": False,
            }
        )
    return {
        "n": len(rows),
        "rows": rows[:limit],
        "writes_cleared": False,
        "note": "Same UTR on two credits. Confirm with the bank. Overlay does not write CLEARED.",
    }


def amount_twin_rows(credits: Sequence[BankCredit], limit: int = 12) -> dict[str, Any]:
    groups: dict[tuple[str, int], list[BankCredit]] = defaultdict(list)
    for credit in credits:
        groups[(credit.account_id, credit.amount_paise)].append(credit)
    rows = []
    seen: set[tuple[str, ...]] = set()
    for (account, paise), bucket in groups.items():
        if len(bucket) < 2:
            continue
        hit_ids = []
        for credit in bucket:
            for other in bucket:
                delta = other.value_date - credit.value_date
                days = delta.days if delta.days >= 0 else -delta.days
                if other.id != credit.id and days <= 1:
                    hit_ids.append(credit.id)
                    break
        uniq = tuple(sorted(set(hit_ids)))
        if len(uniq) < 2 or uniq in seen:
            continue
        seen.add(uniq)
        rows.append(
            {
                "account": account,
                "amount_display": format_rupees(paise),
                "n": len(uniq),
                "ids": list(uniq),
                "href": "/credit/" + uniq[0],
                "writes_cleared": False,
            }
        )
    return {
        "n": len(rows),
        "rows": rows[:limit],
        "writes_cleared": False,
        "note": "Same account and amount within 1 day. Overlay does not write CLEARED.",
    }


def four_way_gaps(
    credits: Sequence[BankCredit],
    by_credit: Mapping[str, Sequence[Any]],
    ledger: Mapping[str, LedgerItem],
    overlay: Overlay | None,
    limit: int = 8,
) -> dict[str, Any]:
    from residual_zero.console.close_ops import four_way_identity

    missing: Counter[str] = Counter()
    n_full = 0
    almost: list[dict[str, Any]] = []
    for credit in credits:
        declared = tuple(by_credit.get(credit.id) or ())
        gate = overlay.by_id.get(credit.id) if overlay is not None else None
        residual = gate.residual_paise if gate is not None else None
        ident = four_way_identity(credit, declared, ledger, residual)
        if ident["n_hit"] == 4:
            n_full += 1
            continue
        if not ident["utr"]:
            missing["utr"] += 1
        if not ident["settlement"]:
            missing["settlement"] += 1
        if not ident["named_ledger"]:
            missing["named_ledger"] += 1
        if not ident["residual_zero"]:
            missing["residual_zero"] += 1
        if ident["n_hit"] == 3:
            almost.append(
                {
                    "id": credit.id,
                    "n_hit": 3,
                    "missing": [name for name in ("utr", "settlement", "named_ledger", "residual_zero") if not ident[name]],
                    "href": "/credit/" + credit.id,
                    "writes_cleared": False,
                }
            )
    return {
        "n_full": n_full,
        "n_credits": len(credits),
        "missing_utr": missing["utr"],
        "missing_settlement": missing["settlement"],
        "missing_named_ledger": missing["named_ledger"],
        "missing_residual_zero": missing["residual_zero"],
        "almost": almost[:limit],
        "writes_cleared": False,
        "note": "Four-way identity gaps. Evidence only. Overlay does not write CLEARED.",
    }


def standup_markdown(
    pack: Any,
    bridge: Mapping[str, Any],
    radar: Mapping[str, Any],
    cert: Mapping[str, Any],
    exposure: Mapping[str, Any],
    dupes: Mapping[str, Any],
    gaps: Mapping[str, Any],
) -> str:
    top = []
    for row in list(exposure.get("rows") or [])[:5]:
        top.append(f"- {row.get('id')} · {row.get('amount_display')} · age {row.get('age_days')}d")
    lines = [
        "# Residual Zero standup",
        f"as_of: {pack.as_of}",
        "writes_cleared: false",
        f"sha256: {cert.get('sha256')}",
        "",
        f"Human queue {pack.n_human}. Bank uncovered {pack.n_bank_uncovered}. Tax mismatch {pack.n_tax_mismatch}.",
        f"Cash residual {bridge.get('residual_display')} (unplugged). GST delta {radar.get('gst_delta_display')}.",
        f"Four-way full {gaps.get('n_full')}/{gaps.get('n_credits')}. Duplicate UTR groups {dupes.get('n')}.",
        "",
        "## Work first (exposure rank)",
        *(top or ["- (empty human queue)"]),
        "",
        "Search auto-clear 0. Overlay does not write CLEARED.",
        "",
    ]
    return "\n".join(lines)


def close_bundle_zip(
    *,
    close_md: str,
    standup_md: str,
    cert: Mapping[str, Any],
    exceptions_csv_text: str,
) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("close.md", close_md)
        archive.writestr("standup.md", standup_md)
        archive.writestr("certificate.json", json.dumps(dict(cert), sort_keys=True, indent=2) + "\n")
        archive.writestr("exceptions.csv", exceptions_csv_text)
    return buf.getvalue()


def utr_siblings(credits: Sequence[BankCredit], credit_id: str) -> dict[str, Any]:
    """Other credits sharing this UTR. Evidence only — not a clear or a match."""
    found = next((row for row in credits if row.id == credit_id), None)
    if found is None or not found.utr:
        return {"utr": "", "n": 0, "ids": [], "writes_cleared": False}
    ids = [row.id for row in credits if row.utr == found.utr and row.id != credit_id]
    return {
        "utr": found.utr,
        "n": len(ids),
        "ids": ids,
        "writes_cleared": False,
        "note": "Same UTR on another credit. Confirm with the bank. Overlay does not write CLEARED.",
    }

