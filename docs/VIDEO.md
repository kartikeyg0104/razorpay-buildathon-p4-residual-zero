# Video script (five minutes)

Numbers match `artifacts/dev/headline.md` and the commands below, tested 2026-08-28 on
Darwin 25.5.0 arm64 / CPython 3.13.7. Do not use the spec's ₹4,82,150 / ₹5,01,200
illustrations on camera (NN-15). Pre-record anything that can fail. Do not run `make eval`
live.

---

## 0:00–0:20 · The question

**On screen.** Bank credit `crd_001_acc_01_2025-01-09`, amount **59,645.39**, value date
2025-01-09. Fifteen captured payments sit behind it, plus refunds, fee, GST, withholding,
reserve, a bank charge.

**Say.** "A merchant's settlement lands at fifty-nine thousand. The ledger is larger. Why
is my payout this number — and not a guess?"

---

## 0:20–1:00 · The decomposition

**Command (pre-record).**

```
make demo
```

**Expected output (tested).** Starts with:

```
credit crd_001_acc_01_2025-01-09
  regime: A_DECLARED  ok: True  line_deltas: 0  missing: 0
  members: 27
```

and ends with:

```
  credit amount: 59,645.39
  residual:      0.00
```

**Say.** "Twenty-seven lines. Residual zero rupees and zero paise. You can verify this
with a calculator. Search still called the same credit AMBIGUOUS — we cleared nothing. The
declared stack is what we proved."

---

## 1:00–1:45 · Architecture

**On screen.** The pipeline from `docs/ARCHITECTURE.md`. Highlight SOLVER and verifier.
The model box sits beside candidate generation, not on the residual.

**Say.** "The model does not add. It does not pick a match. It does not authorise a clear.
Plain Python, one orchestrator — we did not use an agent framework because this pipeline
does not loop. Period identity holds on both accounts: what landed equals what we have
explained plus what is still unreconciled, at paise."

(F33, one sentence over the diagram — not a new segment.)

---

## 1:45–3:15 · Evidence

**On screen.** `artifacts/dev/headline.md`.

**Say.** "Exact match and optimal fuzzy matching: zero exact decompositions in 239.
Rules-only greedy: still zero exact, and it would auto-clear 147. The full system: 129
exact — every one a declared composition we re-derived — and auto-clear zero, because we
refuse to guess under an AMBIGUOUS window."

**Swap 1, fifteen seconds (F38).** "Fee-drift false-positive rate on this undrifted corpus
is zero of forty-five instrument-weeks. We did not invent an overcharge. The detector
stayed quiet when nothing drifted." (`docs/EVALUATION.md` §12; class 24 was not written
onto `data/dev`.)

**Swap 2, fifteen seconds (F37).** "Two hundred forty-eight exceptions, thirty-four
clusters. Compression 248/34. Purity 159/248 against labels the clusterer never saw."

**Curve.** Point at `artifacts/dev/curve_a3.json`. "Threshold 1.000000, read off the curve
at error budget 1/100, declared before we looked. On this profile that means never
auto-clear."

**Ablation.** "`NO_LLM_TIER` changes nothing — we never called the model. Greedy instead
of the DP: exact goes from 129/239 to 0/239."

**Weakest class.** Per-class table, classes 5/8/12/13/14/18 at 0/9. "The map of where we
are thin: missing lines and sign errors, not the N:M shape."

---

## 3:15–4:05 · Exceptions

**Near-miss.** `make challenge FILE=fixtures/challenges/unsolvable_missing_record.json`

**Expected (tested):**

```
challenge unsolvable_missing_record.json: NONE_FOUND -> MISSING_RECORD
FLAGGED
```

**Say.** "The member that would explain the credit is not in any view. We did not invent
it. Flagged, class MISSING_RECORD."

**Refusal.** "Search found more than one subset inside tolerance. After F31's cap we still
will not call UNIQUE. The human sees the symmetric difference of two sets, not the whole
pool — on this live corpus every AMBIGUOUS credit hit the enumerate cap, so we show N/A
rather than a fake pair. The fixture size is three items of difference against a
one-item decomposition. We decline to pick."

**Q&A (one line).** "The enquiry surface cites transaction ids on the reconciled ledger.
It cannot change a residual."

---

## 4:05–4:40 · The real failure

From `docs/INCIDENTS.md`, 2026-08-27T23:20:00Z.

**Say.** "The reference solver returned UNIQUE for amounts 10 and 11, target 10, tolerance
1. I first thought brute-force tests would have caught it. They used tolerance zero.
Uniqueness-under-tolerance was untested. Enumeration walked one hit total. Two totals in
the window is the production case once you round to rupees."

**Command (pre-record).**

```
python -m pytest -q tests/regressions/test_uniqueness_under_tolerance.py
```

**Expected (tested):** `1 passed`.

---

## 4:40–5:00 · Limits

**Say.** "The data is synthetic. Leakage rupees measure a detector, not incidence. We
evaluated the test split once. Auto-clear is zero on this profile because uniqueness is
the product. Next: a merchant's own files, not another feature."

Stop. Do not tour Phase 2–4. They are in the README when someone asks.
