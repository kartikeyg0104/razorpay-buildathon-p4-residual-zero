#!/bin/sh
# Final hardening master QA. Non-zero on critical failure.
# Does not rerun exhausted official Test evaluation.
set -eu
set -o pipefail
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"
PY="${ROOT}/.venv/bin/python"
if [ ! -x "$PY" ]; then
  echo "missing .venv/bin/python" >&2
  exit 1
fi
mkdir -p artifacts/qa artifacts/e2e artifacts/demo
FAIL=0
CONSOLE_PID=""

echo "== env =="
"$PY" --version
"$PY" -m pytest --version
echo "PROVIDER_KEY_PRESENT=$("$PY" - <<'PY'
from residual_zero.runtime.envfile import load_env_file
import os
load_env_file()
print("true" if (os.environ.get("NVIDIA_API_KEY") or "").strip() else "false")
PY
)"

echo "== hashes before =="
"$PY" scripts/hardening_baseline.py || FAIL=1

echo "== live provider probe: NVIDIA NIM (UNAVAILABLE is allowed) =="
"$PY" scripts/qa_provider_live.py || true

echo "== solver benchmark =="
"$PY" scripts/benchmark_solvers.py || FAIL=1

echo "== pytest (unit; e2e ignored) =="
if ! "$PY" -m pytest -q --tb=line tests --ignore=tests/e2e | tee artifacts/qa/hardening_pytest.txt; then
  FAIL=1
fi

start_console() {
  if "$PY" - <<'PY'
import socket
s=socket.socket(); s.settimeout(0.3)
try:
    s.connect(("127.0.0.1", 8765))
    raise SystemExit(0)
except OSError:
    raise SystemExit(1)
finally:
    s.close()
PY
  then
    echo "console already on 8765"
    return 0
  fi
  "$PY" -m residual_zero.console >/tmp/rz-hardening-console.log 2>&1 &
  CONSOLE_PID=$!
  i=0
  while [ "$i" -lt 80 ]; do
    if "$PY" - <<'PY'
import socket
s=socket.socket(); s.settimeout(0.3)
try:
    s.connect(("127.0.0.1", 8765))
    raise SystemExit(0)
except OSError:
    raise SystemExit(1)
finally:
    s.close()
PY
    then
      echo "console started pid=$CONSOLE_PID"
      return 0
    fi
    i=$((i + 1))
    sleep 0.25
  done
  echo "console failed to bind 8765" >&2
  return 1
}

stop_console() {
  if [ -n "${CONSOLE_PID}" ]; then
    kill "$CONSOLE_PID" 2>/dev/null || true
    wait "$CONSOLE_PID" 2>/dev/null || true
    CONSOLE_PID=""
  fi
}

echo "== start console for browser/demo =="
if ! start_console; then
  FAIL=1
fi

echo "== browser E2E =="
if ! RZ_E2E=1 "$PY" -m pytest -q --tb=line tests/e2e | tee artifacts/qa/hardening_e2e.txt; then
  echo "browser E2E failed" >&2
  FAIL=1
fi

echo "== demo certification =="
if ! sh scripts/verify_demo.sh; then
  FAIL=1
fi

stop_console

echo "== restart test =="
if ! "$PY" scripts/restart_console_check.py; then
  FAIL=1
fi

echo "== hashes after =="
"$PY" - <<'PY' || FAIL=1
import hashlib, json
from pathlib import Path
before = json.loads(Path("artifacts/qa/source_hashes_hardening.json").read_text())
files = {
    "bank.csv": Path("data/dev/rendered/bank.csv"),
    "ledger.csv": Path("data/dev/rendered/ledger.csv"),
    "settlement.csv": Path("data/dev/rendered/settlement.csv"),
    "tax_rates.yaml": Path("config/tax_rates.yaml"),
    "fees.yaml": Path("config/fees.yaml"),
    "solver.yaml": Path("config/solver.yaml"),
}
after = {k: hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else "" for k, p in files.items()}
changed = [k for k in before if before.get(k) != after.get(k)]
Path("artifacts/qa/source_hashes_after_hardening.json").write_text(json.dumps({"after": after, "changed": changed}, indent=2) + "\n")
print("changed", changed)
if changed:
    raise SystemExit(1)
PY

echo "== reports =="
"$PY" scripts/write_hardening_reports.py || FAIL=1

echo "OFFICIAL EVALUATION NOT RERUN — BUDGET EXHAUSTED"
if [ "$FAIL" -ne 0 ]; then
  echo "FINAL HARDENING: FAIL" >&2
  exit 1
fi
echo "FINAL HARDENING: critical steps returned 0"
exit 0
