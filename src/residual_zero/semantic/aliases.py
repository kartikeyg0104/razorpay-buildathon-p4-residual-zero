"""F26 alias table. Tuned parameters, not a trained scorer (spec §6.2)."""

from __future__ import annotations

import json
from pathlib import Path

from residual_zero.normalise import normalise_narration


class AliasTable:
    """normalised display name → closed-set entity id. Dict lookup only."""

    def __init__(self, mapping: dict[str, str] | None = None) -> None:
        self._map = dict(mapping or {})

    def lookup(self, raw: str) -> str | None:
        return self._map.get(normalise_narration(raw))

    def learn(self, raw: str, entity_id: str) -> None:
        self._map[normalise_narration(raw)] = entity_id

    def dump(self) -> dict[str, str]:
        return dict(self._map)

    @classmethod
    def load(cls, path: Path) -> "AliasTable":
        if not path.is_file():
            return cls()
        raw = json.loads(path.read_text(encoding="utf-8"))
        return cls({str(k): str(v) for k, v in raw.items()})

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.dump(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
