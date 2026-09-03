# Residual Zero

Settlement reconciliation as signed subset-sum: for every bank credit, the member set, a
zero-paise residual, a uniqueness check, and a hash-chained proof.

## Headline (dev, n=239 credits)

| arm | exact | assignment P | assignment R | cleared | flagged |
|---|---|---|---|---|---|
| A0 exact match | 0/239 | — | 0/5973 | 0 | — |
| A1 fuzzy 1:1 | 0/239 | — | 0/5973 | 0 | — |
| A2 rules-only greedy | 0/239 | 142/1163 | 142/5973 | 147 | 92 |
| A3 full system | 148/239 | 3977/3977 | 3977/5973 | 0 | 239 |
| A4 human | 0/20 | — | — | — | 20 |

Reproduced by `make eval` → `artifacts/dev/headline.md`. Auto-clear coverage of A3 is 0/239
at the derived threshold `1.000000` (error budget `1/100`, `artifacts/dev/curve_a3.json` /
`artifacts/dev/threshold.json`). Search uniqueness under `ε_R = 7` is AMBIGUOUS on the
5-day pool, so the system flags rather than guesses. Residual-zero reconciliations
are 159/239 (`verify_declared.ok`, ledger ops, settlement-declared ops, or reconstructed
rate lines). Settlement-linked / member-identified is 148/239 (6 extra credits where the
report named the true ids but both ledger and settlement amounts were shortened — class 8).
Those 6 are not residual-zero. Search auto-clear is still 0/239. Flags-off / ledger-only
verify-gated exact stays 129/239.

## Eval vs console overlay

A3 search auto-clear of `0/239` is UNIQUE + FULL + threshold `1.000000`: refuse-all on this
pool, not a tuned knee that happens to be 1. The ops console overlay counts
`verify_declared.ok` on posted credits and **does not write `CLEARED`**. Those are different
predicates. A3 exact `148/239` is member-set match to truth. Assignment R `3977/5973`
is complete on predicted members and incomplete versus the full truth set.
Test-split A3 (`artifacts/test/headline.md`, eval 4 of 4) is member-identified
`501/800`, `BUDGET_EXCEEDED` 0, search completed `800/800`, cleared 0. Residual-zero
is `521/800` (`artifacts/test/t04.md`). Eval 1 was member-identified `425/800`
and budget 684. Eval 3 confirmed f59 at residual-zero `501/800`.
F56 is not run. The corpus is synthetic.

## One proof block

```
PROOF  crd_001_acc_01_2025-01-09
amount      59,645.39
regime      A_DECLARED  ok: True
uniqueness  AMBIGUOUS (search) / declared composition residual 0.00
members     27 lines (15 PAYMENT + 2 REFUND + fee + GST + withholding + reserve + bank charge)
residual    0.00
```

Class-4 MIXED_N_M. Reproduced by
`python -m residual_zero.cli solve --split dev --class 4 --show-proof --limit 1`
(also `make demo`).

## Rubric map (§4)

| Vector | Where it lives |
|---|---|
| Problem taste | "Why is my payout short?" — Razorpay's own finance question |
| AI judgment | Tiers 1–3 resolved 66034/66034 counterparties; the model was not spent (Q2=C) |
| Engineering taste | Integer paise, uniqueness across the tolerance window, hash-chained audit, `--offline` |
| Evidence discipline | Four arms, Wilson-ready stats, threshold read off the curve, evaluation log below |

## Quickstart

From a clone, with Python 3.11+ (this machine: 3.13.7 in `.venv`):

