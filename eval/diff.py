"""F54 disposition diff between two runs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def load_map(run: Path) -> dict[str, str]:
    path = run.joinpath("dispositions.json")
    if not path.is_file():
        raise FileNotFoundError(f"missing {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {str(k): str(v) for k, v in raw.items()}


def diff_maps(a: dict[str, str], b: dict[str, str]) -> list[dict[str, str]]:
    rows = []
    ids = sorted(set(a) | set(b))
    for cid in ids:
        left, right = a.get(cid), b.get(cid)
        if left == right:
            continue
        rows.append(
            {
                "credit_id": cid,
                "from": left or "ABSENT",
                "to": right or "ABSENT",
            }
        )
    return rows


def render_md(rows: list[dict[str, str]], run_a: str, run_b: str) -> str:
    lines = [
        f"# eval-diff `{run_a}` → `{run_b}`",
        "",
        f"{len(rows)} disposition change(s).",
        "",
        "| credit_id | from | to |",
        "|---|---|---|",
    ]
    if not rows:
        lines.append("| — | — | — |")
    for row in rows:
        lines.append(f"| {row['credit_id']} | {row['from']} | {row['to']} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--a", dest="run_a", required=True)
    parser.add_argument("--b", dest="run_b", required=True)
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)
    a_path, b_path = Path(args.run_a), Path(args.run_b)
    try:
        left, right = load_map(a_path), load_map(b_path)
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 1
    rows = diff_maps(left, right)
    text = render_md(rows, str(a_path), str(b_path))
    print(text)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
