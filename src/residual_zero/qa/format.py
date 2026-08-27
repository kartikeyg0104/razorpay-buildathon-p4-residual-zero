"""Every figure in a Q&A answer is rendered here from typed rows."""

from __future__ import annotations

from typing import Mapping

from residual_zero.money import format_rupees
from residual_zero.qa.retrieve import Intent, RetrievedRows


def render_slots(rows: RetrievedRows) -> dict[str, str]:
    slots: dict[str, str] = {"INTENT": rows.intent.value}
    if not rows.rows:
        slots["CITATIONS"] = "(none)"
        return slots
    rec = rows.rows[0]
    if "claimed_total_paise" in rec and isinstance(rec["claimed_total_paise"], int):
        slots["TOTAL"] = format_rupees(rec["claimed_total_paise"])
    if "residual_paise" in rec and isinstance(rec["residual_paise"], int):
        slots["RESIDUAL"] = format_rupees(rec["residual_paise"])
    if "disposition" in rec:
        slots["DISPOSITION"] = str(rec["disposition"])
    if "uniqueness" in rec:
        slots["UNIQUENESS"] = str(rec["uniqueness"])
    slots["CITATIONS"] = ", ".join(rows.citations) if rows.citations else "(none)"
    return slots


def deterministic_answer(rows: RetrievedRows, slots: Mapping[str, str]) -> str:
    if rows.intent == Intent.UNRECOGNISED or not rows.rows:
        return "I cannot answer that from the reconciled ledger. Citations: {CITATIONS}.".format(**{**{"CITATIONS": "(none)"}, **slots})
    return (
        "Credit {CITATIONS}: disposition {DISPOSITION}, uniqueness {UNIQUENESS}, "
        "computed total {TOTAL}, residual {RESIDUAL}."
    ).format(**{k: slots.get(k, "?") for k in ("CITATIONS", "DISPOSITION", "UNIQUENESS", "TOTAL", "RESIDUAL")})
