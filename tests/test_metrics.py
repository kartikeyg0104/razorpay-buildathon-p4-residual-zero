"""Metric implementations agree with a hand-worked fixture, as exact Fractions."""

from __future__ import annotations

from fractions import Fraction

from eval.metrics import assignment_precision_recall, exact_decomposition_rate, pair_set


def test_precision_recall_on_hand_worked_example():
    pred = pair_set({"c1": ("a", "b"), "c2": ("c",)})
    truth = pair_set({"c1": ("a", "d"), "c2": ("c",)})
    # pairs: pred {(c1,a),(c1,b),(c2,c)} truth {(c1,a),(c1,d),(c2,c)}
    # tp=2, fp=1, fn=1 -> P=2/3 R=2/3
    p, r = assignment_precision_recall(pred, truth)
    assert p == Fraction(2, 3)
    assert r == Fraction(2, 3)


def test_exact_decomposition_unpredicted_is_not_exact():
    pred = {"c1": ("a",)}
    truth = {"c1": ("a",), "c2": ("b",)}
    assert exact_decomposition_rate(pred, truth) == Fraction(1, 2)
