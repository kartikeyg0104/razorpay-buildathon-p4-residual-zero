"""NN-12: verifier acceptance does not move when F32 widens or narrows search ε."""

from __future__ import annotations

from residual_zero.config import load_fees, load_solver_config, load_tax_rates
from residual_zero.features import FeatureFlags
from residual_zero.models import Kind, Regime
from residual_zero.solver.tolerance import apply_derived_epsilon
from residual_zero.verify import verify_decomposition

from tests.test_verify import _credit, _item


def test_one_paise_residual_is_rejected_before_and_after_f32():
    rates, fees = load_tax_rates(), load_fees()
    payment = _item("p1", Kind.PAYMENT, 100_00)
    ledger = {payment.id: payment}
    credit = _credit(100_00 + 1)
    off = apply_derived_epsilon(load_solver_config(), FeatureFlags.all_off())
    on = apply_derived_epsilon(load_solver_config(), FeatureFlags())
    assert off.search.epsilon_rupees == 7
    assert on.search.epsilon_rupees == 2
    a = verify_decomposition(credit, ("p1",), ledger, Regime.B_SEARCHED, rates, fees)
    b = verify_decomposition(credit, ("p1",), ledger, Regime.B_SEARCHED, rates, fees)
    assert a.accepted is False
    assert b.accepted is False
    assert a.residual_paise != 0
    assert verify_decomposition.__code__.co_varnames  # ε is not a parameter
    assert "epsilon" not in verify_decomposition.__code__.co_varnames
