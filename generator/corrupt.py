"""Stage 3: corruption of rendered views only. Ground truth is not mutated (NN-7)."""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import IntEnum
from random import Random
from typing import Callable, NamedTuple

from residual_zero.config import MerchantProfile
from residual_zero.models import Kind
from residual_zero.money import apply_bps, format_rupees, is_whole_rupee, to_rupee_units
from residual_zero.normalise import parse_rupee_display
from residual_zero.tz import IST, IST_UTC_OFFSET_SECONDS, ensure_utc, to_ist_display

from .render import RenderedViews
from .scenario import add_business_days, is_business_day
from .truth import TruthRecord, TruthSet


class CorruptionClass(IntEnum):
    CLEAN_1_1 = 1
    AGGREGATE_N_1 = 2
    SPLIT_1_N = 3
    MIXED_N_M = 4
    AMOUNT_TRANSPOSE = 5
    DATE_SHIFT_TZ = 6
    OFF_BY_ONE_DAY = 7
    PARTIAL_PAYMENT = 8
    OVERPAYMENT = 9
    DUPLICATE_CREDIT = 10
    MISSING_REFUND = 11
    NETTED_FEE = 12
    WITHHOLDING_GAP = 13
    GST_ON_FEE_OMITTED = 14
    ROUNDING_RESIDUE = 15
    NARRATION_TRUNCATION = 16
    NARRATION_NOISE = 17
    SIGN_REVERSAL = 18
    CHARGEBACK_REPRESENTMENT = 19
    PRIOR_PERIOD_ADJUSTMENT = 20
    RESERVE_HOLD_RELEASE = 21
    BANK_CHARGE = 22
    AMBIGUOUS_BY_CONSTRUCTION = 23
    FEE_RATE_DRIFT = 24
    CROSS_ACCOUNT_MISPOSTING = 25
    FX_ROUNDING_RESIDUE = 26


FORBIDDEN_UNTIL_PHASE4 = frozenset({25, 26})

# Parameter ranges. Range B strictly contains range A for every parameterised class (D4).
RANGE_A: dict[int, dict[str, int | tuple[int, ...]]] = {
    5: {"delta_paise_max": 90_000},
    6: {"items": 1},
    7: {"day_offsets": (1,)},
    8: {"short_bps_max": 500},
    9: {"over_bps_max": 500},
    10: {"date_jitter_days": 0},
    11: {"refunds": 1},
    12: {"fee_lines": 1},
    15: {"members_max": 10},
    16: {"truncate_chars": 35},
    17: {"transforms": 1},
    18: {"items": 1},
    20: {"adjustments": 1},
    22: {"debits": 1},
}
RANGE_B: dict[int, dict[str, int | tuple[int, ...]]] = {
    5: {"delta_paise_max": 9_000_000},
    6: {"items": 3},
    7: {"day_offsets": (-2, -1, 1, 2)},
    8: {"short_bps_max": 2000},
    9: {"over_bps_max": 2000},
    10: {"date_jitter_days": 1},
    11: {"refunds": 3},
    12: {"fee_lines": 5},
    15: {"members_max": 40},
    16: {"truncate_chars": 30},  # 30–35; the min is wider than A's exact 35
    17: {"transforms": 3},
    18: {"items": 2},
    20: {"adjustments": 3},
    22: {"debits": 3},
}

MUTATION_CLASSES: tuple[int, ...] = tuple(range(5, 24))
HELD_OUT_DEV = 9  # OVERPAYMENT, D4.8. Frozen in docs/EVALUATION.md at CP2.


class CorruptionPlan(NamedTuple):
    range_id: str
    apply_class_23: bool
    class23_count: int
    stacked: bool
    mutation_classes: tuple[int, ...]
    held_out_class: int | None
    per_class_target: int


def phase1_dev_plan() -> CorruptionPlan:
    return plan_for_range("A", stacked=False, held_out_class=HELD_OUT_DEV)


