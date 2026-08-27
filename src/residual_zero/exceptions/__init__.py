"""Exception-queue owner of the db privilege map. Classification arrives at CP5."""

from __future__ import annotations

from pathlib import Path

from residual_zero.db import _open_readwrite


def open_exceptions(path: Path):
    return _open_readwrite(path, "exceptions")
