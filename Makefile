# ─────────────────────────────────────────────────────────────────────
# SportsQuant v0.2.0 Makefile
# ─────────────────────────────────────────────────────────────────────

.PHONY: help install install-dev install-notebook test lint format clean \
        docker-build-base docker-build-poller docker-build-web docker-build-all \
        docker-up docker-up-detach docker-down docker-clean docker-logs \
        poller-once poller-status poller-logs

# Default Python interpreter
PYTHON ?= python3
DOCKER ?= docker

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-25s\033[0m %s\n", $$1, $$2}'

# ── Local development ───────────────────────────────────────────────

install:  ## Install core package only
	uv sync

install-dev:  ## Install with dev extras (linters, test tools)
	uv sync --extra dev

install-notebook:  ## Install with notebook extras (jupyter, ML libs)
	uv sync --extra notebook --extra dev

test:  ## Run pytest test suite
	uv run pytest tests/ -v

lint:  ## Run ruff lint
	uv run ruff check src/

format:  ## Format code with ruff
	uv run ruff format src/

clean:  ## Remove build artifacts
	rm -rf dist/ build/ *.egg-info .pytest_cache .ruff_cache

# ── Docker: build ───────────────────────────────────────────────────

docker-build-base:  ## Build the timescaledb base image (pulled from registry, no build)
	@echo "timescaledb uses the upstream image docker.io/timescale/timescaledb:latest-pg18 — no build needed"

docker-build-poller:  ## Build the poller container image
	$(DOCKER) build -f docker/Dockerfile.poller -t sportsquant/poller:latest .

docker-build-web:  ## Build the web UI container image
	$(DOCKER) build -f docker/Dockerfile.web -t sportsquant/web:latest .

docker-build-all: docker-build-poller docker-build-web  ## Build both poller and web images
	@echo "All images built. Timescaledb is pulled from registry on first run."

# ── Docker: run ─────────────────────────────────────────────────────

docker-up:  ## Bring up the full stack (timescaledb + poller + web)
	$(DOCKER) compose up -d
	@echo "Web UI: http://localhost:8080"
	@echo "TimescaleDB: localhost:5432"

docker-up-detach: docker-up  ## Alias for docker-up (deprecated, kept for backwards compat)

docker-down:  ## Stop all containers and remove them
	$(DOCKER) compose down

docker-clean:  ## Stop containers AND remove volumes (deletes DB data!)
	$(DOCKER) compose down -v
	@echo "WARNING: All DB data has been deleted."

docker-logs:  ## Tail logs from all containers
	$(DOCKER) compose logs -f

# ── Docker: poller shortcuts ────────────────────────────────────────

poller-once:  ## Run a single poller cycle (for testing)
	$(DOCKER) compose run --rm poller uv run sportsquant-poller once

poller-status:  ## Show poller health and run history
	$(DOCKER) compose run --rm poller uv run sportsquant-poller status

poller-logs:  ## Tail the poller container logs
	$(DOCKER) compose logs -f poller