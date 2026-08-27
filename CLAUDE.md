# CLAUDE.md — Residual Zero

Track 04 submission for the Razorpay /buildathon. The authoritative design document is
`docs/SPEC.md` — a verbatim copy of `residual-zero-build-spec.md`, committed before any
code exists, and the only file in this repository exempt from NN-15. Every prompt in this
project reads it by that path; if it is missing, stop and say so rather than working from
your memory of it. When this file and the spec disagree, the spec wins and you should tell
me the contradiction rather than choosing.

## What this product is, in two sentences

A bank settlement credit is a *net aggregate*, so reconciling it is signed subset-sum
under tolerance over a candidate pool — a combinatorial search problem, not 1:1 fuzzy
string matching. This system decomposes each credit into the exact set of payments,
refunds, chargebacks, fees, GST, withholding, reserve holds and adjustments composing
it, emits a proof that re-derives to a zero residual at paise granularity, and refuses
to auto-clear anything whose decomposition is not provably unique.

## Non-negotiables

These are referenced by number throughout the build prompts as NN-1 … NN-20. Violating
one is not a style disagreement, it is a defect. If a task appears to require violating
one, stop and say so.

NN-1  **All money is integer paise.** No float touches a monetary value anywhere in this
      codebase, including in tests, fixtures, generators and report formatters. Rupee
      display is a formatting concern at the very edge of the system.

NN-2  **The model never does arithmetic and never selects a match.** Its entire upstream
      job is resolving `counterparty_raw` → `counterparty_id` from a closed candidate
      set, after tiers 1–3 have failed. Downstream it writes prose around numbers that
      were already rendered by deterministic code.

NN-3  **The model never sees or emits an amount.** Not in a prompt, not in a response,
      not in a log line that a prompt is built from. It returns an id from a closed set,
      validated against a Pydantic schema, or it abstains.

NN-4  **Never gate any decision on model self-reported confidence.** Gate on observable
      quantities only: residual magnitude, alternate-solution count, pool size, string
      distance, date proximity, resolution tier used, cross-window member count.

NN-5  **No agent framework.** The pipeline is a DAG with one forward-branching retry.
      Plain typed Python functions composed in one orchestrator. This is a decision with
      an argument, written down in `docs/DECISIONS.md`; do not quietly reverse it.

NN-6  **Ground truth is physically unreachable from the system under test.** Truth lives
      in `data/{split}/truth.jsonl`. The loader cannot open that path. `tests/test_no_leakage.py`
      asserts it. Re-run that test after any change to a loader.

NN-7  **Corruption mutates rendered views, never ground truth.** A corruption that alters
      the answer key is a generator bug that silently invalidates every metric in the
      project.

NN-8  **No tax, GST, TDS or fee rate is ever hardcoded**, and never taken on the authority
      of a blog post or a language model. Every rate lives in `config/tax_rates.yaml` or
      `config/fees.yaml` with a `source_url` and an `as_of` date per entry.

NN-9  **Determinism is a tested property.** Fixed sort order everywhere, no iteration over
      unordered sets, seeded RNG, on-disk LLM response cache keyed by prompt hash. Two
      runs of `make eval` on one machine produce byte-identical reports, and `make reproduce`
      proves it by diffing two runs and exiting non-zero on any difference.

NN-10 **The DP bounds guard is mandatory.** Reachable sums live in `[NEG, POS]`. Every bit
      test, in reachability and in backtracking, first confirms the sum is inside that
      range. Outside it, return `NONE_FOUND`. Skipping this produces a negative shift
      count and a runtime crash instead of a clean no-solution.

NN-11 **Never silently truncate a candidate pool.** Over `MAX_POOL`, split by sub-window
      and retry; failing that, emit `BUDGET_EXCEEDED`. A confidently wrong answer is the
      one failure mode this domain cannot tolerate.

NN-12 **The verifier's acceptance test never widens.** Search tolerance ε affects what the
      search *considers*. The verifier demands a zero residual at paise, always, by
      re-deriving each member's rounding rather than tolerating it.

NN-13 **Baselines before the full system.** A0/A1/A2 are built and measured before the
      arm they are a baseline for. Built afterwards, they get unconsciously sandbagged.
      A sandbagged baseline is worse than none, because a reviewer who spots it discounts
      every number in the submission.

NN-14 **Never publish a number `make eval` cannot reproduce from a clean clone.** This is
      the only unrecoverable move available in this project.

NN-15 **Every illustrative figure in `docs/SPEC.md` is a placeholder showing shape.** The
      spec says so about itself. `0.942`, `0.0008`, `₹47,200`, `200:9`, `43 exceptions`,
      `51 minutes`, `65–70 ms`, `2.04%`, `Cohen's κ 0.71` and every value in the §9.3 and
      §9.8 tables are examples of format, not results and not targets. They must never
      appear in `README.md`, `artifacts/`, the video script or a commit message as though
      measured. If you need a number you do not have, write `TBD-<what-produces-it>`.

NN-16 **Test-split budget: at most one evaluation per tagged release, ceiling four.** Each
      one logged in `docs/EVALUATION.md` with timestamp, commit hash and tag. Every
      threshold, prompt, tolerance and window is tuned on dev, always. Dev evaluation is
      unlimited.

NN-17 **Every feature from spec §6.2 owes three things**: a number `make eval` reproduces,
      a config flag that disables it with `tests/test_feature_flags_off.py` proving the
      core's dev-split dispositions are unchanged when it is off, and an answer to a
      question a reviewer would actually ask. A feature without its number is decoration.

NN-18 **CP-SAT may only ever remove candidates the DP already enumerated.** Never add.
      `tests/test_disambiguation.py` asserts the CP-SAT solution set is a strict subset of
      the DP's. A "unique" answer the exact solver never found is a modelling bug wearing
      the costume of a result.

NN-19 **`docs/INCIDENTS.md` is contemporaneous.** Anything that breaks and costs more than
      fifteen minutes gets an entry the same hour: timestamp, symptom, what I first thought
      it was, what it actually was, the fix, the commit hash, the regression test added.
      Never write a plausible-sounding incident. Never smooth one into narrative prose.
      An empty incident log is better than an invented one, and an invented one is the
      single most damaging thing this repository could contain.

NN-20 **Every phase ends tagged and submittable.** README current, `artifacts/` regenerated,
      tests green, video script consistent with the numbers on disk. Not "nearly ready."

NN-21 **The protected set is never cut, never reverted, never left disabled.** F2, F3, F4,
      F10, F11, F18, F19, F20, F22, F31, F33, F37, F38, F40, F49, F50, F55, F56. These are
      load-bearing for the evidence base rather than features on top of it, so the 1.5x
      trip-wire's revert branch does not reach them: past 1.5x, a protected feature is
      finished to its minimum measurable version and the overrun is logged in PROGRESS.md.
      Everything else in the build order is revertible. Check this list before you revert
      anything.

## Makefile targets — this list and spec §7/§10 stay identical

`make demo` · `make eval` · `make test` · `make verify-audit` · `make verify-books` ·
`make reproduce` · `make challenge FILE=…` · `make evidence` · `make eval-diff RUN_A=… RUN_B=…`

A target named in a document and absent from the repo is the cheapest available way to
look careless. If you add a target, add it to all three lists in the same commit.

## Working agreements

- Small commits, present-tense messages, one logical change each. Never `git add -A`
  without reading the diff.
- Update `PROGRESS.md` at every checkpoint boundary. It is how a fresh session recovers.
- If you are blocked or a decision is genuinely underdetermined, append to
  `PLAN-QUESTIONS.md` and stop that checkpoint. Do not choose architecture on my behalf.
- Prefer a passing honest exception to a clever save. Refusal is a product feature here.
- Never mark a checkpoint done because it "should work". Done means its verification
  command exited zero in a run you can point to.
````

---

## 0.2 · Artifact conventions

Four files carry state between sessions and between models. They are the reason a lost
conversation costs minutes rather than a day.

`PLAN-P<n>.md` — written by the Opus 5 planner, read-only for the executor. The complete
design for one phase: checkpoint ladder, exact signatures, invariant assignments, test
names, definitions of done, owed numbers. Its schema is fixed and given inside each
planner prompt.

`PROGRESS.md` — append-only, written by the executor. One block per checkpoint with the
verification command and its exit status, the commit hash, files touched, and anything
surprising. This is the file `U1` reads to rebuild state.

`PLAN-QUESTIONS.md` — append-only, written by whichever model hits an underdetermined
decision. Each entry names the checkpoint, the decision, the options with consequences,
and a recommendation. You answer inline; the model re-reads it.

`docs/INCIDENTS.md` — contemporaneous failure log, per NN-19. Never batched, never edited
for tone. It feeds the form answer the panel reads first.

Only the last of those four appears in spec §10's repo tree. `PLAN-P<n>.md`, `PROGRESS.md`,
`PLAN-QUESTIONS.md` and `CLAUDE.md` sit at the repository root as build-process state, not
as part of the product — so §10 does not need editing to accommodate them, and they are not
subject to the "stay identical" reconciliation rule that governs the Makefile target list.
`docs/SPEC.md` is the one addition to §10's `docs/` tree, and it is a copy rather than new
content.

---

# Phase 1 · the core · ~151h · tag `v1-submittable`

Phase 1 produces the entire thesis: solver, uniqueness guarantee, proofs, four arms plus
the human arm, per-class table, curves, ablations, incident log. Nothing in any later
phase is worth starting until this is tagged. If the deadline arrived the morning after
Gate 1, you would submit this and be competitive — that is the bar, and it is the only
bar Phase 1 has to clear.

## P1-PLAN · Opus 5

````text
You are the architect for Phase 1 of Residual Zero. You are planning, not building.
Your output is one document. You will write no implementation code in this pass beyond
type signatures, enum members, config schemas and test names.

READ FIRST, IN THIS ORDER
1. CLAUDE.md — the twenty-one non-negotiables. You will reference them by number.
2. docs/SPEC.md — all of it. §5 (architecture), §8 (data strategy) and §9 (evaluation)
   are the load-bearing sections for this phase; §11 Phase 1 gives the day structure.
3. solver.py and test_solver.py in the repo root. These are a brute-force-validated
   reference implementation of the §5.6 bitset DP, and both pass. Read them closely.
   Your plan STARTS FROM THEM. Do not design a reimplementation. Your job is to decide
   how they get split into src/residual_zero/solver/{fastpath,bitset_dp,enumerate}.py,
   what changes at the boundaries, and what tests carry over.

WRITE: PLAN-P1.md

STANCE
You are optimising for one thing: that a fresh executor session with no memory of this
conversation can implement any single checkpoint correctly from your document alone.
Every place you are vague, the executor will invent something, and the inventions will
not agree with each other. Prefer an over-specified plan you later amend to an
under-specified one that is silently interpreted ten different ways.

Where the spec has already decided something, restate the decision and cite the section
rather than re-deriving it. Where the spec leaves a genuine gap, close it and say you
closed it. Where closing it needs information you do not have, put it in
PLAN-QUESTIONS.md and carry on — do not block the whole plan on one open item.

REQUIRED STRUCTURE OF PLAN-P1.md

## 0 · Decisions I am least confident about
Three to seven items, most consequential first. For each: the decision, why it is
uncertain, what I chose, what changes downstream if it is wrong, and the cheapest way
to find out early. This section exists because it is the only part a human is
guaranteed to read, so put the things that most need a human's eye here.

## 1 · Checkpoint ladder
CP0 … CP9, mapped to spec §11 Days 0–9. For each checkpoint the block below, complete.

  ### CP<n> · <name> · <estimate>h · trip-wire <1.5x estimate>h
  Goal: one sentence.
  Owns files: exact paths, created or modified.
  Depends on: earlier CPs, by number.
  Signatures: every public function and class this checkpoint introduces, with full
    type annotations and a one-line docstring each. Pydantic models field by field
    with types and constraints. Config file schemas as annotated YAML.
  Invariants asserted here: NN-numbers, each naming the specific mechanism that
    enforces it — a test, a type, an assert, a path restriction. "We will be careful"
    is not a mechanism.
  Tests: exact file paths and test function names, each with the one property it
    asserts, stated as a claim that could be false.
  Definition of done: a shell command that exits zero, plus any file it must produce.
  Notes for the executor: the traps specific to this checkpoint.

