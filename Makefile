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
	@echo "make verify-audit: not implemented until CP4 (needs the hash chain)"; exit 1

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
