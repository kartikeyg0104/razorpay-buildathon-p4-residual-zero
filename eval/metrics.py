"""Assignment precision/recall and exact-decomposition as exact Fractions. No floats."""

from __future__ import annotations

from fractions import Fraction
from typing import Any, Mapping, NamedTuple, Sequence

from pydantic import BaseModel, ConfigDict, Field

from residual_zero.candidates import CandidatePool
from residual_zero.models import Disposition, Regime

from .arms import ArmResult

_STRICT = ConfigDict(frozen=True, extra="forbid")


class CountedRatio(NamedTuple):
    """Unreduced n/N, because ``Fraction(0, 239)`` canonicalises to ``0/1`` and that is not publishable."""

    numerator: int
    denominator: int

    def as_fraction(self) -> Fraction:
        if self.denominator == 0:
            return Fraction(0)
        return Fraction(self.numerator, self.denominator)

    def render(self) -> str:
        if self.denominator == 0:
            return "— (n=0)"
        reduced = self.as_fraction()
        return f"{self.numerator}/{self.denominator} ({float(reduced):.4f})"


def pair_set(predictions: Mapping[str, Sequence[str]]) -> frozenset[tuple[str, str]]:
    """Flatten to (credit_id, item_id) pairs — the unit §9.2 defines precision and recall over."""
    return frozenset((cid, iid) for cid, ids in predictions.items() for iid in ids)


def assignment_precision_recall(
    pred: frozenset[tuple[str, str]], truth: frozenset[tuple[str, str]],
) -> tuple[Fraction, Fraction]:
    """TP/(TP+FP), TP/(TP+FN) as exact Fractions. Empty pred or truth is Fraction(0)."""
    p, r = assignment_precision_recall_counted(pred, truth)
    return p.as_fraction(), r.as_fraction()


def assignment_precision_recall_counted(
    pred: frozenset[tuple[str, str]], truth: frozenset[tuple[str, str]],
) -> tuple[CountedRatio, CountedRatio]:
    tp = len(pred & truth)
    return CountedRatio(tp, len(pred)), CountedRatio(tp, len(truth))


def exact_decomposition_rate(
    pred: Mapping[str, Sequence[str]],
    truth: Mapping[str, Sequence[str]],
) -> Fraction:
    """Fraction of credits whose predicted member set equals ground truth exactly. Unpredicted -> not exact."""
    return exact_decomposition_counted(pred, truth).as_fraction()


def exact_decomposition_counted(
    pred: Mapping[str, Sequence[str]],
    truth: Mapping[str, Sequence[str]],
) -> CountedRatio:
    if not truth:
        return CountedRatio(0, 0)
    n_exact = 0
    for cid, members in truth.items():
        predicted = tuple(pred.get(cid, ()))
        if tuple(sorted(predicted)) == tuple(sorted(members)):
            n_exact += 1
    return CountedRatio(n_exact, len(truth))


