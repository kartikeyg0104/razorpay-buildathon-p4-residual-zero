# Residual Zero

Settlement reconciliation as signed subset-sum: for every bank credit, the member set, a
zero-paise residual, a uniqueness check, and a hash-chained proof.

## Headline (dev, n=239 credits)

| arm | exact | assignment P | assignment R | cleared | flagged |
|---|---|---|---|---|---|
| A0 exact match | 0/239 | — | 0/5973 | 0 | — |
| A1 fuzzy 1:1 | 0/239 | — | 0/5973 | 0 | — |
| A2 rules-only greedy | 0/239 | 142/1163 | 142/5973 | 147 | 92 |
| A3 full system | 129/239 | 3339/3339 | 3339/5973 | 0 | 239 |
| A4 human | 0/20 | — | — | — | 20 |

Auto-clear coverage of A3 is 0/239 at the derived threshold `1.000000` (error budget `1/100`,
read off `artifacts/dev/curve_a3.json`). Search uniqueness under `ε_R = 7` is AMBIGUOUS on
the 5-day pool, so the system flags rather than guesses. Exact decomposition 129/239 is the
Regime A declared composition, predicted and arithmetically verified, not auto-cleared.

A1's similarity threshold and amount tolerance were swept on the dev split and fixed at the
values that maximised A1's own exact-decomposition rate. A2 was given the same tax and fee
configuration, the same asymmetric cross-window widening, and the same normalisation pipeline
and candidate pools as A3; the only things it lacks are the exact solver and the uniqueness
check, which are the two components it exists to measure. Both sweeps are recorded in
`docs/EVALUATION.md`. No baseline parameter was chosen to make A3 look better.

## One proof block

```
PROOF  crd_001_acc_01_2025-01-09
regime      A_DECLARED
uniqueness  AMBIGUOUS (search) / declared composition residual 0.00
members     15 PAYMENT + refunds + fee + GST + withholding + reserve + bank charge
residual    0.00
```

Class-4 MIXED_N_M, five credits, residual `0.00` at paise via Regime A `verify_declared`
(CP3). The N:M shape is on the proof.

## Rubric map (§4)

| Vector | Where it lives |
|---|---|
| Problem taste | "Why is my payout short?" — Razorpay's own finance question |
| AI judgment | Tiers 1–3 resolved 66034/66034 counterparties; the model was not spent (Q2=C) |
| Engineering taste | Integer paise, uniqueness across the tolerance window, hash-chained audit, `--offline` |
| Evidence discipline | Four arms, Wilson-ready stats, threshold read off the curve, evaluation log below |

## Test-split evaluation log (NN-16)

Evaluation **1 of 4**, `2026-08-27T18:45:00+05:30`, tag `v1-submittable`. n=800 credits (seeds 101–105). Tuned on dev only.

| arm | exact | assignment P | assignment R | cleared | flagged | budget |
|---|---|---|---|---|---|---|
| A0 | 0/800 | — | 0/20487 | 0 | — | — |
| A1 | 0/800 | — | 0/20487 | 0 | — | — |
| A2 | 0/800 | 262/4026 | 262/20487 | 510 | 52 | 238 |
| A3 | 425/800 | 11467/11470 | 11467/20487 | 0 | 116 | 684 |

Held-out class 9 `OVERPAYMENT` was present in this split. Auto-clear remains 0 at threshold `1.000000`.

## Limitations

The corpus is synthetic. The PII boundary is Phase 2 (F49). Ordering-score weights are uniform,
not fitted. `ε_R = 7` is derived from the worst-case sub-rupee member count, which makes
Regime B search ambiguous on this profile — that is the §0.1 coverage cost, not a missed
bug. F56 was not run (no additional raters). Tier 4 was not exercised (no model spend).
Razorpay test-mode is behind an adapter with `enabled: false`.

## Reproduce

