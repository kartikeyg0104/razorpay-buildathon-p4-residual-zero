# F46 bitemporal as-of

As-of view equals audit-chain replay at 20 sampled seqs (0..23 inclusive ends) after `run_split(dev, limit=24)`.
Assertion: `tests/test_bitemporal.py::test_as_of_equals_replay_at_twenty_seqs`.
The audit `seq` is the learned-at axis. Credit `value_date` remains when it happened; as-of does not invent a second store.
