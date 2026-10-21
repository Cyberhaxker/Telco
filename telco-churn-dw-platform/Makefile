SHELL := /bin/bash
.DEFAULT_GOAL := help

COMPOSE      ?= docker compose
ALL_PROFILES := --profile airflow --profile ml --profile observability
PROD         := $(COMPOSE) -f docker-compose.yml -f docker-compose.prod.yml $(ALL_PROFILES)
DW_COMPOSE   := $(COMPOSE) -f docker-compose.dw.yml
PY_SERVICES  := ingestion_api metadata_api analytics_api stream_consumer

.PHONY: help env up up-core down clean logs ps build bootstrap dw-up dw-down dw-package dw-backup dw-restore \
        prod-up prod-down test test-py test-dbt test-web e2e lint fmt k6 dbt-build train score secrets

help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

env: ## Create .env from .env.example with random secrets (never overwrites)
	@test -f .env && echo ".env already exists - leaving it untouched" || ./scripts/generate-env.sh

up: env ## Start the whole platform (all profiles) and run the first pipeline
	$(COMPOSE) $(ALL_PROFILES) up -d --build --wait --wait-timeout 900 || ($(COMPOSE) $(ALL_PROFILES) ps; exit 1)
	@./scripts/print-urls.sh

up-core: env ## Start only the core services (no Airflow, MLflow, observability)
	$(COMPOSE) up -d --build --wait --wait-timeout 600
	@./scripts/print-urls.sh

down: ## Stop all containers (keeps volumes)
	$(COMPOSE) $(ALL_PROFILES) down

clean: ## Stop and delete all containers AND volumes (destroys data)
	$(COMPOSE) $(ALL_PROFILES) down -v --remove-orphans

logs: ## Tail logs (SERVICE=name to filter)
	$(COMPOSE) $(ALL_PROFILES) logs -f --tail=200 $(SERVICE)

ps: ## Show container status
	$(COMPOSE) $(ALL_PROFILES) ps

build: ## Build every image
	$(COMPOSE) $(ALL_PROFILES) build

bootstrap: ## Re-run seed + first DAG runs (Airflow profile must be up)
	$(COMPOSE) $(ALL_PROFILES) run --rm airflow-bootstrap

# ---------------------------------------------------------------- warehouse
dw-up: env ## Run ONLY the packaged data warehouse (Postgres + dbt bootstrap)
	$(DW_COMPOSE) up -d --build --wait --wait-timeout 600
	$(DW_COMPOSE) run --rm dbt-bootstrap

dw-down: ## Stop the standalone warehouse
	$(DW_COMPOSE) down

dw-package: ## Build and save the warehouse images to dist/ as a portable tarball
	./scripts/package-dw.sh

dw-backup: ## pg_dump the warehouse to backups/
	./scripts/dw-backup.sh

dw-restore: ## Restore the warehouse from FILE=backups/<file>.dump
	./scripts/dw-restore.sh $(FILE)

dbt-build: ## Run dbt build inside the stack
	$(COMPOSE) run --rm dbt-bootstrap

train: ## Train models, promote champion and score customers
	$(COMPOSE) --profile ml run --rm ml-train

# ---------------------------------------------------------------- prod
prod-up: ## Start with the production overlay (TLS, 3 Kafka brokers, Celery)
	$(PROD) up -d --build --wait --wait-timeout 1200

prod-down:
	$(PROD) down

# ---------------------------------------------------------------- quality
test: test-py test-web ## Run all unit tests

test-py: ## Python unit tests (services, libs, ml)
	python -m pytest -m "not integration" --cov --cov-report=term-missing

test-integration: ## Python integration tests (needs Docker for Testcontainers)
	python -m pytest -m integration

test-dbt: ## dbt build against the running warehouse + baseline reconciliation
	$(COMPOSE) run --rm dbt-bootstrap bash -c "dbt build && python /app/reconcile.py"

test-web: ## Frontend unit tests
	cd apps/web && npm ci && npm run test

e2e: ## Playwright end-to-end tests against the running stack
	cd tests/e2e && npm ci && npx playwright install --with-deps chromium && npx playwright test

k6: ## Load test (needs k6 and a TOKEN env var)
	k6 run tests/load/k6-analytics-ingest.js

lint: ## Lint Python and TypeScript
	ruff check . && ruff format --check . && mypy libs/common_py services ml
	cd apps/web && npm run lint && npm run format:check

fmt: ## Auto-format
	ruff format . && ruff check --fix .
	cd apps/web && npm run format
