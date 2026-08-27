# Submission drafts (U5)

Paste into the application form. Every factual claim here is on disk. Do not polish the
incident into a generic orchestration story.

---

## What broke, and how you got out

The reference subset-sum solver returned `UNIQUE` for amounts `[10, 11]`, target `10`,
tolerance `1`. A second subset sums to 11, which is inside the window. I first thought
the brute-force tests would have caught it. They would not: they used `tol=0`, and the
tolerance test only asserted reachability, not uniqueness.

The bug was in `enumerate_solutions`: it picked one hit total and enumerated *inside that
total*. Uniqueness-under-tolerance — the actual production case once amounts are projected
onto a rupee axis — was untested. The fix walks every hit in the window into one shared
solution list with one shared cap. Empty subsets are never solutions.

Commit of the diagnosis: `0d45ad6820e902e4e9c69379ea13048618311c9d`. The guard is
`tests/regressions/test_uniqueness_under_tolerance.py`. A green uniqueness test at
tolerance zero is not a uniqueness test.

---

## Where we deliberately chose not to use a model, and why

The solver, the arithmetic, and every gate that can produce `CLEARED`. A settlement credit
is a net aggregate; matching it is signed subset-sum under tolerance. A language model
cannot prove uniqueness across a window, cannot re-derive GST on a fee at paise, and
cannot be the thing a reviewer checks with a calculator.

Exception class assignment is a pure function whose signature has no client and whose
input type has no confidence field. The ordering score is six observables, rendered to a
fixed six-decimal string. Auto-clear still needs UNIQUE, a full pool, residual 0, and that
score at a threshold read off a curve. The model may resolve a counterparty name from a
closed set after tiers 1–3 fail. It cannot authorise.

On this corpus that division cost no coverage: tiers 1–3 already resolve every name, and
auto-clear is 0 because search is AMBIGUOUS, not because the model abstained.

---

## Capability we declined (F43)

"Would this payment have succeeded on a different rail" is a behavioural counterfactual.
It is unfalsifiable on synthetic data — the same trap as picking a revenue-recovery track
and inventing a world in which a retry worked. We restricted what-if to parameter
substitution over an already-known member set: change reserve bps or a fee table, re-derive
the stack, compare paise totals. Of 136 Regime A accepted declared compositions, 136/136
reproduce under the generator's own tables. That is arithmetic. The rail-counterfactual
is not, and it is not in the product.

---

## One-line product

Everyone else submits a match rate. This submits a proof, a baseline beside it, an honest
exception list, and a real war story with the wrong first hypothesis still in it.
