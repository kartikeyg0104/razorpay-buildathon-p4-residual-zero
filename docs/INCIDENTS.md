# INCIDENTS.md

Contemporaneous failure log, per NN-19 and spec §13.2. Anything that breaks and costs more than
fifteen minutes gets an entry **the same hour**: timestamp, symptom, what I first thought it was,
what it actually was, the fix, the commit hash, the regression test added.

Raw and unpolished on purpose. Written live it is unfakeable; written retrospectively it reads
like fiction, because it is. An empty log is better than an invented one, and an invented one is
the single most damaging thing this repository could contain.

Format:

```
## <ISO timestamp> · <one-line symptom>
**Symptom.**
**First hypothesis.** (and why it was plausible)
**Actual cause.**
**Fix.**
**Commit.**
**Regression test.** tests/regressions/<file>::<function>
**What it changed about my thinking.**
```

---

_No entries yet. Created at CP0, before any logic module, per NN-19._
