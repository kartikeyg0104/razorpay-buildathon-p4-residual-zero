# Adversarial self-test (F24)

Attempted 2026-08-28 against `v1-submittable` plus Phase 2 F31 predicates.
Auto-clear still requires UNIQUE + FULL + zero residual + ordering score ≥ `1.000000`.
The threshold never auto-clears on this corpus, so several attacks are vacuously
unable to reach CLEARED. They are still recorded: a uniqueness bug that minted
UNIQUE would be the interesting failure, and F31 is the new door.

| # | Attack | Outcome | Fixed? |
|---|---|---|---|
| 1 | Two disjoint payment pairs, equal rupee sums (class-23 shape), both structurally valid | CP-SAT leaves AMBIGUOUS (2 feasible). No UNIQUE. | n/a — correct refusal |
| 2 | Empty member set presented to the verifier | Rejected (`empty member set`). | n/a |
| 3 | Two PAYMENTs sharing `order_id` vs one legal singleton | Illegal pair eliminated; singleton UNIQUE on structural grounds. The UNIQUE set is in the DP enumeration (NN-18). | n/a — intended |
| 4 | Cap-hit enumeration | Refuses UNIQUE and refuses INFEASIBLE. | n/a — intended |
| 5 | Sign-reversed decoy that restores the arithmetic sum | Verifier still demands paise identity; not auto-cleared. | n/a |
| 6 | Duplicate-credit reuse of members | Conservation sweep (F33) is the joint check; double-claim test fails identity. | n/a |
| 7 | F50 injection as counterparty text | Closed-set entity id; 0/30 auto-clear. | n/a |
| 8 | Near-tolerance residual (1 paise) | Verifier does not widen (NN-12). | n/a |

**Negative result.** No attack produced an auto-clear of a non-truth member set.
The search itself is the deliverable. The most serious remaining door is an F31
predicate that is *too tight* and would UNIQUE the wrong enumerated survivor;
NN-18 plus `tests/test_disambiguation.py` are the mitigation, not a proof that
every future constraint is safe.
