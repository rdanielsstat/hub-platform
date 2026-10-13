# Common commands, run from the repo root. `make help` lists them.
#
# Test layers:
#   test-unit         backend pytest (in-memory SQLite), frontend Vitest, the MCP
#                     server (fake API) and the agent hook. No services.
#   test-integration  backend pytest -m integration against the Compose Postgres.
#   test-mcp-live     the MCP server's tools against a real backend on :8000.
#   test-e2e          Playwright (browser + API) against whatever backend is on :8000.
#   test-e2e-docker   Playwright's Compose project against the full Compose stack,
#                     including the tests that stop and pause Postgres.
#
# The Vite dev server for E2E is started by Playwright (or reused if one is
# already on :5173). The backend never is: for test-e2e, run
# `make docker-up` or `uv run uvicorn app.main:app` in backend/ first.

.DEFAULT_GOAL := help
SHELL := /bin/bash

API_URL ?= http://localhost:8000
# The Compose frontend (nginx), which proxies /api/* to the backend.
WEB_URL ?= http://localhost:8080

.PHONY: help install check lint lint-backend lint-frontend lint-mcp lint-hooks \
	fmt test test-unit test-backend test-frontend test-mcp test-hooks \
	test-integration test-mcp-live test-e2e test-e2e-docker docker-up \
	docker-db-up docker-down docker-logs

help: ## List the targets
	@grep -E '^[a-z0-9-]+:.*## ' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*## "}; {printf "  %-18s %s\n", $$1, $$2}'

install: ## Install backend, frontend and MCP server dependencies
	cd backend && uv sync
	cd frontend && pnpm install
	cd mcp-server && uv sync

check: lint test-unit ## Every local gate AGENTS.md requires before a task is done
	cd frontend && pnpm build

lint: lint-backend lint-frontend lint-mcp lint-hooks ## Lint and format checks, everywhere

lint-backend: ## Backend: Ruff lint and format check
	cd backend && uv run ruff check . && uv run ruff format --check .

lint-frontend: ## Frontend: ESLint and Prettier check
	cd frontend && pnpm lint && pnpm format:check

lint-mcp: ## MCP server: Ruff lint and format check
	cd mcp-server && uv run ruff check . && uv run ruff format --check .

# agent-hooks/ has no dependencies of its own; the backend's Ruff lints it,
# with agent-hooks/ruff.toml (Python 3.9 target).
lint-hooks: ## Agent hook: Ruff lint and format check
	cd backend && uv run ruff check ../agent-hooks && uv run ruff format --check ../agent-hooks

fmt: ## Format and auto-fix: Ruff (backend, MCP server, hook), Prettier (frontend)
	cd backend && uv run ruff check --fix . && uv run ruff format .
	cd backend && uv run ruff check --fix ../agent-hooks && uv run ruff format ../agent-hooks
	cd mcp-server && uv run ruff check --fix . && uv run ruff format .
	cd frontend && pnpm format

test: test-unit ## Alias for test-unit

test-unit: test-backend test-frontend test-mcp test-hooks ## Unit tests: backend, frontend, MCP server, agent hook

test-backend: ## Backend unit tests (integration tests deselected)
	cd backend && uv run pytest -q

test-frontend: ## Frontend unit tests (Vitest)
	cd frontend && pnpm test

test-mcp: ## MCP server unit tests (fake Hub API; live test deselected)
	cd mcp-server && uv run pytest -q

test-hooks: ## Agent hook tests (standard library unittest)
	python3 -m unittest discover -s agent-hooks/tests -t agent-hooks

test-integration: docker-db-up ## Backend integration tests against the Compose Postgres
	cd backend && uv run pytest -m integration -q

test-mcp-live: ## MCP server tools against a real backend on :8000
	@curl -sf $(API_URL)/health >/dev/null || \
		{ echo "No backend at $(API_URL). Run 'make docker-up' (or uvicorn) first."; exit 1; }
	cd mcp-server && HUB_API_URL=$(API_URL) uv run pytest -m integration -q

test-e2e: ## Playwright browser + API tests; needs a backend on :8000
	@curl -sf $(API_URL)/health >/dev/null || \
		{ echo "No backend at $(API_URL). Run 'make docker-up' (or uvicorn) first."; exit 1; }
	cd frontend && E2E_API_URL=$(API_URL) pnpm exec playwright test --project=chromium

test-e2e-docker: docker-up ## Playwright Compose-stack tests, incl. stopping Postgres
	cd frontend && E2E_DOCKER=1 E2E_API_URL=$(API_URL) \
		pnpm exec playwright test --project=docker-compose --workers=1

docker-up: ## Build and start the Compose stack; wait until the API and the web app answer
	docker compose up -d --build
	@echo "Waiting for $(API_URL)/health and $(WEB_URL)/api/health ..."
	@for i in $$(seq 1 90); do \
		curl -sf $(API_URL)/health >/dev/null && curl -sf $(WEB_URL)/api/health >/dev/null && \
			{ echo "API is up; web app on $(WEB_URL)."; exit 0; }; \
		sleep 2; \
	done; \
	echo "The stack never came up. Recent logs:"; docker compose logs --tail=50; exit 1

docker-db-up: ## Start only the Compose Postgres and wait until it's healthy
	docker compose up -d --wait postgres

docker-down: ## Stop the Compose stack (keeps the database volume)
	docker compose down

docker-logs: ## Follow the Compose logs
	docker compose logs -f
