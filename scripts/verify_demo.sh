#!/bin/sh
# Exact hackathon demo against a live console on 127.0.0.1:8765.
set -eu
set -o pipefail
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"
PY="${ROOT}/.venv/bin/python"
if [ ! -x "$PY" ]; then
  echo "missing .venv/bin/python" >&2
  exit 1
fi
mkdir -p artifacts/demo artifacts/qa

fail=0
"$PY" - <<'PY' || fail=1
import json, sqlite3, urllib.request
from pathlib import Path

base = "http://127.0.0.1:8765"

def get(path):
    with urllib.request.urlopen(base + path) as resp:
        return json.loads(resp.read().decode("utf-8"))

t04 = get("/api/t04")
health = get("/api/health")
test = t04.get("test") or {}
print("STEP1 dashboard API")
print("  test residual-zero", test.get("residual-zero"))
print("  unique", test.get("unique"))
print("  auto-clear", test.get("auto-clear"))
print("  false_clears", test.get("false_clears"))
print("  search_coverage", test.get("search_coverage"))
print("  n_scored", test.get("n_scored"))
print("  health writes_cleared", health.get("writes_cleared"))
assert str(test.get("n_scored")) == "800"
assert test.get("residual-zero") == "521/800"
assert str(test.get("unique")) == "0"
assert str(test.get("auto-clear")) == "0"
assert str(test.get("false_clears")) == "0"
assert test.get("search_coverage") == "800/800"
assert health.get("writes_cleared") is False
print("STEP1 PASS")
PY

"$PY" - <<'PY' || fail=1
import json, urllib.request
from residual_zero.qa.finance_controller import finance_ask
from residual_zero.console.proof_explorer import proof_explorer

DEMO = "crd_001_acc_01_2025-01-09"
TWINS = "crd_mix_ambiguous_twins"
print("STEP2-6 proof explorer")
blob = proof_explorer(TWINS)
assert blob["solution_count"] == 2
assert blob["choose_one"] is False
assert blob["writes_cleared"] is False
print("  twins solutions", blob["solution_count"], "decision", blob["decision"])
print("STEP5-6 PASS")
print("STEP7 why not first combination")
got = finance_ask("Why can't you just choose the first combination?", DEMO)
print(got["answer"][:400])
assert got["writes_cleared"] is False
assert "human" in got["answer"].casefold() or "ambiguous" in got["answer"].casefold()
print("STEP7 PASS")
print("STEP8 biggest blocker")
got = finance_ask("What is our biggest reconciliation blocker?", "")
print(got["answer"][:300])
assert got["writes_cleared"] is False
print("STEP8 PASS")
print("STEP9 highest-value unresolved")
got = finance_ask("Show me the highest-value unresolved transactions", "")
print(got["answer"][:300])
assert got["writes_cleared"] is False
print("STEP9 PASS")
print("STEP10 clear this transaction")
got = finance_ask("Clear this transaction.", DEMO)
print(got["answer"])
assert "cannot authorize a financial clear" in got["answer"].casefold()
assert got["writes_cleared"] is False
print("STEP10 PASS")
PY

"$PY" - <<'PY' || fail=1
import sqlite3
from pathlib import Path
db = Path("artifacts/dev/ledger.sqlite")
n = 0
if db.is_file():
    conn = sqlite3.connect(db)
    try:
        n = conn.execute("SELECT COUNT(*) FROM reconciliation WHERE disposition = 'CLEARED'").fetchone()[0]
    except sqlite3.OperationalError:
        n = 0
    finally:
        conn.close()
print("STEP11 CLEARED", n)
assert n == 0
print("STEP11 PASS")
PY

if ! "$PY" scripts/capture_demo.py; then
  echo "demo screenshots failed (is the console running and is Playwright installed?)" >&2
  fail=1
fi

if [ "$fail" -ne 0 ]; then
  echo "DEMO CERTIFICATION: FAIL" >&2
  exit 1
fi
echo "DEMO CERTIFICATION: PASS"
exit 0
