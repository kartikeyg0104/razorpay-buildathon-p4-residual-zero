# EVALUATION.md

Written at CP0, **before any logic module**, per spec §11 Day 0 and PLAN-P1 CP0 note 2. Defining
what counts as success before building the thing that will be judged by it is the highest-leverage
hour in the project.

Every definition here is frozen. Changing one after results exist requires a dated note in this
file saying what changed and why, plus a re-run.

---

## 1 · What a "record" is

We decompose **bank credits**. Each credit is composed of some number of **ledger items**. The
brief's "50+ records" is ambiguous, so we state the unit explicitly in both directions and report
`n` for every published number.

- Dev split: seeds 1–3, corruption parameter range A, counterparty pool A, at most one corruption
  class per credit. Realised counts recorded in `docs/DATA.md` at CP1.
- Test split: seeds 101–105, range B, pool B, **stacked corruptions** (two or three classes on one
  credit) and **one class held out of dev entirely**.
- Devscale corpus: seeds 11–18, range A, pool A. Exists only to measure throughput, cost and
  memory at test-split scale without spending a test-split evaluation. Publishes no quality
  metric.

## 2 · Metric definitions (§9.2)

Predictions are sets of `(credit_id, item_id)` pairs. All proportions are computed as exact
`Fraction`s over integer counts; no metric is a float.

**Assignment precision.** `|pred ∩ truth| / |pred|`.

**Assignment recall.** `|pred ∩ truth| / |truth|`.

This is the primary quality pair because it degrades gracefully: a decomposition that gets 35 of
37 members right is partially credited, which is the honest description of what happened.

**Exact decomposition rate.** Fraction of credits whose predicted member set equals ground truth
*exactly*. A credit with no prediction is not exact. Strict, unforgiving, and the number a
finance team actually cares about.

**Auto-clear coverage.** `n_cleared / n_credits`.

**Auto-clear error rate.** `n_cleared_wrong / n_cleared`, where wrong means the member set differs
from ground truth. **This is the single most important number in the project** — coverage is a
convenience, this is a safety property. When `n_cleared == 0` this is **not applicable**, rendered
`—`, never `0`: zero errors out of zero clears is not a zero error rate.

**Exception precision.** Of credits flagged for review, the fraction that genuinely required a
human. The predicate is **frozen here** so it cannot be adjusted after seeing results:

> `genuinely_required_human(credit)` is true if and only if at least one of:
> 1. some ground-truth member of the credit is absent from every rendered source view; or
> 2. the credit carries corruption class 23 `AMBIGUOUS_BY_CONSTRUCTION`; or
> 3. some ground-truth member falls outside the candidate window the system was permitted to search.

This metric exists to stop "route everything to review" from gaming the safety number. Flagging
something you would have got right anyway wastes a human minute, so flagging everything is not a
strategy. Including the metric is how we demonstrate we anticipated that attack on our own design.

**Residual distribution.** Median and p95 of `|residual_paise|` among non-cleared credits,
reported in rupees and as integer basis points of credit value.

**Throughput.** Credits per minute and total wall clock, **on stated hardware**. A throughput
number without a named machine is not a number.

**Cost.** Total tokens, total paise, paise per credit, cache hit rate, and the count of model
calls avoided by deterministic tiers 1–3.

**Regime split.** Every metric above is reported separately for Regime A (`A_DECLARED`) and
Regime B (`B_SEARCHED`), and pooled. Blending them hides that the declared-report path is the
easy half (§3.3).

## 3 · Dispositions

Every credit terminates in exactly one of three, and there is no fourth outcome and no silent
pass:

| Disposition | Meaning |
|---|---|
| `CLEARED` | Verifier accepted at zero paise residual, uniqueness is `UNIQUE`, pool scope is `FULL`, ordering score at or above the derived threshold |
| `FLAGGED` | Routed to a human with a class, a diagnosis and a suggested resolution |
| `BUDGET_EXCEEDED` | The search did not complete within the deterministic budget, or completed only on a reduced pool |

`BUDGET_EXCEEDED` is counted **separately** from exceptions in the headline table, which is why
coverage, exceptions and budget-exceeded sum to exactly 1.00 rather than coverage and exceptions
doing so.

## 4 · Arms

| Arm | Description |
|---|---|
| A0 | Exact single-item amount match inside the base window. No exception path. |
| A1 | Fuzzy 1:1 on normalised narration plus amount tolerance, resolved by **optimal** assignment (`scipy.optimize.linear_sum_assignment`), not greedy. No exception path. |
| A2 | Rules-only: full deduction-stack arithmetic plus largest-first greedy subset selection. Same pools, same tax config, same cross-window widening as A3. No exact solver, no uniqueness check. |
| A3 | The full system. |
| A4 | Human (F19, extended to three raters by F56). Reported as time per credit and accuracy, not coverage, since a human clears everything they attempt. |

A0 and A1 have **no exception path at all**, which is why their exception and budget cells are
dashes and not zeros. That distinction lives in the data structure, not the formatter.