```
make test
make eval
make reproduce
make challenge FILE=fixtures/challenges/unsolvable_missing_record.json
make evidence
make verify-books
make eval-diff RUN_A=artifacts/v1 RUN_B=artifacts/v1
```

## Controller results (Phase 2, below the fold)

Phase 1 auto-clear coverage remains `0/239` at threshold `1.000000`. Phase 2 does not move that threshold (F54). What changed is the controller surface around a still-conservative clearer.

- **Books (F33).** Period identity holds on both accounts. double_claimed=`0`. Unreconciled value `1,44,25,758.19` (all credits; nothing auto-cleared).
- **Journal (F40).** Debits equal credits at paise. Bank control residual `0`. Uncleared credits post to suspense `2300`. No plug line. This is a file you import; nothing here holds accounting-system credentials.
- **Exceptions (F37).** Compression and purity are the measured pair in `docs/EVALUATION.md` §12, not an invented ratio.
- **Fees (F38).** False-positive rate on the undrifted Phase 1 corpus is in §12. Class `24 FEE_RATE_DRIFT` exists; classes 25–26 do not.

## Operational depth (Phase 3, below the fold)

Phase 3 does not move auto-clear coverage (`0/239` at threshold `1.000000`) or A3 exact (`129/239`).

- **Tolerance (F32).** Fitted `k=21`; applied rupee window 2 vs D6's 7. Two boundaries: the DP opens `ceil(ε_paise/100)` rupees; the verifier still demands residual 0. Empty F54 diff.
- **Ladder (F51).** Coverage 0 at every rung; monotonicity is a test.
- **Books-adjacent (F39/F41/F42).** Leakage rupees are a detector measurement on synthetic data. Reserve outstanding ties at paise and is arithmetic over known release dates, not a forecast. Dispute reconstruction on this corpus is 0/9.
- **Formats (F45/F48).** CAMT.053 and MT940 round-trip the CSV path field-by-field. Malformed fixtures load nothing.

## Second-order results (§9.10)

See `docs/EVALUATION.md` §12–§14. Phase 3 rows: F32, F51, F39, F45, F48, F35, F41, F42, F57; F30/F23/F26 in the same table from §6.1.

## Phase 3 test-split note (NN-16)

Evaluation **1 of 4** remains the only test-split spend (`v1-submittable`). Phase 2 skipped evaluation 2 of 4. Phase 3 also skipped it: F32 narrowed the search window from 7 to 2 rupees, which could have moved uniqueness, but the flags-on A3 disposition map vs `artifacts/v1` is empty and auto-clear stayed 0. A test-split run could not publish a new headline number. Dev eval was re-run for Gate 3.

## Safety

1. **PII boundary (F49).** Detectors for VPAs, card fragments, phones and account tails. `CachedLLMClient` redacts then **raises** `PiiLeakError` on a residual hit. It does not warn-and-send. Raw VPA/card/phone count in the model egress log: `0`. Redacted-vs-raw entity-resolution accuracy delta: not estimable (Q2=C stub; both paths `0` model resolutions).
2. **Injection corpus (F50).** 30 planted narration strings. Auto-clears: `0/30`. The model returns an id from a closed candidate set, never sees or emits an amount, and cannot authorise: auto-clear still needs UNIQUE + zero paise residual + an ordering score from observables.
3. **Degradation ladder (F51).** Coverage at every rung on this corpus: **0/239**. Error is not applicable (nothing auto-clears). The ladder is NORMAL → NO_MODEL → NO_SEARCH → READ_ONLY → HALTED. Monotonic conservatism is a test (`tests/test_degrade.py`).
4. **Derived tolerance (F32).** Search ε is fitted `k=21` in `ε(n)=ceil(k·√n)` paise; the DP window is `ceil(ε/100)=2` rupees. The verifier still demands a zero paise residual. D6's flat 7 remains the flags-off window.
5. **Leakage (F39).** Rupee totals in §14 measure the **detector on synthetic data**, not real-world incidence.
