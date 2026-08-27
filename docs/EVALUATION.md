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
| Declared error budget | `TBD-CP6-DECLARED` |
| Threshold read off the curve | `TBD-CP6-CURVE` |
| Curve artifact | `TBD-CP6-CURVE` |

## 8 · Held-out class

Frozen at CP2, **before the test split is generated**, and not revisited after the test
evaluation.

| Item | Value |
|---|---|
| Held-out class | `TBD-CP2` |
| Selection criteria | not structural; no other class depends on it; not required to prove any Phase 1 feature; delta structure unlike anything in dev |

## 9 · Baseline tuning log

Recorded so that fairness is documented rather than asserted (§9.1).

| Arm | Parameter | Swept over | Chosen | Criterion |
|---|---|---|---|---|
| A1 | similarity threshold | `TBD-CP2` | `TBD-CP2` | maximises A1's **own** exact-decomposition rate on dev |
| A1 | amount tolerance | `TBD-CP2` | `TBD-CP2` | as above |
| tier 3 | rapidfuzz threshold | `TBD-CP5` | `TBD-CP5` | knee of the dev precision-vs-threshold curve at the declared entity-resolution error budget |

## 10 · Test-split evaluation log (NN-16)

At most one evaluation per tagged release; project-lifetime ceiling of four. Every threshold,
prompt, tolerance and window is tuned on dev, always. Dev evaluation is unlimited.

| # | Timestamp | Commit | Tag | Phase | Notes |
|---|---|---|---|---|---|
| — | — | — | — | — | No test-split evaluation has been run. |

## 11 · Pre-registered questions

Registered before the answer is knowable, so the answer counts either way.

| # | Registered | Question | Answered |
|---|---|---|---|
| 1 | `TBD-CP5` | On the credits where the three raters disagreed with each other (any pairwise disposition disagreement), did the system flag rather than clear? | `TBD-CP6` |
