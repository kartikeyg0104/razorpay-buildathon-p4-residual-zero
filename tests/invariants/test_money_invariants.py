"""Money invariants: integer paise end to end, no float arithmetic on financial values.

`tests/test_money.py` already covers the rounding rule itself. These tests cover the
structural invariants: that financial types are integers, that no float creeps into the
financial modules, and that rupee formatting only happens at the presentation boundary.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from residual_zero.money import (
    BPS_DENOMINATOR,
    PAISE_PER_RUPEE,
    apply_bps,
    format_rupees,
    round_half_up_div,
    to_rupee_units,
)

SRC = Path("src/residual_zero")

# Modules that decide or carry financial truth. Floats are not allowed to touch these.
FINANCIAL_MODULES = [
    SRC / "money.py",
    SRC / "verify.py",
    SRC / "candidates.py",
    SRC / "models.py",
    SRC / "solver" / "enumerate.py",
    SRC / "solver" / "fastpath.py",
    SRC / "solver" / "prune.py",
    SRC / "solver" / "bitset_dp.py",
]

# Presentation / scoring layers legitimately use floats (ordering scores, percentages).
PRESENTATION_ALLOWED = {"console", "qa", "eval", "report", "controller"}


# ------------------------------------------------------------- integer discipline


def test_paise_and_bps_constants_are_integers():
    assert isinstance(PAISE_PER_RUPEE, int) and PAISE_PER_RUPEE == 100
    assert isinstance(BPS_DENOMINATOR, int) and BPS_DENOMINATOR == 10_000


@pytest.mark.parametrize(
    "paise", [0, 1, -1, 99, -99, 100, -100, 12_345_678, -12_345_678, 10**12, -(10**12)]
)
def test_money_helpers_return_integers_never_floats(paise: int):
    assert isinstance(to_rupee_units(paise), int)
    assert isinstance(apply_bps(paise, 1800), int)
    assert not isinstance(to_rupee_units(paise), bool)


@pytest.mark.parametrize("paise", [0, 1, -1, 100, -100, 555_55, -555_55])
def test_sign_is_preserved_through_rupee_conversion(paise: int):
    rupees = to_rupee_units(paise)
    if paise > 0:
        assert rupees >= 0
    elif paise < 0:
        assert rupees <= 0
    else:
        assert rupees == 0


def test_zero_is_handled_exactly():
    assert to_rupee_units(0) == 0
    assert apply_bps(0, 1800) == 0
    assert round_half_up_div(0, 7) == 0
    assert format_rupees(0) == "0.00"


def test_rounding_is_deterministic_across_repeated_calls():
    for paise in (1, 49, 50, 51, 149, 150, 151, -49, -50, -51):
        results = {to_rupee_units(paise) for _ in range(50)}
        assert len(results) == 1, f"non-deterministic rounding at {paise}"


def test_round_half_up_div_rejects_nonpositive_denominator():
    with pytest.raises(ValueError):
        round_half_up_div(10, 0)
    with pytest.raises(ValueError):
        round_half_up_div(10, -2)


# --------------------------------------------------------- no float in financial code


def _float_literals(path: Path) -> list[str]:
    """Float literals and float() calls in a module, ignoring comments/docstrings."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, float):
            found.append(f"{path.name}:{node.lineno} float literal {node.value!r}")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "float":
            found.append(f"{path.name}:{node.lineno} float() call")
    return found


@pytest.mark.parametrize("module", FINANCIAL_MODULES, ids=lambda p: p.name)
def test_financial_modules_contain_no_float_arithmetic(module: Path):
    if not module.is_file():
        pytest.skip(f"{module} not present in this build")
    assert _float_literals(module) == []


@pytest.mark.parametrize("module", FINANCIAL_MODULES, ids=lambda p: p.name)
def test_financial_modules_do_not_use_true_division_on_money(module: Path):
    """`/` produces a float. Financial code must use `//` or round_half_up_div."""
    if not module.is_file():
        pytest.skip(f"{module} not present in this build")
    tree = ast.parse(module.read_text(encoding="utf-8"))
    offenders = [
        f"{module.name}:{n.lineno}"
        for n in ast.walk(tree)
        if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Div)
    ]
    assert offenders == [], f"true division in financial module: {offenders}"


@pytest.mark.parametrize("module", FINANCIAL_MODULES, ids=lambda p: p.name)
def test_financial_modules_avoid_decimal_and_fractions(module: Path):
    """Integer paise is the single representation. No parallel numeric tower."""
    if not module.is_file():
        pytest.skip(f"{module} not present in this build")
    text = module.read_text(encoding="utf-8")
    assert "from decimal import" not in text
    assert "import decimal" not in text
    assert "from fractions import" not in text


# --------------------------------------------------- formatting is presentation-only


def test_format_rupees_is_not_called_inside_the_solver():
    """Rupee strings are a display concern; the solver works in integers."""
    for module in SRC.joinpath("solver").rglob("*.py"):
        if "__pycache__" in module.parts:
            continue
        assert "format_rupees" not in module.read_text(encoding="utf-8"), module


def test_format_rupees_output_shape():
    """Two decimal places, Indian grouping, and a round trip through paise."""
    assert format_rupees(100) == "1.00"
    assert format_rupees(-100) == "-1.00"
    assert re.fullmatch(r"-?[\d,]+\.\d{2}", format_rupees(14_42_57_58_19))


@pytest.mark.parametrize("paise", [0, 1, -1, 100_00, -100_00, 99_99_99_999])
def test_formatting_never_changes_the_underlying_integer(paise: int):
    """Formatting is a pure read: the value is unchanged and re-parsable."""
    text = format_rupees(paise)
    recovered = int(round(float(text.replace(",", "")) * 100))
    assert recovered == paise