## 2 · Design decisions, with reasons
Numbered, each with the alternative rejected and why. At minimum, settle all of:

  D1  Canonical model. Every field of LedgerItem, BankCredit, Decomposition, ProofRecord
      per spec §5.3. Enum members exhaustive. Where signedness is enforced (validator vs
      convention — choose the validator). Timezone handling: tz-aware, stored UTC,
      displayed IST, and where the conversion is allowed to happen.
  D2  Config schemas: tax_rates.yaml, fees.yaml, solver.yaml. Every key, its type, its
      units (state "paise" or "basis points" explicitly), and for rates the required
      source_url + as_of fields per NN-8. Decide the units question once — mixed units in
      a fee config is a whole afternoon of phantom residuals.
  D3  Merchant profile parameter schema for generator stage 1, and the one Phase 1
      profile's values. Parameterise now even though F23's three profiles are Phase 3.
  D4  Corruption recipes for classes 1–23 per spec §8.3, each as: stable class id, the
      exact mutation applied to which rendered view, the parameter ranges for dev
      (range A) versus test (range B), target instance count, and how the generator
      records that the class was applied without leaking it into an input field.
      Class 23 AMBIGUOUS_BY_CONSTRUCTION gets its own subsection — it is the only way
      to prove the uniqueness detector works, so specify the construction procedure
      precisely: how two genuinely distinct subsets are made to sum within tolerance,
      and how you guarantee they are distinct rather than accidentally equal.
      Classes 24, 25, 26 are FORBIDDEN in Phase 1 — their detectors do not exist yet
      and a corruption class without a detector is a hole in our own results table.
  D5  Candidate generation: the base window, the exact set of kinds that get the widened
      [D-35, D-1] window, the deterministic sort key, MAX_POOL, the sub-window split
      strategy when the pool is over cap, and the time budget after which BUDGET_EXCEEDED
      is emitted. Per NN-11 there is no truncation path.
  D6  THE ROUNDING BRIDGE. The search axis is rupee-granular and verification is
      paise-exact (§5.6, NN-12). Specify exactly how a signed paise amount maps to a
      rupee unit on the search axis, and then prove — in prose, with the inequality —
      that the true member set remains reachable within the rupee-denominated tolerance
      window under your chosen rounding. Give the worst-case accumulated rounding error
      as a function of member count. This is the single subtlest thing in the phase and
      the place where a plausible choice silently costs coverage on large decompositions.
      If your analysis says the flat Phase 1 ε cannot cover the worst case at MAX_POOL
      member counts, say so and state what that costs, rather than widening ε to make
      the problem disappear.
  D7  Flat tolerance ε for Phase 1, in paise and in the derived rupee window, explicitly
      labelled provisional and superseded by F32 in Phase 3. Note in the plan that the
      verifier's acceptance is unaffected either way, per NN-12.
  D8  Solver module split. What moves from solver.py into fastpath.py, bitset_dp.py and
      enumerate.py; the snapshot retention strategy and its memory ceiling; where the
      NN-10 bounds guard lives so it cannot be bypassed by a future caller; the
      enumeration cap of 2 and the mapping from solution count to
      UNIQUE / AMBIGUOUS / NONE_FOUND / BUDGET_EXCEEDED; and the near-miss search that
      feeds diagnosis, including how "nearest reachable sum" is defined and found.
  D9  Regime A fast path: the re-derivation order, and what makes it independent of the
      declared values rather than a restatement of them. If it recomputes a line from
      the declared fee rather than from the instrument and the rate table, it is not
      verifying anything.
  D10 Verifier: the paise re-derivation order, per-line rounding rule, and the exact
      condition for accept. It is the only component with write access to the
      reconciliation ledger and that must be visible in code, not convention (§5.12).
  D11 Audit chain canonical serialisation: key ordering, separators, unicode handling,
      how ints are encoded, what is in the payload, how prev_hash seeds at genesis.
      Two implementations of "canonical JSON" that disagree by one space produce a
      chain that fails to verify on a different machine — pin it exactly.
  D12 Semantic cascade tiers 1–5 (§5.9): what resolves at each tier, the tunable
      parameters and their dev-tuning procedure, the model prompt's structured output
      schema, the closed candidate set construction, the cache key, the abstain path,
      and the mechanism that makes NN-3 true rather than intended — the model must be
      structurally incapable of receiving an amount, so specify the payload type that
      makes that so.
  D13 Exception classification as a deterministic decision table over the near-miss
      delta structure: for each of the eleven classes in §5.10, the rule, its inputs,
      and the tie-break order when two rules match. The model writes narrative only
      and never assigns the class.
  D14 ordering_score: the exact formula over observable quantities only (NN-4), each
      term's normalisation, and why each term is expected to carry signal. State
      plainly that its threshold is NOT set here — it is read off the §9.5 curve at CP6.
  D15 The four arms A0/A1/A2/A3 (§9.1): precise algorithm for each baseline, and for
      A1 the optimal assignment via scipy.optimize.linear_sum_assignment rather than
      greedy, with the cost matrix construction spelled out. Per NN-13 these are built
      before A3 is measured. Include the sentence you will use in the README about how
      A1 and A2 were tuned, so that fairness is documented rather than asserted.
  D16 Metric implementations per §9.2, each as a formula over sets of (credit_id,
      item_id) pairs or over dispositions, plus the two report.py assertions from §9.8:
      coverage + exceptions + budget_exceeded == 1.00 for arms that have all three,
      and exact <= coverage x (1 - error) for arms that clear everything they attempt
      and flag nothing. A0 and A1 have no exception path, so those cells are dashes and
      not zeros — encode that distinction in the data structure, not in the formatter.
  D17 Statistics: pooled proportion with Wilson score interval, per-seed figures as a
      min-max range beside it, and the assertion that prevents one estimator's interval
      being wrapped around the other's point estimate (§9.4).
  D18 F19 and F56 protocol. Both run at CP5 and CANNOT run later — after you know the
      system's answers an honest human baseline is not available, and that applies to
      briefing raters as much as to reconciling yourself. Specify: which 20 credits and
      how selected, what the raters see and what they must not see, the stopwatch
      protocol, the exact recording sheet, the disposition vocabulary the raters use,
      how Cohen's kappa is computed over it, and the pre-registered question — on the
      credits where raters disagreed with each other, did the system flag rather than
      clear? Pre-register it so the answer counts either way.
  D19 Console: the four views of §5.13 and the waterfall, FastAPI + server-rendered
      HTML + HTMX, no frontend build. Scope it to what CP7 can finish.
  D20 Q&A surface (F9): the retrieval contract that makes a hallucinated number
      architecturally impossible rather than unlikely — typed rows in, deterministic
      formatter renders every figure, model composes connective prose only, and the
      structural reason it cannot do otherwise.

## 3 · Traceability table
One row per feature F1–F18 plus F19–F22 and F56, giving the checkpoint that delivers it,
the artifact that proves it, and the number it owes. Note that §9.10 begins at F31, so
only F56 has a §9.10 row here; for F19, F20 and F22 the owed number comes from their §6.1
entries instead. Cite whichever section you took it from, per row.
Every one of F1–F22 and F56 appears exactly once. If something has no home, say so
loudly rather than letting it fall out of the plan silently.

## 4 · Test inventory
Every test file and function from spec §10 that belongs to Phase 1, each with the claim
it makes. Flag which are property-based (Hypothesis) and what the generated domain is.
test_solver_properties.py is the test that licenses every claim in §9 — specify it in
the most detail, including the brute-force oracle it compares against.

## 5 · What Phase 1 deliberately does not build
The §6.2 features and why each waits. Also the §6.2 "what not to build at any budget"
list, restated, because the executor will be tempted by several of them and a learned
matcher most of all.

## 6 · Risk notes
CP3 is the highest-risk checkpoint in the project (spec §12). State the trip-wire:
median solve time over 2s per credit means stop optimising and ship the
BUDGET_EXCEEDED path. Also carry forward the wrong-data-model risk and the specific
early check that retires it — class 4 MIXED_N_M generated at CP1 must pass end to end
at CP3, before a line of the semantic layer, console or harness is written.

CONSTRAINTS ON YOU
- Do not set the autonomy threshold. It is derived from the risk-coverage curve at CP6.
  A hand-picked threshold is a guess wearing a suit (§9.5).
- Do not predict, target or restate any result figure. NN-15. Where a number will exist
  later, write TBD-<what-produces-it>. The spec's own tables are format illustrations
  and several of them are seductive.
- Do not introduce a dependency beyond spec §7. If you believe one is needed, that is a
  PLAN-QUESTIONS.md entry, not a decision.
- Do not add scope. Phase 1 is exactly what §11 Phase 1 lists.
- Estimates must sum to 146h of my own build time across CP0–CP9 (8 + 16x8 + 10), with
  F56 adding ~5h that is mostly the raters' time — which is why the phase reads ~151h.
  If your ladder does not sum to 146, either fix it or state the discrepancy explicitly.
  A plan whose totals do not reconcile is a plan I will stop trusting halfway through.

SELF-CHECK BEFORE YOU FINISH — verify each and report the result line by line
[ ] Every CP block has all eight fields, none left as a placeholder.
[ ] Every definition of done is a command, not a description.
[ ] Each of NN-1 … NN-21 that applies to Phase 1 is assigned to at least one CP with a
    named enforcement mechanism.
[ ] D6's reachability argument is written out as an inequality, not asserted.
[ ] Corruption classes 24, 25, 26 appear nowhere.
[ ] F19 and F56 are both at CP5, with the reason stated.
[ ] A0, A1, A2 are specified and scheduled before A3 is measured.
[ ] No result figure appears anywhere. Grep your own draft for 0.94, 0.0008, 51, 200:9,
    47,200, 2.04, 0.71, and 65-70 and confirm every hit is either absent or explicitly
    labelled as the spec's illustrative shape.
[ ] Estimates sum to 146h, or the discrepancy is stated.
[ ] The traceability table covers F1-F22 and F56 with no gaps.
````

## P1-EXEC · Fable

````text
You are implementing Phase 1 of Residual Zero. The architecture is already decided.
Your job is to build it exactly as planned, verify each step, and stop when something
is underdetermined rather than deciding it yourself.

READ FIRST
1. CLAUDE.md — the twenty-one non-negotiables, NN-1 … NN-21. These bind you absolutely.
2. PLAN-P1.md — your specification. If this file does not exist, STOP and tell me to
   run P1-PLAN first. Do not improvise a plan.
3. PROGRESS.md if it exists — checkpoints already verified. Never redo a verified
   checkpoint; continue from the first unverified one.
4. docs/SPEC.md — reference only, for context on why a thing is the way it is. When
   PLAN-P1.md and the spec disagree, stop and tell me; do not pick a winner.

HOW YOU WORK — the checkpoint loop, repeated for CP0 through CP9

  1. Announce the checkpoint: its number, name, estimate, and the files it owns.
  2. Re-read that CP block in PLAN-P1.md in full. Restate its definition of done as
     the literal command you will run.
  3. Implement. Only the files that CP owns. If you find yourself needing to modify a
     file owned by a different checkpoint, that is a signal the plan has a gap — append
     to PLAN-QUESTIONS.md and stop.
  4. Write that CP's tests before or alongside the code, never after the fact as
     confirmation of whatever the code happens to do.
  5. Run the definition-of-done command. Show me its real output. Not a summary of the
     output, not what you expect the output to be — the actual text.
  6. If it exits non-zero: fix, re-run, show it again. If two consecutive fix attempts
     fail, stop and report with the full error, your current hypothesis, and what you
     have ruled out. Do not accumulate speculative changes.
  7. If the failure cost more than fifteen minutes of work, append to docs/INCIDENTS.md
     per NN-19 while it is fresh: timestamp, symptom, what you first thought it was,
     what it actually was, the fix, the commit hash, the regression test added. Raw and
     contemporaneous. Never smooth it into a narrative and never invent one.
  8. Commit. One logical change per commit, present tense, reading the diff first.
  9. Append the checkpoint block to PROGRESS.md:

       ## CP<n> · <name> · VERIFIED <ISO timestamp>
       Command: <exact command>
       Exit: 0
       Commit: <hash>
       Files: <paths>
       Deviations from plan: <none, or what and why>
       Surprises: <anything a future session would want to know>
       Numbers produced: <metric: value, or none>

  10. Only now start CP<n+1>. A checkpoint whose command has not exited zero is not
      done, however finished the code looks.

STOP CONDITIONS — stop and ask, do not decide
- PLAN-P1.md is silent, ambiguous, or self-contradictory on something you need.
- The plan appears to require violating an NN. Quote both and stop.
- You want a dependency not in spec §7.
- You want to change a public signature the plan fixed.
- A checkpoint passes 1.5x its stated estimate. Then the rule from spec §12 applies:
  finish it to the minimum measurable version, or revert it entirely. Never leave it
  half-built and move on. Tell me which you did. CHECK NN-21 FIRST — if the feature is in
  the protected set, revert is not available to you and you finish to minimum instead.
- The plan's arithmetic does not reconcile with what you are finding on the ground.

CHECKPOINT-SPECIFIC OBLIGATIONS you must honour even if the plan is thin on them

