# F19 / F56 protocol (D18)

Frozen at CP5 **before** A3 dispositions and exception classes exist for these credits.

## Pre-registered question

Registered 2026-08-27T18:15:00+05:30, before `python -m residual_zero.cli run --split dev --offline`
produced exception classes or ordering scores for the selected credits.

> On the credits where the raters disagreed with each other — any pairwise disposition
> disagreement — did the system flag rather than clear?

Answered at CP6.

## Selection

Twenty credits from **dev**. Script: `eval/human_study.py`. Sort key
`(seed, account_id, value_date, credit_id)`, then stratified: at least 2 class-23, 2 class-4,
2 class-1, at least 1 Regime A; remainder by the sort key. IDs in `selected_credits.json`.

## What raters see

The three rendered source views for the credit's account over a ±40 day window;
`config/tax_rates.yaml` and `config/fees.yaml`; and `primer.md`.

## What raters must not see

`truth.jsonl`; any system output; any proof block; the corruption class labels; the ordering
score; the selection strategy; and each other's sheets.

## Stopwatch

Credits in the given order. Clock starts when views open, stops when disposition is written.
Breaks recorded and excluded. Elapsed time per credit, not a single total.

## Sheet

`artifacts/human_study/rater_{n}.csv`:

```
credit_id, disposition, member_ids, elapsed_seconds, confusion_note
```

Disposition vocabulary: `CLEARED` | `FLAGGED` | `GAVE_UP` (maps to `BUDGET_EXCEEDED`).

## Q3

No additional raters were available in the CP5 window (`PLAN-QUESTIONS.md` Q3, option C).
Sheets 2 and 3 are blank templates. F56 is recorded as not run. F19 is not scored: the
executor had already seen solver output at CP3/CP4, so an honest human baseline no longer
exists. That is the NN-21 minimum measurable version: protocol, frozen selection, sealed blank
sheets, honest `results.json`.