```
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
# Browser certification only (kept out of [dev] so unit tests need no browser toolchain):
#   .venv/bin/pip install -e ".[e2e]" && .venv/bin/python -m playwright install chromium
.venv/bin/python -m generator.cli --split dev --profile config/profiles/phase1.yaml
make demo
.venv/bin/python -m residual_zero.console
# then open http://127.0.0.1:8765  (batch / exceptions / audit / one credit proof)
# Chrome/Edge: chrome://extensions → Load unpacked → extension/
# Cursor MCP (read-only stdio): .venv/bin/python -m residual_zero.mcp  (.cursor/mcp.json)
# Ask: fitted controller on artifacts/dev — optional NVIDIA NIM rewrite via .env NVIDIA_API_KEY
# Train: .venv/bin/python -m residual_zero.qa
# Eval A3 stays stub (Q2=C). Overlay does not write CLEARED.
make eval
make reproduce
make challenge FILE=fixtures/challenges/unsolvable_missing_record.json
make evidence
make verify-books
make eval-diff RUN_A=artifacts/v1 RUN_B=artifacts/v1
```

`data/dev/rendered` and `data/dev/truth.jsonl` are committed so `make demo` / `make eval`
work from a clone. Regenerating the split does **not** reproduce the tagged headline
(generator drift after Phase 1). The test split stays gitignored; its numbers live in
`artifacts/test/`. `src/` still cannot open `truth.jsonl` (NN-6).

Rates live in `config/tax_rates.yaml` and `config/fees.yaml`, each with a `source_url` and
`as_of` date. The loader refuses any unverified rate value.

## Deploying it

Local behaviour is unchanged and remains the default: no login, SQLite, the committed
synthetic dev corpus. `make demo`, `make eval`, the CLI and the whole test suite run
exactly as before.

For a public HTTPS deployment the same process runs authenticated and multi-tenant on
PostgreSQL. Full instructions in [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md); the shape:

```
export RZ_ENV=production RZ_AUTH_MODE=required RZ_TRUST_PROXY=1 RZ_HOST=0.0.0.0
export RZ_SESSION_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
export RZ_PUBLIC_ORIGIN=https://your-domain.example
export RZ_DATABASE_URL='postgresql://…?sslmode=require'

python scripts/migrate.py --shared
python scripts/bootstrap_admin.py --email you@example.com --org demo --dataset files
python -m residual_zero.console
```

`RZ_ENV=production` **refuses to start** without authentication, a session secret, an
`https://` origin and a PostgreSQL URL — the dangerous failure for a public finance console
is booting happily with authentication off, and that combination is unreachable.

**Isolation is structural.** One PostgreSQL schema per organisation, and a connection whose
`search_path` names only that schema. A query that forgot an `org_id` filter resolves inside
the caller's own schema or not at all. Identity lives in a separate schema that no tenant
connection can reach.

**Nothing about the numbers changes.** The engine, the solver, the verifier, the rate tables
and the committed corpus are untouched.
`tests/deployment/test_corpus_migration.py` asserts that reading the corpus out of
PostgreSQL yields the same residual, the same gate decision and the same member set for
every one of the 248 credits as reading it out of the CSVs; `scripts/migrate_corpus.py`
compares row counts and signed paise totals before and after and exits non-zero on any
difference.

**Authentication does not touch financial authority.** Roles are `viewer` / `analyst` /
`owner`; there is no `clear` permission for any of them. `CLEARED` still requires UNIQUE +
zero-paise residual + a FULL pool + a derived threshold, and the production schema restates
that as a CHECK constraint so a bug, a migration or a hand-written `UPDATE` cannot persist a
clear that never passed the gate.

The Chrome extension authenticates with a personal access token the user mints for
themselves at `/tokens`. It ships **no** secret — no provider key, no database credential —
and it consumes authoritative backend results rather than reimplementing anything.

## Architecture

```
ingest → normalise → candidate generation → SOLVER → verifier → [pass] → proof + audit + ledger write
                                                   ↘ [fail/ambiguous] → diagnosis → exception queue → human
```

Plain typed Python functions in one orchestrator. No agent framework (`docs/DECISIONS.md`
ADR-1). The semantic layer sits *beside* candidate generation, not inside the solver. The
Q&A surface sits *downstream* of the reconciled ledger. Diagram: `docs/ARCHITECTURE.md`.

## Where we chose not to use AI, and what that cost

