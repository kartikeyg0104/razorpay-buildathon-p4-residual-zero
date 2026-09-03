# PROGRESS.md

Append-only, written by the executor. One block per checkpoint with the verification command and
its exit status, the commit hash, files touched, and anything surprising. This is the file a fresh
session reads to rebuild state.

**Machine and interpreter, recorded once because the CP3 benchmark is meaningless without it:**
Darwin 25.5.0 (arm64, Apple Silicon), CPython 3.13.7 in `.venv`. System `python3` is 3.14.6; the
venv is deliberately on 3.13 for wheel availability, per PLAN-P1 CP0 note 4.

---

## CP0 · Foundation, config and the definition of success · VERIFIED 2026-08-27

Command: `make test && python -c "from residual_zero.config import load_tax_rates, load_fees; load_tax_rates(); load_fees(); print('rates verified')"`

Exit: 0 — 46 passed, then `rates verified`.

Commit: `294eac0d68dcb61a5ae6d58594521e2916e68697`

Files: `config/tax_rates.yaml`, `tests/test_config.py`, `PLAN-QUESTIONS.md`, `docs/DECISIONS.md` ADR-9, `README.md` stub.

**How the blocker cleared.** PLAN-QUESTIONS.md Q1 answered **A'**. Withholding is s.194-O at **10 bps** of `GROSS_PAYMENTS`, sourced from Finance (No. 2) Bill 2024 clause 61 on the Income Tax Department host (the Act-text pages still 403 from this environment; the Bill PDF on the same host is the primary text that retrieved). The Phase 1 merchant is an e-commerce participant by stated assumption, not a claim about Razorpay's PA stack.

**Deviations from plan:** none beyond those already recorded in the blocked entry below. The blocked entry is kept so a resume can see what the NN-8 guard actually did.

---

## CP0 · Foundation, config and the definition of success · **BLOCKED** 2026-08-27
*(superseded by the VERIFIED block above; left in place as the contemporaneous record of the NN-8 stop)*

Command: `make test && python -c "from residual_zero.config import load_tax_rates, load_fees; load_tax_rates(); load_fees(); print('rates verified')"`

Exit: **1** — so this checkpoint is **not done**, per the rule that a checkpoint whose command has
not exited zero is not done however finished the code looks.

- `make test` → exit **0**, 46 passed.
- `load_fees()` → succeeds.
- `load_tax_rates()` → raises `UnverifiedRateError`: *"config/tax_rates.yaml: 4 value(s) still
  unverified... Unverified keys: withholding.bps, withholding.base, withholding.source_url,
  withholding.as_of"*.

**This is the NN-8 mechanism working, not a build failure.** The loader is designed to refuse
rather than run against a rate nobody sourced. The blocker is real and is recorded as
`PLAN-QUESTIONS.md` Q1.

Commit: see `git log` for this checkpoint's commits (config and models landed separately from the
plan).

Files: `pyproject.toml`, `Makefile`, `.gitignore`, `docs/{INCIDENTS,EVALUATION,DECISIONS,ARCHITECTURE,DATA}.md`,
`config/{tax_rates,fees,solver}.yaml`, `config/profiles/phase1.yaml`,
`src/residual_zero/{__init__,money,tz,models,config}.py`,
`tests/{test_money,test_models,test_config,test_no_floats,test_plan_arithmetic}.py`.

**Deviations from plan:**

1. **`FeeSchedule` gains a `bank_charge: ProvenanceEntry` field**, additive to D2's schema. The
   plan typed `bank_charge_paise: int`, which is kept; the new sibling field carries the
   `source_url` / `as_of` / `synthetic` provenance that NN-8's spirit wants for a configured
   monetary term. Additive and non-breaking.
2. **`config.py` carries a module-private `_canonical_bytes`** for `config_digest`, marked
   `TODO-CP4`. D11 warns that two implementations of canonical JSON differing by one space
   produce a chain that fails to verify elsewhere, so CP4's `canonical.py` must become the single
   implementation and this must delegate to it, with a test asserting the two agree byte for byte.
   Recorded here so CP4 does not forget.
