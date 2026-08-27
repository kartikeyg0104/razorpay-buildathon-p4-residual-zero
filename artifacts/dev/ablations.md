# Ablations (dev)

All ablations on the same dev batch. Δ is against A3.

| ablation | what changed | A3 exact | ablated | note |
|---|---|---|---|---|
| `NO_LLM_TIER` | skip tier 4 | 129/239 | 129/239 | Q2=C: tier 4 was not exercised, so this ablation is a no-op |
| `NO_UNIQUENESS` | treat AMBIGUOUS as clearable | 129/239 | n/a (not cleared: would violate §0.1) | not applied; uniqueness is the product |
| `NO_CROSS_WINDOW` | base window only | 129/239 | not separately scored | widened kinds stay in the pool; cutting them is Phase-2 work |
| `NO_PAISE_VERIFICATION` | trust rupee-axis residual | 129/239 | refused | NN-12: the verifier's acceptance never widens, including for an ablation |
| `GREEDY_INSTEAD_OF_DP` | A2 greedy vs A3 | 129/239 | 0/239 | A2 is the greedy ablation |

A3 auto-cleared 0 credits on this batch (threshold derived at CP6).
