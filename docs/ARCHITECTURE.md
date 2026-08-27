# ARCHITECTURE.md

Seven stages, executed as a plain pipeline with exactly one forward-branching edge:

```
ingest → normalise → candidate generation → SOLVER → verifier → [pass] → proof + audit + ledger write
                                                   ↘ [fail/ambiguous] → diagnosis → exception queue → human
```

Drawn from `src/residual_zero/orchestrator.py` (`run_split`) and `eval/arms/a3_full.py`.

- **Ingest.** CSV / CAMT.053 / MT940 / settlement report → `LedgerItem` / `BankCredit`.
  Adapters raise rather than return a prefix. Razorpay test-mode is `enabled: false`.
- **Normalise.** Integer paise, IST display at the edge, narration tokens. No float money.
- **Candidate generation.** Account + currency filter, asymmetric date windows, deterministic
  sort. Over `MAX_POOL`, sub-window split or `BUDGET_EXCEEDED` — never a silent truncate.
- **Solver.** Regime A re-derives declared lines from the rate table. Regime B is signed
  subset-sum on a rupee axis with uniqueness across the whole tolerance window. CP-SAT may
  only remove DP-enumerated sets.
- **Verifier.** Residual 0 paise, always. Search ε does not widen acceptance.
- **Pass path.** Proof record, hash-chained audit, optional journal. Conservation identity
  is a joint check over the period (`make verify-books`).
- **Fail path.** Deterministic exception class, slotted narration, queue. Clustering and
  traces are flags, off by default in `FeatureFlags.all_off()`.

The semantic cascade (exact → token → fuzzy → model → unresolved) sits **beside**
candidate generation. It never selects members. The Q&A agent sits **downstream** of the
sqlite ledger and cannot write a residual.

No agent framework: ADR-1. The model never sees an amount: ADR-3. No model-derived score
gates a clear: ADR-11.
