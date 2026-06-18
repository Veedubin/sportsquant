# Docker

## Overview
sportsquant v0.2.0 ships as a 3-service docker compose stack:
- `timescaledb` — PostgreSQL 18 with TimescaleDB 2.28 (pulled from upstream)
- `poller` — built from `docker/Dockerfile.poller`, fetches odds + injuries
- `web` — built from `docker/Dockerfile.web`, serves ops dashboard

## Quick start

```bash
make docker-up   # brings up timescaledb + poller + web
```

Then visit `http://localhost:8080`.

## Building images

```bash
make docker-build-poller  # ~1.26 GB
make docker-build-web      # ~1.01 GB
make docker-build-all      # both
```

Note: `timescaledb` uses the upstream image `docker.io/timescale/timescaledb:latest-pg18` — no build needed.

## Running the stack

`make docker-up` brings up all 3 services with `docker compose up -d`. To use podman instead:

```bash
make docker-up DOCKER=podman
```

Or directly:
```bash
docker compose up -d
podman compose up -d
```

## Service URLs

| Service | URL | Notes |
|---------|-----|-------|
| Web UI | http://localhost:8080 | Ops dashboard |
| Web API docs | http://localhost:8080/api/docs | OpenAPI Swagger UI |
| TimescaleDB | `localhost:5432` | DB client access (psql, DBeaver, etc.) |
| Poller logs | `docker compose logs -f poller` | Background worker |

## Stopping / cleaning up

```bash
make docker-down       # stop containers, keep DB data
make docker-clean      # stop containers AND delete DB data
```

## Configuration

All config is via environment variables. See `.env.example`:

```bash
cp .env.example .env
# Edit .env with your Odds API key
# Then: make docker-up
```

Key variables:
- `SPORTSQUANT_DB_*` — DB connection
- `SPORTSQUANT_POLLER_*` — poller behavior (scheduler, sports, intervals)
- `SPORTSQUANT_POLLER_ODDS_API_KEY` — your Odds API key (optional, ESPN works without)

## Architecture details

```
┌─────────────┐    writes    ┌──────────────┐
│  poller     │ ──────────► │ timescaledb   │
│ (Prefect/   │              │ (PG 18 +      │
│  cron)      │              │  Timescale)   │
└─────────────┘              └──────┬───────┘
                                    │ reads
                              ┌─────▼──────┐
                              │   web      │
                              │ (FastAPI + │
                              │  Jinja2)   │
                              └────────────┘
```

The poller is **independent** from the web UI — you can run one without the other.

## Troubleshooting

- **TimescaleDB won't start**: PG 18 requires the mount path to be `/var/lib/postgresql` (not `/var/lib/postgresql/data`). This is fixed in `docker-compose.yml`.
- **TimescaleDB compression errors**: TimescaleDB 2.28 uses the new `columnstore` API. The init script uses `CALL add_columnstore_policy(...)` (not `SELECT add_compression_policy(...)`).
- **Web UI shows "no data"**: Start the poller with `make poller-once` to run one cycle, or wait for the cron interval (default 15 min for ESPN).
- **Poller logs say "API key missing"**: Set `SPORTSQUANT_POLLER_ODDS_API_KEY` in your `.env` file. ESPN works without a key.
- **Image build is slow**: The poller image includes Prefect (~1 GB). The web image is ~1 GB. Build once, reuse the layers.

## Healthchecks

All services have healthchecks:
- `timescaledb`: `pg_isready` every 10s
- `poller`: module import every 60s
- `web`: `curl /` every 30s

`docker compose ps` shows health status.
