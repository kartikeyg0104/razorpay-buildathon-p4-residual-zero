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

