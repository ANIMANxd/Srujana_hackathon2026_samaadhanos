# SamadhaanOS build/dev tasks. Layout: architecture.md section 3.
# Frontend targets print "not yet implemented" until prompt F0 lands.
# Recipes are shell-agnostic on purpose: this repo is built on Windows where
# make may fall back to cmd.exe, so no sh syntax ($$, [], backslash
# continuations) and no cmd-only syntax. Logic lives in one-line python.

.PHONY: dev backend frontend test fixtures demo openapi types contract-fixtures contract

PYTHON ?= python

dev: backend
	@echo --- frontend: not yet implemented until F0 ---

backend:
	@echo Starting backend on http://127.0.0.1:8000 - Ctrl+C to stop
	$(PYTHON) -m uvicorn backend.app.main:app --reload --app-dir .

frontend:
	@echo not yet implemented - frontend arrives with prompt F0

# pytest exits 5 when zero tests are collected; that counts as success here.
test:
	$(PYTHON) -c "import subprocess, sys; rc = subprocess.call([sys.executable, '-m', 'pytest', 'backend/tests', '-q']); sys.exit(0 if rc in (0, 5) else rc)"

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