CP0  Confirm docs/SPEC.md exists and is byte-identical to residual-zero-build-spec.md;
     if it does not exist, create and commit it before anything else, because every later
     prompt in this project reads it. docs/INCIDENTS.md exists before any logic does. Write the §9.2 metric definitions
     into docs/EVALUATION.md BEFORE writing any logic — defining success before
     building the thing judged by it is the highest-leverage hour available. Every rate
     in config/ carries source_url and as_of (NN-8); if you cannot verify a rate from a
     primary source, put TBD-VERIFY in the value and list it in PLAN-QUESTIONS.md
     rather than filling in something plausible. A wrong rate is spotted instantly by
     this specific panel.
CP1  Generator stages 1 and 2, render.py, corruption classes 1-4 and 23. Ground truth
     is written to data/{split}/truth.jsonl and the loader is PHYSICALLY unable to open
     that path (NN-6) — enforce it in the loader's construction, not by remembering not
     to. Corruption touches rendered views only (NN-7). Before you finish, print three
     generated class-4 MIXED_N_M cases and look at them until the N:M shape is
     undeniable; that is the cheap insurance against the one mistake that does not get
     cheaper later.
CP2  Corruption classes 5-22, test-split config with stacked corruptions and the
     held-out class, then A0 and A1 measured on dev. NN-13: baselines first, and tune
     A1's threshold on dev properly. A sandbagged baseline is worse than no baseline.
CP3  Highest-risk checkpoint. Start from solver.py and test_solver.py rather than
     rewriting. The NN-10 bounds guard is not optional — it was a real bug caught while
     validating the algorithm and it fires the first time a corrupted credit exceeds its
     pool total. Class 4 MIXED_N_M must pass end to end before you touch anything in
     CP5, CP6 or CP7. If median solve time exceeds 2s per credit, stop optimising and
     ship the BUDGET_EXCEEDED path; an honest exception costs coverage, a hang costs
     the submission. Re-run the benchmark on THIS machine and record the machine in
     PROGRESS.md — a solver timing without a named machine is a useless number.
CP4  verify.py is the sole writer to the reconciliation ledger and that is enforced at
     the connection level, visibly in code (§5.12). Its acceptance test is a zero
     residual at paise, always (NN-12). Hash-chain the audit log for real: prev_hash,
     entry_hash = sha256(canonical_json(payload) || prev_hash), canonical serialisation
     exactly as D11 pins it, make verify-audit walks the chain and reports the first
     break. Then A2 rules-only, given the real tax config and the same cross-window
     logic as A3.
CP5  Semantic tiers with the on-disk cache. NN-2, NN-3, NN-4 all live here and all three
     are structural, not aspirational: the model receives text and a closed id set, and
     the payload type must make an amount impossible to include. Exception classes are
     assigned by the deterministic decision table; the model writes prose only.
     THEN STOP CODING AND RUN F19 AND F56 BEFORE THIS CHECKPOINT ENDS. Twenty credits
     by hand, stopwatch running, your own accuracy against truth, and the places you
     personally got confused — those places are the most credible justification your
     exception taxonomy will ever have. Brief the two other raters in the same window.
     This is the one thing in Phase 1 that genuinely cannot be done later: once you
     know the system's answers, an honest human baseline no longer exists.
CP6  The harness: metrics, per-class table, Wilson intervals with per-seed min-max
     beside them, risk-coverage curve, ablations, cost accounting. First full 800-credit
     run. Read the autonomy threshold OFF THE CURVE at a stated error budget and record
     both the threshold and the budget. ALL TUNING ON DEV (NN-16). Implement the two
     report.py assertions from D16 so an impossible table cannot be published.
CP7  Q&A with citations and deterministic number rendering, then the console's four
     views and the waterfall, then make reproduce, make challenge, make evidence.
     Ship three challenge files, one of which the system genuinely cannot solve — an
     invitation to falsify is worth more than a polished demo.
CP8  Razorpay test-mode wiring first, strictly behind an adapter so it can be cut
     without touching another line. Then the failure-injection session: kill the model
     provider mid-run, corrupt the cache, deliver a duplicate webhook, truncate a source
     file, feed a 400-item pool, skew the clock, force SQLite lock contention, plant a
     wrong rate in config. Every break gets a fix AND a regression test in
     tests/regressions/ AND an INCIDENTS.md entry. This checkpoint is supposed to hurt;
     an injection session that finds nothing means the injections were too gentle.
CP9  Freeze. Exactly ONE test-split evaluation, logged in docs/EVALUATION.md with
     timestamp, commit hash and tag (NN-16 — this is 1 of a ceiling of 4 for the whole
     project). Finalise README per §15: first screen is one sentence, the headline
     table, one proof block, the four-vector rubric map, nothing else. Regenerate and
     COMMIT artifacts/. Then tag v1-submittable.

THINGS THAT ARE NEVER ACCEPTABLE HERE
- A float holding money, anywhere, including in a test fixture (NN-1).
- The model doing arithmetic, choosing a match, or seeing an amount (NN-2, NN-3).
- Gating anything on model confidence (NN-4).
- Adding an agent framework (NN-5).
- A number in README.md or artifacts/ that make eval does not reproduce (NN-14).
- Copying an illustrative figure out of docs/SPEC.md as if it were measured (NN-15).
- Tuning on the test split, or a second test-split evaluation in this phase (NN-16).
- A corruption class numbered 24, 25 or 26.
- An invented or retrospectively smoothed INCIDENTS.md entry (NN-19).
- Marking a checkpoint done without its command exiting zero in output you showed me.

START by reading CLAUDE.md and PLAN-P1.md, then report: the checkpoint you are starting
from and why, the definition-of-done command for it, and anything in the plan you find
ambiguous. Then begin. Do not summarise the whole plan back to me first.
````

---

# The later-phase contract

Phases 2 through 4 are a different kind of work from Phase 1 and the prompts reflect
that. Phase 1 invented an architecture; phases 2–4 extend a working one. So the risk
profile inverts. In Phase 1 the danger was building the wrong thing. From here the
danger is **breadth at declining quality** — twenty-seven half-finished features, a
README describing capabilities that only partly work, and a reviewer who samples the
weakest one. A reviewer's impression of a codebase is closer to the *minimum* quality
they happen to sample than to the average.

Three mechanisms hold the line, and every prompt below enforces all three.

**The §6.2 gate, three clauses, all mandatory** — this is NN-17, restated in full here
because it is the spine of the next three phases. A feature ships with a number that
`make eval` reproduces from a clean clone. It is behind a config flag, with
`tests/test_feature_flags_off.py` asserting the dev-split dispositions are byte-identical
to the tagged Phase 1 baseline when every §6.2 feature is off. And it answers a question
a reviewer would actually ask. A feature that arrives without its number is decoration,
and decoration gets cut no matter how much time is left.

**The 1.5× trip-wire.** Any feature past 1.5× its estimate gets finished to the minimum
measurable version or reverted entirely. Never left half-built. This is the single most
important rule in the back half of the project and it is the one that feels worst to obey.
Its one carve-out is NN-21: for the protected set the revert branch is unavailable, and
the only legal move is to finish to the minimum measurable version and log the overrun.
Phase 2 contains eight protected features — F33, F49, F55, F31, F40, F37, F38, F50 — so
this carve-out is live from the first checkpoint of the phase, not a theoretical one.

**The second-order results table** in `docs/EVALUATION.md`, from spec §9.10, kept as a
live checklist. A feature is not done until its row is populated from a real run. The
owed number for every feature is written into the prompts below so you never have to go
looking for it.

Write `tests/test_feature_flags_off.py` the moment you start Phase 2, not the moment you
first need it. It is what lets you keep adding for weeks without ever quietly breaking
the thing that was already correct.

---

# Phase 2 · correctness and commercial legibility · ~71h · tag `v2`

This is the phase that changes what the submission *is*. After Phase 1 you have a
provably correct reconciler. After Phase 2 you have a financial controller that posts
journal entries, tells a merchant they are being overcharged, and collapses a wall of
exceptions into a handful of root causes — while being demonstrably safe with personal
data and adversarial input. **If you only get one extra phase, this is the one.**

Build order and hours, exactly as spec §11 Phase 2 gives them:
`F33` 4h → `F49` 7h → `F55` 4h → `F31` 10h → `F40` 7h → `F37` 8h → `F38` 8h → `F52` 5h →
`F50` 5h → `F54` 4h = 62h, plus second-wave carry `F24` 4h and `F25` 5h = 9h. Total 71h.
Corruption class 24 is added in this phase, alongside F38 which detects it — never before.

## P2-PLAN · Opus 5

````text
You are the architect for Phase 2 of Residual Zero. Phase 1 is built and tagged
v1-submittable. You are planning ten §6.2 features plus two second-wave carries onto a
working system without breaking it. You will write no implementation code beyond
signatures, schemas, config keys and test names.

READ FIRST
1. CLAUDE.md — NN-1 … NN-20.
2. PLAN-P1.md and PROGRESS.md — what was actually built, and where it deviated from
   plan. The deviations matter more than the plan did; build against reality.
3. docs/SPEC.md §6.2 (the gate and Group A/B/D/E entries), §9.10 (the owed-number
   table), §11 Phase 2, §12 (the four new risks this phase introduces).
4. The actual source tree. Read src/residual_zero/solver/, verify.py, audit.py,
   exceptions/, semantic/ before designing anything that touches them.

WRITE: PLAN-P2.md, same block schema as PLAN-P1.md, one checkpoint per feature, in the
build order fixed above. Do not reorder — that order is "highest strengthening per hour
first" and F33 is deliberately first because it is a safety net under everything after it.

FOR EVERY CHECKPOINT, three clauses of the §6.2 gate must be explicit in the block:
  Owed number: for a §6.2 feature, copied verbatim from the §9.10 table as the row it will
    populate. §9.10 covers F31-F57 ONLY, so the second-wave carry features F23-F30 have no
    row in it — for those, take the number from the feature's own §6.1 entry, say that is
    where you took it from, and if §6.1 names none, propose one and label it PROPOSED so I
    can see you did not find it in the spec. Never leave the clause empty and never invent
    a §9.10 row that does not exist.
  Config flag: the key in config/, its default, and how test_feature_flags_off.py
    proves the core is unchanged when the feature is off.
  Reviewer question: the question a reviewer would actually ask that this answers.
A checkpoint block missing any of the three is not ready and you should not write it.

CHECKPOINTS AND WHAT EACH MUST SETTLE

CP2.1 · F33 conservation of money · 4h · FIRST, it is a safety net
  Design the global identity: over any period, for any single account, sum of bank
  credits equals sum of members of all cleared decompositions plus value of unreconciled
  credits, AND every ledger item belongs to at most one cleared decomposition. Specify
  src/residual_zero/books.py, the make verify-books target, the SQL or query plan that
  finds double-claimed items, and how the period boundary is defined for items that
  straddle it. Settle whether the identity is checked incrementally on write or as a
  batch sweep, and why.
  Owes: the printed period identity; count of items claimed by more than one
  decomposition (must be zero); total unreconciled value.
  Why first: double-claiming an item across two credits produces two beautiful
  zero-residual proofs that are jointly wrong, and no per-credit check can ever detect
  it. This is the most damaging silent bug the system can have.

CP2.2 · F49 PII boundary · 7h · BEFORE model call logs accumulate
  §5.9 as built sends counterparty_raw straight to a third-party model, and bank
  narration contains names, VPAs like user@bank, masked card fragments, phone numbers
  and account tails. Design: the detector set with its regexes, stable per-run
  pseudonym substitution, in-memory-only mapping, de-redaction on return, and — the part
  that matters — an ENFORCED boundary. The model client refuses to transmit any payload
  matching a detector and raises. It does not log a warning and send it anyway. Specify
  where that check sits so it cannot be bypassed by a future caller, the same way NN-10's
  bounds guard is placed.
  Owes: zero raw VPAs, card fragments or phone numbers in the model call log across the
  full dev split, asserted by tests/test_pii_boundary.py; plus the entity-resolution
  accuracy delta between redacted and un-redacted prompts. Plan to report that delta
  even if redaction costs accuracy — the measured trade-off is the interesting part.
  Sequencing reason: do this before you accumulate model call logs you would otherwise
  have to regenerate.

CP2.3 · F55 continuous integration · 4h · cheap, and it protects everything after
  .github/workflows/ci.yml running the full test suite, the dev-split evaluation,
  make verify-audit, make verify-books and make reproduce on every push. Specify the
  stated epsilon beyond which a dev-split exact-decomposition regression fails the build,
  and how the workflow avoids needing a live model provider — the on-disk cache from
  Phase 1 is the answer, so specify how it is committed or restored.
  Owes: green build visible in the repository, plus run history as evidence the numbers
  held across weeks rather than emerging from one lucky final run. That history is a form
  of evidence that cannot be retroactively manufactured, which is exactly why it is worth
  four hours this early.