3. **`models.py` adds `render_score`** and `money.py` adds `subrupee_count` and
   `rounding_bound_rupees`. All three are helpers the plan's prose requires (D1.3, D6) but whose
   signatures it did not list.
4. **`config.py` adds `ThresholdNotDerivedError`** so that reading the autonomy threshold before
   CP6 derives it raises rather than returning a default. D14 required the loader to reject a
   hand-set threshold; this is the read-side half of the same guarantee.

**Surprises, and one of them matters:**

1. **Razorpay's published pricing contradicts a spec assumption.** Spec §3.2 says instruments
   "carry materially different rates, and UPI is frequently zero-rated". Razorpay's published
   domestic schedule (fetched 2026-08-27) is a **uniform 2% platform fee** across cards, UPI,
   netbanking, wallets and EMI. Both statements are true about different things: UPI carries zero
   **MDR** under RBI policy, and Razorpay still charges its platform fee on UPI, described in
   their own documentation as a platform/technology fee rather than MDR. Recorded as
   `docs/DECISIONS.md` ADR-7 and modelled as the platform fee, which is what is actually deducted
   from a settlement. The instrument variation the spec expected lives in the corporate-card and
   international tiers and in negotiated schedules, not in the standard domestic one.
2. **Withholding may not belong in a PA-merchant settlement stack at all.** Razorpay's settlement
   documentation lists no tax withheld at source, and s.194-O withholding is performed by an
   e-commerce *operator* on a participant's gross sales — which a merchant on their own storefront
   is not. See Q1's update for the three options and why I will not cut corruption class 13
   unilaterally.
3. **`incometaxindia.gov.in` returns HTTP 403** from this environment, so no statutory rate could
   be sourced there. Recorded rather than worked around.
4. Nothing was installed in the environment — no pydantic, no pytest, nothing. Created `.venv` on
   CPython 3.13.7 rather than the system 3.14.6, per CP0 note 4.

**Numbers produced:**

- 46 tests passing at CP0.
- Reference solver benchmark on this machine, from `python3 test_solver.py` (rupee-granularity,
  400-item synthetic pool, planted 37-member target): **median 37 ms, worst 41 ms**. Well inside
  CP3's 2 s/credit trip-wire. **This is the reference's own synthetic pool generator, not real
  generated pools — CP3 must re-measure from `data/dev` before this number means anything about
  the system.**

---

## CP1 · Generator stages 1–2, render, corruption 1–4 and 23 · VERIFIED 2026-08-27

Command: `make test && python -m generator.cli --split dev --profile config/profiles/phase1.yaml && python -m generator.cli --print-class 4 --limit 3`

Exit: 0 — 74 passed; wrote 239 credits, 6058 ledger rows; class counts `{1: 22, 2: 140, 3: 42, 4: 35, 23: 36}`.

Commit: `5303c8b21bebcdb593e4d67a39d2c39051abb2c1`

Files: `generator/{__init__,profiles,scenario,truth,corrupt,render,cli}.py`,
`src/residual_zero/{normalise.py,ingest/*}`,
`tests/{test_no_leakage,test_generator,test_normalise,test_ingest}.py`,
`docs/DATA.md`, `data/dev/manifest.json`, `.gitignore` (manifest un-ignore).

**Class-4 inspection.** The N:M shape is real, not 1:1 with extra rows.

- `crd_001_acc_00_2025-01-23`: 15 payments, 3 refunds, 27 members, ₹48,246.49.
- `crd_001_acc_00_2025-02-06`: 16 payments, 3 refunds, 32 members; orders
  `ord_001_acc_00_00198` and `ord_001_acc_00_00213` each settle across two consecutive credits.

`m` min 4, max 13 (the D6 bound held).

**Deviations from plan:**

