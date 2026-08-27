# Target list must stay identical to spec §7, spec §10 and CLAUDE.md. If you add a target,
# add it to all three lists in the same commit.

PY := $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)

.PHONY: demo eval test verify-audit verify-books reproduce challenge evidence eval-diff

test:
	$(PY) -m pytest -q

demo:
	@echo "make demo: not implemented until CP7 (needs console + orchestrator)"; exit 1

eval:
	@echo "make eval: not implemented until CP6 (needs the harness)"; exit 1

verify-audit:
	$(PY) -m residual_zero.cli run --split dev --limit 5 --out artifacts/dev
	$(PY) -c "from pathlib import Path; from residual_zero.db import open_readonly; from residual_zero.audit import verify_chain; conn=open_readonly(Path('artifacts/dev/ledger.sqlite')); ok, broken, head=verify_chain(conn); n=conn.execute('SELECT COUNT(*) FROM audit_entry').fetchone()[0]; print(f'verify-audit ok={ok} entries={n} head={head}'); raise SystemExit(0 if ok else 1)"

verify-books:
	@echo "make verify-books: not implemented until Phase 2 (F33 conservation identity)"; exit 1

reproduce:
	@echo "make reproduce: not implemented until CP7 (F20)"; exit 1

challenge:
	@echo "make challenge FILE=...: not implemented until CP7 (F21)"; exit 1

evidence:
	@echo "make evidence: not implemented until CP7 (F22)"; exit 1

eval-diff:
	@echo "make eval-diff RUN_A=... RUN_B=...: not implemented until Phase 2 (F54)"; exit 1