def plan_for_profile(profile: MerchantProfile) -> CorruptionPlan:
    # Held-out means absent from DEV, present on TEST (D4.8). The test profile records
    # held_out_class: 9 as documentation; we still *apply* class 9 on range B.
    held = HELD_OUT_DEV if profile.corruption_range == "A" else None
    return plan_for_range(
        profile.corruption_range,
        stacked=profile.stacked_corruptions,
        held_out_class=held,
    )


def phase2_drift_plan() -> CorruptionPlan:
    """Class 24 only. Does not regenerate the Phase 1 corpus."""
    return CorruptionPlan(
        range_id="A",
        apply_class_23=False,
        class23_count=0,
        stacked=False,
        mutation_classes=(24,),
        held_out_class=None,
        per_class_target=3,
    )


def phase4_class25_plan() -> CorruptionPlan:
    """Class 25 only. Does not regenerate data/dev."""
    return CorruptionPlan(
        range_id="P4",
        apply_class_23=False,
        class23_count=0,
        stacked=False,
        mutation_classes=(25,),
        held_out_class=None,
        per_class_target=3,
    )


def phase4_fx_plan() -> CorruptionPlan:
    """Class 26 only. Does not regenerate data/dev."""
    return CorruptionPlan(
        range_id="P4",
        apply_class_23=False,
        class23_count=0,
        stacked=False,
        mutation_classes=(26,),
        held_out_class=None,
        per_class_target=3,
    )


def plan_for_range(range_id: str, *, stacked: bool, held_out_class: int | None) -> CorruptionPlan:
    # Targets are PER SEED. Dev has 3 seeds, test 5, and each seed has ~80–160 credits,
    # so a target of 8-per-seed would exhaust the seed before class 22.
    if range_id == "A":
        target, c23 = 3, 4
    else:
        target, c23 = 5, 6
    return CorruptionPlan(
        range_id=range_id,
        apply_class_23=True,
        class23_count=c23,
        stacked=stacked,
        mutation_classes=MUTATION_CLASSES,
        held_out_class=held_out_class,
        per_class_target=target,
    )


def apply_corruptions(
    views: RenderedViews,
    truth: TruthSet,
    plan: CorruptionPlan,
    rng: Random,
) -> tuple[RenderedViews, tuple[TruthRecord, ...]]:
    """Mutate rendered views only. member_ids and total_paise of every record stay identical."""
    if FORBIDDEN_UNTIL_PHASE4 & set(plan.mutation_classes) and plan.range_id != "P4":
        raise ValueError("corruption classes 25 and 26 are forbidden outside a Phase 4 plan")
    original = {r.bank_credit_id: (r.member_ids, r.total_paise) for r in truth.records}
    records = list(truth.records)
    ledger_rows = list(views.ledger_rows)
    bank_rows = list(views.bank_rows)
    settlement_rows = list(views.settlement_rows)
    ranges = RANGE_A if plan.range_id == "A" else RANGE_B

    if plan.apply_class_23:
        ledger_rows, records = _apply_class_23(
            ledger_rows, records, truth, plan.class23_count, rng, replace=not plan.stacked,
        )

    claimed = {r.bank_credit_id for r in records if 23 in r.corruption_classes}
    if not plan.stacked:
        # Keep at least two credits of each structural class so 1–4 survive relabelling.
        for structural in (1, 2, 3, 4):
            keep = [
                r.bank_credit_id for r in records
                if structural in r.corruption_classes and r.bank_credit_id not in claimed
            ][:2]
            claimed.update(keep)
    for class_id in plan.mutation_classes:
        if class_id == 23:
            continue
        if plan.held_out_class is not None and class_id == plan.held_out_class:
            continue
        ledger_rows, bank_rows, settlement_rows, records, claimed = _apply_mutation(
            class_id, ledger_rows, bank_rows, settlement_rows, records, truth,
            plan, ranges, rng, claimed,
        )

    if plan.stacked:
        records = _stack_second_class(records, rng)

    for record in records:
        before = original[record.bank_credit_id]
        if record.member_ids != before[0] or record.total_paise != before[1]:
            raise AssertionError(f"NN-7 violation: truth mutated for {record.bank_credit_id}")
        if plan.held_out_class is not None and plan.held_out_class in record.corruption_classes:
            raise AssertionError(f"held-out class {plan.held_out_class} leaked onto {record.bank_credit_id}")
    if not plan.stacked:
        for record in records:
            if len(record.corruption_classes) > 1:
                # Structural 1-4 plus a mutation is stacking. On dev, replace was requested.
                pass
    return (
        RenderedViews(
            bank_rows=tuple(bank_rows),
            ledger_rows=tuple(ledger_rows),
            settlement_rows=tuple(settlement_rows),
        ),
        tuple(records),
    )


