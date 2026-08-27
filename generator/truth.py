"""Stage 2: the answer key. Computed exactly from the payment stream and the rate config."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime
from random import Random
from typing import NamedTuple

from pydantic import BaseModel, ConfigDict

from residual_zero.config import FeeSchedule, TaxRates
from residual_zero.models import (
    BankCredit,
    Instrument,
    Kind,
    LedgerItem,
    Regime,
    Source,
    has_expected_sign,
)
from residual_zero.money import apply_bps, subrupee_count
from residual_zero.normalise import normalise_narration
from residual_zero.tz import IST, ensure_utc, to_ist_date_display

from .scenario import Order, Scenario, add_business_days, settlement_date_for

_STRICT = ConfigDict(frozen=True, extra="forbid")


class TruthRecord(BaseModel):
    """One credit's answer key. Written to truth.jsonl, which src/ cannot open."""

    model_config = _STRICT

    bank_credit_id: str
    member_ids: tuple[str, ...]
    total_paise: int
    regime: Regime
    corruption_classes: tuple[int, ...]
    cause_labels: dict[str, str]
    subrupee_member_count: int


class TruthSet(NamedTuple):
    items: tuple[LedgerItem, ...]
    credits: tuple[BankCredit, ...]
    records: tuple[TruthRecord, ...]


def _ist(day: date, hour: int, minute: int, second: int = 0) -> datetime:
    return ensure_utc(datetime(day.year, day.month, day.day, hour, minute, second, tzinfo=IST))


class _Factory:
    def __init__(self, seed: int) -> None:
        self._seed = seed
        self._seq = 0

    def item_id(self) -> str:
        self._seq += 1
        return f"itm_{self._seed:03d}_{self._seq:06d}"


def _item(
    factory: _Factory,
    *,
    kind: Kind,
    amount_paise: int,
    occurred_at: datetime,
    account_id: str,
    instrument: Instrument | None,
    order_id: str | None,
    parent_id: str | None,
    narration_raw: str,
    counterparty_raw: str | None,
    source: Source,
) -> LedgerItem:
    return LedgerItem(
        id=factory.item_id(),
        kind=kind,
        amount_paise=amount_paise,
        occurred_at=occurred_at,
        account_id=account_id,
        currency="INR",
        instrument=instrument,
        order_id=order_id,
        parent_id=parent_id,
        narration_raw=narration_raw,
        narration_norm=normalise_narration(narration_raw),
        counterparty_raw=counterparty_raw,
        counterparty_id=None,
        source=source,
    )


