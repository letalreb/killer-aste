.DEFAULT_GOAL := help
SHELL := /bin/bash

# ── Environment ───────────────────────────────────────────────────────────────
ENV_FILE ?= .env
PYTHON    = .venv/bin/python
PIP       = .venv/bin/pip
PYTEST    = .venv/bin/pytest
ALEMBIC   = .venv/bin/alembic
UVICORN   = .venv/bin/uvicorn
BLACK     = .venv/bin/black
RUFF      = .venv/bin/ruff
MYPY      = .venv/bin/mypy

COMPOSE   = docker compose -f docker/docker-compose.yml
COMPOSE_DEV = $(COMPOSE) -f docker/docker-compose.dev.yml

.PHONY: help setup install dev-up dev-down dev-remote migrate test test-unit test-integration \
        lint format typecheck dry-run logs clean

help:          ## Show this help
	@awk 'BEGIN{FS=":.*##"} /^[a-zA-Z_-]+:.*##/{printf "  \033[36m%-20s\033[0m %s\n",$$1,$$2}' $(MAKEFILE_LIST)

# ── Local setup ───────────────────────────────────────────────────────────────

setup:         ## Copy .env.example and install Python deps
	@[ -f .env ] || cp .env.example .env && echo ".env created from .env.example"
	$(MAKE) install

install:       ## Install Python dependencies into .venv
	python3 -m venv .venv
	$(PIP) install --upgrade pip --quiet
	$(PIP) install -r requirements.txt

# ── Docker (local dev) ────────────────────────────────────────────────────────

dev-up:        ## Start all services with hot-reload
	$(COMPOSE_DEV) up --build

dev-down:      ## Stop all services
	$(COMPOSE_DEV) down

up:            ## Start production-like stack
	$(COMPOSE) up --build -d

down:          ## Stop production stack
	$(COMPOSE) down

logs:          ## Tail application logs
	$(COMPOSE) logs -f app

# ── Database ──────────────────────────────────────────────────────────────────

migrate:       ## Run Alembic migrations
	$(ALEMBIC) upgrade head

migrate-down:  ## Rollback last migration
	$(ALEMBIC) downgrade -1

migrate-sql:   ## Print SQL for next migration (dry-run)
	$(ALEMBIC) upgrade head --sql

# ── Ingestion ─────────────────────────────────────────────────────────────────

migrate-sql-remote: ## Print SQL for next migration on remote DB (dry-run)
	@export $(grep -v '^#' .prod.env | grep DATABASE_SYNC_URL | xargs) && alembic upgrade head --sql


dev-remote:    ## Run backend locally connected to the remote Neon DB (reads .prod.env)
	@echo "Starting backend with remote DB (development mode)..."
	@DATABASE_URL=$$(grep '^DATABASE_URL' .prod.env | cut -d= -f2-) \
	 DATABASE_SYNC_URL=$$(grep '^DATABASE_SYNC_URL' .prod.env | cut -d= -f2-) \
	 SECRET_KEY=$$(grep '^SECRET_KEY' .prod.env | cut -d= -f2-) \
	 APP_ENV=development \
	 LOG_LEVEL=INFO \
	 INGESTION_MODE=safe \
	 DRY_RUN=false \
	 REDIS_ENABLED=false \
	 ENABLE_METRICS=false \
	 $(UVICORN) app.api.main:app --host 0.0.0.0 --port 8000 --reload

dry-run:       ## Run one ingestion cycle in dry_run mode (no real HTTP)
	DRY_RUN=true INGESTION_MODE=dry_run $(PYTHON) -m scripts.run_ingestion

# ── Tests ─────────────────────────────────────────────────────────────────────

test:          ## Run all tests (unit + integration)
	$(PYTEST) tests/ -v --tb=short --cov=app --cov-report=term-missing

test-unit:     ## Run only unit tests
	$(PYTEST) tests/unit/ -v --tb=short

test-integration: ## Run integration tests (needs running DB)
	$(PYTEST) tests/integration/ -v --tb=short

# ── Code quality ──────────────────────────────────────────────────────────────

lint:          ## Run ruff linter
	$(RUFF) check app/ tests/

format:        ## Auto-format with black + ruff
	$(BLACK) app/ tests/
	$(RUFF) check --fix app/ tests/

typecheck:     ## Run mypy type checker
	$(MYPY) app/ --ignore-missing-imports

# ── Misc ──────────────────────────────────────────────────────────────────────

clean:         ## Remove Python cache files
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete
	rm -rf .mypy_cache .pytest_cache .coverage htmlcov