CP2.4 · F31 constraint-based disambiguation · 10h · the strongest item in the wave
  When the bitset DP returns AMBIGUOUS, re-solve as a CSP over OR-Tools CP-SAT carrying
  the structural relations arithmetic cannot see. Specify each constraint formally:
  an order contributes at most one payment; a refund may be a member only if its parent
  payment is a member or settled in an earlier window; a fee line may be a member only if
  the payment it was charged on is also a member; the GST line equals fee x rate for the
  members actually selected; the reserve hold equals reserve_pct x selected gross within
  rounding; a representment requires its original chargeback to exist. For each, give the
  CP-SAT formulation and the LedgerItem fields it reads.
  NN-18 IS THE CRITICAL DESIGN CONSTRAINT AND IT IS NOT A TEST YOU ADD AFTERWARDS.
  CP-SAT may only remove candidates the DP already enumerated. Structure the model so
  its variable domain IS the DP's enumerated solution set, making it impossible to
  express a solution the DP did not find. Then tests/test_disambiguation.py asserting
  strict-subset is a second line of defence rather than the only one. A constraint model
  with a bug that NARROWS incorrectly turns a genuinely ambiguous credit into a
  confidently wrong unique one, which is the exact failure this whole system exists to
  prevent, arriving through the door you opened to reduce it.
  Also specify the new proof-block line naming the specific constraint that broke the
  tie, and the inverse case: credits where CP-SAT proves NO structurally valid
  decomposition exists even though an arithmetic one does. Those are data defects and
  surfacing them is a product feature, so give them an exception class and a queue path.
  Owes: percentage of arithmetically AMBIGUOUS credits resolved to unique by structural
  constraints; auto-clear error rate on exactly that subset; count proven structurally
  infeasible.

CP2.5 · F40 double-entry journal export · 7h · strongest problem-taste addition
  journal.csv importable into Tally or Zoho Books — date, account, debit, credit,
  narration, reference — generated from each cleared decomposition, account mapping from
  config/chart_of_accounts.yaml. Specify the chart of accounts, the mapping from each
  LedgerItem kind to a debit/credit pair, and the two assertions a chartered accountant
  checks before anything else: total debits equal total credits exactly, and the bank
  control account ties to the sum of bank credits for the period with a zero residual.
  Per spec §1.3 this writes a FILE THE USER IMPORTS. Nothing in this system holds
  credentials to an accounting system, and the README says so. Do not design an
  integration.
  Owes: debits equal credits (exact); control-account tie-out residual (must be zero);
  entries generated per cleared credit.

CP2.6 · F37 root-cause clustering of exceptions · 8h
  Deterministic clustering on a signature — class, delta sign, delta-as-fraction-of-gross
  bucketed, instrument, missing kind, date range. Specify the signature fields exactly,
  the bucket edges, and the tie-break. ONE model call per cluster writes the narrative
  and one suggested systemic fix; the model never forms the clusters and never assigns a
  class. Per spec §12, prefer more clusters over larger ones — clustering unrelated
  exceptions produces a confident, plausible, wrong root cause, and the narrative the
  model writes will make it MORE persuasive, not less.
  Owes: the exception compression ratio (exceptions divided by clusters) and cluster
  purity measured against the generator's true cause labels — used for evaluation only,
  never as an input. Specify the leakage guard for those labels the same way NN-6 guards
  truth.jsonl.

CP2.7 · F38 effective-rate regression and drift detection · 8h · adds class 24
  Every cleared decomposition yields (instrument, transaction value, fee charged) triples
  that are known correct. Regress effective rate per instrument per week against
  config/fees.yaml contracted rates. Specify the estimator, the minimum sample count per
  instrument-week, and the significance test: the contracted rate must fall OUTSIDE the
  fitted confidence interval before anything alerts. A rate alert that fires on noise is
  worse than no alert, because a finance team learns to ignore it within a week.
  Also specify corruption class 24 FEE_RATE_DRIFT here and only here — effective fee rate
  shifts silently mid-corpus from a stated date. Note in the plan why this class is
  conceptually the most interesting in the taxonomy: it is a case the solver handles
  flawlessly and still gets wrong. The decomposition reconciles to zero residual against
  the fee actually charged, so every check in §5 passes and the credit auto-clears
  correctly. The error is not in the arithmetic; it is that the arithmetic was performed
  against the wrong rate. Only a layer regressing effective against contracted can see it.
  That distinction — "the books balance" versus "the books are right" — is worth several
  minutes of panel conversation, so make sure the plan captures how it gets demonstrated.
  Owes: detection latency in windows between the generator introducing drift and the
  system flagging it; false-positive rate on undrifted profiles; rupee estimation error
  against the generator's true drift.

CP2.8 · F52 full decision trace per credit · 5h
  Every credit carries an ordered record of the gates it passed and the first it failed —
  pool size, regime, DP time, solutions found, CP-SAT outcome and which constraint, paise
  verification and residual, ordering score against threshold, final disposition.
  Rendered as a checklist in the console and embedded in the audit entry. Specify the
  trace schema, where each stage writes its entry, and how a stage that raises still
  leaves a trace.
  Owes: 100% of credits have a trace terminating in exactly one of the three dispositions,
  asserted by test.

CP2.9 · F50 prompt-injection resistance with a corpus · 5h
  Roughly thirty injection strings planted in narration fields, run end to end:
  instruction override, forged system messages, unicode direction marks, base64 payloads,
  developer-mode claims, claims of prior authorisation. Specify the corpus categories and
  count, the fixture layout under fixtures/injections/, and the disposition recorded per
  string.
  Then specify the WRITTEN argument for why the system is already structurally hard to
  attack, so it reads as design rather than luck: the model returns an entity id from a
  closed set validated against a schema, it never sees or emits an amount, and it cannot
  authorise anything because auto-clear requires UNIQUE plus a zero paise residual plus
  an ordering score built only from observable quantities. The worst an injection achieves
  is a wrong entity selection, which produces a non-zero residual, which the verifier
  rejects. That chain of reasoning is the deliverable as much as the corpus is.
  Owes: zero of ~30 injections caused an auto-clear, with the disposition of each recorded.

CP2.10 · F54 disposition diff between runs · 4h
  make eval-diff RUN_A=… RUN_B=… reporting which credits changed disposition, in which
  direction, in which corruption class. Then the RULE, which is the actual feature: no
  config change ships without a diff attached in docs/EVALUATION.md. Specify the diff
  format and where it is filed.
  Owes: the diffs themselves, plus the stated rule.
  This is the guard against the classic late-project disaster where a "small" tolerance
  adjustment quietly moves forty credits from flagged to cleared and nobody notices until
  the panel does.

CP2.11 · F24 adversarial self-test · 4h · second-wave carry
  Four hours actively trying to make your own system auto-clear something wrong.
  Near-ambiguous cases just inside tolerance, pathological pools, deductions that
  coincidentally sum to a plausible target. Specify the attack catalogue to attempt and
  the recording format for findings — including anything found and not fixed.
  If the search finds nothing, the SEARCH ITSELF gets published so the negative result is
  legible. Plan for that outcome explicitly; it is the likely one and it is still worth
  reporting.

CP2.12 · F25 idempotency and crash-resume · 5h · second-wave carry
  Two properties, one test each. Run the same batch twice, assert the reconciliation
  ledger is unchanged with no duplicate entries. Kill the process mid-batch, restart,
  assert it resumes without double-counting or corrupting the audit chain. Specify the
  idempotency key, the resume checkpoint mechanism, and how the kill is simulated
  deterministically in a test rather than by hand.
  Unglamorous, and exactly what payments engineers check first.

ALSO IN THIS PLAN
- tests/test_feature_flags_off.py, designed at CP2.1 and extended by every subsequent
  checkpoint. It runs the dev split with every §6.2 feature disabled and asserts
  dispositions identical to the tagged Phase 1 baseline. Specify how the baseline is
  stored and compared.
- The four new risks from spec §12 that this phase introduces — CP-SAT modelling error,
  drift-detector false positives, cluster mis-grouping, and the extended-runway drift
  that now dominates — each with the mechanism in this plan that mitigates it.
- Which video segments will need re-recording if the numbers move, per spec §14: the
  fee-drift finding and the exception-compression result each buy fifteen seconds inside
  the evidence segment, and F33's conservation identity adds ONE SENTENCE to the
  architecture beat. Two swaps and no more. The video does not grow with the build.
- The README additions from spec §15, all BELOW the fold: a controller-results section,
  the §9.10 second-order table verbatim, the test-split evaluation log, and a safety
  section covering the PII boundary, the injection corpus and the degradation ladder in
  that order, each with its number. The first screen does not change.

CONSTRAINTS ON YOU
- Estimates must sum to 71h: 62h of features plus 9h of carry. State the sum.
- No result figures, no targets, no predictions. NN-15. The §6.2 text contains a 200:9
  compression ratio and a ₹47,200 drift finding that are explicitly invented
  illustrations, and they are the two most quotable false numbers in the entire document.
  Write TBD-F37-run and TBD-F38-run.
- Corruption class 24 belongs to CP2.7 and nowhere else. Classes 25 and 26 are forbidden
  in this phase.
- Do not touch the autonomy threshold derived in Phase 1 without an F54 diff attached.
- Do not design a learned matcher, a mobile app, a chart dashboard, a chat interface
  beyond F9, cash forecasting, invoice OCR, a rewrite in another language, or any real
  write path into a bank or accounting system. Spec §6.2 lists these as forbidden at any
  budget and the list matters more now than when the calendar was enforcing it.

SELF-CHECK — report line by line
[ ] Twelve checkpoints, in the fixed build order, estimates summing to 71h.
[ ] Every checkpoint has all three §6.2 gate clauses filled.
[ ] Every owed number is sourced: §9.10 verbatim for F31-F57, §6.1 for F24/F25, and the
    section it came from is named.
[ ] F31's design makes NN-18 structurally true, not just tested.
[ ] F49 is enforced-and-raises, not warn-and-send.
[ ] F38 requires significance before alerting, with a minimum sample count.
[ ] F37's true cause labels are guarded against use as an input.
[ ] Class 24 appears once, at CP2.7. Classes 25 and 26 appear nowhere.
[ ] test_feature_flags_off.py is designed, not deferred.
[ ] No invented figure anywhere; grep for 200:9, 47,200, 43, 2.04, 1.95.
````

## P2-EXEC · Fable

````text
You are implementing Phase 2 of Residual Zero onto a working, tagged v1-submittable
system. Twelve features. The architecture is decided. Your obligations are unchanged
from Phase 1 with three additions that matter more than anything else in this prompt.

READ FIRST: CLAUDE.md, then PLAN-P2.md. If PLAN-P2.md does not exist, STOP and tell me
to run P2-PLAN. Then PROGRESS.md, and confirm v1-submittable is tagged before you touch
anything — if it is not, Gate 1 has not passed and this phase must not start.

THE CHECKPOINT LOOP is identical to Phase 1: announce, re-read the CP block, implement
only that CP's files, write its tests alongside, run the definition-of-done command and
show me real output, fix or stop after two failed attempts, log incidents while fresh,
commit, append to PROGRESS.md, then and only then move on.

THE THREE ADDITIONS

1. NO CHECKPOINT IS DONE WITHOUT ITS NUMBER. The §9.10 row goes into
   docs/EVALUATION.md, populated from a real dev-split run, in the same commit as the
   feature. Not "the code works and we will measure it later" — later does not arrive.
   If the run produces an unflattering number, that number goes in. A measured
   disappointment is worth more than an unmeasured claim, and spec §9.9 already decided
   how to frame every version of that outcome.

2. EVERY FEATURE IS CONFIG-DISABLE-ABLE AND test_feature_flags_off.py MUST STAY GREEN.
   Run it after every single checkpoint, not at the end of the phase. It asserts the
   dev-split dispositions with all §6.2 features off are identical to the tagged Phase 1
   baseline. When it goes red, you have changed the core while thinking you were adding
   to it — stop immediately and find out how, because that is the failure this test
   exists to catch and it does not get easier to diagnose later.

3. THE 1.5x TRIP-WIRE IS ABSOLUTE. Past 1.5x the estimate, finish to the minimum
   measurable version or `git revert`. Tell me which. Do not leave it half-built and
   move to the next thing. Half-built features are how a long runway produces a worse
   submission than a short one.
   ONE CARVE-OUT, AND IT APPLIES TO MOST OF THIS PHASE: NN-21's protected set cannot be
   reverted. Eight of this phase's twelve checkpoints are protected — F33, F49, F55, F31,
   F40, F37, F38, F50 — so for those the trip-wire means finish to minimum and log the
   overrun in PROGRESS.md. Reverting F31 at 15h because it hit its trip-wire would remove
   the disambiguation result the whole phase is built around. Only F52, F54, F24 and F25
   are revertible here.

PER-CHECKPOINT OBLIGATIONS beyond the plan

