"""One-file evidence pack for a reviewer who will not run the code."""

from __future__ import annotations

from pathlib import Path


def main() -> None:
    root = Path("artifacts")
    parts = ["<!doctype html><html><head><meta charset='utf-8'><title>Residual Zero evidence</title></head><body>"]
    parts.append("<h1>Residual Zero — evidence</h1>")
    for rel in (
        "dev/headline.md",
        "dev/per_class.md",
        "dev/ablations.md",
        "dev/cost.md",
        "dev/threshold.json",
        "human_study/results.json",
    ):
        path = root.joinpath(rel)
        parts.append(f"<h2>{rel}</h2><pre>")
        parts.append(path.read_text(encoding="utf-8") if path.is_file() else "(missing)")
        parts.append("</pre>")
    parts.append("</body></html>")
    out = root.joinpath("evidence.html")
    out.write_text("".join(parts), encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