def _label(record: TruthRecord, class_id: int, stacked: bool) -> TruthRecord:
    if stacked:
        classes = tuple(sorted(set(record.corruption_classes) | {class_id}))
    else:
        classes = (class_id,)
    return record.model_copy(update={"corruption_classes": classes})


def _apply_class_23(
    ledger_rows: list[dict[str, str]],
    records: list[TruthRecord],
    truth: TruthSet,
    count: int,
    rng: Random,
    *,
    replace: bool,
) -> tuple[list[dict[str, str]], list[TruthRecord]]:
    items_by_id = {item.id: item for item in truth.items}
    credits_by_id = {c.id: c for c in truth.credits}
    eligible: list[TruthRecord] = []
    for record in records:
        payments = [
            items_by_id[mid]
            for mid in record.member_ids
            if items_by_id[mid].kind == Kind.PAYMENT and is_whole_rupee(items_by_id[mid].amount_paise)
        ]
        if len(payments) >= 2:
            rupee_sum = to_rupee_units(payments[0].amount_paise) + to_rupee_units(payments[1].amount_paise)
            if rupee_sum >= 2:
                eligible.append(record)
    rng.shuffle(eligible)
    chosen = {r.bank_credit_id for r in eligible[:count]}
    updated: list[TruthRecord] = []
    decoy_seq = 0
    for record in records:
        if record.bank_credit_id not in chosen:
            updated.append(record)
            continue
        credit = credits_by_id[record.bank_credit_id]
        payments = [
            items_by_id[mid]
            for mid in record.member_ids
            if items_by_id[mid].kind == Kind.PAYMENT and is_whole_rupee(items_by_id[mid].amount_paise)
        ]
        payments.sort(key=lambda p: p.id)
        a1, a2 = payments[0], payments[1]
        v_rupees = to_rupee_units(a1.amount_paise) + to_rupee_units(a2.amount_paise)
        b1_rupees = v_rupees // 2
        b2_rupees = v_rupees - b1_rupees
        for rupees, suffix in ((b1_rupees, "a"), (b2_rupees, "b")):
            decoy_seq += 1
            decoy_id = f"itm_c23_{credit.id}_{suffix}_{decoy_seq:04d}"
            order_id = f"ord_c23_{credit.id}_{suffix}"
            ledger_rows.append(
                {
                    "id": decoy_id,
                    "kind": Kind.PAYMENT.value,
                    "amount": format_rupees(rupees * 100),
                    "occurred_at": to_ist_display(a1.occurred_at),
                    "account_id": credit.account_id,
                    "currency": "INR",
                    "instrument": (a1.instrument.value if a1.instrument else ""),
                    "order_id": order_id,
                    "parent_id": "",
                    "narration_raw": f"PAYMENT {order_id} decoy",
                    "counterparty_raw": a1.counterparty_raw or "decoy",
                    "source": "INTERNAL_LEDGER",
                }
            )
        updated.append(_label(record, int(CorruptionClass.AMBIGUOUS_BY_CONSTRUCTION), stacked=not replace))
    return ledger_rows, updated


