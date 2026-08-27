"""Ingest adapters. Each one produces canonical models and nothing else."""

from __future__ import annotations

from .source_root import SourceRoot, SourceRootError

__all__ = ["SourceRoot", "SourceRootError", "IngestError"]


class IngestError(ValueError):
    """A typed ingestion failure that names the offending file and line.

    A partial load is forbidden (spec §5.4, PLAN-P1 CP1). Callers must not catch this and
    continue; the adapter raises before returning any rows.
    """

    def __init__(self, message: str, *, path: str | None = None, line: int | None = None) -> None:
        self.path = path
        self.line = line
        where = []
        if path is not None:
            where.append(path)
        if line is not None:
            where.append(f"line {line}")
        prefix = ":".join(where)
        super().__init__(f"{prefix}: {message}" if prefix else message)
