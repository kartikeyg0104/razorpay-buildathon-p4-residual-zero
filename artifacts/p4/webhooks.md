# F47 live webhooks

Four deliveries (normal, duplicated, reversed, replayed) produced byte-identical ledger state.
Assertion: `tests/test_webhooks.py::test_four_deliveries_identical_ledger_state`.
Adapter remains `enabled: false` in `config/razorpay.yaml`. Event store is a dedicated sqlite, not the reconciliation ledger.
