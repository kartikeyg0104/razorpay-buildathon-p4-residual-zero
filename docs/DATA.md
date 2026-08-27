# DATA.md

Synthetic corpus for Residual Zero. The data is generated, not observed, and this file is
where that is documented rather than glossed (spec §8.1).

Generated at CP1 from `config/profiles/phase1.yaml`, seeds 1–3, corruption range A,
counterparty pool A. Command:

```
python -m generator.cli --split dev --profile config/profiles/phase1.yaml
```

## Four stages, in this order, because inverting them destroys the answer key

1. **Scenario** (`generator/scenario.py`). Sample a merchant profile: orders per day,
   instrument mix, counterparties, capture timestamps. No money is computed.
2. **Ground truth** (`generator/truth.py`). Compute each settlement exactly from the payment
   stream and `config/{tax_rates,fees}.yaml`. The true member set is written to
   `data/{split}/truth.jsonl`. The system under test cannot open that path (NN-6,
   `SourceRoot`).
3. **Corruption** (`generator/corrupt.py`). Mutate **rendered views only**. CP1 applied
   structural classes 1–4 and class 23. CP2 extends the same function with classes 5–22.
   Class 24 exists on `phase2_drift_plan()` only. Classes 25 and 26 exist on
   `phase4_class25_plan()` / `phase4_fx_plan()` only. `data/dev` was not regenerated for
   classes 24–26.
4. **Render** (`generator/render.py`). Emit bank / ledger / settlement CSVs with IST dates
   and rupee-display amounts.

Inverting (2) and (3) would write a corrupted answer key. Every metric in the project would
then be silently invalid (NN-7).

## Phase 1 merchant profile

See `config/profiles/phase1.yaml`. Headline parameters: 2 accounts, 40 settlement dates,
60-day horizon, T+2, business days only (weekends skipped, no holiday calendar), 15 orders
per day per account except 8 sparse 1-order days on account 0 so class 1 exists by
construction, whole-rupee order amounts, fee itemisation
`PER_SETTLEMENT_INSTRUMENT`, `subrupee_member_max: 13`.

## Realised counts (dev, seeds 1–3)

| Quantity | Value |
|---|---|
| Credits | 239 |
| Ledger items in the answer key | 5986 |
| Rendered ledger rows (includes 72 class-23 decoys) | 6058 |
| Class 1 `CLEAN_1_1` | 22 |
| Class 2 `AGGREGATE_N_1` | 140 |
| Class 3 `SPLIT_1_N` | 42 |
| Class 4 `MIXED_N_M` | 35 |
| Class 23 `AMBIGUOUS_BY_CONSTRUCTION` | 36 |

`m`, the sub-rupee member count the search tolerance is derived from: min 4, max 13
(the design bound), sum 2531 across 239 credits. The D6 guard held.

Class 4 is genuinely N:M. Inspected examples:

- `crd_001_acc_00_2025-01-23`: 15 payments, 3 refunds, 27 members, residual-zero total
  ₹48,246.49.
- `crd_001_acc_00_2025-02-06`: 16 payments, 3 refunds, 32 members; orders
  `ord_001_acc_00_00198` and `ord_001_acc_00_00213` each settle across two consecutive
  credits.

That is the shape 1:1 fuzzy matching cannot express, and it is in the corpus before a
line of the solver is written.

## Assumptions we are least confident about (§8.1)

1. **The merchant is an e-commerce participant, so s.194-O withholding sits on gross
   captured payments.** A plain Razorpay PA merchant on their own storefront would not
   attract this deduction (ADR-9). The assumption is what keeps class 13 and the
   `SUSPECTED_WITHHOLDING` diagnosis meaningful. It is a generator choice, not a claim
   about Razorpay's settlement stack.
2. **Fees are aggregated per (settlement, instrument), not per payment.** That is what
   caps `m` at 13 and derives `ε_R = 7`. A reviewer who expects Razorpay's per-payment
   fee rows will see a different itemisation. The blast radius is coverage, not
   correctness (PLAN-P1 §0.2).
3. **Payments, refunds and chargebacks are whole-rupee by construction.** Real gateways
   post paise. Whole-rupee operational lines are what makes the D6 bound a function of
   the *computed* lines rather than of member count.
4. **Reserve releases are not posted in CP1.** A release landing on a later settlement
   is a 14th sub-rupee member and would break the bound of 13. Holds still deduct.
   Releases arrive with class 21 at CP2.
5. **The fee is Razorpay's platform fee, not MDR** (ADR-7). Domestic UPI is not
   zero-rated in this corpus.
6. **No Indian holiday calendar.** Business days are weekdays. Class 7 will shift by
   business days under that definition.
7. **Counterparty names are invented.** They are a closed pool so semantic resolution
   has something to resolve against, not a sample of real merchants.

## MT940 `:86:` and class 16 (F45)

SWIFT MT940's `:86:` information-to-account-owner field is where banks actually truncate
narration — typically around 35 characters, with continuation lines for the overflow.
Corruption class 16 in `generator/corrupt.py` models that truncation on the CSV path.
The MT940 adapter round-trips the full `BankCredit` through `:86:` plus continuation
lines so parse fidelity against CSV can be asserted field-by-field; the class-16
generator still mutates the CSV narration independently. The two are the same real-world
seam, two renderings of it.

## Realised counts (test, seeds 101–105, frozen at CP2)

Profile `config/profiles/phase1_test.yaml`: 4 accounts, range B, pool B, stacked
corruptions, held-out class **9 OVERPAYMENT** (absent from dev, present on test). Recorded
in `docs/EVALUATION.md` before this split was generated.

| Quantity | Value |
|---|---|
| Credits | 825 |
| Ledger items in the answer key | 20487 |
| Rendered ledger rows | 20448 |
| Truth records | 800 |

Dev after CP2 regen: 248 credits, 5983 truth items, 5991 rendered ledger rows, 239 truth
records. The extra bank credits over truth records are class-23 decoy *credits* that have
no answer-key members of their own.
