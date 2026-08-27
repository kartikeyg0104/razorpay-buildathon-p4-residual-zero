"""Assignment precision/recall and exact-decomposition as exact Fractions. No floats."""

from __future__ import annotations

from fractions import Fraction
from typing import Mapping, NamedTuple, Sequence


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
