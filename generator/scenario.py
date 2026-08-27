"""Stage 1: a seeded merchant scenario. No money is computed here, only sampled."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from random import Random
from typing import NamedTuple

from residual_zero.config import MerchantProfile
from residual_zero.models import Instrument
from residual_zero.tz import IST, ensure_utc

# Fixed epoch so two machines generate the same calendar for the same seed.
HORIZON_START = date(2025, 1, 6)  # Monday

POOL_A: tuple[str, ...] = (
    "Aarav Textiles Pvt Ltd",
    "Meera Krishnan",
    "Sahil Grocery Mart",
    "Narmada Traders PVT LTD",
    "Kaveri Electronics Corp",
    "Rohan Deshpande",
    "Eastern Spices Co",
    "Priya Nair",
    "Himalaya Woollens Pvt Ltd",
    "Aditya Rao",
    "Coastal Fisheries LLP",
    "Ananya Iyer",
    "Deccan Hardware",
    "Vikram Singh",
    "Lotus Pharma PVT. LTD.",
    "Fatima Begum",
    "Sundaram Iyengar & Sons",
    "Neha Kapoor",
    "Malabar Coffee Roasters",
    "Arjun Mehta",
    "Ganga Stationery Mart",
    "Ishita Bose",
    "Western Ghat Tea Co",
    "Karthik Subramanian",
    "Pearl Jewellery Pvt Ltd",
    "Sana Qureshi",
    "Indus Logistics Corp",
    "Diya Sharma",
    "Chennai Silks PVT LTD",
    "Mohammed Irfan",
    "Pune Auto Spares",
    "Lakshmi Venkatesh",
    "Greenfield Agro Co",
    "Rahul Banerjee",
    "Bombay Dyeing Retail",
    "Kavya Reddy",
    "Triveni Stationery",
    "Amit Joshi",
    "Southern Rail Catering",
    "Pooja Malhotra",
)

POOL_B: tuple[str, ...] = (
    "Northwind Exports Pvt Ltd",
    "Zara Ahmed",
    "Godavari Mills CORP",
    "Harish Patel",
    "Skyline Furnishings Co",
    "Nikita Rao",
    "Pacific Marine Stores",
    "Devika Menon",
    "Ujjain Handloom Pvt Ltd",
    "Sameer Khan",
    "Delta Packagings LTD",
    "Ritika Jain",
    "Orchid Cosmetics PVT LTD",
    "Yusuf Ali",
    "Kanpur Leather Works",
    "Shreya Gupta",
    "Everest Trekking Gear",
    "Manish Tiwari",
    "Coral Bay Resorts Co",
    "Aditi Kulkarni",
    "Bharat Fasteners Pvt Ltd",
    "Farhan Sheikh",
    "Mysore Sandal Retail",
    "Tanvi Pillai",
    "Frontier Spices Corp",
    "Vivek Anand",
    "Silverline Optics PVT. LTD.",
    "Ayesha Rahman",
    "Howrah Engineering Co",
    "Nandini Prasad",
    "Cauvery Silks Pvt Ltd",
    "Imran Hashmi",
    "Alpine Dairy Products",
    "Sneha Kaur",
    "Rajasthan Crafts CORP",
    "Abhay Narayan",
    "Vindhya Minerals Co",
    "Leela Krishnan",
    "Goa Cashew Traders",
    "Harshita Das",
)


class Order(NamedTuple):
    order_id: str
    account_id: str
    instrument: Instrument
    gross_paise: int
    captured_at: datetime
    counterparty: str


class Scenario(NamedTuple):
    profile: MerchantProfile
    seed: int
    orders: tuple[Order, ...]
    settlement_dates: tuple[date, ...]


def is_business_day(day: date) -> bool:
    return day.weekday() < 5


def iter_business_days(start: date, horizon_days: int) -> tuple[date, ...]:
    out: list[date] = []
    for offset in range(horizon_days):
        day = start + timedelta(days=offset)
        if is_business_day(day):
            out.append(day)
    return tuple(out)


def add_business_days(day: date, n: int) -> date:
    """Advance ``n`` business days. ``n`` is non-negative."""
    if n < 0:
        raise ValueError("add_business_days does not step backwards")
    current = day
    stepped = 0
    while stepped < n:
        current = current + timedelta(days=1)
        if is_business_day(current):
            stepped += 1
    return current


def _pick_instrument(rng: Random, weights: dict[Instrument, int]) -> Instrument:
    items = sorted(weights.items(), key=lambda kv: kv[0].value)
    total = sum(weight for _, weight in items)
    cursor = rng.randrange(total)
    running = 0
    for instrument, weight in items:
        running += weight
        if cursor < running:
            return instrument
    return items[-1][0]


def _counterparties(profile: MerchantProfile) -> tuple[str, ...]:
    return POOL_A if profile.counterparty_pool == "A" else POOL_B


def build_scenario(profile: MerchantProfile, seed: int) -> Scenario:
    """Deterministically sample orders and settlement dates. Seeded RNG, no global random."""
    rng = Random(seed)
    capture_days = iter_business_days(HORIZON_START, profile.horizon_days)
    # One settlement date per capture day, T+cycle, truncated to the profile's count.
    raw_settlements = []
    for capture in capture_days:
        settle = add_business_days(capture, profile.settlement_cycle_days)
        if settle not in raw_settlements:
            raw_settlements.append(settle)
    settlement_dates = tuple(raw_settlements[: profile.settlement_dates_per_horizon])
    names = _counterparties(profile)
    orders: list[Order] = []
    seq = 0
    # Capture days that actually have a settlement slot.
    live_captures = capture_days[: len(settlement_dates)]
    for account_index in range(profile.accounts):
        account_id = f"acc_{account_index:02d}"
        for day_index, capture in enumerate(live_captures):
            # First 8 capture days on account 0 are 1-order days so class 1 exists by construction.
            if account_index == 0 and day_index < 8:
                n_orders = 1
            else:
                n_orders = profile.orders_per_day_per_account
            for _ in range(n_orders):
                seq += 1
                hour = 10 + rng.randrange(0, 8)
                minute = rng.randrange(0, 60)
                second = rng.randrange(0, 60)
                captured = ensure_utc(
                    datetime(
                        capture.year, capture.month, capture.day,
                        hour, minute, second, tzinfo=IST,
                    )
                )
                lo = profile.order_amount_min_paise
                hi = profile.order_amount_max_paise
                gross = rng.randrange(lo, hi + 1, 100)
                orders.append(
                    Order(
                        order_id=f"ord_{seed:03d}_{account_id}_{seq:05d}",
                        account_id=account_id,
                        instrument=_pick_instrument(rng, profile.instrument_mix_weights),
                        gross_paise=gross,
                        captured_at=captured,
                        counterparty=names[rng.randrange(len(names))],
                    )
                )
    orders.sort(key=lambda o: (o.captured_at, o.order_id))
    return Scenario(
        profile=profile,
        seed=seed,
        orders=tuple(orders),
        settlement_dates=settlement_dates,
    )


def settlement_date_for(capture: date, settlement_dates: tuple[date, ...], cycle_days: int) -> date | None:
    """First settlement date on or after T+cycle. None if the order falls off the horizon."""
    earliest = add_business_days(capture, cycle_days)
    for day in settlement_dates:
        if day >= earliest:
            return day
    return None