The model does not add, subtract, or pick a member set. It does not assign an exception
class. It does not authorise a clear. Those jobs are integer arithmetic, a uniqueness
check over the tolerance window, a verifier that re-derives every rate line at paise, and
a decision table with no client parameter (`src/residual_zero/exceptions/classify.py`).

What the model is allowed to do, and only after tiers 1–3 fail: map a redacted counterparty
string to an id from a closed set, and fill slotted prose around figures deterministic code
already rendered. It never sees an amount (NN-3). Auto-clear still requires UNIQUE + zero
paise residual + an ordering score built from observables (NN-4, ADR-11).

**What that cost.** On this corpus it cost nothing in coverage: tiers 1–3 already resolve
every counterparty (66034/66034 EXACT_NORM in the A3 pool walk; 5991/5991 unique ledger
items in F53). Auto-clear is 0 because search is AMBIGUOUS, not because the model abstained.
The cost is the thing we declined: a learned matcher that would approximate the DP's
enumerated set and could not prove uniqueness. F43's behavioural "would this have succeeded
on another rail" is the same refusal, written down rather than built.

## Evaluation

Definitions are frozen in `docs/EVALUATION.md` (written before the logic existed). Assignment
precision/recall are set-overlap fractions. Exact decomposition is member-set equality.
Auto-clear error is `n_cleared_wrong / n_cleared`, rendered `—` when the denominator is 0.
Exception precision uses a frozen "genuinely required human" predicate so flagging everything
cannot game the safety number.

n=239 on dev (seeds 1–3) is large enough that a single exact rate is a real fraction, not
45/50. The test split is n=800 (seeds 101–105). We publish the pooled proportion; Wilson
intervals belong on those headline fractions, not on a 9-row per-class cell.

**Test-split count (NN-16):** **4 of 4 spent.** Official Test evaluation is **not rerun**.
The committed card is `artifacts/test/t04.md`. Working-tree `artifacts/test/headline.md`
matches that card (A3 exact 501/800, cleared 0). Eval 1 at `v1-submittable` was 425/800
with budget 684. Do not overwrite `artifacts/test/` to chase a new score.

**Live LLM (explanation + next-tool only):** the provider is selected by `AI_PROVIDER`
(`nvidia` | `stub`) and is never financial authority. **NVIDIA NIM is the only supported
backend.** Groq was removed on 2026-09-03 — its key is out of the environment and it is no
longer selectable, addressable, or a fallback; an unrecognised `AI_PROVIDER` now resolves to
no endpoint and makes no call. (Historically, Groq returned **HTTP 403** on that key and
stayed `UNAVAILABLE`, which is why it was never load-bearing.)
NVIDIA NIM (`https://integrate.api.nvidia.com/v1`) with
`openai/gpt-oss-20b` is **live and executed**: rewrite ~6-24 s, and the model's next-tool pick
is validated against the 43-name read-only allowlist before the application runs it, so
`LIVE_LLM_TOOL_LOOP = YES`. Both DeepSeek v4 models in that catalogue exceeded 120 s on a
realistic prompt and are unusable against the 30 s controller budget. Eval A3 stays stub
(`config/llm.yaml`) so scoring never depends on a provider.

**Browser:** Playwright Chromium E2E lives in `tests/e2e/` (`RZ_E2E=1`, install via the `e2e` extra). Certification
artifacts: `docs/DEMO_CERTIFICATION.md`, `artifacts/qa/RELEASE_CERTIFICATION.md`.

A1's similarity threshold and amount tolerance were swept on dev and fixed at the values
that maximised A1's own exact rate. A2 shares A3's tax config, windows, normalisation, and
pools; it lacks the exact solver and the uniqueness check. Sweeps: `docs/EVALUATION.md` §9.
No baseline parameter was chosen to make A3 look better.

## Results

