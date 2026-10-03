.PHONY: help up down logs ps api-install web-install install migrate api web test lint typecheck check

help:            ## Show targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-14s %s\n", $$1, $$2}'

up:              ## Build and start db, api, web with Docker Compose
	docker compose up -d --build
down:            ## Stop all services
	docker compose down
logs:            ## Tail service logs
	docker compose logs -f
ps:              ## Show service status
	docker compose ps

install: api-install web-install ## Install backend and frontend deps
api-install:
	cd apps/api && uv sync
web-install:
	cd apps/web && npm ci

migrate:         ## Apply database migrations (local)
	cd apps/api && uv run alembic upgrade head
api:             ## Run API with reload (local)
	cd apps/api && uv run uvicorn app.main:app --reload --port 8000
web:             ## Run frontend dev server (local)
	cd apps/web && npm run dev

test:            ## Run all tests
	cd apps/api && uv run pytest
	cd apps/web && npm test
lint:            ## Lint everything
	cd apps/api && uv run ruff check . && uv run ruff format --check .
	cd apps/web && npm run lint
typecheck:       ## Type-check everything
	cd apps/api && uv run mypy app tests
	cd apps/web && npm run typecheck
check: lint typecheck test ## Lint + typecheck + tests
