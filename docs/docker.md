# Docker

SportsQuant ships with a multi-stage Dockerfile and a profile-driven
`docker-compose.yml`. Three profiles cover the common cases:

| Profile | Services | Use case |
|---------|----------|----------|
| `web` | Web UI | Local dashboard, light dev work |
| `api` | Web UI + REST API + Postgres | REST integration, data persistence |
| `full` | All of `api` + poller + Redis + Kafka + Ignite | Full stack, end-to-end testing |

## Quick start

```bash
# Build the web image and start the dashboard
make docker-up-web
# → http://localhost:8080
# → http://localhost:8080/nfl-predict
```

The web image is built with `target: web` from the multi-stage Dockerfile
and uses `uv` for fast, reproducible installs. Source is bind-mounted
read-only so the running container reflects your working tree on restart.

## Profiles

### `web` — Dashboard only (default for development)

```bash
docker compose --profile web up -d --build
# or
make docker-up-web
```

- One service: `web`
- Port: `8080`
- Routes available: `/`, `/ev/`, `/backtest/`, `/ratings/`, `/nfl-predict/`
- OpenAPI docs: `/api/docs`

### `api` — Web + REST API + Postgres

```bash
docker compose --profile api up -d --build
# or
make docker-up-api
```

- Adds: `api` (FastAPI on :8000) and `postgres` (TimescaleDB on :5432)
- The web UI binds to :8080 and the REST API to :8000.
- Postgres credentials come from `.env` (defaults: `sportsquant/sportsquant`).

### `full` — Everything

```bash
docker compose --profile full up -d --build
# or
make docker-up-full
```

Adds to `api`:
- `poller` — background odds/stats poller (currently a stub; included so
  the compose file documents the intended service topology)
- `redis` — caching layer on :6379
- `kafka` — event bus on :9092
- `ignite` — in-memory data grid on :10800 (thin client) / :11211 (REST)

## Multi-stage build

The Dockerfile exposes four targets. Most users only need `web`:

```bash
# Default (web) — dashboard on :8080
docker build -f docker/Dockerfile --target web -t sportsquant/web:latest .

# Production API — REST service on :8000
docker build -f docker/Dockerfile --target api -t sportsquant/api:latest .

# Background poller
docker build -f docker/Dockerfile --target poller -t sportsquant/poller:latest .

# Dev image with live-reload
docker build -f docker/Dockerfile --target dev -t sportsquant/dev:latest .
```

All targets share the same base layer (Python 3.12 + uv + ca-certificates)
so the build cache is reused across targets.

## Common operations

```bash
# Tail logs across all services
make docker-logs

# List running containers
make docker-ps

# Open a shell in the web container
make docker-shell

# Stop everything
make docker-down

# Stop and remove volumes (full reset)
make docker-down-volumes

# Build all three production images
make docker-build-all
```

## Configuration

Environment variables (set in `.env` or shell):

| Variable | Default | Used by |
|----------|---------|---------|
| `LOG_LEVEL` | `INFO` | web, api, poller |
| `POSTGRES_USER` | `sportsquant` | postgres |
| `POSTGRES_PASSWORD` | `sportsquant` | postgres |
| `POSTGRES_DB` | `sportsquant` | postgres |
| `ODDS_API_KEY` | _(empty)_ | poller |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | _(empty)_ | api |

## Notes

- **Live reload**: the `web` and `dev` targets mount `src/` and
  `notebooks/` read-only, so editing code on the host and restarting
  the container picks up changes. For a true hot-reload dev loop use
  the `dev` target with `uvicorn --reload`.
- **Source mounts are read-only** to mirror production. To run with
  full write access, remove the `:ro` suffix in `docker-compose.yml`.
- **Poller is a stub**: `sportsquant-poller` is registered in
  `pyproject.toml` as an entrypoint but the underlying module is not
  yet fully implemented. The `poller` service will exit immediately
  in the `full` profile until the poller is wired up.
- **Old Dockerfiles**: The `docker/` directory contains several
  legacy Dockerfiles (`nba-stats.Dockerfile`,
  `Nvidia-Spark-RAPIDS-ubuntu.dockerfile`, etc.) that predate the
  current architecture. They are excluded from the build context
  via `.dockerignore` and should be considered for cleanup.