Per-class table: `artifacts/dev/per_class.md` (`make eval`). Weakest exact cells on dev are
classes 5, 8, 12, 13, 14, 18 at **0/9** — amount transpose, partial payment, netted fee,
withholding gap, omitted GST, sign reversal. Directional map, not a 90-vs-82 claim.

Risk-coverage curve: `artifacts/dev/curve_a3.json`. Threshold `1.000000` was read off that
curve at error budget `1/100`, declared before the curve was read. On this profile no
UNIQUE+FULL credit is eligible, so the threshold never auto-clears.

Ablations: `artifacts/dev/ablations.md`. Skipping tier 4 is a no-op (Q2=C). Replacing the
DP with A2 greedy drops verify-gated exact from 129/239 to 0/239. Named-declared exact is 148/239. The verifier is not ablated (NN-12).

Cost: `artifacts/dev/cost.md` — 0 tokens, 0 paise, Darwin 25.5.0 arm64.

## Controller results (Phase 2, below the fold)

Phase 1 auto-clear coverage remains `0/239` at threshold `1.000000`. Phase 2 does not move
that threshold (F54). What changed is the controller surface around a still-conservative
clearer.

- **Books (F33).** Period identity holds on both accounts. double_claimed=`0`. Unreconciled
  value `1,44,25,758.19` (all credits; nothing auto-cleared). `make verify-books`.
- **Journal (F40).** Debits equal credits at paise. Bank control residual `0`. Uncleared
  credits post to suspense `2300`. No plug line. Nothing here holds accounting-system
  credentials.
- **Exceptions (F37).** Compression **248/34**, purity **159/248** against generator cause
  labels used only in eval (`docs/EVALUATION.md` §12).
- **Fees (F38).** False-positive rate on the undrifted Phase 1 corpus: **0/45**
  instrument-weeks. Class `24 FEE_RATE_DRIFT` exists on `phase2_drift_plan()`. Classes 25
  and 26 exist on Phase 4 fixture plans; `data/dev` was not regenerated.

## Operational depth (Phase 3, below the fold)

Phase 3 does not move auto-clear coverage (`0/239`). Verify-gated A3 exact stays `129/239` with f58 off.

- **Tolerance (F32).** Fitted `k=21`; applied rupee window 2 vs D6's 7. The DP opens
  `ceil(ε_paise/100)` rupees; the verifier still demands residual 0.
- **Ladder (F51).** Coverage 0 at every rung; monotonicity is a test.
- **Books-adjacent (F39/F41/F42).** Leakage rupees measure the **detector on synthetic
  data**, not incidence. Reserve outstanding ties at paise over known release dates, not a
  forecast. Dispute reconstruction on this corpus is 0/9.
- **Formats (F45/F48).** CAMT.053 and MT940 round-trip the CSV path field-by-field.
  Malformed fixtures load nothing.

## Phase 4 (below the fold)

Phase 4 does not move auto-clear coverage or A3 exact.

- **Providers (F53).** Three stub backends, equal tuning (`none`). Tier-4 calls: **0**.
  Cost: **0** paise/credit. `artifacts/p4/providers.md`.
- **Alternate diff (F36).** Live corpus both medians **—** (245/245 cap-refused). Fixture:
  median symmetric-difference size 3, median decomposition size 1.
- **Parallelism (F34).** Byte-identical at 1/4/8 workers. Throughput did not scale (GIL).
- **Webhooks (F47).** Four deliveries, identical ledger state. Adapter `enabled: false`.
- **What-if (F43).** **136/136** accepted declared sets reproduce under generator tables.
  **Declined:** "would this payment have succeeded on a different rail."
- **Accounts (F44).** FP **0/248** on legitimate `data/dev`; class 25 detection **3/3** on
  the fixture. `data/dev` not regenerated.
- **As-of (F46).** As-of equals audit replay at 20 sampled seqs.
- **FX (F29).** Class 26 is a 1–99 paise rounding residue. Multi-currency FX beyond that
  residue stays out of scope (§1.3).

## Second-order results (§9.10)

