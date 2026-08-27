"""Monetary arithmetic. The only module in the system permitted to compute on money.

Every monetary value is a Python ``int`` counting paise (NN-1, ADR-5). There is exactly one
rounding rule, :func:`round_half_up_div`, and every derived line in the deduction stack goes
through it, applied once at the line level and never to a running total. Rounding a total
instead of each line is how a spreadsheet drifts, and reproducing that drift would be a defect
rather than realism.

Rupee display is a formatting concern and lives at the very edge of the system, in
:func:`format_rupees`.
"""

from __future__ import annotations

Paise = int
"""Documentary alias. Every monetary value is a plain ``int`` counting paise."""

RupeeUnits = int
"""Documentary alias for a value on the rupee-granular search axis (PLAN-P1 D6)."""

PAISE_PER_RUPEE = 100
BPS_DENOMINATOR = 10_000


def round_half_up_div(numerator: int, denominator: int) -> int:
    """Integer division rounding halves toward ``+inf``. The single rounding rule in the system.

    Uses only integer operations, so no float ever touches a monetary value. Halves round
    consistently upward for both signs, which keeps the rule sign-symmetric in magnitude::

        round_half_up_div(15, 10)  ==  2      # 1.5 -> 2
        round_half_up_div(-15, 10) == -1      # -1.5 -> -1
        round_half_up_div(14, 10)  ==  1      # 1.4 -> 1

    Raises:
        ValueError: if ``denominator`` is not strictly positive. A negative denominator would
            silently invert the rounding direction, so it is rejected rather than handled.
    """
    if denominator <= 0:
        raise ValueError(f"denominator must be strictly positive, got {denominator}")
    return (2 * numerator + denominator) // (2 * denominator)


def apply_bps(amount_paise: int, bps: int) -> int:
    """Apply an integer basis-point rate to a paise amount, rounded by :func:`round_half_up_div`.

    Rates are integer basis points rather than float percentages precisely so that this
    function stays in integer arithmetic (ADR-6). ``1800`` bps is 18.00%.
    """
    return round_half_up_div(amount_paise * bps, BPS_DENOMINATOR)


def to_rupee_units(amount_paise: int) -> int:
    """Map signed paise onto the rupee-granular search axis.

    This is ``r(a) = (a + 50) // 100`` from PLAN-P1 D6, and it is identical to
    ``round_half_up_div(a, 100)``. The per-item rounding error is bounded by half a rupee in
    magnitude, and is exactly zero for a whole-rupee amount — which is the observation the
    search tolerance is derived from.
    """
    return (amount_paise + PAISE_PER_RUPEE // 2) // PAISE_PER_RUPEE


def is_whole_rupee(amount_paise: int) -> bool:
    """Whether the amount is an exact multiple of 100 paise, i.e. contributes zero rounding error.

    The count of members for which this is *false* is ``m`` in D6's bound
    ``|sum r(a_i) - r(T)| <= floor((m + 1) / 2)``.
    """
    return amount_paise % PAISE_PER_RUPEE == 0


def subrupee_count(amounts_paise: "list[int] | tuple[int, ...]") -> int:
    """Count the amounts that are not whole rupees. This is ``m`` in D6's bound."""
    return sum(1 for a in amounts_paise if not is_whole_rupee(a))


def rounding_bound_rupees(subrupee_members: int) -> int:
    """The D6 worst-case rupee-axis error for a member set with this many sub-rupee members.

    ``floor((m + 1) / 2)``. The search tolerance must be at least this for the true member set
    to be reachable inside the window.
    """
    if subrupee_members < 0:
        raise ValueError(f"subrupee_members must be non-negative, got {subrupee_members}")
    return (subrupee_members + 1) // 2


def _group_indian(digits: str) -> str:
    """Group an unsigned integer digit string in the Indian convention: last 3, then 2s.

    ``'501200'`` -> ``'5,01,200'``.
    """
    if len(digits) <= 3:
        return digits
    head, tail = digits[:-3], digits[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ",".join(parts) + "," + tail


def format_rupees(amount_paise: int) -> str:
    """Render signed paise as Indian-grouped rupees. Display only, never an input to arithmetic.

    ``-482150`` -> ``'-4,821.50'``;  ``50120000`` -> ``'5,01,200.00'``.
    """
    sign = "-" if amount_paise < 0 else ""
    magnitude = -amount_paise if amount_paise < 0 else amount_paise
    rupees, paise = divmod(magnitude, PAISE_PER_RUPEE)
    return f"{sign}{_group_indian(str(rupees))}.{paise:02d}"
