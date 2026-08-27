"""F49 PII detectors and per-run redaction. Enforced-and-raises, never warn-and-send."""

from __future__ import annotations

import re

from residual_zero.semantic.schema import CandidateEntity, EntityResolutionRequest

_VPA = re.compile(
    r"(?i)\b[\w.\-]{2,}@(?:okaxis|okhdfcbank|oksbi|paytm|ybl|upi|ibl|axl|"
    r"okicici|okyesbank|apl|waaxis|[a-z0-9.\-]{2,64})\b"
)
_CARD_PAN = re.compile(r"\b(?:\d{4}[\s\-*]?){3}\d{1,4}\b")
_CARD_MASK = re.compile(r"(?i)\b(?:x{2,}|xx+)[\s\-]*\d{4}\b")
_PHONE = re.compile(r"(?:\+91[\s\-]?)?[6-9]\d{9}\b")
_ACCT = re.compile(r"(?i)\b(?:a/?c|acct|account|acc)[^\d]{0,8}\d{4,}\b")

DETECTORS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("vpa", _VPA),
    ("card", _CARD_PAN),
    ("card_mask", _CARD_MASK),
    ("phone", _PHONE),
    ("acct_tail", _ACCT),
)


class PiiLeakError(RuntimeError):
    """Raised when a detector hits an outbound model payload. F49 as a mechanism."""


def find_pii(text: str) -> tuple[tuple[str, str], ...]:
    """Return (detector_name, matched_span) hits. Ordered by span start, then name."""
    hits: list[tuple[int, str, str]] = []
    for name, pattern in DETECTORS:
        for match in pattern.finditer(text):
            hits.append((match.start(), name, match.group(0)))
    hits.sort(key=lambda row: (row[0], row[1]))
    return tuple((name, span) for _start, name, span in hits)


def assert_no_pii(payload: bytes) -> None:
    """Scan outbound bytes. Raise on the first detector hit."""
    text = payload.decode("utf-8", errors="replace")
    hits = find_pii(text)
    if hits:
        name, span = hits[0]
        raise PiiLeakError(f"outbound payload contains {name} PII ({span!r})")


class RedactionSession:
    """In-memory, per-run pseudonyms. Never written to disk."""

    def __init__(self) -> None:
        self._fwd: dict[tuple[str, str], str] = {}
        self._rev: dict[str, str] = {}
        self._counts: dict[str, int] = {}

    def _token(self, kind: str, raw: str) -> str:
        key = (kind, raw)
        existing = self._fwd.get(key)
        if existing is not None:
            return existing
        n = self._counts.get(kind, 0) + 1
        self._counts[kind] = n
        token = f"[{kind}_{n:03d}]"
        self._fwd[key] = token
        self._rev[token] = raw
        return token

    def redact(self, text: str) -> str:
        if not text:
            return text
        # Longer spans first so a PAN is not partially eaten by a phone-like tail.
        hits = find_pii(text)
        if not hits:
            return text
        # Apply left-to-right on non-overlapping spans by re-scanning after each replace of the
        # leftmost remaining hit on the current string.
        out = text
        guard = 0
        while guard < 64:
            guard += 1
            found = find_pii(out)
            if not found:
                break
            name, span = found[0]
            token = self._token(name, span)
            out = out.replace(span, token, 1)
        return out

    def deredact(self, text: str) -> str:
        out = text
        for token, raw in self._rev.items():
            out = out.replace(token, raw)
        return out


def redact_entity_request(
    request: EntityResolutionRequest, session: RedactionSession
) -> EntityResolutionRequest:
    """Redact narration and display names. Candidate ids are closed-set keys and stay."""
    candidates = tuple(
        CandidateEntity(id=c.id, display_name=session.redact(c.display_name))
        for c in request.candidates
    )
    return EntityResolutionRequest(
        narration_norm=session.redact(request.narration_norm),
        counterparty_text=session.redact(request.counterparty_text),
        candidates=candidates,
    )
