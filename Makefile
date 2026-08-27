# Target list must stay identical to spec §7, spec §10 and CLAUDE.md. If you add a target,
# add it to all three lists in the same commit.

PY := $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)

.PHONY: demo eval test verify-audit verify-books reproduce challenge evidence eval-diff

test:
	$(PY) -m pytest -q

demo:
	$(PY) -c "from residual_zero.console.app import app; print('demo ok')"

eval:
	$(PY) -m eval.cli --split dev --full --out artifacts/dev

eval-test:
	$(PY) -m eval.cli --split test --full --out artifacts/test --i-am-at-a-gate

verify-audit:
	$(PY) -m residual_zero.cli run --split dev --limit 5 --out artifacts/dev
	$(PY) -c "from pathlib import Path; from residual_zero.db import open_readonly; from residual_zero.audit import verify_chain; conn=open_readonly(Path('artifacts/dev/ledger.sqlite')); ok, broken, head=verify_chain(conn); n=conn.execute('SELECT COUNT(*) FROM audit_entry').fetchone()[0]; print(f'verify-audit ok={ok} entries={n} head={head}'); raise SystemExit(0 if ok else 1)"

verify-books:
	$(PY) -m residual_zero.books --db artifacts/dev/ledger.sqlite --split dev

reproduce:
	sh scripts/reproduce.sh

challenge:
	$(PY) -m residual_zero.cli challenge $(FILE)

evidence:
	$(PY) scripts/evidence.py

eval-diff:
	$(PY) -m eval.diff --a $(RUN_A) --b $(RUN_B)