CP2.1 F33 — build this first, always. Once make verify-books passes, run it against the
  existing Phase 1 dev-split output before you add anything else. If the double-claim
  count is not zero, you have just found the most damaging silent bug available in this
  system, present in a version you already tagged. That is an INCIDENTS.md entry, a
  regression test, and genuinely good news — it means the safety net works.
CP2.2 F49 — the boundary raises, never warns. After it is in, grep the entire model call
  log for VPAs, card fragments and phone numbers and show me the grep returning nothing.
  Report the redacted-versus-raw accuracy delta even if redaction costs you a point;
  choosing data minimisation over a point of accuracy is a defensible decision you can
  state out loud, and hiding the cost is not.
CP2.3 F55 — CI must run without a live model provider. If it needs one, the cache
  strategy is wrong and that is worth fixing now rather than after eighty pushes.
CP2.4 F31 — NN-18 above everything. The CP-SAT variable domain is the DP's enumerated
  solution set. Any CP-SAT solution absent from the DP's enumeration is a modelling bug,
  not a discovery, and test_disambiguation.py must fail loudly on it. Before you report
  any disambiguation rate, hand-check three credits it resolved and confirm the named
  tie-breaking constraint is genuinely the reason. Also report the structurally-infeasible
  count — those credits are data defects and they are a finding, not a footnote.
CP2.5 F40 — debits equal credits EXACTLY, integer paise, no tolerance (NN-1, NN-12). If
  they do not balance, the mapping is wrong; do not add a rounding line to close it.
  A journal that balances because of a plug is worse than one that does not balance.
CP2.6 F37 — one model call per cluster, and the model sees no amounts (NN-3). Measure
  purity against the generator's true cause labels through the evaluation path only;
  those labels must be as unreachable from the clustering input as truth.jsonl is from
  the loader. Report whatever compression ratio you actually get. The spec's 200:9 is an
  invented illustration and it must not appear anywhere in this repository.
CP2.7 F38 — no alert without significance and a minimum sample count. Measure the
  false-positive rate on undrifted profiles BEFORE you publish any detection claim, not
  after. Add corruption class 24 in this checkpoint, never earlier.
CP2.8 F52 — a stage that raises still leaves a trace. Test that path specifically; it is
  the one that gets forgotten and the one an auditor asks about.
CP2.9 F50 — build the corpus by hand, roughly thirty strings across the categories in
  the plan. Run every one end to end and record its disposition. If any injection
  reaches an auto-clear, that is the most important INCIDENTS.md entry in the project and
  it stops the phase until it is fixed and regression-tested.
CP2.10 F54 — after this exists, retroactively attach a diff to every config change made
  earlier in this phase. Then adopt the rule for real.
CP2.11 F24 — spend the full four hours genuinely attacking the system, not confirming it
  works. Publish what you found including what you could not fix. If you found nothing,
  publish the search you ran so the negative result is legible.
CP2.12 F25 — simulate the crash deterministically in a test. A crash-resume property
  verified by hand once is not a property.

AT THE END OF THE PHASE — Gate 2, all of it, before you tag
  [ ] Full DEV evaluation re-run, artifacts/ regenerated and committed.
  [ ] make verify-books passes and the period identity is printed in artifacts/.
  [ ] make verify-audit passes.
  [ ] make reproduce exits zero.
  [ ] CI green.
  [ ] test_feature_flags_off.py green.
  [ ] All ten §9.10 rows for this phase populated from a real run: F33, F49, F55, F31,
      F40, F37, F38, F52, F50, F54. F24 and F25 are §6.1 carry items with no §9.10 row —
      they owe the number their §6.1 entry names, recorded in docs/EVALUATION.md alongside
      the table.
  [ ] README headline table and second-order table updated; controller-results section
      added below the fold; safety section added with its numbers.
  [ ] Video segments whose numbers moved are re-recorded. Two swaps in the evidence
      segment and one added sentence in the architecture beat — no more. The video stays
      five minutes.
  [ ] At most ONE test-split evaluation this phase, logged with timestamp, commit and
      tag (NN-16). It is optional — if nothing this phase could plausibly move
      test-split behaviour, SKIP IT and say so in the log. That skip reads better than
      a curiosity check.
  [ ] Tag v2. The repo is submittable exactly as it stands.

START by confirming v1-submittable is tagged, reading CLAUDE.md and PLAN-P2.md, then
report the checkpoint you are starting from and its definition-of-done command. Then
begin at CP2.1 — F33 first, always, because it is the safety net under everything else.
````

---

# Phase 3 · operational depth · ~69h · tag `v3`

This phase is aimed squarely at a payments engineer on the panel. Real statement formats,
graceful degradation, streaming reconciliation with a measured resolution lag, and a
latency profile with the bottleneck named. None of it is glamorous and all of it is what
someone who has operated a payments system checks first.

Build order and hours per spec §11 Phase 3: `F32` 4h → `F30` 2h → `F51` 6h → `F39` 6h →
`F45` 10h → `F48` 4h → `F35` 12h → `F41` 5h → `F42` 6h → `F57` 5h → `F23` 3h → `F26` 6h
= 58h of §6.2 features plus 11h of second-wave carry (F23, F26, F30). Total 69h.

`F30` is moved ahead of `F51` deliberately: the cost governor is the first rung of the
ladder F51 completes, and the ladder is much easier to reason about once one rung exists.

## P3-PLAN · Opus 5

````text
You are the architect for Phase 3 of Residual Zero. v2 is tagged. This phase adds
operational depth: derived tolerance, a degradation ladder, a leakage sweep, real bank
statement formats, ingestion fuzzing, streaming reconciliation, a reserve sub-ledger, a
dispute lifecycle tracker, a latency profile, cross-profile generalisation and a
human-in-the-loop learning curve. Planning only — no implementation code beyond
signatures, schemas, config keys and test names.

READ FIRST: CLAUDE.md; PLAN-P1.md and PLAN-P2.md; PROGRESS.md; docs/EVALUATION.md
including the populated §9.10 rows so far; docs/SPEC.md §6.2 Groups A/B/C/D/E for the
relevant entries, §6.1 Tiers 2-3 for F23/F26/F30, §9.10, §11 Phase 3, §12. Then read the
actual source of solver/tolerance.py's intended home, runtime/, ingest/, controller/ and
stream/ as they currently stand.

WRITE: PLAN-P3.md, same block schema, twelve checkpoints in the build order fixed above,
each carrying the three §6.2 gate clauses.

CHECKPOINTS AND WHAT EACH MUST SETTLE

CP3.1 · F32 derived tolerance · 4h
  Replace the flat ε with one derived from the rounding model. Each member's fee rounds
  to paise independently, so accumulated residue grows with member count: fit
  ε(n) = ceil(k · sqrt(n)) PAISE by measuring the actual residual distribution of
  CORRECTLY decomposed credits on the dev split. Specify the fitting procedure, the
  quantile targeted, and how "correctly decomposed" is established without touching
  truth from inside the system (evaluation path only).
  TWO BOUNDARIES MUST BE IN THE PLAN AND IN THE README. First, the search axis is
  rupee-granular, so a paise-denominated ε is not directly expressible on it — the window
  the DP opens is ceil(ε(n)/100) rupees, and the fitted paise figure is what JUSTIFIES
  that window rather than what is applied to it. Second, THE VERIFIER'S ACCEPTANCE TEST
  DOES NOT MOVE AT ALL (NN-12). It still demands a zero residual at paise because it
  re-derives each member's rounding instead of tolerating it. ε widens what the search
  will consider; it never widens what the verifier will accept. A derived tolerance that
  leaked into the acceptance test would undo §5.7 and turn §5.12's auto-clear condition
  into a threshold sitting on top of a fudge factor. Cross-reference D6 from PLAN-P1.md
  and state whether the fitted result confirms or contradicts that analysis.
  Owes: dev-split residual distribution for true decompositions; the fitted k; coverage
  and error at derived ε versus flat ε. Attach an F54 eval-diff — this is precisely the
  "small tolerance adjustment" F54 exists to catch.

CP3.2 · F30 cost governor · 2h · carry, and the first rung of F51
  Per-batch token budget that degrades gracefully: when exhausted, the semantic tier stops
  and remaining unresolved items become exceptions rather than the run failing. Specify
  the budget config key, the accounting point, and the exception disposition.
  A real operational property — the system gets MORE conservative under resource pressure,
  never less.

CP3.3 · F51 degradation ladder · 6h
  The full ladder as an explicit state machine with a named state and a published
  behaviour per rung: NORMAL → NO_MODEL (semantic tier 4 disabled, residue becomes
  exceptions) → NO_SEARCH (Regime A fast path only, all Regime B routed to humans) →
  READ_ONLY (decompose and report, write nothing) → HALTED. Specify each transition
  trigger — token budget exhaustion, rolling-window error rate, verifier failure rate,
  provider unavailability, manual switch — with its threshold in config/degrade.yaml, and
  the transitions that are one-way versus recoverable.
  Owes: measured coverage and error on the dev split AT EVERY RUNG, plus an assertion
  that degradation is monotonic toward conservatism — coverage falls, error never rises.
  Specify that assertion as a test, because "monotonic" is the claim and a table alone
  does not enforce it.

CP3.4 · F39 leakage report · 6h
  Deterministic sweep for the five things that actually leak, each with evidence rows
  attached: reserve holds past their scheduled release and never released; chargebacks
  never represented while still inside the representment window; refunds posted twice;
  duplicate credits with only one backing; fees charged on transactions later voided or
  failed; GST charged where the underlying fee was subsequently reversed. Specify the
  detection rule and the evidence rows for each.
  Owes: rupees identified per merchant profile with precision against generator truth.
  THE README MUST STATE PLAINLY that on synthetic data this measures the DETECTOR, not
  real-world incidence. Quoting the rupee figure as a business result is exactly the
  overclaim spec §2.3 forbids, and it is a tempting one because the number will look big.

CP3.5 · F45 CAMT.053 and MT940 ingestion · 10h
  Real bank statements arrive as ISO 20022 CAMT.053 XML or MT940 flat text. Design both
  adapters properly, including the awkward parts: MT940 continuation lines, CAMT
  entry-versus-transaction nesting, credit/debit indicator handling, multi-day statements,
  and opening/closing balance validation. MT940's :86: narration field is precisely where
  the ~35-character truncation modelled in §5.4 comes from in reality — connect the two
  explicitly in the plan and in docs/DATA.md.
  Owes: parse fidelity — round-trip a generated statement through each format and assert
  the resulting BankCredit set is IDENTICAL TO THE CSV PATH ON EVERY FIELD. Specify that
  as one parameterised test over both formats.
  This earns its ten hours as a domain-competence signal that cannot be faked, because
  producing it requires already knowing these are the formats banks actually send.

CP3.6 · F48 ingestion fuzzing · 4h
  Deliberately malformed input to every adapter: truncated XML, wrong encoding, a
  byte-order mark, mixed line endings, a CAMT entry missing its amount, an MT940 with an
  unparseable date, a CSV with a duplicated header row. Every one must produce a TYPED
  ingestion error naming the offending line or element, and NEVER a partial load.
  Specify the fixture set under fixtures/malformed/ and the error type hierarchy.
  Owes: zero partial loads across the malformed fixture set.
  A partial load is how a reconciliation system silently reconciles against half a
  statement, which is a confidently wrong answer arriving through the front door.

CP3.7 · F35 incremental reconciliation with a carry-forward pool · 12h · largest item
  Real settlements arrive as a stream. Design a streaming engine that keeps a persistent
  pool of unconsumed ledger items, consumes members when a credit clears, ages items out
  under a STATED policy, and RE-ATTEMPTS previously unsolved credits when new items
  arrive — which is exactly what happens in life when the missing refund finally posts.
  Specify the pool store, the ageing policy and its justification, the re-attempt trigger,
  and how idempotency (F25) and the conservation identity (F33) both continue to hold
  when an item can be consumed at a later time than it arrived.
  Owes: the RESOLUTION LAG DISTRIBUTION. For credits not solvable on arrival, how many
  windows later did they resolve, and what fraction resolved eventually. That distribution
  describes real finance operations and no batch-only submission can produce it.
  Twelve hours is the largest single estimate in the phase, so the 1.5x trip-wire is 18h.
  Name in the plan what the minimum measurable version is, so the executor knows what
  "finish to minimum" means here before it needs to.

CP3.8 · F41 reserve sub-ledger with deterministic release schedule · 5h
  Track reserve hold by hold: held date, percentage, source window, scheduled release
  date, actual release, running outstanding balance. Publish a forward schedule that is
  pure arithmetic over ALREADY-KNOWN release dates and explicitly NOT a forecast — per
  spec §1.3 that distinction keeps this out of the counterfactual trap, so state it in the
  plan and in the README.
  Owes: outstanding reserve balance tying exactly to holds minus releases (an identity,
  must hold); count of overdue releases detected.

