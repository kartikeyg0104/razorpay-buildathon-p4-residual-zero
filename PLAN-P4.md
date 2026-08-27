# PLAN-P4.md — Residual Zero, Phase 4

Architect: written 2026-08-28 after `v3`. Read-only for the executor once implementation starts.

Inputs: `CLAUDE.md` P4-PLAN/P4-EXEC, `PLAN-P1.md`–`PLAN-P3.md`, `PROGRESS.md`,
`docs/EVALUATION.md` §12–§14 (including F57), `docs/SPEC.md` §6.1–§6.2, §9.10, §11 Phase 4.

**On numbers.** NN-15. No invented figures. Placeholders `TBD-<run>`. Class 25 arrives
only with F44; class 26 only with F29.

Estimates: 8+4+5+10+4+6+9+2+1+3 = **52h**.

**Three reserved days** after Gate 4 are untouchable: freeze, README, video, submission.
No feature work in them. This plan does not spend them.

The user asked to complete Phase 4. Section 0 still assesses each item; the
recommendation is to **ship all ten at the minimum measurable version**, drop none.

---

## 0 · Stopping assessment

A reviewer who has already seen `v3` already knows: integer paise, uniqueness refusal,
auto-clear 0 at threshold 1.000000, conservation, journal, degradation ladder, CAMT/MT940,
derived ε, DP as the named bottleneck. Phase 4 is optional breadth. For each item, what
they conclude *with it* that they would not conclude *without it*:

| Feature | Without it | With it (if finished) | Drop? |
|---|---|---|---|
| F53 | Model is a stub (Q2=C); tiers 1–3 already 100% EXACT_NORM | The swap boundary is real; all three backends get **zero** tier-4 calls on this corpus. That is the commodity-component finding, not a missing study. | No — one afternoon of interface + a table of zeros is the honest result. |
| F36 | AMBIGUOUS credits dump the whole pool on a human | Symmetric difference of two surviving sets. On this corpus F31 cap-refuses 245/245, so live medians may be N/A; fixtures still show the shape. | No — fixtures plus an honest N/A on the capped corpus. |
| F34 | Reproducibility is single-threaded | Byte-identical at 1/4/8 workers, or disabled with the reason. | No. |
| F47 | Batch files only | Four delivery modes, one test, identical ledger state. | No — this is the payments-engineer check. |
| F43 | No what-if | Parameter substitution over **already-known** member sets. Declined: behavioural rail-counterfactuals. Auto-clear is 0, so exactness is measured on Regime A verified (accepted) decompositions, stated as that. | No. |
| F44 + class 25 | Two accounts exist but no misposting class | Detector + FP on the existing legitimate two-account batch. Do not regenerate `data/dev`. | No. |
| F46 | Auditor replays the audit log by hand | As-of view equals audit replay at 20 seqs. Cut if the equality test is not green inside 9h: revert the feature, keep audit replay. | No at start; cut criterion is the equality test. |
| F27 | F57 named DP | Prose extrapolation to 100k credits/day citing F57's table. | No — two hours of writing. |
| F28 | Implied NN-4 | One paragraph after a gate audit. The short version is the win. | No. |
| F29 + class 26 | Domestic only | Residue class + README still refuses full FX. Domestic case is finished (v3). | No. |

**Recommendation.** Build all ten. Drop none. If F46's equality test is not green at the
trip-wire, revert F46 only. Half-built is worse than absent.

---

## 1 · Ladder (52h)

| CP | Feature | h | trip-wire |
|---|---|---:|---:|
| CP4.1 | F53 provider swap | 8 | 12 |
| CP4.2 | F36 alternate diff | 4 | 6 |
| CP4.3 | F34 deterministic parallelism | 5 | 7 |
| CP4.4 | F47 live webhooks | 10 | 15 |
| CP4.5 | F43 parameter recomputation | 4 | 6 |
| CP4.6 | F44 multi-account + class 25 | 6 | 9 |
| CP4.7 | F46 bitemporal as-of | 9 | 9 (cut, not stretch) |
| CP4.8 | F27 scale analysis | 2 | 3 |
| CP4.9 | F28 calibration note | 1 | 1 |
| CP4.10 | F29 FX residue + class 26 | 3 | 4 |

---

### CP4.1 · F53 provider-swap study · 8h · trip-wire 12h

**Owed number.** Spec §9.10: *tier-4 accuracy, cost per credit, end-to-end coverage and error per backend*.

**Config flag.** `features.f53_providers` (default true). `config/providers.yaml` names three
`model_id`s: `stub-frontier`, `stub-small`, `stub-local-7b`. Cache dir partitioned by
`model_id` (already in `CachedLLMClient` key). Equal tuning: all three are the same stub
protocol; zero extra prompt engineering on any. Q2=C: no live Ollama/API in this
environment — state that. Both findings (local within a point / not) are good; here the
finding is **tier-4 never reached**.

**Reviewer question.** "Is the model a commodity, or the product?"

**DoD.** `eval/providers.py` + `tests/test_providers.py`. Table in EVALUATION.md.

---

### CP4.2 · F36 alternate-decomposition diff · 4h · trip-wire 6h

**Owed number.** Spec §9.10: *median symmetric-difference size presented to the human vs median decomposition size*.

**Config flag.** `features.f36_alt_diff`. Renders into `artifacts/dev/alt_diff.md` and the
exception view helper. Domain is F31's feasible enumerated sets (NN-18). Cap-hit: no
diff, not a fake UNIQUE pair.

**Reviewer question.** "Does the human read 4 items or 37?"

**DoD.** `tests/test_alt_diff.py` on a two-solution fixture. Live corpus: report whatever
median you get, including N/A if every AMBIGUOUS is cap-refused.

---