class NA(BaseModel):
    """Sentinel for a metric an arm structurally cannot have. Renders '—'. Arithmetic raises."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    marker: str = "NA"

    def __repr__(self) -> str:
        return "NA"

    def __str__(self) -> str:
        return "—"

    def __bool__(self) -> bool:
        return False

    def _nope(self, *args, **kwargs):
        raise TypeError("NA is not a number; arithmetic on it is a metric bug (D16)")

    __add__ = __radd__ = __sub__ = __rsub__ = __mul__ = __rmul__ = _nope
    __truediv__ = __rtruediv__ = __floordiv__ = __rfloordiv__ = _nope
    __int__ = __float__ = _nope


NA_CELL = NA()
MetricCell = CountedRatio | Fraction | int | NA


class ArmMetrics(NamedTuple):
    arm: str
    n_credits: int
    n_cleared: int
    n_cleared_correct: int
    n_flagged: Any
    n_budget_exceeded: Any
    n_exact: int
    assignment_precision: Any
    assignment_recall: Any
    exception_precision: Any
    residual_median_paise: Any
    residual_p95_paise: Any
    residual_median_bp: Any
    tokens: int = 0
    cost_paise: int = 0
    cache_hit_rate: Fraction = Fraction(0, 1)
    wall_clock_ms: int = 0
    machine: str = ""
    regime: Regime | None = None


def _median(values: Sequence[int]) -> int:
    if not values:
        raise ValueError("median of empty")
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    # Integer median: lower of the two middle values (deterministic, no float).
    return ordered[mid - 1]


def _p95(values: Sequence[int]) -> int:
    if not values:
        raise ValueError("p95 of empty")
    ordered = sorted(values)
    idx = (95 * (len(ordered) - 1)) // 100
    return ordered[idx]


def compute_arm_metrics(
    result: ArmResult,
    truth_members: Mapping[str, Sequence[str]],
    truth_records,
    pools: Mapping[str, CandidatePool],
    rendered_ids: frozenset[str],
    credit_amounts: Mapping[str, int],
    regime: Regime | None,
    machine: str,
    wall_clock_ms: int = 0,
) -> ArmMetrics:
    ids = tuple(truth_members)
    if regime is not None:
        recs = {r.bank_credit_id: r for r in truth_records}
        ids = tuple(cid for cid in ids if recs[cid].regime == regime)
    n = len(ids)
    disp = result.dispositions
    n_cleared = sum(1 for cid in ids if disp.get(cid) == Disposition.CLEARED)
    n_flagged = sum(1 for cid in ids if disp.get(cid) == Disposition.FLAGGED)
    n_budget = sum(1 for cid in ids if disp.get(cid) == Disposition.BUDGET_EXCEEDED)
    n_cleared_correct = 0
    n_exact = 0
    for cid in ids:
        truth = tuple(sorted(truth_members[cid]))
        pred = tuple(sorted(result.predictions.get(cid, ())))
        if pred == truth and pred:
            n_exact += 1
        if disp.get(cid) == Disposition.CLEARED and pred == truth:
            n_cleared_correct += 1
    # Unpredicted credits count against exact (already handled: pred empty != truth).
    pred_pairs = pair_set({cid: result.predictions.get(cid, ()) for cid in ids})
    truth_pairs = pair_set({cid: truth_members[cid] for cid in ids})
    prec, rec = assignment_precision_recall_counted(pred_pairs, truth_pairs)
    flagged_ids = [cid for cid in ids if disp.get(cid) == Disposition.FLAGGED]
    if result.has_exception_path and flagged_ids:
        recs = {r.bank_credit_id: r for r in truth_records}
        genuine = sum(
            1
            for cid in flagged_ids
            if cid in pools and genuinely_required_human(recs[cid], pools[cid], rendered_ids)
        )
        exc_p: MetricCell = CountedRatio(genuine, len(flagged_ids))
    else:
        exc_p = NA_CELL
    residual_paise = getattr(result, "residuals", None)
    if residual_paise:
        non_cleared = [
            abs(residual_paise[cid])
            for cid in ids
            if disp.get(cid) != Disposition.CLEARED and cid in residual_paise
        ]
    else:
        non_cleared = []
    if non_cleared:
        med = _median(non_cleared)
        p95 = _p95(non_cleared)
        amts = [credit_amounts[cid] for cid in ids if disp.get(cid) != Disposition.CLEARED]
        med_bp = (med * 10000) // max(1, _median(amts) if amts else 1)
        res_med: MetricCell = med
        res_p95: MetricCell = p95
        res_bp: MetricCell = med_bp
    else:
        res_med = res_p95 = res_bp = NA_CELL
    return ArmMetrics(
        arm=result.arm,
        regime=regime,
        n_credits=n,
        n_cleared=n_cleared,
        n_cleared_correct=n_cleared_correct,
        n_flagged=n_flagged if result.has_exception_path else NA_CELL,
        n_budget_exceeded=n_budget if result.has_budget_path else NA_CELL,
        n_exact=n_exact,
        assignment_precision=prec,
        assignment_recall=rec,
        exception_precision=exc_p,
        residual_median_paise=res_med,
        residual_p95_paise=res_p95,
        residual_median_bp=res_bp,
        machine=machine,
        wall_clock_ms=wall_clock_ms,
    )



def render_cell(cell: MetricCell) -> str:
    if isinstance(cell, NA):
        return "—"
    if isinstance(cell, CountedRatio):
        return cell.render()
    if isinstance(cell, Fraction):
        return f"{cell.numerator}/{cell.denominator}"
    return str(cell)


def genuinely_required_human(record, pool, rendered_ids: frozenset[str]) -> bool:
    """Frozen in docs/EVALUATION.md at CP0. Do not widen after seeing results."""
    if 23 in record.corruption_classes:
        return True
    pool_ids = frozenset(pool.item_ids)
    for mid in record.member_ids:
        if mid not in rendered_ids:
            return True
        if mid not in pool_ids:
            return True
    return False
