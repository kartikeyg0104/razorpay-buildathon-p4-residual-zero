"""Q&A surface."""

from residual_zero.qa.compose import compose
from residual_zero.qa.format import deterministic_answer, render_slots
from residual_zero.qa.retrieve import Intent, RetrievedRows, classify_intent, retrieve

__all__ = [
    "Intent",
    "RetrievedRows",
    "classify_intent",
    "compose",
    "deterministic_answer",
    "render_slots",
    "retrieve",
]