### CP4.3 · F34 deterministic parallelism · 5h · trip-wire 7h

**Owed number.** Spec §9.10: *throughput at 1/4/8 workers; byte-identical output assertion*.

**Config flag.** `features.f34_parallel`. Work partition: `credit.id` sorted, then slices.
Reduce: sort by `credit.id`. Pin: no per-worker RNG; results are frozen dicts; SQLite
writes stay single-threaded (map is CPU-side only).

**Reviewer question.** "Does reproducibility survive more than one core?"

**DoD.** `tests/test_determinism.py`: 1 vs 4 vs 8, `canonical_json` equal. If it cannot be
made deterministic, ship **disabled** with the reason (NN-9) — that is a finding.

---

### CP4.4 · F47 live webhook mode · 10h · trip-wire 15h

**Owed number.** Spec §9.10: *ledger-state equality across normal / duplicated / reversed / replayed delivery*.

**Config flag.** `features.f47_webhooks`. Event store: sqlite `webhook_event`. Idempotency
key: Razorpay `event_id`. Out-of-order: buffer `refund.*` until matching `payment.*`
(parent) exists. Replay: wipe applied state, replay log in stored seq.

**Reviewer question.** "What if the webhook arrives twice, backwards, or we rebuild from the log?"

**DoD.** One parameterised test, four deliveries. Then `make verify-books` on a stream
that consumed nothing twice.

---

### CP4.5 · F43 parameter recomputation · 4h · trip-wire 6h

**Owed number.** Spec §9.10: *% of cleared credits whose settlement is reproduced exactly under the generator's own parameters (target 100%)*.

**Config flag.** `features.f43_whatif`. Surface: substitute `reserve_bps` / fee bps on an
**already-known** member set; re-derive rate lines; compare paise totals. **Declined:**
"would this payment have succeeded on a different rail." README paragraph in the same
commit.

On this corpus n_cleared=0. Measure exactness on Regime A **accepted** decompositions
(declared + zero residual) and say so. Vacuous 100% of 0 is not the row.

**Reviewer question.** "Is this a counterfactual?"

---

### CP4.6 · F44 multi-account + class 25 · 6h · trip-wire 9h

**Owed number.** Spec §9.10: *class 25 detection rate; false-positive rate on legitimate multi-account batches*.

**Config flag.** `features.f44_accounts`. Detector: any member `account_id` ≠ credit
`account_id`. FP protocol **first**: run on current `data/dev` (two legitimate accounts,
already scoped in `build_pool`). Then fixture-apply class 25 (repoint bank credit to the
other account; truth `member_ids` untouched). Do not regenerate `data/dev`.

**Reviewer question.** "Does it cry wolf on a merchant who just has two MIDs?"

---

### CP4.7 · F46 bitemporal as-of · 9h · trip-wire 9h · LAST, cuttable

**Owed number.** Spec §9.10: *as-of view equals audit-chain replay, across 20 sampled timestamps*.

**Config flag.** `features.f46_bitemporal`. The audit chain already has a total order
(`seq`). As-of at seq N = last disposition per `bank_credit_id` among entries with
`seq <= N`. Replay = fold the same prefix. Equality of the two dicts **is** the feature.

**Cut criterion.** If `tests/test_bitemporal.py` is not green at 9h, revert F46. Audit-log
replay already answers the auditor. Do not add a second time axis that disagrees with the
first.

**Reviewer question.** "What did the books say on the evening of date D?"

---

### CP4.8 · F27 scale analysis · 2h · trip-wire 3h · PROSE

**Owed number.** Spec §6.1: *what breaks at 100,000 credits/day*, written against F57.

**Config flag.** Documentary `f27_scale`. File: `docs/SCALE.md`. Cite F57 p50 DP, pool
cap 400, SQLite, token budget 0 (Q2=C).

---

### CP4.9 · F28 calibration note · 1h · trip-wire 1h · PROSE

**Owed number.** Spec §6.1: reliability diagram **or** a paragraph that none is owed.

**First task:** audit every gate (eligibility, uniqueness, residual, ordering score,
threshold). If any model-derived score gates, that is an NN-4 bug to fix, not a curve.
Expected: ordering score is observables only; model cannot authorise. One paragraph in
`docs/DECISIONS.md`.

---

### CP4.10 · F29 FX rounding + class 26 · 3h · trip-wire 4h

**Owed number.** Spec §6.1: the class exists and is handled; full FX stays out of scope
(§1.3). README keeps saying so.

**Config flag.** `features.f29_fx`. `phase4_fx_plan()` only. Mutation: add a 1–99 paise
residue to a credit amount (conversion rounding), truth members unchanged. Detector:
nonzero residual inside the rounding ceiling that is not a rate match. `data/dev` not
regenerated.

---

## 2 · Flags, video, README, test-split

New keys on `FeatureFlags` / `all_off()` / `config/features.yaml`. Video: first screen
unchanged unless a number moves. README below-fold: F43 declined-capability; F29 not
full FX; F53 table of zeros if that is the measurement.

Test-split eval **4 of 4**: skip unless a shipped feature could move test behaviour.
F44/F29 do not regenerate the test split. F32 already showed empty disposition diffs.
Default: skip and say so.

## 3 · Self-check

- [x] Section 0 assesses all ten; drop recommendation: none (complete-the-phase instruction).
- [x] Ten CPs, 52h.
- [x] Gate clauses; §9.10 for F53/F36/F34/F47/F43/F44/F46; §6.1 for F27/F28/F29.
- [x] F43 restriction + declined paragraph specified.
- [x] F44 FP measured first.
- [x] F46 last, cut at equality test / 9h.
- [x] F28 starts with a gate audit.
- [x] Classes 25 and 26 once each.
- [x] Three reserved days untouchable.
- [x] No invented figures.
