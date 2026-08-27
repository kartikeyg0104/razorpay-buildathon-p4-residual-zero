"""Stage 3: corruption of rendered views only. Ground truth is not mutated (NN-7)."""

from __future__ import annotations

from enum import IntEnum
from random import Random
from typing import NamedTuple

from residual_zero.models import Kind
from residual_zero.money import format_rupees, is_whole_rupee, to_rupee_units
from residual_zero.tz import to_ist_display

from .render import RenderedViews
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
    # 24, 25, 26 are FORBIDDEN in Phase 1: their detectors do not exist yet.


FORBIDDEN_PHASE1 = frozenset({24, 25, 26})


class CorruptionPlan(NamedTuple):
    range_id: str
    apply_class_23: bool
    class23_count: int
    stacked: bool
    mutation_classes: tuple[int, ...]


def phase1_dev_plan() -> CorruptionPlan:
    """CP1: structural classes 1–4 already sit on the records; the only mutation is class 23."""
    return CorruptionPlan(
        range_id="A",
        apply_class_23=True,
        class23_count=12,
        stacked=False,
        mutation_classes=(23,),
    )


def apply_corruptions(
    views: RenderedViews,
    truth: TruthSet,
    plan: CorruptionPlan,
    rng: Random,
) -> tuple[RenderedViews, tuple[TruthRecord, ...]]:
    """Mutate rendered views only. member_ids and total_paise of every record stay identical."""
    if FORBIDDEN_PHASE1 & set(plan.mutation_classes):
        raise ValueError("corruption classes 24, 25, 26 are forbidden in Phase 1")
    original = {r.bank_credit_id: (r.member_ids, r.total_paise) for r in truth.records}
    records = list(truth.records)
    ledger_rows = list(views.ledger_rows)
    bank_rows = list(views.bank_rows)
    settlement_rows = list(views.settlement_rows)

    if plan.apply_class_23:
        ledger_rows, records = _apply_class_23(
            ledger_rows, records, truth, plan.class23_count, rng,
        )

    for record in records:
        before = original[record.bank_credit_id]
        if record.member_ids != before[0] or record.total_paise != before[1]:
            raise AssertionError(
                f"NN-7 violation: truth mutated for {record.bank_credit_id}"
            )
    return (
        RenderedViews(
            bank_rows=tuple(bank_rows),
            ledger_rows=tuple(ledger_rows),
            settlement_rows=tuple(settlement_rows),
        ),
        tuple(records),
    )


def _apply_class_23(
    ledger_rows: list[dict[str, str]],
    records: list[TruthRecord],
    truth: TruthSet,
    count: int,
    rng: Random,
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
    chosen = {r.bank_credit_id: r for r in eligible[:count]}
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
            occurred = to_ist_display(a1.occurred_at)
            narration = f"PAYMENT {order_id} decoy"
            ledger_rows.append(
                {
                    "id": decoy_id,
                    "kind": Kind.PAYMENT.value,
                    "amount": format_rupees(rupees * 100),
                    "occurred_at": occurred,
                    "account_id": credit.account_id,
                    "currency": "INR",
                    "instrument": (a1.instrument.value if a1.instrument else ""),
                    "order_id": order_id,
                    "parent_id": "",
                    "narration_raw": narration,
                    "counterparty_raw": a1.counterparty_raw or "decoy",
                    "source": "INTERNAL_LEDGER",
                }
            )
        classes = tuple(sorted(set(record.corruption_classes) | {int(CorruptionClass.AMBIGUOUS_BY_CONSTRUCTION)}))
        updated.append(
            record.model_copy(update={"corruption_classes": classes})
        )
    return ledger_rows, updated
