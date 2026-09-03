"""Reject LLM prose that invents financial facts. Templates always pass."""

from __future__ import annotations

import json
import re
from typing import Any, Mapping

from residual_zero.semantic.schema import MONEY_PATTERN

CREDIT_RE = re.compile(r"crd_[a-zA-Z0-9_]+")
RATIO_RE = re.compile(r"\b\d+/\d+\b")
INT_CLAIM_RE = re.compile(
    r"(\d+)\s+(?:transactions?\s+are\s+)?(?:ambiguous|auto-cleared|false clears?)",
    re.I,
)


def _blob(evidence: Mapping[str, Any]) -> str:
    return json.dumps(evidence, default=str)


def _unsafe_clear_claim(text: str) -> bool:
    if "does not write CLEARED" in text:
        lowered = text.replace("does not write CLEARED", "")
        return "CLEARED" in lowered and "not CLEARED" not in lowered
    return " is CLEARED" in text or "was CLEARED" in text or "credit is CLEARED" in text


# --------------------------------------------------------------- state-aware gate
# A transaction that the engine did not resolve must never be described as resolved.
# The previous rules only forbade a few literal uppercase tokens (CLEARED / UNIQUE /
# VERIFIED), so prose like "the reconciliation engine found a match" passed.

UNRESOLVED_UNIQUENESS = frozenset({"AMBIGUOUS", "NONE_FOUND", "BUDGET_EXCEEDED"})
UNRESOLVED_STATUS = frozenset(
    {"REVIEW_REQUIRED", "FLAGGED", "UNMATCHED", "POTENTIALLY_RECOVERABLE", "BUDGET_EXCEEDED"}
)

# Claims that assert the transaction as a whole was resolved, matched or picked.
_RESOLVED_CLAIMS: tuple[tuple[str, str], ...] = (
    (r"\bfound\s+(?:a|the|one)\s+(?:unique\s+|single\s+|exact\s+)?match\b", "match found"),
    (r"\b(?:a|the)\s+match\s+(?:was|has been|is)\s+found\b", "match found"),
    (r"\b(?:is|was|has been)\s+(?:now\s+)?(?:fully\s+|successfully\s+)?matched\b", "matched"),
    (r"\b(?:is|was|has been)\s+(?:now\s+)?(?:fully\s+|successfully\s+)?reconciled\b", "reconciled"),
    (r"\bhas been\s+(?:cleared|verified)\b", "cleared or verified"),
    (r"\bsuccessfully\s+(?:matched|reconciled|cleared|verified)\b", "resolved"),
    (r"\bmatch(?:es|ed)?\s+(?:the\s+)?(?:ledger|settlement)\s+records?\s+exactly\b", "matched"),
    (r"\buniqueness\s+is\s+UNIQUE\b", "unique"),
    (r"\b(?:is|was)\s+(?:a\s+)?unique\s+(?:match|explanation|solution)\b", "unique"),
    (r"\bunique\s+(?:match|explanation|solution)\s+(?:was\s+|has been\s+)?(?:found|established)\b", "unique"),
    (r"\bcandidate\s+[A-Z0-9]\s+(?:is|was)\s+(?:the\s+)?(?:correct|right|winner)\b", "candidate picked"),
    (r"\bthe\s+correct\s+(?:candidate|solution|subset)\s+is\b", "candidate picked"),
    # "the transaction reconciles" / "is resolved" / "is settled" / "is fully explained".
    # Present tense and the resolved/settled vocabulary were both uncovered, so
    # "residual is 0 so the transaction reconciles and is resolved" passed (found 2026-09).
    (r"\b(?:is|was|are|were|has been|have been)\s+(?:now\s+)?(?:fully\s+)?(?:resolved|settled)\b", "resolved"),
    (r"\b(?:is|was|has been)\s+fully\s+explained\b", "resolved"),
    (r"\b(?:transaction|credit|payout|payment|settlement)\s+(?:\w+\s+){0,2}reconciles\b", "reconciled"),
)