def build_truth(scenario: Scenario, rates: TaxRates, fees: FeeSchedule) -> TruthSet:
    """Compute settlements exactly. Asserts signed members sum to the credit at paise."""
    profile = scenario.profile
    rng = Random(scenario.seed + 10_003)
    factory = _Factory(scenario.seed)

    # Map each order to a settlement date. Orders that fall off the horizon are dropped.
    home: dict[str, date] = {}
    for order in scenario.orders:
        capture = to_ist_date_display(order.captured_at)
        capture_date = date.fromisoformat(capture)
        settle = settlement_date_for(
            capture_date, scenario.settlement_dates, profile.settlement_cycle_days,
        )
        if settle is not None:
            home[order.order_id] = settle

    live_orders = [o for o in scenario.orders if o.order_id in home]

    # SPLIT_1_N: even-rupee split of selected orders across consecutive settlement dates.
    next_date = {d: nxt for d, nxt in zip(scenario.settlement_dates, scenario.settlement_dates[1:])}
    split_order_ids: set[str] = set()
    order_counts = Counter((o.account_id, home[o.order_id]) for o in live_orders)
    busy_order_keys = [k for k, n in order_counts.items() if n >= 5]
    busy_order_keys.sort()
    # First, split one order that will also sit in a MIXED_N_M credit, so class 4 is genuinely N:M
    # across credits (PLAN-P1 test_class4_is_genuinely_n_to_m).
    mixed_priority = busy_order_keys[:12]
    for key in mixed_priority:
        if split_order_ids:
            break
        account_id, settle = key
        if settle not in next_date:
            continue
        for order in live_orders:
            if order.account_id != account_id or home[order.order_id] != settle:
                continue
            half = (order.gross_paise // 200) * 100
            rest = order.gross_paise - half
            if half <= 0 or rest <= 0:
                continue
            split_order_ids.add(order.order_id)
            break
    candidates = [
        o for o in live_orders
        if o.order_id not in split_order_ids
        and (o.account_id != "acc_00" or home[o.order_id] != scenario.settlement_dates[0])
    ]
    rng.shuffle(candidates)
    for order in candidates:
        if len(split_order_ids) >= 10:
            break
        settle = home[order.order_id]
        nxt = next_date.get(settle)
        if nxt is None:
            continue
        half = (order.gross_paise // 200) * 100
        rest = order.gross_paise - half
        if half <= 0 or rest <= 0:
            continue
        split_order_ids.add(order.order_id)

    # Build payment items, possibly split.
    payments: list[LedgerItem] = []
    payment_settle: dict[str, date] = {}
    parent_by_order: dict[str, str] = {}
    for order in live_orders:
        settle = home[order.order_id]
        if order.order_id in split_order_ids and settle in next_date:
            half = (order.gross_paise // 200) * 100
            rest = order.gross_paise - half
            first = _payment_item(factory, order, half, settle)
            second = _payment_item(factory, order, rest, next_date[settle])
            payments.extend((first, second))
            payment_settle[first.id] = settle
            payment_settle[second.id] = next_date[settle]
            parent_by_order.setdefault(order.order_id, first.id)
        else:
            item = _payment_item(factory, order, order.gross_paise, settle)
            payments.append(item)
            payment_settle[item.id] = settle
            parent_by_order[order.order_id] = item.id

    payments_by_key: dict[tuple[str, date], list[LedgerItem]] = defaultdict(list)
    for item in payments:
        payments_by_key[(item.account_id, payment_settle[item.id])].append(item)

    # Refunds: cluster 2–4 onto busy credits so MIXED_N_M exists; skip the 1-order credits.
    refunds: list[LedgerItem] = []
    refund_settle: dict[str, date] = {}
    busy_keys = [
        key for key, group in payments_by_key.items()
        if len(group) >= 5
    ]
    busy_keys.sort()
    forced_mixed: list[tuple[str, date]] = []
    for order in live_orders:
        if order.order_id in split_order_ids:
            key = (order.account_id, home[order.order_id])
            if key in payments_by_key and key not in forced_mixed:
                forced_mixed.append(key)
    rng.shuffle(busy_keys)
    mixed_keys = set(forced_mixed[:1])
    for key in busy_keys:
        if len(mixed_keys) >= 12:
            break
        mixed_keys.add(key)
    used_orders: set[str] = set()
    for key in mixed_keys:
        account_id, settle = key
        group = payments_by_key[key]
        n_refunds = 2 + rng.randrange(0, 3)  # 2–4
        # Prefer refunding other-window payments into this settlement (cross-window).
        donors = [
            p for p in payments
            if p.account_id == account_id
            and p.order_id not in used_orders
            and p.order_id not in split_order_ids
        ]
        rng.shuffle(donors)
        made = 0
        for donor in donors:
            if made >= n_refunds:
                break
            magnitude = (donor.amount_paise // 200) * 100  # ~50%, whole rupee
            if magnitude <= 0:
                continue
            occurred = _ist(add_business_days(settle, 0), 14, rng.randrange(0, 60))
            # Shift occurred_at back 1–4 business days so the refund sits inside the window.
            lag = 1 + rng.randrange(0, 4)
            occurred_day = date.fromisoformat(to_ist_date_display(donor.occurred_at))
            try:
                refund_day = add_business_days(occurred_day, lag)
            except ValueError:
                refund_day = settle
            if refund_day > settle:
                refund_day = settle
            item = _item(
                factory,
                kind=Kind.REFUND,
                amount_paise=-magnitude,
                occurred_at=_ist(refund_day, 14, rng.randrange(0, 60)),
                account_id=account_id,
                instrument=donor.instrument,
                order_id=donor.order_id,
                parent_id=donor.id,
                narration_raw=f"REFUND {donor.order_id} {donor.counterparty_raw or ''}".strip(),
                counterparty_raw=donor.counterparty_raw,
                source=Source.INTERNAL_LEDGER,
            )
            refunds.append(item)
            refund_settle[item.id] = settle
            used_orders.add(donor.order_id or "")
            made += 1

    # Reserve-hold schedule is CP1; releases are class 21 (CP2) because a release on a
    # later settlement is a 14th sub-rupee member and breaks the D6 bound of 13.

    items: list[LedgerItem] = []
    credits: list[BankCredit] = []
    records: list[TruthRecord] = []

    keys = sorted({(p.account_id, payment_settle[p.id]) for p in payments})
    # Also include keys that only have refunds.
    keys = sorted(set(keys) | {(r.account_id, refund_settle[r.id]) for r in refunds})

    n_keys = len(keys)
    for index, (account_id, settle) in enumerate(keys):
        members: list[LedgerItem] = []
        pays = [p for p in payments if p.account_id == account_id and payment_settle[p.id] == settle]
        refs = [r for r in refunds if r.account_id == account_id and refund_settle[r.id] == settle]
        members.extend(pays)
        members.extend(refs)

        gross = sum(p.amount_paise for p in pays)
        by_instrument: dict[Instrument, int] = {}
        for payment in pays:
            assert payment.instrument is not None
            by_instrument[payment.instrument] = by_instrument.get(payment.instrument, 0) + payment.amount_paise

        for instrument in sorted(by_instrument, key=lambda i: i.value):
            inst_gross = by_instrument[instrument]
            fee_bps = fees.per_instrument_bps[instrument].bps
            fee = -apply_bps(inst_gross, fee_bps)
            if fee != 0:
                members.append(
                    _item(
                        factory,
                        kind=Kind.FEE,
                        amount_paise=fee,
                        occurred_at=_ist(settle, 18, 0),
                        account_id=account_id,
                        instrument=instrument,
                        order_id=None,
                        parent_id=None,
                        narration_raw=f"PLATFORM FEE {instrument.value} {settle.isoformat()}",
                        counterparty_raw="Razorpay",
                        source=Source.SETTLEMENT_REPORT,
                    )
                )
            gst = apply_bps(fee, rates.gst_on_fee.bps)
            if gst != 0:
                members.append(
                    _item(
                        factory,
                        kind=Kind.TAX_GST,
                        amount_paise=gst,
                        occurred_at=_ist(settle, 18, 1),
                        account_id=account_id,
                        instrument=instrument,
                        order_id=None,
                        parent_id=None,
                        narration_raw=f"GST ON FEE {instrument.value} {settle.isoformat()}",
                        counterparty_raw="Razorpay",
                        source=Source.SETTLEMENT_REPORT,
                    )
                )

        if gross > 0 and rates.withholding.bps > 0:
            if rates.withholding.base == "GROSS_PAYMENTS":
                withholding = -apply_bps(gross, rates.withholding.bps)
            else:
                fee_total = sum(-m.amount_paise for m in members if m.kind == Kind.FEE)
                withholding = -apply_bps(fee_total, rates.withholding.bps)
            if withholding != 0:
                members.append(
                    _item(
                        factory,
                        kind=Kind.TAX_WITHHOLDING,
                        amount_paise=withholding,
                        occurred_at=_ist(settle, 18, 2),
                        account_id=account_id,
                        instrument=None,
                        order_id=None,
                        parent_id=None,
                        narration_raw=f"TDS 194O {settle.isoformat()}",
                        counterparty_raw="Tax withheld",
                        source=Source.SETTLEMENT_REPORT,
                    )
                )

        if gross > 0 and profile.reserve_bps > 0:
            hold = -apply_bps(gross, profile.reserve_bps)
            if hold != 0:
                hold_item = _item(
                    factory,
                    kind=Kind.RESERVE_HOLD,
                    amount_paise=hold,
                    occurred_at=_ist(settle, 18, 3),
                    account_id=account_id,
                    instrument=None,
                    order_id=None,
                    parent_id=None,
                    narration_raw=f"RESERVE HOLD {settle.isoformat()}",
                    counterparty_raw="Rolling reserve",
                    source=Source.SETTLEMENT_REPORT,
                )
                members.append(hold_item)
                # Reserve *releases* are class 21 (CP2). Emitting them here adds a 14th
                # sub-rupee member on later settlements (hold + release + 2×5 fee/GST +
                # withholding + bank) and breaks the D6 bound of 13. Holds still deduct.

        if fees.bank_charge_paise > 0:
            members.append(
                _item(
                    factory,
                    kind=Kind.BANK_CHARGE,
                    amount_paise=-fees.bank_charge_paise,
                    occurred_at=_ist(settle, 18, 4),
                    account_id=account_id,
                    instrument=None,
                    order_id=None,
                    parent_id=None,
                    narration_raw=f"BANK CHARGE {settle.isoformat()}",
                    counterparty_raw="Merchant bank",
                    source=Source.BANK_STATEMENT,
                )
            )

        total = sum(m.amount_paise for m in members)
        if total <= 0:
            # A credit that does not land is not a BankCredit; drop the window rather than
            # invent a plug. The items still exist as unattached ledger rows.
            items.extend(members)
            continue

        credit_id = f"crd_{scenario.seed:03d}_{account_id}_{settle.isoformat()}"
        for member in members:
            if not has_expected_sign(member):
                raise AssertionError(f"stage-2 sign defect on {member.id} {member.kind}")
        member_sum = sum(m.amount_paise for m in members)
        if member_sum != total:
            raise AssertionError("internal sum mismatch")

        regime = Regime.A_DECLARED if (index * 10) < (n_keys * 7) else Regime.B_SEARCHED
        classes = _structural_classes(members, payments, payment_settle, split_order_ids)
        amounts = tuple(m.amount_paise for m in members)
        m_count = subrupee_count(amounts)
        if m_count > profile.subrupee_member_max:
            raise AssertionError(
                f"subrupee member count {m_count} exceeds profile bound {profile.subrupee_member_max}"
            )

        narration = f"NEFT RAZORPAY SETTLEMENT {account_id} {settle.isoformat()}"
        credits.append(
            BankCredit(
                id=credit_id,
                amount_paise=total,
                value_date=settle,
                account_id=account_id,
                currency="INR",
                narration_raw=narration,
                narration_norm=normalise_narration(narration),
                utr=f"UTR{scenario.seed:03d}{account_id[-2:]}{settle.strftime('%Y%m%d')}",
            )
        )
        records.append(
            TruthRecord(
                bank_credit_id=credit_id,
                member_ids=tuple(sorted(m.id for m in members)),
                total_paise=total,
                regime=regime,
                corruption_classes=classes,
                cause_labels={"structural": ",".join(str(c) for c in classes)},
                subrupee_member_count=m_count,
            )
        )
        items.extend(members)

    items_t = tuple(sorted(items, key=lambda i: (i.occurred_at, i.id)))
    credits_t = tuple(sorted(credits, key=lambda c: (c.value_date, c.id)))
    records_t = tuple(sorted(records, key=lambda r: r.bank_credit_id))
    _assert_sums(items_t, credits_t, records_t)
    return TruthSet(items=items_t, credits=credits_t, records=records_t)


def _payment_item(factory: _Factory, order: Order, amount_paise: int, settle: date) -> LedgerItem:
    return _item(
        factory,
        kind=Kind.PAYMENT,
        amount_paise=amount_paise,
        occurred_at=order.captured_at,
        account_id=order.account_id,
        instrument=order.instrument,
        order_id=order.order_id,
        parent_id=None,
        narration_raw=f"PAYMENT {order.order_id} {order.counterparty}",
        counterparty_raw=order.counterparty,
        source=Source.INTERNAL_LEDGER,
    )


def _structural_classes(
    members: list[LedgerItem],
    all_payments: list[LedgerItem],
    payment_settle: dict[str, date],
    split_order_ids: set[str],
) -> tuple[int, ...]:
    pays = [m for m in members if m.kind == Kind.PAYMENT]
    refs = [m for m in members if m.kind == Kind.REFUND]
    n_pay = len(pays)
    n_ref = len(refs)
    order_ids = {p.order_id for p in pays if p.order_id}
    is_split = bool(order_ids & split_order_ids)
    if n_pay >= 2 and n_ref >= 1:
        return (4,)
    if is_split:
        return (3,)
    if n_pay == 1 and n_ref == 0:
        return (1,)
    if n_pay >= 2:
        return (2,)
    return (1,)


def _assert_sums(
    items: tuple[LedgerItem, ...],
    credits: tuple[BankCredit, ...],
    records: tuple[TruthRecord, ...],
) -> None:
    by_id = {i.id: i for i in items}
    for record in records:
        credit = next(c for c in credits if c.id == record.bank_credit_id)
        total = sum(by_id[mid].amount_paise for mid in record.member_ids)
        if total != credit.amount_paise or total != record.total_paise:
            raise AssertionError(
                f"{record.bank_credit_id}: members sum {total} != credit {credit.amount_paise}"
            )
        for mid in record.member_ids:
            if not has_expected_sign(by_id[mid]):
                raise AssertionError(f"truth item {mid} has unexpected sign")
