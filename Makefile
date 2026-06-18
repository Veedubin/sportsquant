.PHONY: install install-dev test lint format typecheck docs clean \
        docker-build docker-build-web docker-build-api docker-up docker-up-web docker-up-api docker-up-full \
        docker-down docker-down-volumes docker-logs docker-ps docker-shell \
        k8s-deploy k8s-destroy kind-up kind-down \
        web all

# ── Install ──────────────────────────────────────────────────────────────

install:
	uv sync

install-dev:
	uv sync --group dev

# ── Quality Gates ─────────────────────────────────────────────────────────

test:
	uv run pytest tests/ -v

lint:
	uv run ruff check src/sportsquant/

format:
	uv run ruff format src/sportsquant/

typecheck:
	uv run mypy src/sportsquant/

docs:
	@echo "TODO: generate API docs (e.g. uv run pdoc src/sportsquant -o docs/api)"

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .ruff_cache -exec rm -rf {} +
	rm -rf .pytest_cache .mypy_cache dist *.egg-info

# ── Docker ────────────────────────────────────────────────────────────────
# Multi-stage build; targets: web (default), api, poller, dev.
# See docker/Dockerfile for details.

docker-build: docker-build-web

docker-build-web:
	docker build -f docker/Dockerfile --target web -t sportsquant/web:latest .

docker-build-api:
	docker build -f docker/Dockerfile --target api -t sportsquant/api:latest .

docker-build-poller:
	docker build -f docker/Dockerfile --target poller -t sportsquant/poller:latest .

docker-build-all: docker-build-web docker-build-api docker-build-poller

docker-up: docker-up-web

# Web UI only (default profile). Visit http://localhost:8080
docker-up-web:
	docker compose --profile web up -d --build
	@echo "Web UI:    http://localhost:8080"
	@echo "NFL page:  http://localhost:8080/nfl-predict"

# Web + API + Postgres. Visit http://localhost:8080 (web) and
# http://localhost:8000/docs (REST API)
docker-up-api:
	docker compose --profile api up -d --build
	@echo "Web UI:    http://localhost:8080"
	@echo "REST API:  http://localhost:8000/docs"

# Everything: web + api + poller + postgres + redis + kafka + ignite
docker-up-full:
	docker compose --profile full up -d --build
	@echo "Web UI:    http://localhost:8080"
	@echo "REST API:  http://localhost:8000/docs"
	@echo "Postgres:  localhost:5432"
	@echo "Redis:     localhost:6379"
	@echo "Kafka:     localhost:9092"
	@echo "Ignite:    localhost:10800 (thin) / 11211 (REST)"

docker-down:
	docker compose down

docker-down-volumes:
	docker compose down -v

docker-logs:
	docker compose logs -f

docker-ps:
	docker compose ps

# Open a shell in the web container for debugging
docker-shell:
	docker compose --profile web run --rm web /bin/bash

# ── Kubernetes ─────────────────────────────────────────────────────────────

k8s-deploy:
	./scripts/deploy.sh

k8s-destroy:
	kubectl delete -f k8s/ --recursive

k8s-status:
	kubectl get pods -A -l app.kubernetes.io/part-of=sportsquant

# ── Kind (local dev cluster) ───────────────────────────────────────────────

kind-up:
	kind create cluster --config kind-config.yaml

kind-down:
	kind delete cluster --name sports-platform

# ── Web Dashboard ───────────────────────────────────────────────────────────

web:
	uv run uvicorn sportsquant.web.app:app --host 0.0.0.0 --port 8080 --reload

# ── Composite Targets ─────────────────────────────────────────────────────

all: install test lint format