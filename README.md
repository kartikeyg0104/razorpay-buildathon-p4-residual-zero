# Residual Zero

A bank settlement credit is a net aggregate, so reconciling it is signed subset-sum under
tolerance — not 1:1 fuzzy matching. Residual Zero decomposes each credit into the exact set
of payments, refunds, chargebacks, fees, GST, withholding, reserve holds and adjustments
that compose it, emits a proof that re-derives to a zero residual at paise granularity, and
refuses to auto-clear anything whose decomposition is not provably unique.

Headline numbers land at CP9 from `make eval`. Until then they are not invented.

See `docs/SPEC.md` for the design, `CLAUDE.md` for the non-negotiables, and `PLAN-P1.md` for
the Phase 1 checkpoint ladder.
