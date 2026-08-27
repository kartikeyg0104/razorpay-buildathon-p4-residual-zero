# FUTURE.md

Written at freeze, after `v4`. These are things we wanted to build and did not. They are
not half-done in the tree.

- **Live models (F53 remainder).** Q2=C: no Ollama, no hosted API. The swap boundary exists
  (`config/providers.yaml`, cache partitioned by `model_id`). All three backends are the
  same stub. A later run with real weights would fill tier-4 accuracy; it would not change
  the architecture.
- **F56 additional raters.** No second and third human. A4 remains the 20-credit protocol
  already on disk.
- **Process-level parallelism.** F34 is byte-identical on threads. The GIL means 8 workers
  did not beat 1 on the Python DP. A process pool is a new pickle/reduction surface, not a
  weekend patch.
- **Regenerating `data/dev` with classes 24–26.** Detectors were measured on dedicated
  plans so the Phase 1 answer key stayed frozen. Putting those classes on the headline
  corpus is a new eval, not a config flag.
- **Full FX reconciliation.** Class 26 is residue only. Multi-currency matching stays out
  of scope (§1.3).
- **A non-zero auto-clear operating point.** Threshold `1.000000` is honest for this
  profile. Moving it requires a corpus on which UNIQUE+FULL+zero-residual credits exist
  without guessing. That is data, not a slider.

No feature work in the reserved days.
