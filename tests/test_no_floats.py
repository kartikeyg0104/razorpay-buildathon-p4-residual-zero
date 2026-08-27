"""NN-1 as a mechanism: no float arithmetic on the money paths.

An AST scan over every module the pipeline and the generator own. Float rupees cost a day of
phantom residuals, and this is the cheapest correctness decision available (ADR-5) — so it is
enforced by a test rather than by remembering.

The allow-list is explicit and short, which means adding to it is a visible diff in review.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SCANNED_ROOTS = [Path("src/residual_zero"), Path("generator")]

ALLOW_TRUE_DIVISION = {
    # ordering_score is a weighted geometric mean over normalised observables. It is not a
    # monetary value, and it is rendered to a fixed six-decimal string before any comparison or
    # serialisation (PLAN-P1 D1.3, D14). Arrives at CP5.
    "src/residual_zero/ordering.py",
}

ALLOW_FLOAT_LITERALS = {
    # Same reason: the six ordering_score term weights and normalisers.
    "src/residual_zero/ordering.py",
}


def _modules() -> list[Path]:
    found: list[Path] = []
    for root in SCANNED_ROOTS:
        if root.exists():
            found.extend(sorted(root.rglob("*.py")))
    return found


def test_there_is_something_to_scan():
    """A scan over zero files would pass vacuously and prove nothing."""
    assert _modules(), "no modules found to scan; the NN-1 guard is not testing anything"


@pytest.mark.parametrize("module", _modules(), ids=lambda p: str(p))
def test_no_float_arithmetic_on_money_paths(module: Path):
    """No float literal, no float() call, and no true division outside the allow-list."""
    rel = module.as_posix()
    tree = ast.parse(module.read_text(encoding="utf-8"), filename=rel)
    problems: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, float):
            if rel not in ALLOW_FLOAT_LITERALS:
                problems.append(f"line {node.lineno}: float literal {node.value!r}")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "float":
            problems.append(f"line {node.lineno}: float() call")
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            if rel not in ALLOW_TRUE_DIVISION:
                problems.append(
                    f"line {node.lineno}: true division '/' — use // via money.round_half_up_div"
                )
        elif isinstance(node, ast.AugAssign) and isinstance(node.op, ast.Div):
            if rel not in ALLOW_TRUE_DIVISION:
                problems.append(f"line {node.lineno}: augmented true division '/='")

    assert not problems, f"{rel} violates NN-1:\n  " + "\n  ".join(problems)
