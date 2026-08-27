# PLAN-QUESTIONS.md

Append-only. Written by whichever model hits an underdetermined decision. Answer inline under
each question; the model re-reads this file.

---

## Q1 · Which withholding provision should the synthetic merchant be modelled under?

**Raised by.** Opus 5, P1-PLAN, 2026-08-27. Blocks: CP0's `config/tax_rates.yaml`, and therefore
CP1's ground truth.

**The decision.** §3.2 says withholding "may include withholding on commission, or e-commerce
operator withholding on gross sales" and then forbids taking any rate from a blog post or a
language model (NN-8). The *rate* is the executor's to source from a primary document. But **which
provision applies** is a modelling choice about what kind of relationship our synthetic merchant
has with the aggregator, and it is not something a primary source can settle for us.

**Options and consequences.**

| Option | Consequence |
|---|---|
| **A · E-commerce operator withholding on gross sales** | The withholding base is gross captured payments, so the deduction scales with settlement size. Makes class 13 `WITHHOLDING_GAP` produce a large, obviously percentage-shaped delta, which is the easier diagnosis and the more visible line in the proof block. |
| **B · Withholding on the aggregator's commission** | The base is the platform fee, so withholding compounds on top of GST-on-fee and the deduction is small. Makes class 13 subtler and the `SUSPECTED_WITHHOLDING` rule harder, because the delta is a percentage of a percentage. Structurally more interesting; harder to diagnose. |
| **C · Model both, as two config entries with a per-profile switch** | Costs perhaps an hour at CP0 and CP1, and gives Phase 3's F23 cross-profile work a genuine axis of variation. Doubles the surface the D13 rules must handle. |

**Recommendation: A**, for Phase 1 only, with the config keyed so that B can be added later without
a migration (`withholding.base: GROSS_PAYMENTS | PLATFORM_FEE`). Reason: §5.10's worked diagnosis
describes a delta that is "a clean percentage of the subset gross", which is option A's shape, and
Phase 1 should match the spec's own worked example rather than diverge from it. The `note` field in
`tax_rates.yaml` must name the provision explicitly whichever you choose, so a reviewer can check
the rate against the right source.

**Answer:**

---

## Q2 · Which model provider, which model, and what is the per-run spend ceiling?

**Raised by.** Opus 5, P1-PLAN, 2026-08-27. Affects CP5 (tier 4 and narration) and CP7 (Q&A
composition). Does **not** block CP0–CP4.

**The decision.** §7 specifies "one LLM provider behind a thin interface" without naming one, and
`config/llm.yaml` needs a model id, an effort setting and a hard per-run token budget. The provider
and the money are yours to authorise, not mine to assume. Note that this environment already
exposes `ANTHROPIC_AUTH_TOKEN` and `ANTHROPIC_BASE_URL` pointing at a gateway, so credentials of
some kind exist — but "credentials exist" is not the same as "you have authorised this project to
spend against them", and I am not treating it as such.

**What is unaffected either way.** The `LLMClient` protocol, the schema validation, the on-disk
prompt-hash cache, `--offline` mode, and the amount-boundary guards are all provider-agnostic and
get built at CP5 regardless.

**What changes by answer.**

| Option | Consequence |
|---|---|
| **A · Authorise a frontier model with a stated per-run token budget** | Tier 4 produces a real number, F6's cascade table is complete, and the §9.6 LLM ablation measures something. This is the full Phase 1 deliverable. |
| **B · Authorise a cheaper/smaller model** | Same structure, lower cost, and tier 4 accuracy may be lower — which is itself publishable, and is the study F53 formalises in Phase 4. |
| **C · No spend in Phase 1** | CP5 builds against a stub, the dev split runs `--offline`, and F6 reports the tier 1–3 mix with tier 4 unexercised. That is still a real and publishable result — "deterministic tiers resolved this fraction; the model tier was not exercised in Phase 1" — but the §9.6 LLM ablation cannot be run and the README must say so. |

**Recommendation: A or B, with an explicitly stated per-run token budget** so that
`TokenBudgetExceeded` has a real value to enforce and §9.7's cost-per-credit line has a number in
it. If the answer is C, say so and CP5 will build the stub path and report accordingly rather than
stalling.

**One request regardless of the answer.** `/Users/kartikey0104/Desktop/outputs/.claude/settings.json`
currently holds a long-lived auth token in plaintext. It is not tracked by any git repository right
now — I checked — so nothing has leaked. But §13.1 requires this repository to be public, and the
token sits two directories above it. Rotating it and moving to an environment variable or a
credential helper before CP5 costs a few minutes and removes a class of accident entirely.

**Answer:**

---

## Q3 · Are two additional raters actually available inside the CP5 window?

**Raised by.** Opus 5, P1-PLAN, 2026-08-27. Affects F56, which is in the NN-21 protected set.

**The decision.** F56 needs three independent raters reconciling the same twenty credits by hand,
and it has a hard deadline that no other Phase 1 item has: it must run *before* the system's
answers are known, which is CP5 and not later. Two of those three raters are other people, and
their availability is a fact about the world rather than a design choice.

**Why this cannot be quietly deferred.** F56 is protected (NN-21), so the 1.5× trip-wire's revert
branch is unavailable — the only legal move if it runs long is to finish it to the minimum
measurable version and log the overrun in `PROGRESS.md`. And §9.10 names it one of the two rows
worth more than all the others. So it needs to be scheduled with real people in advance, not
discovered as a problem at CP5.

**Options and consequences.**

| Option | Consequence |
|---|---|
| **A · Two raters confirmed for the CP5 window** | Full F56: three pairwise Cohen's κ, per-rater time and accuracy, and the human-disagreement analysis that produces the single most persuasive sentence available in the submission. |
| **B · One additional rater** | Reduced F56: one pairwise κ instead of three. Still answers the pre-registered question, still reportable, and honestly labelled as two raters rather than three. This is the "minimum measurable version" NN-21 requires. |
| **C · No additional raters** | F19 alone survives as the human arm. F56's §9.10 row reads "not run, and here is why", which is honest but forfeits a protected feature. |

**Recommendation.** Confirm two raters now, before CP0 finishes, and put a date on it. They need
roughly ninety minutes each plus a briefing, they must not have seen any system output, and they
must not discuss cases with each other until sheets are sealed (D18). If only one is available,
that is option B and it is fine — but decide before CP5 rather than during it, because the
briefing is part of what cannot be done after the fact.

**Answer:**