CP3.9 · F42 dispute lifecycle tracker · 6h
  Chargeback raised → debited → represented → won or lost → credited back, every state
  transition tied to a specific ledger item, money trail followed across window
  boundaries. Flag disputes approaching their representment deadline and disputes debited
  but never represented at all. Specify the state machine and the deadline source.
  Owes: fraction of dispute chains reconstructed completely end to end; count of open
  disputes with a deadline inside seven days. Pairs with corruption class 19, which
  already exists — no new class here.

CP3.10 · F57 latency and load profile · 5h
  Per-stage p50/p95/p99 across ingest, candidate generation, DP, CP-SAT, verification,
  semantic resolution and write. Then a sustained run at 5,000 credits to find where the
  system bends. Specify the instrumentation points, how measurement overhead is kept out
  of the numbers, and the hardware description that must accompany every figure.
  Owes: the per-stage table; the throughput curve; THE BOTTLENECK NAMED EXPLICITLY.
  Naming it is the deliverable — a percentile table without a conclusion is data, not a
  finding. This also upgrades F27 in Phase 4 from an argument into a measurement.

CP3.11 · F23 cross-profile generalisation · 3h · carry, mostly runtime
  Full evaluation against three structurally different merchant profiles — high-refund
  D2C, subscription SaaS with low disputes, travel with high chargebacks and long
  representment lags — WITH NO RE-TUNING BETWEEN THEM. Specify each profile's parameters
  in generator/profiles.py and the mechanism that makes "no re-tuning" verifiable rather
  than promised: one config, three runs, and a test asserting the config hash is identical
  across them.
  Answers the reviewer's most obvious doubt — does this work outside the one dataset you
  tuned on. Publish per-profile results whatever they show.

CP3.12 · F26 human-in-the-loop learning curve · 6h · carry
  Exception resolutions become labelled data: accepted decompositions feed the
  entity-resolution alias table, corrections feed the fuzzy threshold and the abbreviation
  map. Specify the feedback store, the update rule per signal, and the guard that stops
  this becoming a learned matcher (spec §6.2 forbids one at any budget — the alias table
  and threshold are tuned parameters, not a trained scorer, and the plan should say where
  that line is).
  Owes: the curve. After 50 simulated human resolutions, does coverage rise and does
  error hold? Specify how resolutions are simulated without leaking truth into the
  online path. Report honestly even if the lift is small; a measured 4-point lift is
  worth more than an unmeasured claim of learning.
  This is the most literal reading of "close one finance-ops loop" and it is what makes
  the submission a system rather than a script.

CONSTRAINTS ON YOU
- Estimates sum to 69h: 58h features plus 11h carry. State the sum.
- F30 before F51. Do not reorder.
- No corruption classes added in this phase. Class 25 belongs to F44 in Phase 4, class 26
  to F29 in Phase 4. A class without its detector is a hole in our own results table.
- NN-12 is the hard edge of CP3.1 and the easiest thing in this phase to get subtly wrong.
- No result figures, no targets. NN-15.
- Every checkpoint carries its config flag and keeps test_feature_flags_off.py green.

SELF-CHECK — report line by line
[ ] Twelve checkpoints, build order as fixed, estimates summing to 69h.
[ ] All three gate clauses on every checkpoint; owed numbers verbatim from §9.10 for
    F32/F51/F39/F45/F48/F35/F41/F42/F57, and from §6.1 for F30/F23/F26.
[ ] CP3.1 states both ε boundaries and confirms the verifier is untouched.
[ ] CP3.1 requires an F54 eval-diff.
[ ] F51's monotonicity is a test, not just a table.
[ ] F45's fidelity test compares against the CSV path field by field.
[ ] F48 asserts zero partial loads, not merely that errors are raised.
[ ] F35 names its minimum measurable version.
[ ] F39's README caveat about detector-versus-incidence is in the plan.
[ ] F23's "no re-tuning" is mechanically verifiable.
[ ] F26 states where the line is between tuned parameters and a learned matcher.
[ ] No new corruption class. No invented figure.
````

## P3-EXEC · Fable

````text
You are implementing Phase 3 of Residual Zero onto a working, tagged v2 system. Twelve
checkpoints of operational depth.

READ FIRST: CLAUDE.md, then PLAN-P3.md — if it does not exist, STOP and tell me to run
P3-PLAN. Then PROGRESS.md and docs/EVALUATION.md. Confirm v2 is tagged before you start.

The checkpoint loop, the three Phase 2 additions (a populated §9.10 row in the same commit
as the feature; a config flag with test_feature_flags_off.py green after every checkpoint;
the absolute 1.5x trip-wire) all carry forward unchanged. Re-read them in P2-EXEC if you
need to; they are not restated here because nothing about them has changed.

PER-CHECKPOINT OBLIGATIONS

CP3.1 F32 — the verifier does not move (NN-12). Before you change anything, write the test
  that asserts the verifier still demands a zero paise residual, and watch it pass. Then
  fit k. Then produce an F54 eval-diff and file it in docs/EVALUATION.md. If the diff
  moves credits from flagged to cleared, look at several of them individually and satisfy
  yourself they are genuinely correct before you accept the new ε. This is the exact
  change F54 was built to catch and you are the first person it is catching.
CP3.2 F30 — build before F51. Two hours. Do not gold-plate it; it is one rung.
CP3.3 F51 — measure every rung on the dev split and assert monotonicity in a test. If
  coverage does not fall or error does rise between two adjacent rungs, the ladder is
  wrong somewhere and that is a finding worth an INCIDENTS.md entry, not a number to
  publish quietly.
CP3.4 F39 — write the README caveat in the same commit as the detector. The rupee figure
  will look impressive and the temptation to quote it as a business result is precisely
  the overclaim spec §2.3 forbids.
CP3.5 F45 — round-trip fidelity against the CSV path, field by field, both formats, one
  parameterised test. Handle the awkward parts properly: MT940 continuation lines, CAMT
  nesting, credit/debit indicators, multi-day statements, opening and closing balance
  validation. Do not stub any of them with a TODO — a reviewer who works in payments will
  open exactly this file.
CP3.6 F48 — the assertion is ZERO PARTIAL LOADS, which is stronger than "an error was
  raised". Test the state of the ledger after each malformed input, not just the exception.
CP3.7 F35 — largest item in the phase, trip-wire at 18h. Check the conservation identity
  (make verify-books) after implementing pool consumption, because an item consumable at
  a later time than it arrived is exactly the shape of bug that produces a double claim.
  If you hit 18h, fall back to the minimum measurable version the plan names.
CP3.8 F41 — the outstanding-balance tie-out is an identity and must hold exactly. If it
  does not, do not tolerance it; find the missing release.
CP3.9 F42 — no new corruption class. Class 19 already exists and is what you test against.
CP3.10 F57 — name the bottleneck in prose in docs/EVALUATION.md. Every figure carries the
  machine it was measured on. A percentile table with no named bottleneck and no named
  machine is data pretending to be a finding.
CP3.11 F23 — same config hash across all three profiles, asserted by test. Publish
  per-profile results whatever they show; a profile where the system does worse is a
  finding and spec §9.9 already tells you how to frame it.
CP3.12 F26 — an alias table and a tuned threshold are not a learned matcher. If you find
  yourself training a scorer over candidate decompositions, stop: spec §6.2 forbids it at
  any budget and the argument for the refusal belongs in docs/DECISIONS.md instead.
  Report the measured lift honestly, including if it is small or absent.

AT THE END — Gate 3, before you tag
  [ ] Full DEV evaluation re-run; artifacts/ regenerated and committed.
  [ ] make verify-books, make verify-audit, make reproduce all exit zero.
  [ ] CI green. test_feature_flags_off.py green.
  [ ] All nine §9.10 rows for this phase populated from real runs: F32, F51, F39, F45,
      F48, F35, F41, F42, F57. F30, F23 and F26 are §6.1 carry items with no §9.10 row —
      they owe the number their §6.1 entry names, recorded alongside the table.
  [ ] Every config change in this phase has an F54 diff attached in docs/EVALUATION.md.
  [ ] README and second-order table updated. Safety section now includes the degradation
      ladder with its per-rung numbers.
  [ ] At most one test-split evaluation, logged — or skipped with the reason stated.
  [ ] Tag v3. Submittable exactly as it stands.

START by confirming v2 is tagged, then report your starting checkpoint and its
definition-of-done command.
````

---

# Phase 4 · breadth and scale · ~52h · tag `v4`

**Genuinely optional.** Take items from the front of the list as time allows and stop
wherever you stop — the phase is ordered so that stopping early costs you the least
valuable thing remaining. The gate still applies, and it applies *especially* here:
whatever you built either ships finished, measured and in the §9.10 table, or gets
reverted. A half-built optional feature is worse than an absent one.

Build order and hours per spec §11 Phase 4: `F53` 8h → `F36` 4h → `F34` 5h → `F47` 10h →
`F43` 4h → `F44` 6h → `F46` 9h = 46h, plus second-wave carry `F27` 2h, `F28` 1h, `F29` 3h
= 6h. Total 52h. Corruption class 25 arrives with F44; class 26 with F29. `F46` is
deliberately last — two time axes is the most reliable source of subtle off-by-one bugs in
ledger systems, and if it starts costing more than its nine hours, cut it, because
audit-log replay already answers the auditor's question adequately.

## P4-PLAN · Opus 5

````text
You are the architect for Phase 4 of Residual Zero. v3 is tagged. This phase is optional
breadth, and the ordering encodes that: everything is arranged so stopping early costs
the least. Planning only.

READ FIRST: CLAUDE.md; PLAN-P1 through PLAN-P3; PROGRESS.md; docs/EVALUATION.md with all
rows populated so far, including F57's latency measurements which F27 now writes against;
docs/SPEC.md §6.2 Groups A/B/C/E for the relevant entries, §6.1 Tier 3, §9.10, §11 Phase 4,
§12.

WRITE: PLAN-P4.md, ten checkpoints in the build order fixed above, three gate clauses each.

BEFORE YOU PLAN ANYTHING, ANSWER THE STOPPING QUESTION IN SECTION 0 OF THE PLAN.
Spec §11 says: stop when the next item on the build order no longer changes what a
reviewer would conclude, and reserve the final THREE DAYS regardless of which phase you
reached for freeze, final test-split evaluation, README, video re-record and submission —
untouchable. So Section 0 of PLAN-P4.md is not the usual uncertainty list. It is an
honest assessment, feature by feature, of whether this phase should happen at all: for
each of the ten, what a reviewer concludes with it that they would not conclude without
it. If the honest answer for an item is "nothing much", say so and recommend dropping it.
A planner that recommends building less is doing the job correctly here.

CHECKPOINTS

CP4.1 · F53 provider-swap study including a small local model · 8h
  Run the semantic tier against three backends: the frontier model you developed with, a
  cheap small hosted model, and a local ~7B via Ollama or llama.cpp. Specify the interface
  boundary that makes the swap a config change, the prompt-cache partitioning per
  provider, and how cost is measured per backend.
  Owes: tier-4 accuracy, cost per credit, end-to-end coverage and error for each backend.
  BOTH POSSIBLE FINDINGS ARE GOOD and the plan should say so, so the executor is not
  tempted to make one of them happen. If the local model lands within a point, you have
  demonstrated the architecture reduced the model to a commodity component — the strongest
  available version of the AI-judgment argument, plus a real cost story. If it does not,
  you have quantified precisely what capability the hard slice demands, which is also a
  genuine result.

CP4.2 · F36 alternate-decomposition diff for the human · 4h
  When a credit is still AMBIGUOUS after F31, render the two surviving candidates side by
  side with the symmetric difference highlighted. Specify the rendering and where it sits
  in the exception queue view.
  Owes: median size of the symmetric difference presented, against median decomposition
  size — the shape being "the human decides on a handful of items, not all of them."
  Report both medians; the ratio is the point.

CP4.3 · F34 deterministic parallelism · 5h
  Solve credits across a worker pool, reduce results in a FIXED KEY ORDER, assert
  byte-identical output at 1, 4 and 8 workers. Specify the work partition, the reduction
  order, and every source of nondeterminism parallelism introduces — RNG per worker, dict
  ordering across process boundaries, log interleaving, SQLite write ordering — with the
  mechanism that pins each.
  Owes: throughput against worker count, plus the equality assertion as a test.
  Reproducibility claims almost always quietly assume single-threaded execution. A
  determinism guarantee that survives parallelism is the version a payments engineer
  believes, and NN-9 is what it is defending.

CP4.4 · F47 live mode — webhooks with idempotency, ordering and replay · 10h
  Extends spec §8.5 rather than replacing it. Ingest Razorpay test-mode webhooks, enforce
  idempotency by event id, handle out-of-order delivery (a refund event arriving before
  its payment), support full replay of the stored event log to rebuild state from zero.
  Specify the event store, the idempotency key, the out-of-order buffering policy, and the
  replay entry point.
  Owes: STATE EQUALITY ACROSS FOUR DELIVERIES of the same event stream — normal, every
  event duplicated, events reversed, and full replay from log. All four must produce
  identical ledger state. That is one test with four parameterisations and it is worth
  more than any amount of UI.

