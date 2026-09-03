# Solver benchmark

Development-only comparison of Residual Zero `solve_search` against an independent brute-force enumerator.

- Production solver was **not** replaced.
- Determinism repeat (same pool twice): `True`.
- Independent `dpss` / europeanplaice subset_sum was **not installed**; brute force is the independent check.

| case | n | uniqueness | prod solutions | independent solutions | runtime ns | same class |
|---|---:|---|---:|---:|---:|---|
| single_exact | 3 | UNIQUE | 1 | 1 | 123167 | True |
| multiple_solutions | 2 | AMBIGUOUS | 2 | 2 | 96833 | True |
| no_solution | 3 | NONE_FOUND | 0 | 0 | 20916 | True |
| duplicate_values | 3 | AMBIGUOUS | 2 | 3 | 91000 | True |
| negative_values | 3 | UNIQUE | 1 | 1 | 86959 | True |
| mixed_signs | 3 | UNIQUE | 1 | 1 | 346000 | True |
| zero_values | 3 | NONE_FOUND | 0 | 2 | 43875 | False |
| large_pool_20 | 20 | UNIQUE | 1 | 1 | 144584 | True |
| pool_400 | 400 | NONE_FOUND | 0 | skipped | 749333 | n/a |

400-candidate pool skips independent enumeration (`2^400` is not a measurement).
Zero-value pools may return `BUDGET_EXCEEDED` in production because empty/zero amounts are refused by search.