def _stack_second_class(records: list[TruthRecord], rng: Random) -> list[TruthRecord]:
    """Give some test-split credits a second (or third) class id so stacking is real."""
    extra_pool = [5, 10, 12, 13, 14, 16, 17]
    rng.shuffle(extra_pool)
    updated: list[TruthRecord] = []
    stacked_n = 0
    for rec in records:
        if stacked_n >= 80:
            updated.append(rec)
            continue
        extra = extra_pool[stacked_n % len(extra_pool)]
        if extra in rec.corruption_classes:
            updated.append(rec)
            continue
        classes = tuple(sorted(set(rec.corruption_classes) | {extra}))
        updated.append(rec.model_copy(update={"corruption_classes": classes}))
        stacked_n += 1
    return updated


def _pick(records: list[TruthRecord], claimed: set[str], n: int, rng: Random,
          pred: Callable[[TruthRecord], bool] | None = None) -> list[str]:
    pool = [r for r in records if r.bank_credit_id not in claimed and (pred is None or pred(r))]
    rng.shuffle(pool)
    return [r.bank_credit_id for r in pool[:n]]


def _apply_mutation(
    class_id: int,
    ledger_rows: list[dict[str, str]],
    bank_rows: list[dict[str, str]],
    settlement_rows: list[dict[str, str]],
    records: list[TruthRecord],
    truth: TruthSet,
    plan: CorruptionPlan,
    ranges: dict[int, dict[str, int | tuple[int, ...]]],
    rng: Random,
    claimed: set[str],
) -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]], list[TruthRecord], set[str]]:
    target = plan.per_class_target
    rec_by_id = {r.bank_credit_id: r for r in records}
    chosen = _pick(records, claimed, target, rng)
    if len(chosen) < 1:
        return ledger_rows, bank_rows, settlement_rows, records, claimed
    for cid in chosen:
        rec = rec_by_id[cid]
        ledger_rows, bank_rows, settlement_rows = _mutate(
            class_id, cid, rec, ledger_rows, bank_rows, settlement_rows, truth, ranges, rng,
        )
        claimed.add(cid)
    new_records = []
    for rec in records:
        if rec.bank_credit_id in chosen:
            new_records.append(_label(rec, class_id, stacked=plan.stacked))
        else:
            new_records.append(rec)
    return ledger_rows, bank_rows, settlement_rows, new_records, claimed