See `docs/EVALUATION.md` §12–§15. Every row names the command or test that produced it.

## Test-split evaluation log (NN-16)

| # | When | Tag | Split | Notes |
|---|---|---|---|---|
| 1 | `2026-08-27T18:45:00+05:30` | `v1-submittable` | test, n=800 | A0/A1 exact 0/800. A2 exact 0/800, greedy-cleared 510, budget 238. A3 exact 425/800, assignment 11467/11470 P / 11467/20487 R, auto-cleared 0, flagged 116, budget 684. Held-out class 9 present. Tuned on dev only. Preserved in `artifacts/test/before_scale/headline.md`. |
| 2 | `2026-08-29T16:10:00+05:30` | `75cef50` | test, n=800 | Scale search. Residual-zero 425/800. Settlement-linked 501/800. BUDGET 0. Search completed 800/800. Auto-clear 0. Assignment 13912/13912 P / 13912/20487 R. Wall 69776 ms. |
| 3 | `2026-08-29T16:33:38+05:30` | `75cef50` | test, n=800 | Official f59. Residual-zero 501/800. Member-identified 501/800. Unique 0. Auto-clear 0. Wall 69621 ms. `artifacts/test/t04.md`. |
| 4 | `2026-08-29T16:45:00+05:30` | `75cef50` | test, n=800 | Official f60. Residual-zero **521/800**. Member-identified 501/800. Unique 0. Auto-clear 0. Wall 68299 ms. `artifacts/test/t04.md`. Ceiling exhausted. |

Ceiling is four. This project spent four.

## Safety

1. **PII boundary (F49).** Detectors for VPAs, card fragments, phones and account tails.
   `CachedLLMClient` redacts then **raises** `PiiLeakError`. Egress hits: `0`. Redacted-vs-raw
   accuracy delta: not estimable (Q2=C).
2. **Injection corpus (F50).** 30 planted narration strings. Auto-clears: `0/30`.
3. **Degradation ladder (F51).** Coverage at every rung: **0/239**. Error N/A. NORMAL →
   NO_MODEL → NO_SEARCH → READ_ONLY → HALTED. Monotonic conservatism is a test.

## Limitations

The corpus is **synthetic**. Corruption classes are modelled recipes, not production
incident rates. The leakage rupee figure measures a detector, not real-world incidence.
F23 did not triple the generator eval; the published number is that `config_digest` of
`solver.yaml` is identical across three merchant profiles. The dev-to-test gap is real:
dev residual-zero 159/239 / settlement-linked 148/239; test residual-zero 521/800 / settlement-linked 501/800. Eval 1 spent 684 credits in `BUDGET_EXCEEDED`; eval 2 completed search on 800/800
because range B and stacking make pools and axes larger. Per-class n≈9 is a map of thin
spots, not a comparison of 90% to 82%. Ordering-score weights are uniform, not fitted.
F56 was not run (no additional raters). Tier 4 was not exercised (no model spend).
Razorpay test-mode is `enabled: false`. Auto-clear coverage is 0 by uniqueness, which is
the product, and it means we did not demonstrate a safe non-zero operating point on this
profile.

What we are not claiming: rupees saved, hours returned, headcount avoided, or that a
payment would have succeeded on another rail.

A clean clone that *regenerates* `data/dev` does not match the tagged corpus (5991 ledger
rows vs 5989 on CPython 3.13.7). Headline numbers require the frozen `data/dev` committed
in this freeze.

## Incidents

Real failures, written the hour they happened, including the wrong first hypothesis:
[`docs/INCIDENTS.md`](docs/INCIDENTS.md). The video uses the uniqueness-under-tolerance
bug (`tests/regressions/test_uniqueness_under_tolerance.py`).

Leftovers we refused to start after `v4`: [`docs/FUTURE.md`](docs/FUTURE.md).
Video script: [`docs/VIDEO.md`](docs/VIDEO.md). Submission drafts:
[`docs/SUBMISSION.md`](docs/SUBMISSION.md).
