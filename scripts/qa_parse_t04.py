"""Parse official t04.md into JSON. Does not invent numbers."""

from __future__ import annotations

import json
import re
from pathlib import Path


def parse_t04(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    out: dict[str, object] = {"source": str(path)}
    for line in text.splitlines():
        if not line.startswith("- "):
            continue
        key, _, rest = line[2:].partition(":")
        out[key.strip()] = rest.strip()
    # ratios
    for key in ("residual-zero", "settlement-linked / member-identified", "verified-linked (ids + residual 0)", "search_coverage"):
        raw = str(out.get(key, ""))
        match = re.fullmatch(r"(\d+)/(\d+)", raw)
        if match:
            out[key + "_n"] = int(match.group(1))
            out[key + "_d"] = int(match.group(2))
    for key in ("unique", "ambiguous", "none_found", "budget_exceeded_search", "auto-clear", "flagged", "budget_exceeded_disposition", "false_clears", "n_scored", "wall_clock_ms"):
        raw = str(out.get(key, "")).strip()
        if raw.isdigit():
            out[key + "_int"] = int(raw)
    return out


def main() -> None:
    qa = Path("artifacts").joinpath("qa")
    mapping = {
        "final_dev_evaluation.json": qa.joinpath("official_dev", "t04.md"),
        "final_test_evaluation.json": qa.joinpath("official_test", "t04.md"),
    }
    for name, src in mapping.items():
        if not src.is_file():
            print("missing", src)
            continue
        payload = parse_t04(src)
        dest = qa.joinpath(name)
        dest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print("wrote", dest)


if __name__ == "__main__":
    main()