def _mutate(
    class_id: int,
    credit_id: str,
    rec: TruthRecord,
    ledger_rows: list[dict[str, str]],
    bank_rows: list[dict[str, str]],
    settlement_rows: list[dict[str, str]],
    truth: TruthSet,
    ranges: dict[int, dict[str, int | tuple[int, ...]]],
    rng: Random,
) -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]:
    members = set(rec.member_ids)
    if class_id == 5:
        max_delta = int(ranges[5]["delta_paise_max"])  # type: ignore[arg-type]
        for row in ledger_rows:
            if row["id"] not in members:
                continue
            amt = parse_rupee_display(row["amount"])
            swapped = _transpose(amt, rng, max_delta)
            if swapped is not None:
                row["amount"] = format_rupees(swapped)
                break
    elif class_id == 6:
        for row in ledger_rows:
            if row["id"] not in members:
                continue
            row["occurred_at"] = _shift_ist(row["occurred_at"], IST_UTC_OFFSET_SECONDS)
            break
    elif class_id == 7:
        offsets: tuple[int, ...] = ranges[7]["day_offsets"]  # type: ignore[assignment]
        offset = offsets[rng.randrange(len(offsets))]
        for row in bank_rows:
            if row["id"] != credit_id:
                continue
            day = datetime.fromisoformat(row["value_date"]).date()
            if offset > 0:
                row["value_date"] = add_business_days(day, offset).isoformat()
            else:
                cur = day
                for _ in range(-offset):
                    cur = cur - timedelta(days=1)
                    while not is_business_day(cur):
                        cur = cur - timedelta(days=1)
                row["value_date"] = cur.isoformat()
            break
    elif class_id == 8:
        bps_max = int(ranges[8]["short_bps_max"])  # type: ignore[arg-type]
        bps = 100 + rng.randrange(max(1, bps_max - 99))
        for row in ledger_rows:
            if row["id"] not in members or row["kind"] != Kind.PAYMENT.value:
                continue
            amt = parse_rupee_display(row["amount"])
            short = amt - (amt * bps // 10_000)
            if short != 0 and short != amt:
                row["amount"] = format_rupees(short)
                for srow in settlement_rows:
                    if srow["item_id"] == row["id"]:
                        srow["amount"] = row["amount"]
                break
    elif class_id == 9:
        bps_max = int(ranges[9]["over_bps_max"])  # type: ignore[arg-type]
        bps = 100 + rng.randrange(max(1, bps_max - 99))
        for row in bank_rows:
            if row["id"] != credit_id:
                continue
            amt = parse_rupee_display(row["amount"])
            over = amt + (amt * bps // 10_000)
            if over > amt:
                row["amount"] = format_rupees(over)
            break
    elif class_id == 10:
        for row in list(bank_rows):
            if row["id"] != credit_id:
                continue
            dup = dict(row)
            dup["id"] = row["id"] + "_dup"
            dup["narration_raw"] = row["narration_raw"] + " DUP"
            bank_rows.append(dup)
            break
    elif class_id == 11:
        drop_n = int(ranges[11]["refunds"])  # type: ignore[arg-type]
        dropped = 0
        keep: list[dict[str, str]] = []
        for row in ledger_rows:
            if dropped < drop_n and row["id"] in members and row["kind"] == Kind.REFUND.value:
                dropped += 1
                continue
            keep.append(row)
        ledger_rows = keep
    elif class_id == 12:
        drop_n = int(ranges[12]["fee_lines"])  # type: ignore[arg-type]
        drop_ids: set[str] = set()
        dropped = 0
        keep = []
        for row in ledger_rows:
            if dropped < drop_n and row["id"] in members and row["kind"] == Kind.FEE.value:
                drop_ids.add(row["id"])
                dropped += 1
                continue
            keep.append(row)
        ledger_rows = keep
        settlement_rows = [s for s in settlement_rows if s["item_id"] not in drop_ids]
    elif class_id == 13:
        drop_ids = {row["id"] for row in ledger_rows if row["id"] in members and row["kind"] == Kind.TAX_WITHHOLDING.value}
        ledger_rows = [r for r in ledger_rows if r["id"] not in drop_ids]
    elif class_id == 14:
        drop_ids = {row["id"] for row in ledger_rows if row["id"] in members and row["kind"] == Kind.TAX_GST.value}
        ledger_rows = [r for r in ledger_rows if r["id"] not in drop_ids]
        settlement_rows = [s for s in settlement_rows if s["item_id"] not in drop_ids]
    elif class_id == 15:
        cap = int(ranges[15]["members_max"])  # type: ignore[arg-type]
        touched = 0
        for row in ledger_rows:
            if touched >= cap:
                break
            if row["id"] not in members or row["kind"] != Kind.FEE.value:
                continue
            amt = parse_rupee_display(row["amount"])
            # Opposite rounding residue: nudge one paise toward zero.
            if amt < 0:
                row["amount"] = format_rupees(amt + 1 if amt != -1 else amt - 1)
            elif amt > 0:
                row["amount"] = format_rupees(amt - 1 if amt != 1 else amt + 1)
            touched += 1
    elif class_id == 16:
        nchars = int(ranges[16]["truncate_chars"])  # type: ignore[arg-type]
        for row in bank_rows:
            if row["id"] != credit_id:
                continue
            row["narration_raw"] = row["narration_raw"][:nchars]
            break
    elif class_id == 17:
        for row in ledger_rows:
            if row["id"] not in members:
                continue
            row["narration_raw"] = row["narration_raw"].upper().replace(" ", "  ")
            row["counterparty_raw"] = (row.get("counterparty_raw") or "").replace("i", "ı")
            break
        for row in bank_rows:
            if row["id"] != credit_id:
                continue
            row["narration_raw"] = row["narration_raw"].lower()
            break
    elif class_id == 18:
        for row in ledger_rows:
            if row["id"] not in members:
                continue
            amt = parse_rupee_display(row["amount"])
            row["amount"] = format_rupees(-amt)
            break
    elif class_id == 19:
        # Distractors: a chargeback and a representment, not in the answer key.
        ledger_rows.append(_decoy_row(credit_id, "CHARGEBACK", -50_000, rec, "c19cb"))
        ledger_rows.append(_decoy_row(credit_id, "REPRESENTMENT", 50_000, rec, "c19rp"))
    elif class_id == 20:
        ledger_rows.append(_decoy_row(credit_id, "ADJUSTMENT", -10_000, rec, "c20adj"))
    elif class_id == 21:
        ledger_rows.append(_decoy_row(credit_id, "RESERVE_RELEASE", 25_000, rec, "c21rel"))
    elif class_id == 22:
        ledger_rows.append(_decoy_row(credit_id, "BANK_CHARGE", -1_180, rec, "c22bc"))
    elif class_id == 24:
        # Scale CARD fee lines of this credit. Truth member_ids unchanged (NN-7).
        new_bps = 220
        card_gross = 0
        fee_ids: list[str] = []
        items_by_id = {it.id: it for it in truth.items}
        for mid in rec.member_ids:
            item = items_by_id.get(mid)
            if item is None:
                continue
            if item.kind == Kind.PAYMENT and item.instrument and item.instrument.value == "CARD":
                card_gross += item.amount_paise
            if item.kind == Kind.FEE and item.instrument and item.instrument.value == "CARD":
                fee_ids.append(mid)
        if card_gross > 0 and fee_ids:
            new_fee = -apply_bps(card_gross, new_bps)
            for row in ledger_rows:
                if row["id"] == fee_ids[0]:
                    row["amount"] = format_rupees(new_fee)
                    break
            for srow in settlement_rows:
                if srow["item_id"] == fee_ids[0]:
                    srow["amount"] = format_rupees(new_fee)
    elif class_id == 25:
        accounts = sorted({row["account_id"] for row in bank_rows})
        if len(accounts) >= 2:
            for row in bank_rows:
                if row["id"] != credit_id:
                    continue
                other = next(a for a in accounts if a != row["account_id"])
                row["account_id"] = other
                break
    elif class_id == 26:
        residue = 1 + rng.randrange(99)
        for row in bank_rows:
            if row["id"] != credit_id:
                continue
            amt = parse_rupee_display(row["amount"])
            row["amount"] = format_rupees(amt + residue)
            break
    return ledger_rows, bank_rows, settlement_rows


def _decoy_row(credit_id: str, kind: str, amount_paise: int, rec: TruthRecord, tag: str) -> dict[str, str]:
    credit = credit_id
    return {
        "id": f"itm_{tag}_{credit}",
        "kind": kind,
        "amount": format_rupees(amount_paise),
        "occurred_at": "2025-01-20 12:00:00 IST",
        "account_id": "_".join(credit.split("_")[2:4]),
        "currency": "INR",
        "instrument": "",
        "order_id": "",
        "parent_id": "",
        "narration_raw": f"{kind} decoy {tag}",
        "counterparty_raw": "decoy",
        "source": "INTERNAL_LEDGER",
    }


def _transpose(amount_paise: int, rng: Random, max_delta: int) -> int | None:
    sign = 1 if amount_paise > 0 else -1
    digits = list(str(abs(amount_paise)))
    if len(digits) < 4:
        return None
    rupee = digits[:-2]
    for _ in range(24):
        idx = rng.randrange(len(rupee) - 1)
        if rupee[idx] == rupee[idx + 1]:
            continue
        trial = rupee[:]
        trial[idx], trial[idx + 1] = trial[idx + 1], trial[idx]
        new_abs = int("".join(trial + digits[-2:]))
        if new_abs == 0:
            continue
        if abs(new_abs - abs(amount_paise)) <= max_delta:
            return sign * new_abs
    return None


def _shift_ist(display: str, seconds: int) -> str:
    raw = display[: -len(" IST")] if display.endswith(" IST") else display
    naive = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
    aware = ensure_utc(naive.replace(tzinfo=IST))
    shifted = aware + timedelta(seconds=seconds)
    return to_ist_display(shifted)
