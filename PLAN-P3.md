# PLAN-P3.md — Residual Zero, Phase 3

Architect: written 2026-08-28. Read-only for the executor once implementation starts.

Inputs: `CLAUDE.md` P3-PLAN/P3-EXEC, `PLAN-P2.md`, `PROGRESS.md`, `docs/EVALUATION.md` §12,
`docs/SPEC.md` §6.1 (F23/F26/F30), §6.2, §9.10, §11 Phase 3, §12; live tree
(`solver/enumerate.py`, `verify.py`, `orchestrator.py`, `features.py`, ingest, books).

**On numbers.** NN-15. No result figures. Placeholders `TBD-<run>`. No new corruption
class. Classes 25 and 26 belong to Phase 4.

**Phase 2 reality this plan builds against.** Auto-clear is still 0 at threshold
`1.000000`. F31 cap-32 enumeration is capped on 245/245 AMBIGUOUS credits, so derived
tolerance (F32) is the first thing that could actually move search uniqueness — and
that is why it carries a mandatory F54 diff. Verifier acceptance stays zero paise
(NN-12). `test_feature_flags_off.py` stays green after every CP.

Estimates: 4+2+6+6+10+4+12+5+6+5+3+6 = **69h**.

---

## 0 · Decisions

### 0.1 · F32 fits on the rupee-axis error of *true* member sets, eval-only

**The decision.** `eval/fit_epsilon.py` loads truth (eval path only), for each truth
record computes `n = len(members)` and
`rupee_err = abs(sum(to_rupee_units(a_i)) - to_rupee_units(credit))`.
Target the 95th percentile of `100 * rupee_err` as a paise budget. Fit the smallest
integer `k >= 1` such that `ceil(k * isqrt(n)) >= that paise budget` for every true
decomposition in the fit set (or, if a least-squares-in-integers fit is tighter,
use it and state the quantile it misses).

Search window applied: `epsilon_rupees = ceil(eps_paise / 100)` i.e.
`(eps_paise + 99) // 100`. **Verifier unchanged.** Cross-check D6: Phase 1 set
`ε_R = 7` from `m <= 13`. If fitted `epsilon_rupees` equals 7, F32 *confirms* D6
and the eval-diff is empty — that is a valid result. If it differs, file the diff
and inspect any newly UNIQUE credits before accepting.

**Correctly decomposed without src/ touching truth:** only `eval/fit_epsilon.py`
and `eval/truth_loader.py`. `src/residual_zero/solver/` reads the resulting
`search.epsilon_rupees` from config, never truth.

### 0.2 · F35 minimum measurable version is day-ordered replay, not a live webhook

Persistent unconsumed-item pool in sqlite (`stream_pool`). Credits processed in
`value_date` order. On CLEARED, members are consumed. On FLAGGED/BUDGET, items stay.
After each day's credits, re-attempt still-open credits whose pool grew.
Ageing: items older than `windows.widened_days_before` from the current credit
value_date are aged out (same horizon the batch engine already uses) and counted,
not silently dropped from conservation — aged items are unclaimed, not double-claimed.
Idempotency key unchanged. `make verify-books` after the stream run.

If 18h hits: skip re-attempt beyond one extra window; still publish lag for that
single retry. That is the minimum.

### 0.3 · F51 rungs do not auto-clear more

Monotonic conservatism: coverage (auto-clear fraction) is non-increasing along
NORMAL → NO_MODEL → NO_SEARCH → READ_ONLY → HALTED; auto-clear error is non-increasing
(or N/A when n_cleared=0). On this corpus coverage is already 0, so the interesting
assertion is that no rung *introduces* a clear. Test that.

---

## 1 · Ladder (69h)

| CP | Feature | h | trip-wire |
|---|---|---:|---:|
| CP3.1 | F32 derived tolerance | 4 | 6 |
| CP3.2 | F30 cost governor | 2 | 3 |
| CP3.3 | F51 degradation ladder | 6 | 9 |
| CP3.4 | F39 leakage report | 6 | 9 |
| CP3.5 | F45 CAMT/MT940 | 10 | 15 |
| CP3.6 | F48 ingestion fuzzing | 4 | 6 |
| CP3.7 | F35 incremental reconciliation | 12 | 18 |
| CP3.8 | F41 reserve sub-ledger | 5 | 7 |
| CP3.9 | F42 dispute lifecycle | 6 | 9 |
| CP3.10 | F57 latency profile | 5 | 7 |
| CP3.11 | F23 cross-profile generalisation | 3 | 4 |
| CP3.12 | F26 HITL learning curve | 6 | 9 |

---

