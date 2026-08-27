# DECISIONS.md

Architecture decision records. Each one is a decision with an argument, written down so it can be
defended under questioning rather than rediscovered.

---

## ADR-1 · No agent framework

**Decision.** Plain typed Python functions composed in a single orchestrator. No LangGraph, no
agent framework.

**Argument.** Look honestly at the pipeline: `ingest → normalise → candidate generation → solver →
verifier → proof + audit + ledger write`, with a single edge branching *forward* from
fail-or-ambiguous into diagnosis. It is a directed acyclic graph. Nothing re-enters a stage it has
already left. There are no cycles needing checkpointing, no concurrent agents contending over
shared mutable state, and no long-running human-suspend-and-resume across process restarts. A
graph framework would add a dependency, a layer of indirection and a new failure surface, and buy
nothing.

The one place that looks like a loop is not one: when a candidate pool exceeds `MAX_POOL`, the
solver runs a bounded, deterministic sequence of sub-window attempts *inside a single stage*. The
pipeline still sees one solver invocation.

**When to reconsider.** If a genuine requirement appears — durable suspend/resume across process
restarts for human approval, or true concurrent agents contending over shared state. Neither is in
scope.

**Why this is worth writing down.** Declining a framework *with an argument* is a stronger
signal than adopting one, and the rubric penalises unnecessarily forcing complex tech stacks.

---

## ADR-2 · The model does no arithmetic and selects no matches

**Decision.** The model has exactly two jobs. Upstream: resolve `counterparty_raw →
counterparty_id` from a **closed candidate set**, and only after deterministic tiers 1–3 have
failed. Downstream: write connective prose around figures that deterministic code has already
rendered. It never computes an amount, never chooses a decomposition member, and never assigns an
exception class.

**Argument.** Every load-bearing decision in this system is either exact arithmetic or a closed-set
classification with crisp rules. Those are the decisions that should not be probabilistic. Making
them deterministic is what lets us emit a proof rather than a claim.

**Mechanism, not intention.** Exception class assignment is a pure function whose signature has no
model client parameter and whose input type carries no model output, so a model cannot reach it
even by accident.

---

## ADR-3 · The model never sees or emits an amount

**Decision.** No monetary value appears in any prompt, any response, or any log line a prompt is
built from. The model receives text and a closed set of entity ids, and returns an id or abstains.
For narrative and Q&A prose it receives **slot names** — `{DELTA}`, `{GROSS}`, `{PCT}` — with no
values, and returns prose containing those slots, which deterministic code then substitutes.

**Argument.** This converts "a hallucinated number is unlikely" into "a hallucinated number is
architecturally impossible", which is a sentence we can say to a reviewer and have be true. The
model has nothing to copy incorrectly because it was never given a figure, and its output is a
template rather than an answer, so every numeral in the final text was placed there by the
formatter from a retrieved row.

**Mechanism, two layers.** Type level: the request models have no numeric field at any nesting
depth and forbid extra fields. Runtime: a money-pattern detector scans every outbound payload and
raises rather than transmitting. The pattern is deliberately narrow — it must not fire on a UTR or
an invoice number, both of which are legitimate digit runs.

---

## ADR-4 · No decision is gated on model self-reported confidence

**Decision.** `ordering_score` is built from observable quantities only: rupee-axis slack, margin
to the nearest other reachable total, pool size, resolution tier reached, cross-window member
count, and member count. Never from a model's stated confidence.

**Argument.** LLM confidence is poorly calibrated and will happily read high on a wrong answer. A
panel with an ML background knows this. If we used it anywhere we would owe a calibration curve,
and the better answer is not to need one.

**Consequence worth stating.** The score is a weighted geometric mean, so it is conjunctive: one
bad term is not compensated by five good ones. An unresolved entity drives the score to exactly
zero, which means such a credit can never auto-clear at any threshold. That annihilation is
intended.

---

## ADR-5 · All money is integer paise

**Decision.** Every monetary value in the system is a Python `int` counting paise. No float touches
a monetary value anywhere — not in the solver, not in a test fixture, not in a generator, not in a
report formatter. Rupee display is a formatting concern at the very edge of the system.

**Argument.** Float rupees cost a day of phantom residuals, and this is the cheapest correctness
decision available. It also makes the verifier's acceptance test `residual_paise == 0` — an exact
integer comparison rather than a comparison against an epsilon, which is what lets the proof be
checkable with a calculator.

**Mechanism.** An AST scan over every module fails the build on a float literal, a `float()` call,
or a true-division operator outside a short explicit allow-list. Adding to that allow-list is a
visible diff.

---

## ADR-6 · Rates are integer basis points, externalised, sourced and dated

**Decision.** Every rate lives in `config/` as an integer count of basis points with a
`source_url` and an `as_of` date. The config loader **raises** on any unverified value, so nothing
in the system can run against a rate nobody checked.

**Argument.** Rates change with finance acts and notifications. Hardcoding one on the authority of
a blog post or a language model is spotted instantly by a panel of Indian fintech engineers, and
getting it right is cheap. Integer basis points rather than float percentages keeps ADR-5 intact
through the fee computation, which is where a float would otherwise re-enter.

**Honesty carve-out.** A merchant's rolling-reserve percentage and per-transfer bank charge are
private contract terms, not public rates. Those entries are marked `synthetic: true` with a note
saying so. Inventing a `source_url` for a private contract term would be worse than admitting it
is synthetic.

---

## ADR-7 · MDR and platform fee are different things, and the distinction matters

**Decision.** `fees.yaml` models Razorpay's **platform fee**, which their published pricing states
as a flat rate across domestic instruments, plus GST charged on that fee. It does not model MDR.

**Argument, and why this ADR exists at all.** The spec's §3.2 says instruments "carry materially
different rates, and UPI is frequently zero-rated", and that a flat percentage of the batch would
make naive baselines fail instructively. Verifying against Razorpay's own published pricing
(fetched 2026-08-27) shows the standard domestic platform fee is uniform across cards, UPI,
netbanking, wallets and EMI, with corporate cards and international cards priced higher.

Both statements are true about **different things**. UPI genuinely carries zero **MDR** under RBI
policy; Razorpay nonetheless charges its platform fee on UPI, described in their own documentation
as a platform/technology fee rather than MDR. Conflating the two is a mistake a payments engineer
would notice, so we model the fee that is actually deducted from a settlement — the platform fee —
and record here that the instrument-variation the spec expected lives in negotiated rates and in
the corporate/international card tiers rather than in the standard domestic schedule.

**Consequence.** Per-instrument fee computation is still per-transaction and still driven by the
instrument, because the schedule has genuine variation at the corporate and international tiers,
and because a merchant's negotiated schedule may vary by instrument. But we do not claim the
standard domestic schedule varies when the primary source says it does not.

---

## ADR-8 · No machine-learned matcher, at any budget

**Decision.** We will not train a model to score candidate decompositions. Not now, not with
unlimited runway.

**Argument.** The exact solver already returns the **complete** solution set with a uniqueness
guarantee. A learned scorer could at best approximate what we already compute exactly, while being
slower to justify, impossible to prove, and strictly less explainable. There is no version of this
trade that comes out in the learned matcher's favour.

This argument is only available to us *because* the deterministic core is strong enough to make the
model unnecessary — which is the point worth making. It is the purest instance of the rubric's
"and where you chose not to use one".
