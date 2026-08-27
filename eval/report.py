"""Report assertions and rendering. Impossible tables cannot be published (§9.8)."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from residual_zero.models import Regime

from eval.metrics import NA, ArmMetrics, render_cell


class ReportAssertionError(RuntimeError):
    pass


def assert_dispositions_sum_to_one(m: ArmMetrics) -> None:
    """n_cleared + n_flagged + n_budget_exceeded == n_credits as an INTEGER identity."""
    if isinstance(m.n_flagged, NA) or isinstance(m.n_budget_exceeded, NA):
        return
    total = m.n_cleared + int(m.n_flagged) + int(m.n_budget_exceeded)
    if total != m.n_credits:
        raise ReportAssertionError(
            f"{m.arm} dispositions {total} != n_credits {m.n_credits}"
        )


def assert_exact_bounded_by_coverage(m: ArmMetrics) -> None:
    """For an arm with no exception path, n_exact <= n_cleared_correct."""
    if m.has_exception_path if hasattr(m, "has_exception_path") else m.arm == "a3":
        return
    if m.arm == "a3":
        return
    if m.arm in {"a0", "a1"} and m.n_exact > m.n_cleared_correct:
        raise ReportAssertionError(
            f"{m.arm} n_exact {m.n_exact} exceeds n_cleared_correct {m.n_cleared_correct}"
        )


def _is_a3(m: ArmMetrics) -> bool:
    return m.arm == "a3"


def assert_exact_bounded_by_coverage_strict(m: ArmMetrics, has_exception_path: bool) -> None:
    if has_exception_path or _is_a3(m):
        return
    if m.n_exact > m.n_cleared_correct:
        raise ReportAssertionError(
            f"{m.arm} n_exact {m.n_exact} exceeds n_cleared_correct {m.n_cleared_correct}"
        )


def render_headline(metrics: Sequence[ArmMetrics]) -> str:
    lines = [
        "# Headline",
        "",
        "| arm | n | exact | assignment P | assignment R | cleared | flagged | budget |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for m in metrics:
        lines.append(
            f"| {m.arm} | {m.n_credits} | {m.n_exact}/{m.n_credits} | "
            f"{render_cell(m.assignment_precision)} | {render_cell(m.assignment_recall)} | "
            f"{m.n_cleared} | {render_cell(m.n_flagged)} | {render_cell(m.n_budget_exceeded)} |"
        )
    lines.append("")
    return "\n".join(lines)


def render_report(
    metrics: Sequence[ArmMetrics],
    per_class: str,
    ablations: str,
    out: Path,
    has_exception: dict[str, bool],
) -> None:
    for m in metrics:
        assert_dispositions_sum_to_one(m)
        assert_exact_bounded_by_coverage_strict(m, has_exception.get(m.arm, False))
    out.mkdir(parents=True, exist_ok=True)
    out.joinpath("headline.md").write_text(render_headline(metrics), encoding="utf-8")
    out.joinpath("per_class.md").write_text(per_class, encoding="utf-8")
    out.joinpath("ablations.md").write_text(ablations, encoding="utf-8")
