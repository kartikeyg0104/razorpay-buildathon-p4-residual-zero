"""Q&A surface."""

from residual_zero.qa.compose import compose
from residual_zero.qa.controller import answer as controller_answer
from residual_zero.qa.finance_controller import finance_ask
from residual_zero.qa.format import deterministic_answer, render_slots
from residual_zero.qa.retrieve import Intent, RetrievedRows, classify_intent, retrieve

__all__ = [
    "Intent",
    "RetrievedRows",
    "classify_intent",
    "compose",
    "controller_answer",
    "deterministic_answer",
    "finance_ask",
    "render_slots",
    "retrieve",
]