### CP3.1 · F32 derived tolerance · 4h · trip-wire 6h

**Owed number.** Spec §9.10 verbatim: *fitted `k` in `ε(n)=ceil(k·√n)`; coverage and error at derived ε versus flat ε*.

**Config flag.** `features.f32_derived_epsilon` (default true). When false, `solver.yaml` `search.epsilon_rupees` is used as the flat 7 from D6. When true, loader prefers `search.derived_epsilon_rupees` if set. Flags-off: flat 7, dispositions = v1.

**Reviewer question.** "Did you quietly widen the thing that can auto-clear?"

**Signatures.** `eval/fit_epsilon.py: fit_k(...) -> FittedEpsilon`; `config/solver.yaml` keys `derived_epsilon_paise`, `derived_k`, `derived_epsilon_rupees`; `tests/test_verifier_unmoved.py` asserts `verify_decomposition` rejects residual 1; `docs/diffs/` F54 file.

**DoD.** `python -m pytest -q tests/test_verifier_unmoved.py tests/test_feature_flags_off.py` plus an eval-diff link in EVALUATION.md.

---

### CP3.2 · F30 cost governor · 2h · trip-wire 3h

**Owed number.** Spec §6.1 F30 (no §9.10 row): *when the budget is exhausted, the semantic tier stops and remaining unresolved items become exceptions rather than the run failing*.

**Config flag.** `features.f30_cost_governor` (default true). When false, `TokenBudgetExceeded` still fails the run (Phase 1). When true, catch at `resolve()` and return UNRESOLVED.

**Reviewer question.** "What happens when the model bill runs out mid-batch?"

**DoD.** `tests/test_cost_governor.py`: budget 0 with a forced tier-4 residue → run completes, those credits FLAGGED/UNRESOLVED, not a crash.

---

### CP3.3 · F51 degradation ladder · 6h · trip-wire 9h

**Owed number.** Spec §9.10: *coverage and error at every rung; monotonic conservatism assertion*.

**Config flag.** `features.f51_degrade` (default true). `config/degrade.yaml` names states and triggers. Flags-off: always NORMAL.

**Reviewer question.** "Does the system get *more* conservative when it is in trouble?"

**Signatures.** `src/residual_zero/runtime/degrade.py` — `class Rung`, `def step(...)`.
Rungs: NORMAL, NO_MODEL, NO_SEARCH, READ_ONLY, HALTED.
`tests/test_degrade.py` measures coverage/error per rung on a fixture (or recorded a3 scored list) and asserts monotonic coverage fall and error not rising.

On this corpus coverage is 0 at NORMAL: the test asserts no rung produces a CLEARED that NORMAL did not.

---

### CP3.4 · F39 leakage report · 6h · trip-wire 9h

**Owed number.** Spec §9.10: *rupees identified per profile; detector precision against generator truth*.

**Config flag.** `features.f39_leakage` (default true).

**Reviewer question.** "Besides matching, what money is sitting in the books incorrectly?"

**Detectors (deterministic, src/):** overdue reserve (hold with no release past schedule); chargeback with no representment inside window; duplicate refund `parent_id`; duplicate credits (already a signal); fee on a voided/failed sibling if tagged. Evidence rows in `artifacts/dev/leakage.json`.
README caveat in the same commit: synthetic detector measurement, not incidence.

Precision via `eval/leakage_eval.py` + truth, never from src/.

---

### CP3.5 · F45 CAMT.053 and MT940 · 10h · trip-wire 15h

**Owed number.** Spec §9.10: *field-level parse fidelity against the CSV path*.

**Config flag.** `features.f45_bank_formats` (default true). CSV path remains default ingest.

**Reviewer question.** "Can you read what a bank actually sends?"

**Signatures.** `src/residual_zero/ingest/camt.py`, `mt940.py`. Round-trip: render CSV credits → CAMT/MT940 → parse → equal `BankCredit` fields. MT940 `:86:` truncation connected to class 16 in DATA.md. `lxml` allowed for CAMT. Awkward parts implemented, not TODOed: continuation `:86:`, CdtDbtInd, multi-day stmt, opening/closing balance check.

**DoD.** `tests/test_bank_formats.py` parameterised over `{camt, mt940}`.

---

### CP3.6 · F48 ingestion fuzzing · 4h · trip-wire 6h

**Owed number.** Spec §9.10: *partial loads across the malformed fixture set (must be 0)*.

**Config flag.** `features.f48_fuzz` (documentary; adapters always typed-error).

**Reviewer question.** "If the file is garbage, do you reconcile against half of it?"

