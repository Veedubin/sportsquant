.PHONY: install install-dev test lint format typecheck docs clean \
        docker-build docker-up docker-down \
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

docker-build:
	docker build -f docker/Dockerfile -t sportsquant:latest .

docker-up:
	docker compose up -d

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f

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