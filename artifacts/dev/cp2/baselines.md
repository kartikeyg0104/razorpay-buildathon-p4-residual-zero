# CP2 baselines (dev)

A0 and A1 measured **before** the solver exists (NN-13).

## A0 exact match
- assignment precision: — (n=0)
- assignment recall: 0/5973 (0.0000)
- exact decomposition: 0/239 (0.0000)
- exception path: — (none)
- budget path: — (none)

## A1 fuzzy 1:1 (optimal assignment)
- chosen sim_threshold: 50
- chosen amount_tol_paise: 100
- assignment precision: — (n=0)
- assignment recall: 0/5973 (0.0000)
- exact decomposition: 0/239 (0.0000)
- exception path: — (none)
- budget path: — (none)

A1's similarity threshold and amount tolerance were swept on the dev split and fixed at the
values that maximised A1's own exact-decomposition rate.

