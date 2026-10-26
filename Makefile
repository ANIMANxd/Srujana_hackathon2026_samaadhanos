# SamadhaanOS build/dev tasks. Layout: architecture.md section 3.
# Frontend targets print "not yet implemented" until prompt F0 lands.
# Recipes are shell-agnostic on purpose: this repo is built on Windows where
# make may fall back to cmd.exe, so no sh syntax ($$, [], backslash
# continuations) and no cmd-only syntax. Logic lives in one-line python.

.PHONY: dev backend frontend mock test test-v4 fixtures demo openapi types contract-fixtures contract db-reset seed-history

PYTHON ?= python

# Three processes: api :8000, mock providers :8100, frontend :3000.
# `mock_providers/dev.py` is the launcher, because a Makefile recipe cannot start
# concurrent processes portably (its own header forbids `&`, `$$` and continuations).
dev:
	@echo --- api :8000 - mock providers :8100 - frontend :3000 ---
	$(PYTHON) mock_providers/dev.py

backend:
	@echo Starting backend on http://127.0.0.1:8000 - Ctrl+C to stop
	$(PYTHON) -m uvicorn backend.app.main:app --reload --app-dir .

# SIMULATION ONLY. Signed webhooks, fictional financiers, no real money.
mock:
	@echo Starting mock providers on http://127.0.0.1:8100 - Ctrl+C to stop
	@echo SIMULATION ONLY - no real money, no real signatures, no Aadhaar data
	$(PYTHON) -m uvicorn mock_providers.app:app --reload --port 8100 --app-dir .

frontend:
	@echo Starting frontend on http://127.0.0.1:3000 - Ctrl+C to stop
	npm --prefix frontend run dev

# pytest exits 5 when zero tests are collected; that counts as success here.
# `mock_providers/tests` is included because that service must not import backend/,
# so its suite lives beside it rather than under backend/tests.
test:
	$(PYTHON) -c "import subprocess, sys; rc = subprocess.call([sys.executable, '-m', 'pytest', 'backend/tests', 'mock_providers/tests', '-q']); sys.exit(0 if rc in (0, 5) else rc)"

# v4/v5 infrastructure suites: store, API routes, workflow, webhooks, finance.
# The legal engine's spec and contract suites stay in `make test`; this target
# is the fast green gate for the stateful half of the app.
test-v4:
	$(PYTHON) -c "import subprocess, sys; rc = subprocess.call([sys.executable, '-m', 'pytest', 'backend/tests/dev/store', 'backend/tests/dev/api', 'backend/tests/dev/workflow', 'backend/tests/dev/webhooks', 'backend/tests/dev/finance', '-q']); sys.exit(0 if rc in (0, 5) else rc)"

# Regenerate contracts/fixtures from the real engine: every preset's request +
# response, plus the CASE-01 artifact samples, then copy to frontend/fixtures.
# Refuses to write while backend/tests/spec is failing (export_fixtures gate 1).
fixtures:
	$(PYTHON) -m backend.app.export_fixtures
	$(PYTHON) -c "import pathlib, shutil; pathlib.Path('frontend/fixtures').mkdir(parents=True, exist_ok=True); shutil.copytree('contracts/fixtures', 'frontend/fixtures', dirs_exist_ok=True); print('fixtures copied to frontend/fixtures')"

demo: fixtures
	@echo --- offline demo mode ---
	@echo backend: run make backend then open http://127.0.0.1:8000/docs
	@echo frontend: not yet implemented until F0

# Regenerate contracts/openapi.json from the live FastAPI app (section 9.1).
openapi:
	$(PYTHON) -m backend.app.export_openapi

# Regenerate contracts/types.ts from openapi.json. openapi-typescript via npx
# is the primary path; a small python generator is the offline fallback.
types:
	$(PYTHON) -m backend.app.export_types

# Regenerate contracts/fixtures/*.request.json + *.response.json from the real
# engine, plus the CASE-01 artifact samples (no hand-typed numbers; golden rule
# 7/12). Same script `make fixtures` runs, minus the frontend copy.
contract-fixtures:
	$(PYTHON) -m backend.app.export_fixtures

# Rebuild the whole frozen contract: openapi.json then types.ts then fixtures.
contract: openapi types contract-fixtures

# Delete the v4 store database, recreate every table and seed the demo presets
# as cases (backend/store/seed.py). Destructive by design: demo data only.
db-reset:
	$(PYTHON) -m backend.store

# Rebuild the store with the deterministic 12-month customer history only
# (backend/store/history.py): six fictional customers generated as a CSV and
# imported through POST /api/v1/import/invoices, so the real code runs.
# Destructive by design: demo data only. `make db-reset` keeps the v4 presets and
# runs the same history seed after them.
seed-history:
	$(PYTHON) -m backend.store.history --reset
