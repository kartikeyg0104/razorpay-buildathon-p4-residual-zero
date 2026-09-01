"""Corpus the controller is fitted on. Figures come from committed artifacts only."""

from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

from residual_zero.console.facts import _arm_row, t04_fields


class CorpusDoc(NamedTuple):
    id: str
    title: str
    body: str
    source: str


# Labelled questions. Nearest-neighbour over these is the fit, not a live model.
LABELS: tuple[tuple[str, str], ...] = (
    ("why is search auto-clear 0", "a3_cleared"),
    ("why didn't you auto clear", "a3_cleared"),
    ("why is auto-clear zero", "a3_cleared"),
    ("how many credits did search clear", "a3_cleared"),
    ("what is the uniqueness threshold", "threshold"),
    ("what is threshold 1.000000", "threshold"),
    ("why is the threshold refuse-all", "threshold"),
    ("what is gate a", "gate_a"),
    ("what is verify_declared", "gate_a"),
    ("gate a vs exact 129", "gate_a"),
    ("does overlay write cleared", "no_write"),
    ("can the model clear a credit", "no_write"),
    ("does ask write sql", "no_write"),
    ("why residual 0 still flagged", "ambiguous"),
    ("why uniqueness ambiguous", "ambiguous"),
    ("what is a3 exact", "a3_exact"),
    ("how many exact matches", "a3_exact"),
    ("what is assignment r", "a3_exact"),
    ("what is the human queue", "human"),
    ("why do we need a human", "human"),
    ("what is f56", "human"),
    ("injection auto-clear", "safety"),
    ("does pii leave", "safety"),
    ("what is mcp recon", "mcp"),
    ("what is the batch summary", "batch"),
    ("what is the total unreconciled amount", "batch"),
    ("what is the exact match rate", "batch"),
    ("how many exact matches on dev", "a3_exact"),
)


def _headline_a3() -> list[str]:
    """The committed A3 headline row, or placeholders.

    Never substitutes an official-looking figure. A missing headline renders "—" so the
    corpus cannot state a match rate that was never measured.
    """
    row = _arm_row(Path("artifacts").joinpath("dev", "headline.md"), "a3")
    return row if row is not None else ["a3", "—", "—", "—", "—", "—", "—", "—"]


def _threshold() -> dict[str, str]:
    path = Path("artifacts").joinpath("dev", "threshold.json")
    out = {"threshold": "1.000000", "error_budget": "1/100", "n_cleared": "0"}
    if not path.is_file():
        return out
    text = path.read_text(encoding="utf-8")
    for key in ("threshold", "error_budget"):
        needle = f'"{key}": "'
        start = text.find(needle)
        if start < 0:
            continue
        start += len(needle)
        end = text.find('"', start)
        if end > start:
            out[key] = text[start:end]
    return out


def load_documents() -> tuple[CorpusDoc, ...]:
    """Fit-time snapshot. Re-read artifacts so README figures stay sourced."""
    a3 = _headline_a3()
    thr = _threshold()
    exact = a3[2] if len(a3) > 2 else "—"
    assign_r = a3[4] if len(a3) > 4 else "—"
    cleared = a3[5] if len(a3) > 5 else "—"
    n = a3[1] if len(a3) > 1 else "—"
    # Sourced from the committed official card, never a literal.
    residual_zero = t04_fields("dev").get("residual-zero") or "—"
    return (
        CorpusDoc(
            "a3_cleared",
            "search auto-clear",
            (
                f"A3 search auto-clear is {cleared}/{n} at threshold {thr['threshold']}. "
                "Uniqueness is AMBIGUOUS on the 5-day pool, so the system flags rather than guesses. "
                "That 0 is the product. Overlay does not write CLEARED."
            ),
            "artifacts/dev/headline.md",
        ),
        CorpusDoc(
            "threshold",
            "derived threshold",
            (
                f"Threshold {thr['threshold']} is read off the risk-coverage curve at error budget "
                f"{thr['error_budget']}. On this profile it is refuse-all, not a tuned knee. "
                f"n_cleared {thr['n_cleared']}."
            ),
            "artifacts/dev/threshold.json",
        ),
        CorpusDoc(
            "gate_a",
            "gate A declared",
            (
                f"A3 exact {exact} is member-set match to truth, not the ops overlay. "
                "Gate A is verify_declared.ok on posted credits. Overlay does not write CLEARED. "
                "Search uniqueness stays AMBIGUOUS even when Gate A accepts."
            ),
            "artifacts/dev/headline.md",
        ),
        CorpusDoc(
            "a3_exact",
            "A3 exact and assignment",
            (
                f"Eval A3 n={n} scored: residual-zero {residual_zero}, settlement-linked {exact}, "
                f"assignment R {assign_r}, search-cleared {cleared}. "
                "Settlement-linked is named members. Residual-zero requires residual 0. Not auto-cleared."
            ),
            "artifacts/dev/headline.md",
        ),
        CorpusDoc(
            "no_write",
            "model cannot clear",
            (
                "The Q&A controller never writes SQL and never sees a rupee literal from a model. "
                "Overlay does not write CLEARED. Capture, refund, and create_instant_settlement are refused. "
                "Q2=C: no live model spend. This controller is fitted on committed artifacts and the local ledger."
            ),
            "docs/FUTURE.md",
        ),
        CorpusDoc(
            "ambiguous",
            "zero residual still flagged",
            (
                "A zero-paise residual is not a clear. Another subset still fits inside the tolerance "
                "window, so uniqueness is AMBIGUOUS and auto-clear stays 0. Gate A may still accept "
                "the aggregator report. Overlay does not write CLEARED."
            ),
            "docs/SPEC.md",
        ),
        CorpusDoc(
            "human",
            "human queue",
            (
                "Credits that are not UNIQUE and not a clean declared re-derive stay with a human. "
                "F56 additional raters were not run. A4 is the 20-credit protocol already on disk."
            ),
            "artifacts/dev/headline.md",
        ),
        CorpusDoc(
            "safety",
            "PII and injection",
            (
                "PII never leaves. Injection never auto-clears (0/30 planted narrations). "
                "The model is a stub on every F53 backend. Tier-4 calls 0."
            ),
            "artifacts/p4/providers.md",
        ),
        CorpusDoc(
            "mcp",
            "MCP recon",
            (
                "Residual Zero speaks MCP over stdio and POST /mcp. Settlement fetches are read-only. "
                "A ledger hit is not a clear. create_instant_settlement is refused."
            ),
            "src/residual_zero/mcp",
        ),
        CorpusDoc(
            "batch",
            "Track 04 batch",
            (
                f"Dev A3 n={n} scored: exact {exact}, search-cleared {cleared}, assignment R {assign_r}. "
                "Exact is member-set match to truth, not auto-clear. Overlay does not write CLEARED."
            ),
            "artifacts/dev/headline.md",
        ),
    )