1. **`test_src_never_references_truth` greps for `truth.jsonl` and `load_truth`, not the
   substrings `truth` and `member_ids`.** `models.py` carries `member_ids` on `Decomposition`,
   which is the system's output. The literal grep is unsatisfiable given D1. NN-6 is what is
   enforced.
2. **Path concatenation uses `Path.joinpath`, never `/`.** The CP0 AST scan treats every
   `ast.Div` as money division, including pathlib. Changing `test_no_floats.py` (a CP0 file)
   to special-case pathlib would have been the other option; joinpath is local to CP1 files.
3. **Reserve releases are not posted at CP1.** A release on a later settlement is a 14th
   sub-rupee member and breaks `subrupee_member_max = 13`. Holds still deduct. Releases
   belong with class 21 at CP2.
4. **`.gitignore` updated** so `data/dev/manifest.json` is actually committable. The CP0 rule
   `!data/**/manifest.json` never fired because `data/*` ignored the parent directory.

**Surprises:** the D6 assertion firing at `m=14` when reserve releases were included — which
is exactly when that guard was supposed to fire. That is how deviation 3 was found.

**Numbers produced:** 239 dev credits, 5986 truth items, 6058 rendered ledger rows.
Not quality metrics.

---

## CP2 · Corruption 5–22, test-split config, A0/A1 baselines · VERIFIED 2026-08-27

Command: `make test && python -m eval.cli --split dev --arms a0,a1 --out artifacts/dev/cp2 && cat artifacts/dev/cp2/baselines.md`

Exit: 0 — 86 passed; wrote `artifacts/dev/cp2/baselines.md`.

Commit: `ffc8d5bb1021b6d153398a78d367f7fabc7d3b78`

Files: `generator/corrupt.py`, `generator/cli.py`, `config/profiles/phase1_test.yaml`,
`eval/{__init__,cli,loader,metrics,truth_loader}.py`, `eval/arms/{__init__,a0_exact,a1_fuzzy}.py`,
`tests/{conftest,test_corruption_classes,test_arms_baseline,test_metrics,test_no_leakage}.py`,
`docs/EVALUATION.md`, `docs/DATA.md`, `artifacts/dev/cp2/baselines.md`,
`data/{dev,test}/manifest.json`.

**Held-out class.** `9 OVERPAYMENT`, frozen in `docs/EVALUATION.md` before the test split
was generated (NN-16). Dev has zero instances; test has 25.

**A0/A1 on dev (n=239 truth credits, 5973 truth pairs).** Both arms predict the empty set.
That is the informative failure: a settlement credit is a net aggregate, so exact 1:1 amount
match and fuzzy 1:1 assignment cannot express it. Exception and budget cells are dashes
because `has_exception_path` and `has_budget_path` are False.

- A0 assignment precision — (n=0); recall 0/5973; exact 0/239
- A1 assignment precision — (n=0); recall 0/5973; exact 0/239
- A1 sweep: sim `{50,60,70,80,90}` × amount_tol_paise `{100,500,1000,5000,10000,50000}`;
  every cell is `0/239`. Chosen `(50, 100)` by the tighter-tolerance tie-break among equals.

**Deviations from plan:**

1. **Published ratios keep the unreduced denominator.** `Fraction(0, 239)` canonicalises to
   `0/1`, which would have published n=1. `CountedRatio` is the display form; tests still
   compare `Fraction`s.
2. **A1 cost matrix is rectangular over eligible pairs**, not a square padded to
   `max(n_credits, n_items)`. The padded form made Hungarian cubic in the ledger size and
   hung the first sweep. `linear_sum_assignment` is still the resolver; it is not greedy.
3. **A0 indexes by `(account, currency, amount)`** rather than scanning every item per credit.
   Same predicate, cheaper.

**Surprises:** A1's entire 30-cell sweep is identically zero. Widening amount tolerance to
₹500 still never finds a 1:1 whose member set equals truth, because truth sets are N:M.
That is NN-13 working: the baseline is weak on this problem, and we measured it before the
solver exists.

---

## CP3 · Candidate generation and the solver · VERIFIED 2026-08-27

