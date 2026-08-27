# INCIDENTS.md

Contemporaneous failure log, per NN-19 and spec §13.2. Anything that breaks and costs more than
fifteen minutes gets an entry **the same hour**: timestamp, symptom, what I first thought it was,
what it actually was, the fix, the commit hash, the regression test added.

Raw and unpolished on purpose. Written live it is unfakeable; written retrospectively it reads
like fiction, because it is. An empty log is better than an invented one, and an invented one is
the single most damaging thing this repository could contain.

Format:

```
## <ISO timestamp> · <one-line symptom>
**Symptom.**
**First hypothesis.** (and why it was plausible)
**Actual cause.**
**Fix.**
**Commit.**
**Regression test.** tests/regressions/<file>::<function>
**What it changed about my thinking.**
```

---

## 2026-08-27T23:20:00Z · reference solver reports UNIQUE across two reachable totals
**Symptom.** `solve([10, 11], target=10, tol=1)` on the unmodified `solver.py` returns `UNIQUE` with members `(0,)`. A second subset `{1}` sums to 11, which is inside the window.
**First hypothesis.** The brute-force tests would have caught this. They would not: `test_matches_brute_force_on_signed_instances` uses `tol=0`, and `test_tolerance_mode` only asserts reachability, not uniqueness.
**Actual cause.** Lines 93–115 of `solver.py` pick one hit total (`target` if reachable, else the closest) and enumerate *inside that total*. Uniqueness-under-tolerance was untested. PLAN-P1 §0.1.
**Fix.** `enumerate_solutions` walks every hit in ascending order into one shared solution list with one shared cap. Empty subsets are never solutions.
**Commit.** *(filled with the CP3 commit)*
**Regression test.** `tests/regressions/test_uniqueness_under_tolerance.py::test_two_totals_in_the_window_are_ambiguous` and `tests/test_solver_properties.py::test_reference_solver_misses_cross_total_ambiguity`.
**What it changed about my thinking.** A green uniqueness test at `tol=0` is not a uniqueness test. The rounding bridge makes this the production case, not an edge case.

