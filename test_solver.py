"""
Brute-force validation of the Residual Zero solver.

This is the test that licenses every accuracy claim in the spec. If the solver's
notion of UNIQUE disagrees with exhaustive enumeration, the whole correctness
story collapses — so check it exhaustively on small instances.

Run:  python3 test_solver.py          (standalone, no pytest needed)
      pytest test_solver.py           (also works)
"""

import random
import time
from itertools import combinations

from solver import Uniqueness, solve


def brute_force_count(amounts, target, tol=0):
    n = len(amounts)
    count = 0
    for mask in range(1 << n):
        s = sum(amounts[i] for i in range(n) if mask >> i & 1)
        if abs(s - target) <= tol:
            count += 1
    return count


def test_matches_brute_force_on_signed_instances():
    random.seed(7)
    for _ in range(800):
        n = random.randint(3, 14)
        amounts = [random.choice([1, -1]) * random.randint(1, 60) for _ in range(n)]
        target = random.randint(-100, 140)

        r = solve(amounts, target)
        truth = brute_force_count(amounts, target)

        found = r.uniqueness in (Uniqueness.UNIQUE, Uniqueness.AMBIGUOUS)
        assert found == (truth > 0), (amounts, target, r, truth)

        if truth == 1:
            assert r.uniqueness == Uniqueness.UNIQUE, (amounts, target, r, truth)
            assert sum(amounts[i] for i in r.members) == target
        elif truth > 1:
            assert r.uniqueness == Uniqueness.AMBIGUOUS, (amounts, target, r, truth)
            assert r.members == ()      # never expose a guess


def test_tolerance_mode():
    random.seed(11)
    for _ in range(300):
        n = random.randint(3, 11)
        amounts = [random.choice([1, -1]) * random.randint(1, 50) for _ in range(n)]
        target = random.randint(-60, 90)
        tol = random.randint(0, 3)

        r = solve(amounts, target, tol=tol)
        truth = brute_force_count(amounts, target, tol=tol)
        found = r.uniqueness in (Uniqueness.UNIQUE, Uniqueness.AMBIGUOUS)
        assert found == (truth > 0), (amounts, target, tol, r, truth)


def test_ambiguity_by_construction():
    """Corruption class 23. Without this class in the corpus, "we refuse
    ambiguous decompositions" is an untested claim."""
    r = solve([100, 60, 40, 25, 25, 10], 100)
    assert r.uniqueness == Uniqueness.AMBIGUOUS       # 100 == 60+40
    assert r.alternates >= 2
    assert r.members == ()

    r = solve([100, 60, 41, 7], 107)
    assert r.uniqueness == Uniqueness.UNIQUE          # 100+7 only
    assert sum([100, 60, 41, 7][i] for i in r.members) == 107


def test_none_found_reports_near_miss():
    r = solve([100, 60, 41, 7], 3)
    assert r.uniqueness == Uniqueness.NONE_FOUND
    assert r.nearest_total is not None
    assert r.nearest_delta == r.nearest_total - 3


def test_bounds_guard_does_not_crash():
    """Target far outside [NEG, POS] must return cleanly, not raise."""
    r = solve([10, 20, 30], 10_000_000)
    assert r.uniqueness == Uniqueness.NONE_FOUND
    r = solve([10, 20, 30], -10_000_000)
    assert r.uniqueness == Uniqueness.NONE_FOUND


def test_budget_exceeded_rather_than_silent_truncation():
    r = solve(list(range(1, 502)), 100, max_pool=400)
    assert r.uniqueness == Uniqueness.BUDGET_EXCEEDED


def test_invariant_claimed_match_verifies():
    """The property test from spec §F14: if the solver claims a match, the
    arithmetic must verify. This is the invariant the whole product rests on."""
    random.seed(3)
    for _ in range(500):
        n = random.randint(5, 20)
        amounts = [random.choice([1, -1]) * random.randint(1, 200) for _ in range(n)]
        target = random.randint(-300, 400)
        r = solve(amounts, target, tol=2)
        if r.uniqueness == Uniqueness.UNIQUE:
            total = sum(amounts[i] for i in r.members)
            assert abs(total - target) <= 2
            assert total == r.matched_total


def bench_settlement_scale():
    """Realistic pool: ~380 payments, ~20 refunds/fees, 37-member true subset."""
    random.seed(1)
    times = []
    for _ in range(25):
        pool = ([random.randint(200, 9000) for _ in range(380)]
                + [-random.randint(100, 4000) for _ in range(20)])
        planted = random.sample(range(len(pool)), 37)
        target = sum(pool[i] for i in planted)
        t0 = time.perf_counter()
        r = solve(pool, target)
        times.append(time.perf_counter() - t0)
        assert r.uniqueness in (Uniqueness.UNIQUE, Uniqueness.AMBIGUOUS)
    times.sort()
    print(f"400-item pool, 37-member target: "
          f"median {times[len(times)//2]*1000:.0f} ms, worst {times[-1]*1000:.0f} ms")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS  {name}")
    bench_settlement_scale()
    print("\nAll solver invariants hold.")
