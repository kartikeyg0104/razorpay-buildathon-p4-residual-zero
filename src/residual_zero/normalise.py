"""Deterministic narration normalisation. Baselines depend on this being a pure function (§5.4)."""

from __future__ import annotations

import re
import unicodedata

from residual_zero.models import LedgerItem, expected_sign

# Whole-token expansions. Applied after casefold, so keys are lowercase.
_ABBREVIATIONS: dict[str, str] = {
    "pvt": "private",
    "ltd": "limited",
    "corp": "corporation",
    "co": "company",
    "intl": "international",
    "mfg": "manufacturing",
}

_RAIL_PREFIXES: tuple[str, ...] = (
    "neft-",
    "neft/",
    "imps-",
    "imps/",
    "upi-",
    "upi/",
    "rtgs-",
    "rtgs/",
    "neft ",
    "imps ",
    "upi ",
    "rtgs ",
)

_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
_WS_RE = re.compile(r"\s+")
_REF_RE = re.compile(r"\b(UTR[A-Z0-9]{8,24}|[A-Z]{4}\d{11,16})\b", re.IGNORECASE)


def normalise_narration(raw: str) -> str:
    """NFKC, case fold, rail-prefix strip, punctuation strip, whitespace collapse, abbrev expand.

    Deterministic and idempotent: ``normalise_narration(normalise_narration(s))`` equals
    ``normalise_narration(s)``. The A0/A1 baselines and semantic tiers 1–3 all read this field,
    so a change here is a change to every measured number.
    """
    text = unicodedata.normalize("NFKC", raw).casefold()
    text = _WS_RE.sub(" ", text).strip()
    for prefix in _RAIL_PREFIXES:
        if text.startswith(prefix):
            text = text[len(prefix) :]
            break
    text = _PUNCT_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text).strip()
    tokens = [_ABBREVIATIONS.get(tok, tok) for tok in text.split()]
    return " ".join(tokens)


def extract_reference_token(raw: str) -> str | None:
    """Pull a UTR or reference token into its own field, or None if there isn't one."""
    match = _REF_RE.search(raw)
    if match is None:
        return None
    return match.group(1).upper()


def sign_anomaly(item: LedgerItem) -> bool:
    """Derived class-18 signal: the item's sign contradicts ``expected_sign(kind)``.

    ADJUSTMENT is allowed either sign, so it is never an anomaly on sign alone.
    """
    wanted = expected_sign(item.kind)
    if wanted == 0:
        return False
    return (item.amount_paise > 0) != (wanted > 0)


def parse_rupee_display(text: str) -> int:
    """Parse a rendered rupee string to signed integer paise. No floats.

    Accepts Indian grouping (``5,01,200.00``), a leading sign, and a two-digit fractional part.
    A malformed string raises ``ValueError`` naming the input; callers wrap that into an ingest
    error that names the line.
    """
    raw = text.strip().replace(",", "").replace(" ", "")
    if not raw:
        raise ValueError("empty amount")
    sign = 1
    if raw[0] == "-":
        sign = -1
        raw = raw[1:]
    elif raw[0] == "+":
        raw = raw[1:]
    if "." in raw:
        whole, frac = raw.split(".", 1)
        if not whole.isdigit() or not frac.isdigit() or len(frac) != 2:
            raise ValueError(f"amount is not a rupee display: {text!r}")
        return sign * (int(whole) * 100 + int(frac))
    if not raw.isdigit():
        raise ValueError(f"amount is not a rupee display: {text!r}")
    return sign * int(raw) * 100