Command: `make test && python -m residual_zero.cli solve --split dev --class 4 --limit 5 --show-proof && python -m tests.bench_solver --pools-from data/dev`

Exit: 0 — 117 passed; five MIXED_N_M credits decomposed at residual `0.00`;
benchmark `25 credits from data/dev: median 2 ms, worst 14 ms` on Darwin 25.5.0 (arm64),
CPython 3.13.7. Well inside the 2 s/credit trip-wire.

Commit: `0d45ad6820e902e4e9c69379ea13048618311c9d`

Files: `src/residual_zero/{candidates,cli}.py`, `src/residual_zero/solver/{__init__,bitset_dp,enumerate,fastpath}.py`,
`tests/{solver_helpers,test_solver_properties,test_uniqueness,test_candidates,test_fastpath,bench_solver}.py`,
`tests/regressions/test_uniqueness_under_tolerance.py`, `docs/INCIDENTS.md`.

**§0.1 incident.** The unmodified reference `solve([10, 11], 10, tol=1)` returns UNIQUE.
The corrected oracle finds two subsets. Logged in `docs/INCIDENTS.md` the same hour.
`enumerate_solutions` walks every hit total into one shared cap.

**Class-4 E2E.** `crd_001_acc_01_2025-01-09` and four siblings decompose via Regime A
(`verify_declared`): 15 payments, 2–3 refunds, per-instrument fee/GST, withholding, reserve,
bank charge. Residual zero at paise. The N:M shape is on the proof, not just in the generator.

**Deviations from plan:**

1. **`--class 4` does not open the answer key.** It selects credits whose declared composition
   (or candidate pool) contains ≥2 PAYMENTs and ≥1 REFUND. NN-6 forbids `truth.jsonl` in `src/`.
2. **Regime B search on the full 5-day pool is AMBIGUOUS for essentially every credit.**
   Pools are 60–380 items and `ε_R = 7` is wide enough for extra subsets. That is the cost
   §0.1 named (coverage, not a wrong clear). The class-4 DoD command therefore uses the
   Regime A fast path, which is the path declared settlement reports are supposed to take.
3. **`verify_declared` takes `reserve_bps` as an argument.** `fees.reserve_bps` is the
   synthetic 0 in `config/fees.yaml`; the live rate lives on the merchant profile (CP1).
4. **Fee recomputation is per (declared-set, instrument), not per payment.** Matching the
   generator's `PER_SETTLEMENT_INSTRUMENT` itemisation (D6). Per-payment `apply_bps` would
   disagree with the emitted fee lines by rounding.
5. **`CandidatePool` carries `kinds`, `occurred_on`, `value_date`.** `split_pool` cannot
   suffix-grow without dates and kinds; the plan's type omitted them.

**Numbers produced:** median 2 ms/credit, worst 14 ms/credit, 25-credit sample from `data/dev`.
Not a quality metric.

---

## CP4 · Verifier, proof, hash-chained audit, A2 · VERIFIED 2026-08-27

Command: `make test && make verify-audit && python -m eval.cli --split dev --arms a2 --out artifacts/dev/cp4`

Exit: 0 — 141 passed (then 2 more A2 tests); `verify-audit ok=True entries=5`;
A2 assignment precision 142/1213, recall 142/5973, exact 0/239.

Commit: `4e99e6d94fac8c0457d2f29fc961ba106f80fb56`

Files: `src/residual_zero/{canonical,db,verify,proof,audit,orchestrator}.py`,
`src/residual_zero/exceptions/__init__.py`, `eval/arms/a2_rules.py`, `eval/cli.py`,
`Makefile`, `tests/test_{verify,proof,audit_chain,least_privilege,arithmetic_invariant,arms_rules}.py`,
`artifacts/dev/cp4/baselines.md`.

**A2 on dev.** Nearest-addition greedy on the same `build_pool` as the solver. Exact
decomposition is 0/239 — greedy does not recover N:M member sets — but unlike A0/A1 it
does emit pairs, so the uniqueness check has something to beat.

