#!/usr/bin/env python3
"""Write hardening baseline + financial regression snapshot. Does not rerun official Test eval."""

from __future__ import annotations

import hashlib
import json
import platform
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

def parse_t04(path: Path) -> dict:
    if not path.is_file():
        return {}
    out: dict = {"source": str(path)}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("- ") or ":" not in line:
            continue
        key, _, rest = line[2:].partition(":")
        out[key.strip()] = rest.strip()
    return out


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else ""


def git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return ""


def snapshot_sqlite(db: Path) -> list[dict]:
    if not db.is_file():
        return []
    conn = sqlite3.connect(db)
    rows = []
    try:
        audits = {}
        try:
            for (payload,) in conn.execute("SELECT payload FROM audit_entry"):
                blob = json.loads(payload)
                cid = str(blob.get("bank_credit_id") or "")
                if cid:
                    audits[cid] = blob
        except sqlite3.OperationalError:
            audits = {}
        try:
            recs = list(
                conn.execute(
                    "SELECT bank_credit_id, claimed_total_paise, residual_paise, disposition FROM reconciliation"
                )
            )
        except sqlite3.OperationalError:
            recs = []
        if not recs:
            for cid, blob in audits.items():
                members = blob.get("member_ids") or blob.get("matched_ids") or []
                if isinstance(members, str):
                    members = [members]
                rows.append(
                    {
                        "transaction_id": cid,
                        "status": blob.get("disposition") or blob.get("status"),
                        "residual": blob.get("residual_paise"),
                        "solution_count": blob.get("alternate_count") or blob.get("solution_count"),
                        "matched_ids": sorted(str(x) for x in members),
                        "search_status": blob.get("uniqueness") or blob.get("regime"),
                        "verification": blob.get("disposition"),
                        "uniqueness": blob.get("uniqueness"),
                    }
                )
            return rows
        for cid, claimed, residual, disp in recs:
            audit = audits.get(cid) or {}
            members = audit.get("member_ids") or audit.get("matched_ids") or []
            if isinstance(members, str):
                members = [members]
            rows.append(
                {
                    "transaction_id": cid,
                    "status": disp,
                    "residual": residual,
                    "solution_count": audit.get("alternate_count") or audit.get("solution_count"),
                    "matched_ids": sorted(str(x) for x in members),
                    "search_status": audit.get("uniqueness") or audit.get("regime"),
                    "verification": audit.get("disposition"),
                    "uniqueness": audit.get("uniqueness"),
                }
            )
    finally:
        conn.close()
    return rows


def compare_cards(a: dict, b: dict) -> list[str]:
    keys = (
        "residual-zero",
        "unique",
        "ambiguous",
        "none_found",
        "auto-clear",
        "false_clears",
        "search_coverage",
        "n_scored",
    )
    miss = []
    for key in keys:
        if str(a.get(key)) != str(b.get(key)):
            miss.append(f"{key}: {a.get(key)!r} vs {b.get(key)!r}")
    return miss


def main() -> int:
    qa = ROOT / "artifacts" / "qa"
    qa.mkdir(parents=True, exist_ok=True)
    env = {
        "python": sys.version.split()[0],
        "os": f"{platform.system()} {platform.release()}",
        "pytest": subprocess.check_output(
            [sys.executable, "-m", "pytest", "--version"], text=True
        ).strip(),
    }
    hashes = {
        "bank.csv": sha(ROOT / "data/dev/rendered/bank.csv"),
        "ledger.csv": sha(ROOT / "data/dev/rendered/ledger.csv"),
        "settlement.csv": sha(ROOT / "data/dev/rendered/settlement.csv"),
        "tax_rates.yaml": sha(ROOT / "config/tax_rates.yaml"),
        "fees.yaml": sha(ROOT / "config/fees.yaml"),
        "solver.yaml": sha(ROOT / "config/solver.yaml"),
    }
    official_dev = parse_t04(ROOT / "artifacts/dev/t04.md")
    official_test = parse_t04(ROOT / "artifacts/test/t04.md")
    qa_dev = parse_t04(ROOT / "artifacts/qa/official_dev/t04.md") if (ROOT / "artifacts/qa/official_dev/t04.md").is_file() else {}
    qa_dev_repeat = parse_t04(ROOT / "artifacts/qa/official_dev_repeat/t04.md") if (ROOT / "artifacts/qa/official_dev_repeat/t04.md").is_file() else {}
    qa_test = parse_t04(ROOT / "artifacts/qa/official_test/t04.md") if (ROOT / "artifacts/qa/official_test/t04.md").is_file() else {}
    det_dev = compare_cards(official_dev, qa_dev) if qa_dev else ["qa official_dev missing"]
    det_repeat = compare_cards(qa_dev, qa_dev_repeat) if qa_dev and qa_dev_repeat else ["repeat card missing — not rerun this campaign"]
    det_test = compare_cards(official_test, qa_test) if qa_test else ["qa official_test missing"]
    baseline = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "git_commit": git_commit(),
        "environment": env,
        "source_hashes": hashes,
        "dev": official_dev,
        "test": official_test,
        "official_test_rerun": False,
        "official_evaluation_note": "OFFICIAL EVALUATION NOT RERUN — BUDGET EXHAUSTED",
        "determinism_dev_vs_qa": det_dev,
        "determinism_dev_repeat": det_repeat,
        "determinism_test_vs_qa": det_test,
        "pytest": {},
    }
    (qa / "hardening_baseline.json").write_text(json.dumps(baseline, indent=2) + "\n", encoding="utf-8")
    rows = snapshot_sqlite(ROOT / "artifacts/dev/ledger.sqlite")
    (qa / "financial_regression_baseline.json").write_text(
        json.dumps(
            {
                "n": len(rows),
                "cleared": sum(1 for r in rows if r.get("status") == "CLEARED"),
                "rows": rows,
                "note": "Snapshot of artifacts/dev/ledger.sqlite. Official Test eval not rerun.",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (qa / "source_hashes_hardening.json").write_text(json.dumps(hashes, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"baseline": str(qa / "hardening_baseline.json"), "n_snapshot": len(rows), "cleared": sum(1 for r in rows if r.get("status") == "CLEARED")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
