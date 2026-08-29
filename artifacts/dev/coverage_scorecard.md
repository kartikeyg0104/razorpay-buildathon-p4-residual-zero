# Coverage scorecard — official eval 3 then f60 eval 4

Residual-zero is `verify_declared.ok`. Member-identified is A3 exact (named set == truth).
Auto-clear is UNIQUE + FULL + threshold 1.000000.

Official commands:
- Dev: `python -m eval.cli --split dev --full --out artifacts/dev`
- Test eval 3: f59 confirmation (`artifacts/test` overwritten by eval 4)
- Test eval 4: f60 (`artifacts/test/t04.md`)

| metric | Dev before f59 | Dev official | Test eval 2 | Test eval 3 | Test eval 4 |
|---|---|---|---|---|---|
| Residual-zero | 129/239 | 159/239 | 425/800 | 501/800 | 521/800 |
| Member-identified | 148/239 | 148/239 | 501/800 | 501/800 | 501/800 |
| Verified-linked | 129/239 | 142/239 | 425/800 | 464/800 | 464/800 |
| Unique | 0 | 0 | 0 | 0 | 0 |
| Ambiguous | — | 236 | 779 | 779 | 779 |
| None found | — | 3 | 21 | 21 | 21 |
| Budget | 0 | 0 | 0 | 0 | 0 |
| Search coverage | 239/239 | 239/239 | 800/800 | 800/800 | 800/800 |
| Auto-clear | 0 | 0 | 0 | 0 | 0 |
| False clears | 0 | 0 | 0 | 0 | 0 |
| Wall ms | — | 10066 | 69776 | 69621 | 68299 |

Recovered after eval 3:
- f59 settlement-ops: 13/239 and 39/800 (class 5/18)
- Gate A subsets already residual-zero: 13/239 and 37/800

Recovered eval 4 (f60):
- 4/239 and 20/800 class-13 missing withholding ids reconstructed from the rate table

Not recovered (ceiling):
- Regime B, no settlement, fees posted on value_date: 56/239, 218/800. Including D puts stacks in pool; UNIQUE stays 0.
- Truth id deleted, no remaining declared: 11/239, 18/800
- Class 23 indistinguishable amounts: 5/239, 4/800
- Class 8 both sources dirty: 6/239, 20/800
- Class 11 missing refund (operational): 2/239, 2/800
