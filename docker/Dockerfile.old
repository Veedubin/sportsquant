# syntax=docker/dockerfile:1.6
# ─────────────────────────────────────────────────────────────────────
# SportsQuant Dockerfile (multi-target)
#
# Build targets:
#   docker build --target web -t sportsquant/web .      # Web UI (default)
#   docker build --target api -t sportsquant/api .      # FastAPI service
#   docker build --target poller -t sportsquant/poller .# Background poller
#   docker build --target dev -t sportsquant/dev .       # Full dev image
#
# Base image uses uv for fast, reproducible installs.
# ─────────────────────────────────────────────────────────────────────

FROM python:3.12-slim AS base

# uv: fast Python package manager. Pinned for reproducibility.
COPY --from=ghcr.io/astral-sh/uv:0.4.18 /uv /uvx /usr/local/bin/

WORKDIR /app

# System deps kept minimal: just what pandas/numpy/scipy need.
# Playwright/chromium is intentionally NOT installed (it's not used in
# the runtime; only the old Dockerfile referenced it for scraping).
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Copy only the manifest first so Docker can cache the install layer.
COPY pyproject.toml uv.lock ./

# Install the package and its dependencies. --no-install-project means
# we install deps only, then add the project as editable in a later
# step (or as wheel). For runtime images we install the project too.
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# ─────────────────────────────────────────────────────────────────────
# Web UI target (default)
# Serves the FastAPI + Jinja2 + Tailwind dashboard on :8080
# ─────────────────────────────────────────────────────────────────────
FROM base AS web

# Install full deps (including [dev] extra for notebook-friendly stack).
# Runtime only needs the base deps, but the web image is also used for
# the dashboard which runs notebooks in dev mode.
RUN uv sync --frozen --no-install-project --extra dev

# Now copy the source and install the project itself.
# README.md is required by hatchling (the build backend) so it must
# land before `uv sync` re-runs.
COPY README.md ./
COPY src/ ./src/
COPY notebooks/ ./notebooks/
RUN uv sync --frozen --extra dev

# Default working dir for the web UI
WORKDIR /app

EXPOSE 8080

# Default command: serve the web UI on :8080. Override with
# `docker run sportsquant/web uv run sportsquant-api` to use the API.
CMD ["uv", "run", "uvicorn", "sportsquant.web.app:app", \
     "--host", "0.0.0.0", "--port", "8080"]

# ─────────────────────────────────────────────────────────────────────
# API target
# Runs the FastAPI service (sportsquant-api) for production use.
# ─────────────────────────────────────────────────────────────────────
FROM web AS api

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "sportsquant.api.betting_api:app", \
     "--host", "0.0.0.0", "--port", "8000"]

# ─────────────────────────────────────────────────────────────────────
# Poller target
# Background odds/stats poller (sportsquant-poller).
# Note: the underlying poller module is a stub; this target is here
# so the compose file is consistent.
# ─────────────────────────────────────────────────────────────────────
FROM web AS poller

CMD ["uv", "run", "sportsquant-poller"]

# ─────────────────────────────────────────────────────────────────────
# Dev target
# Full source tree, all extras, includes test/notebook tooling.
# Used by the docker compose dev profile for live-reload.
# ─────────────────────────────────────────────────────────────────────
FROM base AS dev

RUN uv sync --frozen --no-install-project --extra dev

COPY . .

RUN uv sync --frozen --extra dev

WORKDIR /app

EXPOSE 8080 8000

CMD ["uv", "run", "uvicorn", "sportsquant.web.app:app", \
     "--host", "0.0.0.0", "--port", "8080", "--reload"]