**Fixtures.** `fixtures/malformed/` — truncated XML, latin-1 CAMT, BOM CSV, mixed CRLF, CAMT entry missing amount, MT940 bad date, duplicated CSV header. `IngestError` with `line`/`element`. After error, sqlite credit count unchanged (0 new rows).

---

### CP3.7 · F35 incremental reconciliation · 12h · trip-wire 18h

**Owed number.** Spec §9.10: *resolution lag distribution; % unsolvable on arrival; % eventually resolved and by which window*.

**Config flag.** `features.f35_stream` (default true). Batch `run_split` unchanged when false.

**Reviewer question.** "What happens when the missing refund posts tomorrow?"

**Minimum measurable.** Date-ordered replay with sqlite `stream_pool(item_id, consumed_by, aged)`. One retry window. Lag in whole days. Then verify-books.

---

### CP3.8 · F41 reserve sub-ledger · 5h · trip-wire 7h

**Owed number.** Spec §9.10: *outstanding balance tie-out identity; overdue releases detected*.

**Config flag.** `features.f41_reserve` (default true).

**Reviewer question.** "Is the rolling reserve a forecast or arithmetic?"

**Identity.** `outstanding = sum(holds) + sum(releases)` (releases positive, holds negative) at paise. Schedule = hold date + profile reserve days if configured, else same settlement date. README: not a forecast (§1.3).

---

### CP3.9 · F42 dispute lifecycle · 6h · trip-wire 9h

**Owed number.** Spec §9.10: *% of dispute chains reconstructed end to end; open disputes inside 7-day deadline*.

**Config flag.** `features.f42_disputes` (default true). No new class; class 19 fixtures.

**Reviewer question.** "Where is this chargeback in its life, and is the clock running out?"

**States.** RAISED → DEBITED → REPRESENTED → WON|LOST. Deadline 45 calendar days from debit unless config says otherwise (Razorpay-like; mark synthetic).

---

### CP3.10 · F57 latency profile · 5h · trip-wire 7h

**Owed number.** Spec §9.10: *per-stage p50/p95/p99; throughput curve to 5,000 credits; named bottleneck*.

**Config flag.** `features.f57_latency` (default true). Timings in audit `metrics` only (NN-9).

**Reviewer question.** "Where does it bend, and on what machine?"

**DoD.** `artifacts/dev/latency.md` with Darwin/CPython line, bottleneck named in EVALUATION.md. 5,000-credit point: generate a throwaway stream or repeat-pool with measured warning if synthetic; do not invent a knee.

---

### CP3.11 · F23 cross-profile generalisation · 3h · trip-wire 4h

**Owed number.** Spec §6.1 F23: *per-profile results, no re-tuning*.

**Config flag.** `features.f23_profiles` (documentary).

**Reviewer question.** "Does this only work on the merchant you tuned?"

**Mechanism.** Three profiles `config/profiles/{d2c,saas,travel}.yaml`. Test: `config_digest(solver.yaml)` identical across the three eval invocations. Quality numbers from generated mini-splits if full 239×3 is too slow — state n.

---

### CP3.12 · F26 HITL learning curve · 6h · trip-wire 9h

**Owed number.** Spec §6.1 F26: *after 50 simulated human resolutions, does coverage rise and does error hold?*

**Config flag.** `features.f26_feedback` (default true). Alias table is a dict of normalised name → entity id, not a trained scorer. Line in DECISIONS.md.

**Reviewer question.** "Does the exception queue make the next batch better, or did you train a matcher?"

**Simulation.** Eval-only: take 50 flagged credits, apply truth counterparties as *simulated human aliases* written to `artifacts/dev/aliases.json`, re-run resolve. Do not import truth from src/. Report lift even if 0 (likely: tiers 1–3 already 100% EXACT_NORM).

---

## 2 · Flags, video, README

New keys on `FeatureFlags` and `all_off()`. Video: F32/F51 numbers may swap evidence seconds; do not grow the tape. README below-fold: degradation ladder numbers in Safety; F32 two-boundary paragraph; F39 detector-not-incidence caveat.

## 3 · Self-check

- [x] 12 CPs, 69h.
- [x] Gate clauses on each.
- [x] §9.10 for F32/F51/F39/F45/F48/F35/F41/F42/F57; §6.1 for F30/F23/F26.
- [x] F32 both ε boundaries; verifier unmoved; F54 required.
- [x] F51 monotonicity is a test.
- [x] F45 field-by-field vs CSV.
- [x] F48 zero partial loads.
- [x] F35 minimum named.
- [x] F39 README caveat.
- [x] F23 config hash test.
- [x] F26 not a learned matcher.
- [x] No class 25/26. No invented figures.