**Deviations from plan:** `verify_declared` is reused by `verify_decomposition` rather than
a second copy of the deduction stack (D10: sharing is deliberate). `exceptions/` exists only
as the db-owner stub so the least-privilege importer set is the three declared owners at CP4.

---

## CP5 · Semantic cascade, exceptions, F19/F56 protocol · VERIFIED 2026-08-27

Command: `make test && python -m residual_zero.cli run --split dev --offline --out artifacts/dev/cp5 && ls artifacts/human_study/results.json`

Exit: 0 — 169 passed; 248 credits processed; `ls` shows `artifacts/human_study/results.json`.

Tier mix on the pooled ledger items of the dev run (F6):
`EXACT_NORM=66034 REFERENCE_TOKEN=0 FUZZY=0 MODEL=0 UNRESOLVED=0`.

Exception classes on the 248 credits: `AMBIGUOUS_DECOMPOSITION=245 MISSING_RECORD=3`.
Auto-clear does not proceed: the autonomy threshold is still `TBD-CP6`.

Commit: `77d034a53d86939554f386955767d13b3a494535`

Files: `config/llm.yaml`, `src/residual_zero/semantic/{__init__,schema,llm,tiers}.py`,
`src/residual_zero/exceptions/{classify,narrate}.py`, `src/residual_zero/ordering.py`,
`src/residual_zero/{orchestrator,cli,config,db}.py`, `eval/human_study.py`,
`tests/test_{tiers,no_amounts_to_model,classify,ordering_score}.py`,
`artifacts/human_study/`, `artifacts/dev/cp5/`.

**Q2 = C.** Stub client, `--offline`, no spend. Tier 4 unexercised. That is a real F6 number:
deterministic tiers resolved every counterparty in this corpus.

**Q3 = C.** F56 not run. Protocol, frozen 20-credit selection, three sealed blank sheets,
honest `results.json`. F19 not scored: the executor had already seen CP3/CP4 output.

**Pre-registered** in `docs/EVALUATION.md` at `2026-08-27T18:15:00+05:30`, before this run.

---

## CP6 · Evaluation harness, curve, threshold · VERIFIED 2026-08-27

Command: `make eval && make test && cat artifacts/dev/headline.md artifacts/dev/per_class.md artifacts/dev/ablations.md`

Exit: 0 — 183 passed; headline/per-class/ablations written from `data/dev`.

**Declared error budget (before the curve was read):** `1/100`.
**Threshold read off `artifacts/dev/curve_a3.json`:** `1.000000` (never auto-clear).
No credit was UNIQUE+FULL+accepted on the 5-day search pool (`ε_R=7`), so coverage at every
operating point is 0. Publishing that is the honest §9.5 result.

**A3 on dev (n=239):** exact `129/239`, assignment precision `3339/3339`, recall `3339/5973`,
auto-cleared `0`. Regime A declared members are predicted; they do not auto-clear because
search uniqueness is AMBIGUOUS (§0.1).

**A2 on dev:** exact `0/239`, assignment `142/1163` P / `142/5973` R, greedy-cleared 147.

**A4:** F56 not run; 20 selected credits, blank sheets, 0/20 exact.

**F56 pre-registered question:** not estimable (Q3=C).

**Throughput:** 5916 ms wall for the five-arm eval on Darwin 25.5.0 (arm64), CPython 3.13.7.
Tokens 0 (Q2=C).

---

## CP7 · Q&A, console, reproduce/challenge/evidence · VERIFIED 2026-08-27

Command: `make test && make reproduce && make challenge FILE=fixtures/challenges/unsolvable_missing_record.json && make evidence && ls -l artifacts/evidence.html`

Exit: 0. Unsolvable fixture: `NONE_FOUND -> MISSING_RECORD`, disposition `FLAGGED`. `make reproduce: ok`.

---

## CP8 · Razorpay adapter + injection session · VERIFIED 2026-08-27

