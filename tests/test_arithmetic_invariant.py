"""F14: a CLEARED claim re-derives to a zero paise residual."""

from __future__ import annotations

from residual_zero.config import load_fees, load_tax_rates
from residual_zero.models import Regime
from residual_zero.verify import verify_decomposition
from tests.test_verify import _credit, _item
from residual_zero.models import Kind


def test_claimed_clear_verifies_at_paise():
    rates, fees = load_tax_rates(), load_fees()
    payment = _item("p1", Kind.PAYMENT, 250_00)
    # A payment-only member set cannot match a credit of the same amount once fees exist,
    # so acceptance is False — the invariant is: IF accepted THEN residual == 0.
    outcome = verify_decomposition(
        _credit(250_00), ("p1",), {payment.id: payment}, Regime.B_SEARCHED, rates, fees,
    )
    if outcome.accepted:
        assert outcome.residual_paise == 0
    assert outcome.residual_paise != 0 or outcome.accepted