## 5 · Report invariants

Asserted in `report.py` before anything is written, so an impossible table cannot be published:

1. For any arm with all three dispositions populated:
   `n_cleared + n_flagged + n_budget_exceeded == n_credits` (exact integer identity).
2. For any arm with **no** exception path: `n_exact <= n_cleared_correct` — the integer form of
   `exact <= coverage × (1 − error)`. A3 is exempt, because a credit A3 *flagged* can still carry
   a correct member set.

## 6 · Statistics (§9.4)

Five seeds. We publish the **pooled** proportion with a **Wilson score interval**, because our
most important number lives near zero where the normal approximation misbehaves. We publish the
per-seed figures as a **min–max range beside it**, and we never wrap one estimator's interval
around the other's point estimate. Cohen's κ is pairwise by construction, so with three raters we
report all three pairwise values and their mean, and say that is what we did.

## 7 · Autonomy threshold

The threshold is **read off the risk-coverage curve at a declared error budget**, not chosen.

| Item | Value |
|---|---|
| Declared error budget | `1/100` (declared at CP6 **before** the curve was read) |
| Threshold read off the curve | `1.000000` (never auto-clear: no eligible UNIQUE+FULL credit on dev) |
| Curve artifact | `artifacts/dev/curve_a3.json` |

## 8 · Held-out class

Frozen at CP2, **before the test split is generated**, and not revisited after the test
evaluation.

| Item | Value |
|---|---|
| Held-out class | `9 OVERPAYMENT` |
| Selection criteria | not structural; no other class depends on it; not required to prove any Phase 1 feature; delta structure unlike anything in dev |

## 9 · Baseline tuning log

Recorded so that fairness is documented rather than asserted (§9.1).

| Arm | Parameter | Swept over | Chosen | Criterion |
|---|---|---|---|---|
| A1 | similarity threshold | `50,60,70,80,90` | `50` | maximises A1's **own** exact-decomposition rate on dev |
| A1 | amount tolerance (paise) | `100,500,1000,5000,10000,50000` | `100` | as above |
| tier 3 | rapidfuzz threshold | `85` (config default; not swept) | `85` | Q2=C, tier 4 unexercised; 85 is the declared default, not a fitted knee |

## 10 · Test-split evaluation log (NN-16)

At most one evaluation per tagged release; project-lifetime ceiling of four. Every threshold,
prompt, tolerance and window is tuned on dev, always. Dev evaluation is unlimited.

| # | Timestamp | Commit | Tag | Phase | Notes |
|---|---|---|---|---|---|
| 1 | `2026-08-27T18:45:00+05:30` | (tag `v1-submittable`) | `v1-submittable` | 1 | Evaluation **1 of 4**. n=800. A0/A1 exact 0/800. A2 exact 0/800, greedy-cleared 510, budget 238. A3 exact 425/800, assignment 11467/11470 P / 11467/20487 R, auto-cleared 0, flagged 116, budget 684. Held-out class 9 present. Tuned on dev only. |

## 11 · Pre-registered questions

Registered before the answer is knowable, so the answer counts either way.

| # | Registered | Question | Answered |
|---|---|---|---|
| 1 | `2026-08-27T18:15:00+05:30` (CP5, before the `--offline` dev run) | On the credits where the three raters disagreed with each other (any pairwise disposition disagreement), did the system flag rather than clear? | **Not estimable.** F56 was not run (Q3=C: no additional raters). There is no pairwise disagreement set. |

<!-- A1-SWEEP-START -->

A1 exact-decomposition on each (sim, amount_tol_paise) cell, as exact Fractions:

| sim_threshold | amount_tol_paise | exact_decomposition |
|---|---:|---|
| 50 | 100 | `0/239` |
| 50 | 500 | `0/239` |
| 50 | 1000 | `0/239` |
| 50 | 5000 | `0/239` |
| 50 | 10000 | `0/239` |
| 50 | 50000 | `0/239` |
| 60 | 100 | `0/239` |
| 60 | 500 | `0/239` |
| 60 | 1000 | `0/239` |
| 60 | 5000 | `0/239` |
| 60 | 10000 | `0/239` |
| 60 | 50000 | `0/239` |
| 70 | 100 | `0/239` |
| 70 | 500 | `0/239` |
| 70 | 1000 | `0/239` |
| 70 | 5000 | `0/239` |
| 70 | 10000 | `0/239` |
| 70 | 50000 | `0/239` |
| 80 | 100 | `0/239` |
| 80 | 500 | `0/239` |
| 80 | 1000 | `0/239` |
| 80 | 5000 | `0/239` |
| 80 | 10000 | `0/239` |
| 80 | 50000 | `0/239` |
| 90 | 100 | `0/239` |
| 90 | 500 | `0/239` |
| 90 | 1000 | `0/239` |
| 90 | 5000 | `0/239` |
| 90 | 10000 | `0/239` |
| 90 | 50000 | `0/239` |