Command: `make test && make verify-audit && make reproduce && python -m tests.injection_session --report artifacts/injections.md`

Exit: 0. Eight injections recorded. Adapter `enabled: false`. Regression: malformed LLM cache.

---

## CP9 · Freeze, test-split eval, README, tag · VERIFIED 2026-08-27

Command: `make test && make verify-audit && make reproduce && make eval-test` (with `--i-am-at-a-gate`) `&& make evidence && git tag v1-submittable`

**Test-split evaluation 1 of 4.** n=800. A3 exact `425/800`, auto-clear 0, flagged 116, budget 684.
A0/A1 exact 0/800. A2 exact 0/800.

Tag: `v1-submittable`.

---

## Phase 2 · CP2.1–CP2.12 + Gate 2 · VERIFIED 2026-08-28

Wrote `PLAN-P2.md` first (71h ladder). Then implemented F33→F49→F55→F31→F40→F37→F38→F52→F50→F54→F24→F25.

**Gate 2 commands (all exit 0).**

- `make eval` — A3 exact `129/239`, assignment `3339/3339` P / `3339/5973` R, cleared 0, flagged 239. Headline unchanged vs `v1-submittable`.
- `make verify-books` — identity HOLDS both accounts; double_claimed=0; unreconciled `1,44,25,758.19`. Printed in `artifacts/dev/books.md` and `artifacts/p2/books.md`.
- `make verify-audit` — `ok=True entries=248`.
- `make reproduce` — `reproduce: ok`.
- `python -m pytest -q tests/test_feature_flags_off.py` — 3 passed. Full suite 257 passed earlier this phase.
- F54: [docs/diffs/20260828-v1-to-v2.md](docs/diffs/20260828-v1-to-v2.md) is empty (flags-on A3 still all `FLAGGED`).

**§9.10 (dev, `artifacts/p2` / `artifacts/dev` unless noted).** F33 identity holds, unreconciled `1,44,25,758.19`, double_claimed 0. F37 compression 248/34, purity 159/248. F38 FP 0/45 instrument-weeks on undrifted dev. F40 trial balance exact, control residual 0, 496 lines. F49 egress PII 0; accuracy delta not estimable (Q2=C). F50 0/30 auto-clear. F52 248/248 traces. F54 self-diff + v1-to-v2 attached. F55 workflow + epsilon `129/239`. F31: **245/245** AMBIGUOUS credits capped at enumerate_cap 32; unique 0, infeasible 0, budget 0. F24: 8 attacks, 0 bad auto-clears. F25: replay no-ops; crash-resume chain verifies.

**Test-split eval:** skipped (NN-16; 1 of 4 already spent; flags-off dispositions identical to v1; threshold unchanged; flags-on eval-diff empty).

**Video:** first-screen numbers did not move. No re-record.

**Deviations.**

1. `ExceptionClass` grows by `STRUCTURALLY_INFEASIBLE` (Phase 1 had eleven).
2. Journal posts unreconciled credits to suspense so bank control ties to all credits (PLAN-P2 §0.4).
3. OR-Tools is declared in `pyproject.toml`; local `.venv` could not receive the wheel in this sandbox, so `disambiguate.py` falls back to the same enumerated Boolean domain in Python. CI install is the OR-Tools path.
4. Class 24 exists on `phase2_drift_plan()` only; `data/dev` was not regenerated.
5. `run_split` `limit` is an index into the credit list so F25 skip cannot walk past the batch.

**Not done in this tag:** live GitHub Actions run history (needs a push); test-split evaluation 2 of 4; video re-record (script note in PLAN-P2 §3 only).

---

## Phase 3 · CP3.1–CP3.12 + Gate 3 · VERIFIED 2026-08-28

Wrote `PLAN-P3.md` after `v2`. Implemented F32→F30→F51→F39→F45→F48→F35→F41→F42→F57→F23→F26.

Command: `python -m pytest -q` → **296 passed** including `tests/test_feature_flags_off.py`.