CP4.5 · F43 deterministic parameter recomputation — "what-if", done safely · 4h
  BE CAREFUL HERE AND CAREFUL OUT LOUD. This is where the Track 03 counterfactual trap
  reappears inside Track 04. "Would this payment have succeeded on a different rail" is
  behavioural, unfalsifiable on synthetic data, and must not be built. "Recompute this
  window's payout with reserve at 3% instead of 5%, or with the contracted fee instead of
  the fee actually charged" is pure arithmetic over an already-known member set and is
  completely verifiable. Restrict the surface to parameter substitution over CLEARED
  decompositions, and specify the README paragraph naming the capability you declined and
  the epistemics behind declining it.
  Owes: recomputation exactness — substituting the generator's own parameters must
  reproduce the generator's own settlement to the paise on 100% of cleared credits.
  Naming a capability you deliberately declined, with the reasoning, is a stronger signal
  on the AI-judgment vector than the feature itself would have been.

CP4.6 · F44 multi-account and multi-entity consolidation · 6h · adds class 25
  Merchants run several MIDs against several bank accounts, and the classic operational
  error is a credit landing in the wrong account's reconciliation. Specify account scoping
  throughout, the consolidated cross-account view, and corruption class 25
  CROSS_ACCOUNT_MISPOSTING — a credit posted against account B whose true members all
  belong to account A.
  Owes: class 25 detection rate AND — the number that actually matters — the false-positive
  rate on legitimate multi-account batches. A cross-account detector that fires on normal
  multi-account operation is unusable, so plan the false-positive measurement first.

CP4.7 · F46 bitemporal ledger and as-of queries · 9h · LAST, and cuttable
  Two time axes: when a thing happened, and when we learned it. Validity columns on the
  reconciliation ledger, supporting "show me the reconciliation as it stood on the evening
  of <date>" — the auditor's question from §2.1 that the current design can only answer by
  replaying the audit log by hand.
  Owes: as-of reconstruction equality — for twenty sampled historical timestamps, the
  as-of view must EQUAL a replay of the audit chain to that point. That equality holding
  IS the feature working.
  Spec §12 puts this last on purpose and says to cut it if it exceeds nine hours. Put the
  cut criterion in the plan explicitly so the executor does not have to decide under
  sunk-cost pressure at hour twelve.

CP4.8 · F27 scale analysis · 2h · carry · PROSE, written against F57's measurements
  What breaks at 100,000 credits per day: where the DP axis width becomes prohibitive,
  when the pool cap starts costing coverage, where SQLite gives out and what replaces it,
  what the model cost curve looks like. F57 already measured the current profile and named
  the bottleneck, so this is now extrapolation from data rather than pure argument — write
  it that way, citing F57's table.

CP4.9 · F28 calibration note · 1h · carry · PROSE, and the short version is the win
  Only a real deliverable if a learned or model-derived score ended up gating anything. If
  NN-4 was honoured and only observable quantities are used, this is ONE PARAGRAPH saying
  so and why, and that is the better answer. If any model-derived score did creep in
  anywhere, you owe a reliability diagram — so the first task of this checkpoint is an
  audit of every gate in the system to establish which case you are in. Do the audit even
  if you are confident; that is the whole value of the hour.

CP4.10 · F29 FX and multi-currency rounding · 3h · carry · adds class 26
  One additional corruption class for international settlements with conversion-rate
  rounding residue at the currency boundary. Specify class 26 FX_ROUNDING_RESIDUE and the
  handling. Per spec §1.3, multi-currency FX reconciliation beyond rounding residue stays
  out of scope — this is the residue only, and the README should keep saying so.
  Note that §6.1's original cut order put F29 first to go and §6.2 corrected that,
  because class 26 depends on it and this phase gives it a slot. Only build it if the
  domestic case is completely finished.

CONSTRAINTS ON YOU
- Estimates sum to 52h: 46h features plus 6h carry. State the sum.
- Section 0 is the stopping assessment, and recommending fewer features is a valid and
  often correct output.
- Class 25 belongs to CP4.6 and class 26 to CP4.10. Nowhere else.
- The three final days are reserved and untouchable. Say so in the plan.
- No result figures, no targets. NN-15.

SELF-CHECK — report line by line
[ ] Section 0 assesses all ten features against "what does a reviewer conclude" and makes
    a recommendation, including any drops.
[ ] Ten checkpoints, fixed order, estimates summing to 52h.
[ ] Three gate clauses each; owed numbers verbatim from §9.10 for F53/F36/F34/F47/F43/
    F44/F46, and from §6.1 for F27/F28/F29.
[ ] F43's scope restriction and the declined-capability paragraph are both specified.
[ ] F44 plans the false-positive measurement, not only the detection rate.
[ ] F46 is last and carries an explicit cut criterion.
[ ] F28 begins with an audit of every gate in the system.
[ ] Classes 25 and 26 each appear exactly once, with their detector.
[ ] The three reserved final days are stated as untouchable.
````

## P4-EXEC · Fable

````text
You are implementing Phase 4 of Residual Zero onto a working, tagged v3 system. This
phase is optional and the ordering means stopping early is a legitimate outcome, not a
failure.

READ FIRST: CLAUDE.md, then PLAN-P4.md — if it does not exist, STOP. Read Section 0 of
that plan and TELL ME what it recommends dropping before you build anything. If it
recommends dropping items and I have not responded, ask; do not build them by default.
Then PROGRESS.md and docs/EVALUATION.md. Confirm v3 is tagged.

Checkpoint loop and the three additions carry forward unchanged from P2-EXEC.

ONE RULE DOMINATES THIS PHASE. Half-built is worse than absent. At the 1.5x trip-wire you
finish to the minimum measurable version or you `git revert` — and in this phase, unlike
the earlier ones, revert is usually the right call, because nothing here is load-bearing.
No feature in Phase 4 is in NN-21's protected set, which is exactly why the drop
permission is broad here and absent everywhere else. Verify that against NN-21 yourself
before you revert anything. Say which you chose and why.

PER-CHECKPOINT OBLIGATIONS

CP4.1 F53 — report whatever you measure. Do not tune the local model harder than you
  tuned the frontier one, and do not tune it less; state the tuning effort spent on each,
  because an unequal comparison is a sandbagged baseline in a new costume (NN-13). Both
  outcomes are good results and one of them is not more publishable than the other.
CP4.2 F36 — report both medians, not just the ratio.
CP4.3 F34 — byte-identical at 1, 4 and 8 workers or the feature is not done. If you cannot
  make it deterministic, that is a finding and NN-9 means the honest response is to ship it
  disabled with the reason documented rather than to ship a determinism claim you cannot
  support.
CP4.4 F47 — four deliveries, one parameterised test, identical ledger state in all four.
  Then run make verify-books afterwards; replay is another path by which an item could be
  claimed twice.
CP4.5 F43 — parameter substitution over cleared decompositions ONLY. If you find yourself
  modelling what would have happened under different behaviour, stop: that is the
  counterfactual trap and it is the reason this project chose Track 04 in the first place.
  Write the declined-capability paragraph in the same commit as the feature.
CP4.6 F44 — measure the false-positive rate on legitimate multi-account batches BEFORE
  publishing any detection rate. Add class 25 here and nowhere else.
CP4.7 F46 — cut it at the criterion in the plan without negotiating with yourself. Twenty
  sampled timestamps, as-of view equals audit-chain replay, or it does not ship.
CP4.8 F27 — cite F57's actual table. Prose, two hours, no code.
CP4.9 F28 — start with the gate audit. If any model-derived score is gating anything
  anywhere, that is an NN-4 violation to fix, not a calibration curve to draw. The good
  outcome here is one paragraph.
CP4.10 F29 — only if the domestic case is completely finished. Class 26 arrives with it.

AT THE END — Gate 4, and it applies even though the phase was optional
  [ ] Anything half-built is reverted. Nothing is left in a partial state.
  [ ] Full DEV evaluation; artifacts/ regenerated and committed.
  [ ] make verify-books, make verify-audit, make reproduce exit zero. CI green.
      test_feature_flags_off.py green.
  [ ] Every feature you shipped has its §9.10 row populated from a real run. Every feature
      you dropped is recorded as dropped, with the reason.
  [ ] README and second-order table updated.
  [ ] At most one test-split evaluation, logged — or skipped with the reason stated. This
      is the fourth and last permitted evaluation across the whole project (NN-16).
  [ ] Tag v4.
  [ ] THE THREE RESERVED DAYS BEGIN NOW and no feature work happens in them. Freeze,
      final README, video re-record, submission. Run U5 for that work.

START by reading Section 0 of PLAN-P4.md and reporting its recommendation to me.
````

---

# The five utility prompts

These are not phase work. They are the prompts you reach for when something goes wrong, or
when a phase boundary demands a specific piece of process. Four of the five exist because
mega-prompts have known failure modes and this file chose mega-prompts.

| | Prompt | Model | When |
|---|---|---|---|
| U1 | Resume after context loss | same model that was executing | Mid-phase, conversation died or drifted |
| U2 | Adversarial gate audit | Opus 5 | Every phase boundary, before tagging |
| U3 | Incident capture | either | Within an hour of anything breaking |
| U4 | Test-split evaluation | Opus 5 | At most four times, ever |
| U5 | README, video and submission | Opus 5 drafts, Fable assembles | The three reserved final days |

## U1 · resume after context loss · same model that was executing

Paste this into a fresh conversation. Change nothing. It reconstructs state from disk
rather than from your memory of what happened, which is the entire point — the artifacts
on disk are authoritative and your recollection is not.

````text
You are resuming work on Residual Zero mid-phase. A previous conversation was executing a
phase prompt and is gone. Do not guess at state and do not ask me what happened — I may
not remember accurately either. Reconstruct it from disk.

STEP 1 — READ, in this order, and do not skip any of them
  CLAUDE.md
  PLAN-P<n>.md for the phase currently in progress
  PROGRESS.md in full, paying attention to the LAST entry
  git log --oneline -40
  git status
  git tag --list
  docs/EVALUATION.md
  docs/INCIDENTS.md

STEP 2 — REPORT, before you touch anything
  1. Which phase is in progress, and which tag was the last one cut.
  2. The last checkpoint whose definition-of-done command was recorded as exiting zero in
     PROGRESS.md.
  3. Whether the working tree is clean. If it is not, describe what is uncommitted and
     make an assessment: is this a checkpoint in progress, or debris?
  4. RUN the last completed checkpoint's definition-of-done command yourself. Report the
     actual exit code. If it does not exit zero, PROGRESS.md is ahead of reality and you
     must say so loudly — that is the situation this prompt exists to catch.
  5. Run: make test, make verify-books, make verify-audit. Report each exit code.
  6. Any §9.10 row that PROGRESS.md claims is done but docs/EVALUATION.md leaves blank.
  7. grep the README and docs/ for the placeholder figures listed in NN-15 and report hits.

STEP 3 — PROPOSE and wait
  State the checkpoint you believe is next, its definition-of-done command, and its
  estimate from PLAN-P<n>.md. If the working tree is dirty, propose either finishing that
  checkpoint or reverting it, with a recommendation and a reason. THEN STOP AND WAIT FOR
  MY CONFIRMATION.

  Do not start implementing. A resume that guesses wrong and continues is worse than a
  resume that pauses, because it commits on top of a state nobody has verified.

If PROGRESS.md is missing entirely, say so and rebuild what you can from git log alone,
flagging clearly that the reconstruction is inferred rather than recorded.
````

## U2 · adversarial gate audit · Opus 5

Run this at every phase boundary, after the executor claims the gate is met and **before**
you tag. Its job is to disbelieve the executor. Run it in a **fresh conversation** — an
auditor that helped build the thing is not an auditor.

````text
You are auditing Residual Zero at a phase boundary. An executor has just claimed the phase
gate is satisfied. Your job is to disbelieve that claim and try to break it. You did not
build this and you owe it no charity.

Read CLAUDE.md, PLAN-P<n>.md, PROGRESS.md, docs/EVALUATION.md, docs/DECISIONS.md, README.md,
git log for the phase, and the diff of the phase (git diff <previous-tag>..HEAD --stat, then
the individual diffs of anything that looks load-bearing).

RUN EVERY ONE OF THESE YOURSELF AND REPORT ACTUAL EXIT CODES. Do not accept a claim in
PROGRESS.md that a command passes; the claim is the thing under audit.
  make test
  make verify-books
  make verify-audit
  make reproduce
  pytest tests/test_feature_flags_off.py -v
  make eval           (dev split only)

Then work through the following. For each, answer with EVIDENCE — a file path and line, a
command and its output, or a specific number. "It looks fine" is not an answer.

