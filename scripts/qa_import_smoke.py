"""Import every major subsystem. Exit 1 if any import fails."""

from __future__ import annotations

import importlib
import sys

MODULES = (
    "residual_zero.orchestrator",
    "residual_zero.solver.fastpath",
    "residual_zero.solver.enumerate",
    "residual_zero.candidates",
    "residual_zero.ingest.csv_bank",
    "residual_zero.ingest.csv_ledger",
    "residual_zero.ingest.settlement_report",
    "residual_zero.qa.finance_tools",
    "residual_zero.qa.finance_controller",
    "residual_zero.qa.agent_loop",
    "residual_zero.qa.evidence_extract",
    "residual_zero.qa.evidence_ops",
    "residual_zero.qa.investigate_tools",
    "residual_zero.semantic.provider",
    "residual_zero.console.app",
    "eval.cli",
    "eval.arms.a3_full",
    "eval.truth_loader",
    "eval.ai_recovery",
)


def main() -> int:
    failed: list[str] = []
    for name in MODULES:
        try:
            importlib.import_module(name)
            print("OK", name)
        except Exception as exc:
            failed.append(f"{name}: {exc}")
            print("FAIL", name, exc)
    print("imported", len(MODULES) - len(failed), "/", len(MODULES))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