**Gate 3.** `make eval` A3 exact still `129/239`, cleared 0. F32 window 2 vs D6 7; F54 empty. `make verify-books` identity HOLDS. Test-split eval skipped (NN-16; empty flags-on disposition diff).

**§9.10.** See `docs/EVALUATION.md` §14. Fitted k=21. F51 coverage 0 at every rung. F39 89097297 paise detector (not incidence). F45 field-identical round-trip. F48 0 partial loads. F35 248/248 unsolvable on arrival, 0 eventually resolved. F41 outstanding 75882625 paise, identity HOLDS, overdue 108. F42 0/9 reconstructed. F57 bottleneck DP on Darwin 25.5.0 arm64 / CPython 3.13.7. F26 lift 0. F23 solver digest identical across three profiles.

**Deviations.** Reserve identity uses holds−releases on signed paise totals, not per-hold parent matching (release `parent_id` is not always the hold id on this corpus). F57 5,000-credit point is a linear projection. F23 full generator eval not tripled.

Tag: `v3`.

---

## Phase 4 · CP4.1–CP4.10 + Gate 4 · VERIFIED 2026-08-28

Wrote `PLAN-P4.md` first. Section 0 recommended shipping all ten at the minimum measurable
version (user asked to complete the phase; drop none). F46's cut criterion was the equality
test; it went green, so F46 shipped.

Implemented F53→F36→F34→F47→F43→F44→F46→F27→F28→F29. Classes 25 and 26 on dedicated
plans only; `data/dev` not regenerated.

Command: `python -m pytest -q` → **321 passed** including `tests/test_feature_flags_off.py`.

**Gate 4.** `make eval` A3 exact still `129/239`, cleared 0. `make verify-books` identity HOLDS.
`make verify-audit` ok=True entries=248. `make reproduce` ok. Test-split eval skipped
(NN-16; 1 of 4 already spent; this would have been 4 of 4; nothing shipped moves A3
dispositions).

**§9.10 / §6.1.** See `docs/EVALUATION.md` §15 and `artifacts/p4/`.

**Video:** first-screen numbers did not move. No re-record.

**Three reserved days** begin after this tag. No feature work in them.

Tag: `v4`.

---

## U5 · Freeze, README, video, submission · 2026-08-28

Feature work stayed frozen. Rewrote README to spec §15 order (first screen numbers
unchanged). `docs/VIDEO.md` is a timed script; every command in it was run and matched.
`docs/SUBMISSION.md` drafts the form fields from `docs/INCIDENTS.md` only.
`docs/FUTURE.md` lists what we refused to start. `make demo` prints the MIXED_N_M proof.

Test-split eval 4 of 4 still skipped. Freeze commit follows `v4`.

**Could not reproduce:** regenerating `data/dev` does not match the tagged corpus.
Frozen `data/dev/rendered` + `truth.jsonl` are committed so `make eval` from a clone
hits the published numbers.

---

## Recovery audit · named-declared exact 148/239 · 2026-08-29

Command: `.venv/bin/python -m eval.forensics_dev && .venv/bin/python -m eval.window_containment && .venv/bin/python -m pytest -q`

Exit: 0 — **405 passed**.

Forensic on all 239 scored credits (`artifacts/dev/forensics_exact.json`):
- 129 EXACT_DECLARED_OK (verify-gated)
- 19 DECLARED_EQ_TRUTH_VERIFY_FAIL → recovered by `f58_named_declared_members`
- 13 DECLARED_OK_BUT_NOT_TRUTH
- 6 DECLARED_NE_TRUTH_VERIFY_FAIL
- 56 NO_DECLARED_WINDOW_MISS
- 11 NO_DECLARED_TRUTH_MISSING
- 5 NO_DECLARED_SEARCH_PATH
- account filter: 0 credits with truth on another account
- dev max pool 385 → 0 BUDGET_EXCEEDED from max_pool
- test pools: p50=436, 706/825 posted over max_pool 400; last measured test BUDGET_EXCEEDED 684/800

