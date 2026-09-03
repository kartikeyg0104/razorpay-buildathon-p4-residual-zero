#!/bin/sh
# Residual Zero full local QA. Non-zero if a critical step fails.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"
PY="${ROOT}/.venv/bin/python"
if [ ! -x "$PY" ]; then
  echo "missing .venv/bin/python" >&2
  exit 1
fi
mkdir -p artifacts/qa
FAIL=0

echo "== env =="
"$PY" --version
"$PY" -m pytest --version

echo "== fingerprint =="
"$PY" scripts/qa_fingerprint.py || FAIL=1

echo "== live provider probe: NVIDIA NIM (UNAVAILABLE is allowed; YES only if a real rewrite succeeded) =="
"$PY" scripts/qa_provider_live.py || true

echo "== import smoke =="
if ! "$PY" scripts/qa_import_smoke.py; then
  FAIL=1
fi

echo "== dataset integrity =="
if ! "$PY" scripts/qa_dataset_integrity.py > artifacts/qa/dataset_integrity.out; then
  FAIL=1
fi

echo "== schema relationships =="
if ! "$PY" scripts/qa_schema_relationships.py > artifacts/qa/schema_relationships.out; then
  FAIL=1
fi

echo "== solver benchmark (does not replace production) =="
if ! "$PY" scripts/benchmark_solvers.py; then
  FAIL=1
fi

echo "== pytest =="
if ! "$PY" -m pytest -q --tb=line | tee artifacts/qa/full_pytest.txt; then
  FAIL=1
fi

echo "== campaign (tools/uniqueness/AI) =="
if ! "$PY" scripts/qa_campaign.py; then
  FAIL=1
fi

echo "== official Dev evaluation =="
if ! "$PY" -m eval.cli --split dev --full --out artifacts/qa/official_dev; then
  FAIL=1
fi

echo "== official Test evaluation (QA replay; does not overwrite artifacts/test) =="
if ! "$PY" -m eval.cli --split test --full --out artifacts/qa/official_test --i-am-at-a-gate; then
  FAIL=1
fi

"$PY" scripts/qa_parse_t04.py || FAIL=1

echo "== API probe (console must be listening on 8765) =="
if ! "$PY" scripts/qa_api_probe.py; then
  echo "API probe failed (is the console running?)" >&2
  FAIL=1
fi

if [ "$FAIL" -ne 0 ]; then
  echo "FULL LOCAL QA: FAIL" >&2
  exit 1
fi
echo "FULL LOCAL QA: critical steps returned 0"
exit 0
