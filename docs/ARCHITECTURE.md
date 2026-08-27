# ARCHITECTURE.md

_Stub created at CP0. Written properly at CP9, when the pipeline it describes exists and the
diagram can be drawn from the code rather than from the plan._

Seven stages, executed as a plain pipeline with exactly one forward-branching edge:

```
ingest → normalise → candidate generation → SOLVER → verifier → [pass] → proof + audit + ledger write
                                                   ↘ [fail/ambiguous] → diagnosis → exception queue → human
```

The semantic layer sits *beside* candidate generation, not inside the solver. The Q&A agent sits
*downstream* of the reconciled ledger and touches nothing upstream. See `docs/DECISIONS.md` ADR-1
for why there is no agent framework.
