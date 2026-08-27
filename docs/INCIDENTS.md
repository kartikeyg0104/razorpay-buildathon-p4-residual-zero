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
**Commit.** `0d45ad6820e902e4e9c69379ea13048618311c9d`
**Regression test.** `tests/regressions/test_uniqueness_under_tolerance.py::test_two_totals_in_the_window_are_ambiguous` and `tests/test_solver_properties.py::test_reference_solver_misses_cross_total_ambiguity`.
**What it changed about my thinking.** A green uniqueness test at `tol=0` is not a uniqueness test. The rounding bridge makes this the production case, not an edge case.

---

## 2026-08-27T18:30:00+05:30 · malformed LLM cache must not yield a selected_id
**Symptom.** Injection 2: a `{not json` file in the cache directory.
**First hypothesis.** Pydantic would throw a ValidationError the caller might catch and retry.
**Actual cause.** `lookup_entity` now treats any parse failure as `OfflineCacheMiss`, so a corrupt entry is a miss, never a wrong id.
**Fix.** Catch-all around `model_validate_json` in `CachedLLMClient.lookup_entity`.
**Commit.** (this CP8 commit)
**Regression test.** `tests/regressions/test_malformed_llm_cache.py::test_malformed_cache_entry_is_not_a_wrong_id`
**What it changed about my thinking.** A cache is a second parser. If it is more permissive than the live path, it is a vulnerability.

---

## 2026-08-27T18:40:00+05:30 · test-split pool contains a 0-rupee DP input
**Symptom.** `eval.cli --split test` raised `ValueError: zero amounts are not a legal DP input` inside `ReachabilityIndex`.
**First hypothesis.** A zero-paise ledger item leaked past ingest. Ingest forbids amount_paise == 0.
**Actual cause.** `to_rupee_units` maps |paise| < 50 to 0 rupees. The test split has sub-50-paise members (stacked corruptions / more fee lines). The DP axis is rupees, so those items are zeros.
**Fix.** `solve_search` returns `NONE_FOUND` when the pool contains a 0-rupee amount, rather than crashing. Auto-clear stays impossible. The verifier still sees paise.
**Commit.** (this commit)
**Regression test.** (behaviour covered by the test-split eval completing)
**What it changed about my thinking.** The rupee axis is a projection. Projections send some legal paise values to zero, and the DP must treat that as "cannot search", not as a crash.

