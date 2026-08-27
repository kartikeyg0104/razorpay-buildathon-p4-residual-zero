# PROGRESS.md

Append-only, written by the executor. One block per checkpoint with the verification command and
its exit status, the commit hash, files touched, and anything surprising. This is the file a fresh
session reads to rebuild state.

**Machine and interpreter, recorded once because the CP3 benchmark is meaningless without it:**
Darwin 25.5.0 (arm64, Apple Silicon), CPython 3.13.7 in `.venv`. System `python3` is 3.14.6; the
venv is deliberately on 3.13 for wheel availability, per PLAN-P1 CP0 note 4.

---

## CP0 · Foundation, config and the definition of success · **BLOCKED** 2026-08-27

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
