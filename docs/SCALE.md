# SCALE.md — F27, written against F57

Source measurements: `artifacts/p3/latency.md` (Gate 3 / F57). Machine: Darwin 25.5.0 arm64,
CPython 3.13.7. n=248 bank credits.

| stage | n | p50 | p95 | p99 |
|---|---:|---|---|---|
| dp | 248 | 8.4ms | 15.4ms | 19.1ms |
| ingest | 1 | 115ms | 115ms | 115ms |
| verify | 248 | 0.10ms | 0.20ms | 3.2ms |

Wall for this n: 62598650209 ns. Bottleneck named: **DP**. Linear projection of that wall
to 5,000 credits was 1262069560665 ns (~21 min), itself a projection, not a 5,000-credit
corpus.

## What breaks at 100,000 credits/day

**DP first.** At p50 8.4ms, a serial day of 100,000 credits is on the order of 14 minutes
of DP alone, before ingest and verify. p95 15.4ms makes the tail the planning number.
F34's 1/4/8-worker table on this CPython DP did not buy a speedup (GIL; byte-identity held).
Process-level parallelism would be the next lever, not more threads.

**Pool cap second.** `max_pool: 400` and `max_axis_width_rupees: 2000000` already turn oversize
pools into `BUDGET_EXCEEDED`. A 100k-credit day with the same 5-day window and two accounts
does not automatically blow the cap — the cap is per credit, not per day — but a denser
ledger (more items per window) will. Coverage then falls by the budget path, which is the
designed failure, not a hang.

**SQLite third.** One WAL writer, 100k audit rows, 100k reconciliation rows is well inside
SQLite. The replacement is not a different engine; it is "do not have two processes write
the same file". F34 keeps SQLite on the reducing process for that reason.

**Model cost last.** Q2=C, `token_budget: 0`, F53 measured 0 tokens and 0 paise on every
backend. A 100k-credit day costs 0 model paise on this corpus because tiers 1–3 already
resolve every counterparty. That stays true until a residue of unresolved names appears.

**What does not break.** The verifier (0.10ms p50) and the conservation/journal post-pass
are not the constraint. Auto-clear coverage is already 0 at threshold `1.000000`; scaling
does not create clears this profile refused at n=239.