<!-- A1-SWEEP-END -->

## 12 · Second-order results (§9.10)

A feature is not done until its row is populated from a real run. F24 and F25 have no
§9.10 row; their numbers live in §13 and come from spec §6.1.

| Feature | The number it owes | Measured |
|---|---|---|
| F31 constraint disambiguation | % of `AMBIGUOUS` credits resolved to unique by structural constraints; auto-clear error on that subset; count proven structurally infeasible | Full dev pass: **245/245** arithmetically AMBIGUOUS credits hit `f31_enumerate_cap=32` (budget 0). PLAN-P2 §0.2 then refuses UNIQUE and INFEASIBLE. Resolved-to-unique **0/245**. Auto-clear error on that subset: not applicable (`0` auto-clears). Structurally infeasible **0/245**. Fixtures in `tests/test_disambiguation.py` still surface UNIQUE and INFEASIBLE on constructed, fully-enumerated domains. |
| F33 conservation identity | the period identity itself; items claimed by >1 decomposition (must be 0); unreconciled value | Dev split, `artifacts/dev/ledger.sqlite` after `make verify-books`. Identity HOLDS on both accounts. `acc_00` `[2025-01-08, 2025-03-04]`: `62,79,853.99 = 0.00 + 62,79,853.99`, n_credits=121, n_cleared=0. `acc_01` `[2025-01-08, 2025-03-05]`: `81,45,904.20 = 0.00 + 81,45,904.20`, n_credits=127, n_cleared=0. double_claimed=0. unreconciled_value=`1,44,25,758.19`. Cleared members are zero because auto-clear coverage is 0 at threshold `1.000000`; the identity is still the joint check, and it held. |
| F37 exception clustering | exception compression ratio; cluster purity against true cause labels | `artifacts/p2` flags-on run, n=248 exceptions: compression **248/34**. Purity against `cause_labels.structural` (eval-only): **159/248**. Labels never enter `src/residual_zero/cluster.py`. |
| F38 rate drift | detection latency in windows; false-positive rate on undrifted profiles; rupee estimation error | Undrifted `data/dev`: 45 instrument-weeks, **alerts=0**, FP rate **0/45**. Detection latency: not applicable (class 24 is not on `phase1_dev_plan()`; `data/dev` was not regenerated). Rupee estimation error: not applicable with zero alerts. `min_sample=8`; contracted rate must sit outside the integer band. |
| F40 journal export | debits = credits (exact); control-account tie-out residual (0); entries per cleared credit | `artifacts/p2/journal.csv`: debits=`1442575819` paise, credits=`1442575819` paise, control residual=`0`. Lines=496. CLEARED credits=0, so entries per cleared credit is not applicable; unreconciled credits post `Dr 1100 / Cr 2300` (2 lines per credit). No plug. |
| F49 PII boundary | raw VPAs, card fragments, phone numbers in the model call log (must be 0); accuracy delta redacted vs raw | Egress log hits: **0**. Accuracy delta redacted vs raw: **not estimable** (Q2=C stub; both paths 0 model resolutions). Enforcement is `PiiLeakError`, not a warning. |
| F50 injection corpus | injections causing an auto-clear (must be 0 of ~30); disposition of each | **0/30** auto-clear. All 30 recorded `FLAGGED` in `artifacts/injections_f50.json`. |
| F52 decision trace | % of credits with a complete trace terminating in exactly one disposition | `artifacts/p2`: **248/248**. A mid-credit raise still writes a trace (`tests/test_trace.py`). |
| F54 eval-diff | disposition deltas attached to every config change in `docs/EVALUATION.md` | Baseline: [docs/diffs/20260828-v1-self.md](../diffs/20260828-v1-self.md) (v1 vs itself, 0 rows). Gate 2 flags-on: [docs/diffs/20260828-v1-to-v2.md](../diffs/20260828-v1-to-v2.md) (`artifacts/v1` → `artifacts/dev`, 0 rows). **Rule:** no change to `config/solver.yaml`, `config/features.yaml`, or the autonomy threshold ships without an eval-diff link in this file. Threshold not moved. |
| F55 CI | green build; run history; dev-split regression epsilon | Workflow `.github/workflows/ci.yml`. Offline: stub `model_id`, `token_budget: 0`. Epsilon: flags-off A3 exact must equal `129/239` (`config/ci.yaml`). Run history starts when this workflow is pushed. |

## 13 · Second-wave carry (spec §6.1, not §9.10)

| Feature | Source | Measured |
|---|---|---|
| F24 adversarial self-test | §6.1: publish what was found, including anything not fixed | 8 attacks in `artifacts/adversarial/catalogue.md`. Auto-clears of a non-truth set: **0**. Negative result published. |
| F25 idempotency and crash-resume | §6.1: replay equality; kill-and-resume without double-count or a broken chain | Replay: second pass writes 0 new audit rows. Crash-resume: `halt_after` then restart; chain verifies; no double-count (`tests/test_idempotency.py`). |