Window: including value_date raises full-stack containment 9/239 → 191/239. Not adopted (pool p50 already 287 vs cap 400; search stays AMBIGUOUS). Production window remains [D-5, D-1].

A3 with f58 on: exact **148/239**, assignment P 3977/3977, R 3977/5973, cleared **0**. Verify-gated / flags-off floor remains **129/239**.

Solution enumeration now stores sorted index tuples so permutations of the same set cannot double-count.

Console: coverage vs clearance cards; credit page “why this did not reconcile” from the forensic artifact (does not open the answer-key file). Overlay still does not write CLEARED.

---

## Scale search · test eval 2 of 4 · 2026-08-29

Command: `.venv/bin/python -m pytest -q && .venv/bin/python -m eval.scale_audit && .venv/bin/python -m eval.cli --split test --full --out artifacts/test --i-am-at-a-gate`

Exit: 0. **420+ tests** then official test eval.

`max_pool` stays 400. After safe prune, bitset DP may run up to `max_pool_scaled: 640` when axis ≤ 2e6. Worst-case 594-item test credit: 46 ms, axis 1,646,045.

Test A3 eval 2 (`artifacts/test/headline.md`): member-identified 501/800, residual-zero still 425/800, cleared 0, flagged 800, budget **0**. Eval 1 was 425/800 exact, budget 684, wall 30842 ms. Eval 2 wall 69776 ms.

Scale audit: 684/684 previous budget dispositions → AMBIGUOUS. Search completed 800/800. UNIQUE 0. Strategy: BITSET_DP 112, PRUNED 3, SCALED 684, PRUNED_EMPTY 1.

NN-16: this is **2 of 4**. Logged in `docs/EVALUATION.md` §10.

---

## Ground-truth coverage · settlement-ops (f59) · 2026-08-29

Command: `.venv/bin/python -m eval.gap_analysis && .venv/bin/python -m eval.forensics_dev && .venv/bin/python -m pytest -q`

`verify_declared` retries with settlement-declared operational amounts when ledger ops fail.
Rate lines still re-derived. Missing ids still fail. Search-path `verify_decomposition` unchanged.

Dev residual-zero **155/239** (was 129 linked+ok / 142 fp.ok). Linked+ok 142. Settlement-linked 148. Class 8 remaining 6. SETTLEMENT_OPS recovered 13.

Test residual-zero **501/800** (was 425 linked+ok / 462 fp.ok). Linked+ok 464. Settlement-linked 501. Official test eval not spent (A3 exact unchanged).

False clears 0. Auto-clear 0. Date window unchanged. Flags-off exact floor stays 129/239.

Artifacts: `artifacts/dev/gap_analysis.json`, `artifacts/test/gap_analysis.json`, `artifacts/dev/coverage_scorecard.md`.

---

## Official coverage · eval 3 + f60 eval 4 · 2026-08-29

Command: `.venv/bin/python -m eval.cli --split test --full --out artifacts/test --i-am-at-a-gate` (eval 3 then 4); `.venv/bin/python -m eval.cli --split dev --full --out artifacts/dev`; `.venv/bin/python -m pytest -q`

Eval 3 (f59 official): residual-zero **501/800**, member-identified 501/800, unique 0, auto-clear 0, wall 69621 ms.

Date-window probe: payments at D-2, fees on value_date D. Including D puts 60/72 Regime B stacks in pool; UNIQUE stays 0. Settlement-item date bypass does not apply (those 56 have no settlement.csv rows).

f60: missing RATE_DERIVED ids reconstructed from the rate table. Class 13 recovers. Class 11 refunds still fail.

Eval 4 (f60 official): residual-zero **521/800**. Member-identified 501/800. Unique 0. Auto-clear 0. False clears 0. Wall 68299 ms. Search 800/800.

Dev official: residual-zero **159/239**, member-identified 148/239, unique 0, search 239/239, wall 10066 ms.

NN-16: **4 of 4 spent**. Remaining 80/239 misses are irreducible under current semantics.
