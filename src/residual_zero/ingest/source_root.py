"""The NN-6 mechanism: the system can only read files under a rendered-source root."""

from __future__ import annotations

from io import TextIOWrapper
from pathlib import Path


class SourceRootError(ValueError):
    """Raised when a caller asks this object to name a path it is not allowed to open."""


class SourceRoot:
    """The only way the reconciliation path reads inputs.

    Constructed on the rendered-source directory of a split. There is no method that can
    name a path above that directory, which is what keeps the answer-key file physically
    unreachable (NN-6). Absolute paths, ``..`` segments and symlinks that resolve outside
    the root all raise :class:`SourceRootError`.
    """

    def __init__(self, rendered_dir: Path) -> None:
        self._root = rendered_dir.expanduser().resolve()
        if not self._root.is_dir():
            raise FileNotFoundError(f"source root does not exist or is not a directory: {self._root}")

    @property
    def root(self) -> Path:
        return self._root

    def _resolve_inside(self, relative_name: str) -> Path:
        if not relative_name or not relative_name.strip():
            raise SourceRootError("empty relative name")
        candidate = Path(relative_name)
        if candidate.is_absolute():
            raise SourceRootError(f"absolute paths are rejected: {relative_name!r}")
        if ".." in candidate.parts:
            raise SourceRootError(f"parent-directory segments are rejected: {relative_name!r}")
        target = self._root.joinpath(candidate)
        resolved = target.resolve()
        try:
            resolved.relative_to(self._root)
        except ValueError as exc:
            raise SourceRootError(
                f"path escapes the source root: {relative_name!r}"
            ) from exc
        return resolved

    def open(self, relative_name: str) -> TextIOWrapper:
        """Open a file inside the root. Rejects absolute paths, ``..``, and escaping symlinks."""
        target = self._resolve_inside(relative_name)
        if not target.is_file():
            raise FileNotFoundError(f"{relative_name} is not a file under {self._root}")
        return target.open("r", encoding="utf-8", newline="")

    def list_csv(self) -> tuple[str, ...]:
        """Names of readable CSVs, sorted. There is no API that can name a path above the root."""
        names = [p.name for p in self._root.iterdir() if p.is_file() and p.suffix.lower() == ".csv"]
        return tuple(sorted(names))
