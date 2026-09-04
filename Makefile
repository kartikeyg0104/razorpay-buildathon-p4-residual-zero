# Target list must stay identical to spec §7, spec §10 and CLAUDE.md. If you add a target,
# add it to all three lists in the same commit.

PY := $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)

.PHONY: demo eval test verify-audit verify-books reproduce challenge evidence eval-diff

# Deployment targets, declared separately: the .PHONY line above is pinned by
# tests/test_plan_arithmetic.py to exactly the list in spec §7, spec §10 and CLAUDE.md, and
# these are not in those documents. See docs/DEPLOYMENT.md.
.PHONY: test-deploy migrate migrate-status bootstrap-admin migrate-corpus serve

test:
	$(PY) -m pytest -q

demo:
	$(PY) -m residual_zero.cli solve --split dev --class 4 --show-proof --limit 1

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

# ---------------------------------------------------------------- deployment
# See docs/DEPLOYMENT.md. Every target below reads RZ_DATABASE_URL from the environment or
# .env; none of them takes a credential on the command line.

test-deploy:
	$(PY) -m pytest -q tests/deployment

migrate:
	$(PY) scripts/migrate.py --all

migrate-status:
	$(PY) scripts/migrate.py --status

bootstrap-admin:
	$(PY) scripts/bootstrap_admin.py --email $(EMAIL) --org $(ORG) $(ARGS)

migrate-corpus:
	$(PY) scripts/migrate_corpus.py --org $(ORG) --source $(or $(SOURCE),data/dev/rendered)

serve:
	$(PY) -m residual_zero.console
