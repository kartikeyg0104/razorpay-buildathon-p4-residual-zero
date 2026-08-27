#!/bin/sh
# F20: two eval runs, byte-identical outside the timing channel.
set -e
PY="${PY:-python3}"
if [ -x .venv/bin/python ]; then PY=.venv/bin/python; fi
$PY -m eval.cli --split dev --full --out artifacts/repro_a
$PY -m eval.cli --split dev --full --out artifacts/repro_b
$PY - <<'PY'
from pathlib import Path
skip = {"wall_clock_ms", "machine"}
def strip(text: str) -> str:
    lines = []
    for line in text.splitlines():
        if any(s in line for s in skip):
            continue
        lines.append(line)
    return "\n".join(lines)
a = Path("artifacts/repro_a")
b = Path("artifacts/repro_b")
for name in ("headline.md", "per_class.md", "ablations.md"):
    sa, sb = strip((a/name).read_text()), strip((b/name).read_text())
    if sa != sb:
        raise SystemExit(f"reproduce: {name} differs")
print("reproduce: ok")
PY