# Claims that no deterministic template would ever make, and that no amount of nearby
# hedging can make acceptable. These bypass the _QUALIFIER window on purpose: prose like
# "Ignore the ambiguity: the payout is settled" was ACCEPTED precisely because the word
# "ambiguity" sat inside the qualifier window and suppressed the rejection (found 2026-09).
# Selecting a candidate is an authority the model does not have at any confidence.
_SELECTION_NOUN = r"(?:candidate|solution|subset|combination|explanation|option|set|match|pairing)"
_OVERRIDE_CLAIMS: tuple[tuple[str, str], ...] = (
    (
        r"\bignor(?:e|es|ing)\s+(?:the\s+)?(?:ambiguity|ambiguous\w*|alternatives?|"
        r"other\s+(?:candidates?|explanations?|solutions?))\b",
        "instructed to disregard ambiguity",
    ),
    (
        r"\b(?:we|i|the\s+(?:ai|system|engine|model|controller))\s+"
        # an auxiliary may sit between the subject and the verb: "I have selected"
        r"(?:(?:have|has|had|will|can|could|would|already|just)\s+){0,2}"
        r"(?:pick|picks|picked|chose|choose|chooses|select|selects|selected|recommend|recommends)\b"
        r"[^.]{0,40}?" + _SELECTION_NOUN + r"\b",
        "candidate picked",
    ),
    (
        r"\b(?:the\s+)?(?:first|second|best|most\s+likely|likeliest)\s+" + _SELECTION_NOUN +
        r"\b[^.]{0,30}?\b(?:is|was|looks|seems|appears)\b[^.]{0,20}?"
        r"\b(?:correct|right|winner|winning|best|obvious)\b",
        "candidate picked",
    ),
    (
        r"\buse\s+(?:your|my|its)\s+(?:best\s+)?judg(?:e)?ment\b",
        "judgement substituted for arithmetic",
    ),
)

# Wording that legitimately describes the arithmetic rather than the outcome. The spec
# explicitly allows "the amount matches" alongside a statement of ambiguity.
_ARITHMETIC_SUBJECT = re.compile(
    r"\b(?:amount|amounts|total|totals|sum|sums|equation|equations|arithmetic|residual|figure|figures|arithmetic arithmetic)\b",
    re.I,
)
# Nearby wording that shows the claim is being denied or qualified.
_QUALIFIER = re.compile(
    r"\b(?:not|no|never|cannot|can't|without|unless|multiple|more than one|two|several|"
    r"ambiguous|ambiguity|competing|alternative|review|refus\w*|pending|candidate\s+sets?)\b",
    re.I,
)


def _state_of(evidence: Mapping[str, Any]) -> tuple[str, str]:
    recon = evidence.get("reconciliation")
    if not isinstance(recon, dict):
        return "", ""
    uniq = str(recon.get("uniqueness") or "").strip().upper()
    status = str(recon.get("status") or recon.get("disposition") or "").strip().upper()
    return uniq, status


def _is_unresolved(evidence: Mapping[str, Any], intent: str = "") -> bool:
    uniq, status = _state_of(evidence)
    if str(intent or "").strip().upper().endswith("REFUSE_CLEAR"):
        return True
    if uniq and uniq in UNRESOLVED_UNIQUENESS:
        return True
    if status and status in UNRESOLVED_STATUS:
        return True
    return False


def _override_claim(text: str) -> str:
    """Name of the first claim that usurps the engine's authority, qualifiers notwithstanding."""
    for pattern, label in _OVERRIDE_CLAIMS:
        if re.search(pattern, text, re.I):
            return label
    return ""


def _resolved_claim(text: str) -> str:
    """Name of the first resolution claim that is neither negated nor about arithmetic."""
    for pattern, label in _RESOLVED_CLAIMS:
        for match in re.finditer(pattern, text, re.I):
            start = max(0, match.start() - 90)
            window = text[start : match.end() + 90]
            if _QUALIFIER.search(window):
                continue
            lead = text[max(0, match.start() - 40) : match.start()]
            if _ARITHMETIC_SUBJECT.search(lead):
                continue
            return label
    return ""


