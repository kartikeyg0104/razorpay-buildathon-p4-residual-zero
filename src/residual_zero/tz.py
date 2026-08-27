"""Timezone handling. The only module in the system permitted to name a timezone.

Datetimes are tz-aware, stored UTC, displayed IST (spec §5.3). Conversion to IST is permitted
in exactly three places — the proof renderer, the console templates, and the generator's
rendered views, because a real bank statement carries local dates — and all three go through
:func:`to_ist_display`.

Corruption class 6 ``DATE_SHIFT_TZ`` exists to punish getting this wrong, so the discipline is
worth the module.
"""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

UTC = timezone.utc
IST = ZoneInfo("Asia/Kolkata")

IST_UTC_OFFSET_SECONDS = 5 * 3600 + 30 * 60
"""The 5h30m offset corruption class 6 shifts items by. Named so the generator need not
reconstruct it."""


def ensure_utc(value: datetime) -> datetime:
    """Reject naive datetimes; convert any tz-aware datetime to UTC.

    Used by the model validators, so a naive datetime cannot enter the canonical model at all.

    Raises:
        ValueError: if ``value`` has no timezone. A naive datetime in a reconciliation system is
            an ambiguity waiting to become an off-by-one-window bug.
    """
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError(
            "naive datetime rejected: occurred_at must be tz-aware "
            "(spec §5.3 stores UTC and displays IST)"
        )
    return value.astimezone(UTC)


def to_ist_display(value: datetime) -> str:
    """Render a stored-UTC datetime for human display in IST. The only IST conversion point."""
    return ensure_utc(value).astimezone(IST).strftime("%Y-%m-%d %H:%M:%S IST")


def to_ist_date_display(value: datetime) -> str:
    """Render just the IST calendar date, for rendered views and proof blocks."""
    return ensure_utc(value).astimezone(IST).strftime("%Y-%m-%d")


def iso_utc(value: datetime) -> str:
    """Canonical serialisation: ISO 8601, ``+00:00`` suffix, always six microsecond digits.

    Pinned exactly because it feeds the audit chain's canonical JSON (PLAN-P1 D11), where a
    format difference between two machines is indistinguishable from tampering.
    """
    utc = ensure_utc(value)
    return f"{utc.strftime('%Y-%m-%dT%H:%M:%S')}.{utc.microsecond:06d}+00:00"
