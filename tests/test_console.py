"""Console views, waterfall, least privilege."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from residual_zero.config import config_digest, load_fees, load_tax_rates
from residual_zero.console.app import audit, batch, credit_view, exceptions as exceptions_view
from residual_zero.console.waterfall import waterfall_svg
from residual_zero.models import BankCredit, PoolScope, ProofLine, ProofRecord, Regime, Uniqueness
from residual_zero.normalise import normalise_narration


def test_all_four_views_render():
    assert b"batch" in batch().body
    assert b"queue" in exceptions_view().body
    assert b"audit" in audit().body
    assert credit_view("crd_missing").status_code == 200


def test_waterfall_lines_sum_to_zero_residual():
    rates, fees = load_tax_rates(), load_fees()
    credit = BankCredit(
        id="c1", amount_paise=10000, value_date=date(2025, 1, 15),
        account_id="acc_00", currency="INR", narration_raw="NEFT",
        narration_norm=normalise_narration("NEFT"), utr="U",
    )
    proof = ProofRecord(
        bank_credit_id="c1",
        lines=(
            ProofLine(label="PAYMENT", detail="p1", amount_paise=10000, member_ids=("p1",), derived_from="LEDGER"),
        ),
        computed_total_paise=10000,
        residual_paise=0,
        regime=Regime.B_SEARCHED,
        uniqueness=Uniqueness.UNIQUE,
        alternate_count=1,
        pool_size=1,
        pool_scope=PoolScope.FULL,
        rate_config_digest=config_digest(rates, fees),
    )
    svg = waterfall_svg(proof, credit)
    assert 'data-residual="0"' in svg
    assert sum(line.amount_paise for line in proof.lines) + proof.residual_paise == credit.amount_paise


def test_console_cannot_write_ledger():
    src = Path("src/residual_zero/console/app.py").read_text(encoding="utf-8")
    assert "open_verify" not in src
    assert "write_cleared" not in src
    assert "open_exceptions" in src
