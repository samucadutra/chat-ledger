# ChatLedger — single entry point for dev and quality gates.
# CI invokes these targets verbatim (see .github/workflows/ci.yml).

SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help

UV ?= uv
PNPM ?= pnpm
WEB_DIR := apps/web
PY_SRC := packages/core/chatledger_core apps/api/chatledger_api apps/worker/chatledger_worker scripts/check_coverage.py

.PHONY: help up down logs install install-py install-web check lint lint-py lint-web \
	typecheck typecheck-py typecheck-web test web-test web-build migrate gen-api-types smoke

help: ## List available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-16s %s\n", $$1, $$2}'

# ------------------------------------------------------------------ stack
up: ## Build and start the full stack (db, api, worker x2, web)
	docker compose up -d --build --wait

down: ## Stop the stack (volumes kept)
	docker compose down

logs: ## Tail stack logs
	docker compose logs -f --tail=100

smoke: ## Boot the stack and run the end-to-end smoke script
	./scripts/smoke.sh

# ------------------------------------------------------------------ deps
install: install-py install-web ## Install Python and web dependencies

install-py:
	$(UV) sync --frozen

install-web:
	cd $(WEB_DIR) && $(PNPM) install --frozen-lockfile

# ------------------------------------------------------------------ gates
check: ## Run every quality gate (lint, typecheck, test, web-test, web-build)
	@echo "==> [check] lint"
	@$(MAKE) --no-print-directory lint
	@echo "==> [check] typecheck"
	@$(MAKE) --no-print-directory typecheck
	@echo "==> [check] test"
	@$(MAKE) --no-print-directory test
	@echo "==> [check] web-test"
	@$(MAKE) --no-print-directory web-test
	@echo "==> [check] web-build"
	@$(MAKE) --no-print-directory web-build
	@echo "==> [check] all gates passed"

lint: lint-py lint-web ## ruff check + format check + import-linter + eslint

lint-py:
	$(UV) run ruff check .
	$(UV) run ruff format --check .
	$(UV) run lint-imports

lint-web:
	cd $(WEB_DIR) && $(PNPM) run lint

typecheck: typecheck-py typecheck-web ## mypy --strict + tsc --noEmit

typecheck-py:
	$(UV) run mypy $(PY_SRC)

typecheck-web:
	cd $(WEB_DIR) && $(PNPM) run typecheck

test: ## pytest (unit + integration against PostgreSQL) + per-segment coverage gate
	$(UV) run pytest --cov --cov-report=term --cov-report=json:coverage.json
	$(UV) run python scripts/check_coverage.py coverage.json

web-test: ## vitest run
	cd $(WEB_DIR) && $(PNPM) run test

web-build: ## next build
	cd $(WEB_DIR) && $(PNPM) run build

# ------------------------------------------------------------------ dev helpers
migrate: ## Apply Alembic migrations to DATABASE_URL
	$(UV) run alembic upgrade head

gen-api-types: ## Regenerate the web API client types from the API's OpenAPI schema
	$(UV) run python -m chatledger_api.openapi > $(WEB_DIR)/openapi.json
	cd $(WEB_DIR) && OPENAPI_URL=openapi.json $(PNPM) run gen:api
