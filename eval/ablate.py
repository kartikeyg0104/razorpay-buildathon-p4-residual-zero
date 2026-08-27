"""§9.6 ablations. Each returns (baseline A3 metrics note, ablated note) as markdown rows."""

from __future__ import annotations

from enum import Enum


class Ablation(str, Enum):
    NO_LLM_TIER = "NO_LLM_TIER"
    NO_UNIQUENESS = "NO_UNIQUENESS"
    NO_CROSS_WINDOW = "NO_CROSS_WINDOW"
    NO_PAISE_VERIFICATION = "NO_PAISE_VERIFICATION"
    GREEDY_INSTEAD_OF_DP = "GREEDY_INSTEAD_OF_DP"


def ablation_notes(a3_exact: str, a2_exact: str, a3_cleared: int) -> str:
    """Phase 1: Q2=C so NO_LLM_TIER is a structural no-op. Others are labelled from the same batch."""
    return "\n".join(
        [
            "# Ablations (dev)",
            "",
            "All ablations on the same dev batch. Δ is against A3.",
            "",
            "| ablation | what changed | A3 exact | ablated | note |",
            "|---|---|---|---|---|",
            f"| `{Ablation.NO_LLM_TIER.value}` | skip tier 4 | {a3_exact} | {a3_exact} | Q2=C: tier 4 was not exercised, so this ablation is a no-op |",
            f"| `{Ablation.NO_UNIQUENESS.value}` | treat AMBIGUOUS as clearable | {a3_exact} | n/a (not cleared: would violate §0.1) | not applied; uniqueness is the product |",
            f"| `{Ablation.NO_CROSS_WINDOW.value}` | base window only | {a3_exact} | not separately scored | widened kinds stay in the pool; cutting them is Phase-2 work |",
            f"| `{Ablation.NO_PAISE_VERIFICATION.value}` | trust rupee-axis residual | {a3_exact} | refused | NN-12: the verifier's acceptance never widens, including for an ablation |",
            f"| `{Ablation.GREEDY_INSTEAD_OF_DP.value}` | A2 greedy vs A3 | {a3_exact} | {a2_exact} | A2 is the greedy ablation |",
            "",
            f"A3 auto-cleared {a3_cleared} credits on this batch (threshold derived at CP6).",
            "",
        ]
    )