CLAIM INTEGRITY
1. List every number in README.md and docs/EVALUATION.md. For each, name the command that
   reproduces it. Any number without one is a NN-14 violation — report it as blocking.
2. grep the whole repo for every placeholder figure listed in NN-15. Report every hit
   outside the spec file itself. Report any TBD- marker still present.
3. Does any headline number come from the test split more times than NN-16 permits? Check
   the evaluation log for timestamps and commit hashes and count.
4. Are Wilson intervals computed on the pooled proportion, with per-seed min-max reported
   separately? Check the code, not the prose. A per-seed interval mislabelled as pooled, or
   one estimator's interval drawn around the other's point estimate, is a statistics error
   that a panel with a quant on it will find.

SAFETY INVARIANTS — these are the ones that would be genuinely embarrassing
5. Attempt to reach ground truth from inside the reconciliation path. Try to construct an
   import chain from the loader to data/*/truth.jsonl. Try opening it from a module the
   online path imports. If you SUCCEED, that is the most serious possible finding — stop
   the audit and report it immediately.
6. Find every gate condition in the system: grep for thresholds, comparisons and branch
   conditions that decide auto-clear, escalation or refusal. For each, is the quantity
   observable (amount delta, string distance, candidate count, date proximity) or is it
   model-derived? Any model-derived gate violates NN-4.
7. Does the model ever receive an amount, or emit one? Inspect the actual prompt
   construction and the actual response parsing, including any logging of either.
8. Does the verifier's acceptance test still demand a zero paise residual? Compare against
   the tolerance used by the search. If tolerance leaked into acceptance, NN-12 is broken.
9. Can CP-SAT return a decomposition the DP did not enumerate? Read the model construction
   and check the variable domain. NN-18.
10. Does corruption mutate rendered views only, or has anything begun mutating the
    canonical event stream? NN-7.

RIGOUR
11. Are the baselines fairly implemented, or sandbagged? Read A1 specifically: does it use
    rapidfuzz properly and does it use scipy.optimize.linear_sum_assignment for optimal
    global assignment rather than greedy first-match? A weak baseline is a fabricated
    result and NN-13 exists for this.
12. Is determinism actually tested, or merely claimed? Find the test. Run it twice.
13. Is every feature in this phase disable-able, with the core provably unchanged when it
    is off? Toggle at least two flags yourself and run the suite.
14. Is the autonomy threshold derived from the risk-coverage curve, or hand-picked and
    retro-justified? Find the derivation in code.
15. Check NN-21 against the git history. Did anything in the protected set get reverted,
    disabled by default, or left with an unpopulated row? Run `git log --diff-filter=D
    --name-only` for the phase and read the revert commits if there are any. A protected
    feature quietly reverted at a trip-wire is the failure mode NN-21 exists to prevent and
    it will look, in the diff, exactly like ordinary housekeeping.
16. Confirm docs/SPEC.md is byte-identical to the original spec. If it drifted, every
    section reference in every plan is now pointing at something that moved.
17. Pick the THREE most impressive claims in the README. For each, construct the sharpest
    objection a hostile expert reviewer would raise, then check whether the repo already
    answers it. Report the ones it does not.

OUTPUT
  A. BLOCKING — must be fixed before the tag. Anything in 1-10 or 15 that failed.
  B. SHOULD FIX — weakens the submission but does not block.
  C. NOTED — worth knowing.
  D. Your assessment of whether this phase's gate is genuinely met. If it is, say so
     plainly; do not manufacture findings to look thorough.

Write the result to docs/AUDIT-P<n>.md and commit it. The audit trail is itself evidence:
a repo containing its own adversarial audits reads very differently to a reviewer than one
containing only its own claims.
````

## U3 · incident capture · either model

Use within an hour of anything breaking. `docs/INCIDENTS.md` is the raw material for the
application form's *"What broke, and how you got out"* — the field the panel reads first —
and per NN-19 it is contemporaneous or it is worthless. The memory on this project is
explicit that several applicants are submitting the same model-generated failure story;
the defence against that is a real log written while the thing was still broken.

````text
Something just broke in Residual Zero. Capture it in docs/INCIDENTS.md before you fix it,
or immediately after if the fix is already in. Do not clean up the story.

Append an entry with exactly these fields:

  ## <YYYY-MM-DD HH:MM> · <one-line title>
  **Phase / checkpoint:** which one, and how far into its estimate you were.
  **Symptom:** what you actually observed, verbatim. Paste the traceback, the failing
    assertion, the wrong number. Not your interpretation of it — the raw output.
  **First hypothesis:** what you thought it was. INCLUDE THIS EVEN IF IT WAS WRONG.
    Especially if it was wrong. The wrong first guess is the most informative part of the
    entry and it is the part that gets silently dropped when the log is written later.
  **How you actually localised it:** the specific commands, prints, bisections or tests
    that moved you from symptom to cause. Be concrete about the dead ends.
  **Root cause:** the real one, at the level of a specific line or design decision.
  **Fix:** what changed, with the commit hash.
  **Test that now prevents regression:** the test name and path. If there is none, say so
    explicitly and say why not — that absence is itself a finding.
  **What this says about the design:** one or two sentences. Sometimes nothing, and
    "nothing, it was a typo" is an acceptable and honest answer.

RULES
- Contemporaneous. Do not rewrite an old entry to look cleverer than the moment was.
- Do not omit the embarrassing ones. The DP bounds guard (a target outside [NEG, POS]
  producing a negative shift count and a crash) is a real bug that was caught during
  algorithm validation — that class of bug, found by testing rather than by luck, is
  exactly what makes a failure story credible.
- Never invent an incident. NN-19. If the honest log is short, the honest log is short.
- If the same root cause appears a third time, note that explicitly. A recurring cause is
  a design problem wearing a bug costume, and noticing that is worth more than the three
  individual fixes.
````

## U4 · test-split evaluation · Opus 5

**At most four of these will ever run.** One per tagged release, ceiling four (NN-16). If
you are unsure whether you have already spent one on this release, you have — check the log
and skip. The dev split is for iterating; the test split is for the number you publish, and
it is spent the moment you look at it.

````text
You are running a TEST-SPLIT evaluation of Residual Zero. This is a budgeted, logged,
irreversible action.

BEFORE ANYTHING ELSE — the budget check
  1. Read the evaluation log. Count prior test-split evaluations. If the count is already
     4, STOP. If this tagged release already has one, STOP and tell me it is spent.
  2. Confirm the working tree is clean and the release is tagged. A test-split evaluation
     on uncommitted code cannot be cited, because the number would have no commit to
     belong to.
  3. Confirm the dev-split evaluation is complete and every §9.10 row for this phase is
     populated. The test split confirms; it does not discover. If you are still learning
     things from dev, you are not ready.
  4. Confirm you have NOT read any test-split record, sample or artifact during this
     phase's development. If you have, say so — the split is compromised and the honest
     move is to report the number with that caveat attached rather than to publish it
     clean.

THEN
  5. Log the intent FIRST: append to the evaluation log with UTC timestamp, commit hash,
     tag, and the specific reason this evaluation is being spent. Commit that before you
     run anything, so the log cannot be retroactively tidied.
  6. Run the full evaluation on the test split. All arms: A0 exact, A1 fuzzy plus optimal
     assignment, A2 rules-only, A3 full, A4 human where available. Both regimes separately
     (A declared, B searched). Per-corruption-class breakdown across all classes built so
     far.
  7. Compute the statistics as specified: pooled proportion with a Wilson score interval,
     AND the per-seed min-max range reported beside it. Never draw one estimator's
     interval around the other's point estimate.
  8. Produce the risk-coverage curve and confirm the autonomy threshold DERIVED from the
     dev-split curve still sits sensibly on the test-split curve. If it does not, that is
     a real and reportable finding about generalisation — report it, do not re-derive the
     threshold on test data. Re-deriving it on test data is how the split gets burned
     without anyone noticing.

REPORT
  9. Test-split numbers beside the dev-split numbers, in one table, with the gap stated. A
     gap is normal and hiding it is not.
  10. If the test numbers are materially worse, DO NOT re-tune and re-run — the budget is
      spent. Write up the gap in docs/EVALUATION.md and treat the cause as a Phase n+1
      item.
  11. Update README.md so the headline figures are the test-split ones, labelled as such,
      each with the command that reproduces them.
  12. Commit everything including the log entry you wrote in step 5.

The whole discipline exists so that one number in the README is worth more than a hundred
numbers in a repo whose author looked at the answer key whenever it was convenient.
````

## U5 · README, video and submission · Opus 5 drafts, Fable assembles

The three reserved final days. **No feature work happens here.**

````text
You are preparing Residual Zero for submission. Feature work is over — if you find
yourself wanting to build something, write it in docs/FUTURE.md and move on.

READ: CLAUDE.md, docs/SPEC.md §14 (video) and §15 (README), docs/EVALUATION.md in full,
docs/INCIDENTS.md in full, docs/DECISIONS.md, every docs/AUDIT-P<n>.md, and the current
README.md.

PART 1 — THE README
Follow spec §15's structure. Three rules dominate:
  · Every number carries the command that reproduces it. No exceptions (NN-14).
  · grep for every NN-15 placeholder before you finish. Zero hits outside the spec file.
    Zero remaining TBD- markers.
  · The limitations section is real. Synthetic data throughout; the leakage figure measures
    the detector and not real-world incidence; corruption classes are modelled, not
    observed in production; whatever generalisation gap F23 found; whatever the dev-to-test
    gap was. State them plainly. A reviewer who finds a limitation you did not disclose
    discounts everything else you wrote; a reviewer who finds you disclosed it first
    trusts the rest more.
Lead with the insight, not the feature list: a settlement credit is a net aggregate, so
this is signed subset-sum under tolerance, not fuzzy matching — and the system refuses to
auto-clear anything whose decomposition is not provably unique. The refusal is the product.

PART 2 — THE VIDEO SCRIPT
Follow spec §14. Write it as a script with timings, then TEST IT by running every command
it shows and confirming the output matches what the script says appears. A demo command
that behaves differently on camera than in the script is the single worst outcome of this
day.
  Open on the problem in one sentence a non-specialist understands. Show one real
  decomposition with its proof and its zero residual. Then show a REFUSAL — an AMBIGUOUS
  credit with the two surviving candidates and the system declining to clear it — and say
  why that is the important screen. Then the baseline table. Then the failure you actually
  had, from INCIDENTS.md, in your own words.
  Do not narrate the architecture. Show the artifact.

PART 3 — THE FORM
The last field is "What broke, and how you got out" and Razorpay reads it first. Draft it
from docs/INCIDENTS.md ONLY. Use a specific incident with the wrong first hypothesis intact,
the actual localisation path, and the test that now prevents it.
  Do not write about multi-agent context bleeding, do not write about prompt drift between
  agents, and do not write a generic AI-orchestration failure narrative. Several applicants
  are submitting exactly those stories from exactly the same source, into the field the
  panel reads first. A concrete bug with a real traceback and a real dead end beats a
  polished template, and it is the only version that survives a follow-up question at the
  panel.
Also draft, for the other fields: where you deliberately chose NOT to use a model and why
(the solver, the arithmetic, every gate condition — this is the rubric's AI-judgment vector
and the strongest material in the whole project); and one paragraph on the capability you
declined to build (F43's counterfactual surface) with the epistemics.

PART 4 — FINAL VERIFICATION, run it all from a clean clone in a temp directory
  git clone <repo> /tmp/rz-verify && cd /tmp/rz-verify
  make reproduce
  make eval
  make verify-books && make verify-audit && make test
  make evidence
Then open the artifacts and check each README number against them, one at a time, by hand.
If a single number does not match, fix the README rather than the artifact.

FINISH by reporting: every command you ran with its exit code, every number you verified,
and anything you could not reproduce. If there is something you could not reproduce, that
is the most important line in your report and it goes first.
````

---

# Closing note

The order is fixed and the pairing is not optional: `CLAUDE.md` once, then for each phase
`Pn-PLAN` → *you read `PLAN-Pn.md`* → `Pn-EXEC` → `U2` → tag. `U1` when a conversation
dies, `U3` within the hour when something breaks, `U4` at most four times ever, `U5` in the
three reserved days.

Two things in this file matter more than the rest of it combined.

The first is `CLAUDE.md`. It is the only part that persists into every future session
without anyone pasting it, which means NN-1 through NN-21 are the invariants that actually
survive context loss, model swaps, and your own enthusiasm at hour eleven of a checkpoint.
If you change nothing else here, keep that file accurate.

The second is that every prompt asks for a number and a command, never a claim. The gate,
the checkpoints, the audit, the test-split budget and the README rules are all the same
instruction wearing different clothes: publish nothing `make eval` cannot reproduce. That
is the one move in this project that cannot be walked back, and it is the reason the
refusal — the system declining to clear what it cannot prove — is the headline rather than
the accuracy figure.