def validate_answer(
    text: str,
    evidence: Mapping[str, Any],
    question: str = "",
    intent: str = "",
) -> tuple[bool, str]:
    """True when every checkable claim is present in tool evidence.

    State-aware: when the deterministic engine has not resolved the transaction
    (AMBIGUOUS / NONE_FOUND / BUDGET_EXCEEDED, a review-required status, or a
    REFUSE_CLEAR intent), prose that asserts a match, a reconciliation, uniqueness,
    verification or a chosen candidate is rejected. Describing the arithmetic as
    matching is still allowed when ambiguity is stated alongside it.
    """
    if not text.strip():
        return False, "empty"
    if _unsafe_clear_claim(text):
        return False, "cleared claim"
    blob = _blob(evidence)
    hay = blob + "\n" + question
    for match in MONEY_PATTERN.finditer(text):
        token = match.group(0)
        # MONEY_PATTERN is deliberately greedy because it also guards NN-3 egress, where
        # over-matching is the safe direction. Here it is the wrong direction: it reads
        # "1.00" out of the ordering-score threshold "1.000000" and calls it an invented
        # amount. A match with more digits straight after it is a score or a ratio, not
        # money (found 2026-09).
        if match.end() < len(text) and text[match.end()].isdigit():
            continue
        if token not in hay and token.replace("₹", "") not in hay:
            return False, "invented amount"
    for match in RATIO_RE.finditer(text):
        token = match.group(0)
        if token not in hay:
            return False, "invented ratio"
    for match in CREDIT_RE.finditer(text):
        token = match.group(0)
        if token not in hay:
            return False, "invented id"
    stats = evidence.get("stats") if isinstance(evidence.get("stats"), dict) else evidence
    if isinstance(stats, dict):
        claimed = INT_CLAIM_RE.findall(text)
        ambiguous = stats.get("ambiguous")
        auto_clear = stats.get("auto_clear")
        false_clears = stats.get("false_clears")
        folded = text.casefold()
        if "ambiguous" in folded and ambiguous is not None:
            for raw in claimed:
                if raw.isdigit() and "ambiguous" in folded:
                    if int(raw) != int(ambiguous) and f"{raw}/" not in blob:
                        # allow mentioning solution_count 2 on a single credit
                        if int(raw) in {int(ambiguous), int(stats.get("none_found") or -1)}:
                            continue
                        recon = evidence.get("reconciliation") if isinstance(evidence.get("reconciliation"), dict) else {}
                        if int(raw) == int(recon.get("solution_count") or -1):
                            continue
                        if int(raw) == int(recon.get("matched_count") or -1):
                            continue
                        if str(ambiguous) in text or str(ambiguous) in blob:
                            if int(raw) != int(ambiguous):
                                return False, "invented count"
        if auto_clear is not None and "auto-clear" in folded:
            if re.search(r"auto-cleared (?!0)\d+", folded):
                return False, "invented auto-clear"
        if false_clears is not None and "false clear" in folded:
            if re.search(r"false clears?: (?!0)\d+", folded):
                return False, "invented false clears"
    recon = evidence.get("reconciliation") if isinstance(evidence.get("reconciliation"), dict) else {}
    if recon.get("uniqueness") != "UNIQUE" and "uniqueness is UNIQUE" in text:
        return False, "invented uniqueness"
    if recon.get("uniqueness") != "UNIQUE" and re.search(r"\bis VERIFIED\b", text) and "not VERIFIED" not in text:
        return False, "invented verified"
    if recon.get("residual_paise") not in (0, None) and "residual of ₹0.00" in text:
        return False, "invented residual"
    sc = recon.get("solution_count")
    if sc is not None:
        for match in re.finditer(r"solution count(?: of)? (\d+)", text, re.I):
            if int(match.group(1)) != int(sc):
                return False, "invented count"
    if recon.get("auto_cleared") is False and re.search(r"\bwas cleared\b", text.casefold()):
        if "was not cleared" not in text.casefold() and "wasn't cleared" not in text.casefold():
            return False, "invented clear"
    # Last: the broad state gate. It runs after the specific rules above so their more
    # precise reason strings win, and it only catches contradictions they do not name.
    override = _override_claim(text)
    if override:
        # Not state-conditional: the model may never claim this authority, on any
        # transaction, however the surrounding sentence is hedged.
        return False, f"authority claim: {override}"
    if _is_unresolved(evidence, intent):
        claim = _resolved_claim(text)
        if claim:
            return False, f"state contradiction: {claim} claimed on an unresolved transaction"
    return True, ""
