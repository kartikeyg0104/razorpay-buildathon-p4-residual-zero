"""Shared malformed-input guards for CSV adapters (F48)."""

from __future__ import annotations

from residual_zero.ingest import IngestError


def reject_malformed_text(text: str, *, path: str) -> None:
    if text.startswith("\ufeff"):
        raise IngestError("byte-order mark", path=path, line=1)
    has_crlf = "\r\n" in text
    has_lf = "\n" in text.replace("\r\n", "")
    has_cr = "\r" in text.replace("\r\n", "")
    if sum(bool(x) for x in (has_crlf, has_lf, has_cr)) > 1:
        raise IngestError("mixed line endings", path=path, line=1)
    lines = text.splitlines()
    if len(lines) >= 2 and lines[0] == lines[1] and "," in lines[0]:
        raise IngestError("duplicated header row", path=path, line=2)
