"""Schema management utilities for SportsQuant TimescaleDB integration.

Provides idempotent verification, programmatic creation, migration support,
and teardown of the sportsquant database schema.  The canonical DDL lives in
``docker/init-db.sql`` (runs on first Docker startup); this module mirrors
the same SQL so that tests and fresh databases that bypass the entrypoint
can bootstrap the schema from Python.

Usage::

    from sportsquant.infra.db.connection import DatabasePool
    from sportsquant.infra.db.schema import verify_schema, create_schema

    async with DatabasePool() as pool:
        report = await verify_schema(pool)
        if not report["is_valid"]:
            await create_schema(pool)
"""

from __future__ import annotations

import logging
from typing import Any

from sportsquant.infra.db.connection import DatabasePool

logger = logging.getLogger(__name__)

__all__ = [
    "SCHEMA_VERSION",
    "EXPECTED_TABLES",
    "EXPECTED_HYPERTABLES",
    "verify_schema",
    "create_schema",
    "get_schema_version",
    "set_schema_version",
    "drop_schema",
    "get_table_stats",
]

# ──────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────

SCHEMA_VERSION: int = 1
"""Current schema version number.  Bumped when migrations are added."""

EXPECTED_TABLES: frozenset[str] = frozenset(
    {
        "odds_ticks",
        "injuries",
        "games",
        "game_results",
        "poller_runs",
        "poller_health",
        "poller_logs",
    }
)
"""Set of table names that must exist after schema initialisation."""

EXPECTED_HYPERTABLES: frozenset[str] = frozenset({"odds_ticks", "injuries"})
"""TimescaleDB hypertables among :data:`EXPECTED_TABLES`."""

# ──────────────────────────────────────────────
# SQL DDL statements  (mirrors docker/init-db.sql)
# ──────────────────────────────────────────────

_EXTENSION_SQL = "CREATE EXTENSION IF NOT EXISTS timescaledb;"

_CREATE_ODDS_TICKS_SQL = """
CREATE TABLE IF NOT EXISTS odds_ticks (
    id          BIGSERIAL,
    sport       TEXT        NOT NULL,
    league      TEXT        NOT NULL,
    event_id    TEXT        NOT NULL,
    book        TEXT        NOT NULL,
    market      TEXT        NOT NULL,
    selection   TEXT        NOT NULL,
    price       INTEGER     NOT NULL,
    line        DOUBLE PRECISION,
    ts          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_raw  JSONB,
    PRIMARY KEY (id, ts)
);
"""

_HYPER_ODDS_TICKS_SQL = """
SELECT create_hypertable(
    'odds_ticks',
    'ts',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists       => TRUE
);
"""

_COMPRESS_ODDS_TICKS_SQL = """
SELECT add_compression_policy(
    'odds_ticks',
    INTERVAL '7 days',
    if_not_exists => TRUE
);
"""

_RETAIN_ODDS_TICKS_SQL = """
SELECT add_retention_policy(
    'odds_ticks',
    INTERVAL '2 years',
    if_not_exists => TRUE
);
"""

_IDX_ODDS_TICKS_EVENT_TIME_SQL = """
CREATE INDEX IF NOT EXISTS idx_odds_ticks_event_time
    ON odds_ticks (event_id, ts DESC);
"""

_IDX_ODDS_TICKS_BOOK_SPORT_TIME_SQL = """
CREATE INDEX IF NOT EXISTS idx_odds_ticks_book_sport_time
    ON odds_ticks (book, sport, ts DESC);
"""

_IDX_ODDS_TICKS_SPORT_MARKET_TIME_SQL = """
CREATE INDEX IF NOT EXISTS idx_odds_ticks_sport_market_time
    ON odds_ticks (sport, market, ts DESC);
"""

_CREATE_INJURIES_SQL = """
CREATE TABLE IF NOT EXISTS injuries (
    id          BIGSERIAL,
    sport       TEXT        NOT NULL,
    player_id   TEXT        NOT NULL,
    player_name TEXT        NOT NULL,
    team        TEXT        NOT NULL,
    position    TEXT,
    status      TEXT        NOT NULL,
    detail      TEXT,
    ts          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_raw  JSONB,
    PRIMARY KEY (id, ts)
);
"""

_HYPER_INJURIES_SQL = """
SELECT create_hypertable(
    'injuries',
    'ts',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists       => TRUE
);
"""

_COMPRESS_INJURIES_SQL = """
SELECT add_compression_policy(
    'injuries',
    INTERVAL '7 days',
    if_not_exists => TRUE
);
"""

_RETAIN_INJURIES_SQL = """
SELECT add_retention_policy(
    'injuries',
    INTERVAL '2 years',
    if_not_exists => TRUE
);
"""

_IDX_INJURIES_PLAYER_TIME_SQL = """
CREATE INDEX IF NOT EXISTS idx_injuries_player_time
    ON injuries (player_id, ts DESC);
"""

_IDX_INJURIES_TEAM_TIME_SQL = """
CREATE INDEX IF NOT EXISTS idx_injuries_team_time
    ON injuries (team, ts DESC);
"""

_CREATE_GAMES_SQL = """
CREATE TABLE IF NOT EXISTS games (
    id              BIGSERIAL       PRIMARY KEY,
    sport           TEXT            NOT NULL,
    league          TEXT            NOT NULL,
    event_id        TEXT            NOT NULL UNIQUE,
    home_team       TEXT            NOT NULL,
    away_team       TEXT            NOT NULL,
    commence_time   TIMESTAMPTZ     NOT NULL,
    season          INTEGER         NOT NULL,
    week            INTEGER,
    status          TEXT            NOT NULL DEFAULT 'scheduled',
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);
"""

_IDX_GAMES_SPORT_SEASON_SQL = """
CREATE INDEX IF NOT EXISTS idx_games_sport_season
    ON games (sport, season);
"""

_IDX_GAMES_COMMENCE_TIME_SQL = """
CREATE INDEX IF NOT EXISTS idx_games_commence_time
    ON games (commence_time);
"""

_IDX_GAMES_STATUS_SQL = """
CREATE INDEX IF NOT EXISTS idx_games_status
    ON games (status);
"""

_CREATE_GAME_RESULTS_SQL = """
CREATE TABLE IF NOT EXISTS game_results (
    id              BIGSERIAL       PRIMARY KEY,
    event_id        TEXT            NOT NULL REFERENCES games(event_id),
    home_score      INTEGER,
    away_score      INTEGER,
    winner          TEXT,
    closing_spread  DOUBLE PRECISION,
    closing_total   DOUBLE PRECISION,
    spread_result   TEXT,
    total_result    TEXT,
    settled_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);
"""

_IDX_GAME_RESULTS_EVENT_ID_SQL = """
CREATE INDEX IF NOT EXISTS idx_game_results_event_id
    ON game_results (event_id);
"""

_CREATE_POLLER_RUNS_SQL = """
CREATE TABLE IF NOT EXISTS poller_runs (
    id              BIGSERIAL       PRIMARY KEY,
    poller_name     TEXT            NOT NULL,
    started_at      TIMESTAMPTZ     NOT NULL,
    finished_at     TIMESTAMPTZ,
    status          TEXT            NOT NULL DEFAULT 'running',
    rows_written    INTEGER         DEFAULT 0,
    error           TEXT,
    source          TEXT,
    sport           TEXT,
    config_snapshot JSONB
);
"""

_IDX_POLLER_RUNS_NAME_SQL = """
CREATE INDEX IF NOT EXISTS idx_poller_runs_name
    ON poller_runs (poller_name);
"""

_IDX_POLLER_RUNS_STARTED_DESC_SQL = """
CREATE INDEX IF NOT EXISTS idx_poller_runs_started_desc
    ON poller_runs (started_at DESC);
"""

_IDX_POLLER_RUNS_STATUS_SQL = """
CREATE INDEX IF NOT EXISTS idx_poller_runs_status
    ON poller_runs (status);
"""

_CREATE_POLLER_HEALTH_SQL = """
CREATE TABLE IF NOT EXISTS poller_health (
    id                  BIGSERIAL   PRIMARY KEY,
    poller_name         TEXT        NOT NULL UNIQUE,
    last_heartbeat      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_run_id         BIGINT      REFERENCES poller_runs(id),
    status              TEXT        NOT NULL DEFAULT 'unknown',
    consecutive_failures INTEGER    DEFAULT 0,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

_CREATE_POLLER_LOGS_SQL = """
CREATE TABLE IF NOT EXISTS poller_logs (
    id          BIGSERIAL   PRIMARY KEY,
    poller_name TEXT        NOT NULL,
    run_id      BIGINT      REFERENCES poller_runs(id),
    level       TEXT        NOT NULL DEFAULT 'INFO',
    message     TEXT        NOT NULL,
    ts          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

_IDX_POLLER_LOGS_RUN_TIME_SQL = """
CREATE INDEX IF NOT EXISTS idx_poller_logs_run_time
    ON poller_logs (run_id, ts DESC);
"""

_IDX_POLLER_LOGS_NAME_TIME_SQL = """
CREATE INDEX IF NOT EXISTS idx_poller_logs_name_time
    ON poller_logs (poller_name, ts DESC);
"""

_CREATE_DB_METRICS_SQL = """
CREATE MATERIALIZED VIEW IF NOT EXISTS db_metrics AS
SELECT
    'odds_ticks' AS table_name,
    COUNT(*)     AS total_rows,
    COUNT(*) FILTER (WHERE ts > NOW() - INTERVAL '24 hours') AS rows_24h,
    MIN(ts)      AS oldest_ts,
    MAX(ts)      AS newest_ts
FROM odds_ticks
UNION ALL
SELECT
    'injuries'   AS table_name,
    COUNT(*)     AS total_rows,
    COUNT(*) FILTER (WHERE ts > NOW() - INTERVAL '24 hours') AS rows_24h,
    MIN(ts)      AS oldest_ts,
    MAX(ts)      AS newest_ts
FROM injuries
UNION ALL
SELECT
    'poller_runs' AS table_name,
    COUNT(*)      AS total_rows,
    COUNT(*) FILTER (WHERE started_at > NOW() - INTERVAL '24 hours') AS rows_24h,
    MIN(started_at) AS oldest_ts,
    MAX(started_at) AS newest_ts
FROM poller_runs;
"""

_IDX_DB_METRICS_TABLE_SQL = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_db_metrics_table
    ON db_metrics (table_name);
"""

_CREATE_SCHEMA_METADATA_SQL = """
CREATE TABLE IF NOT EXISTS schema_metadata (
    key        TEXT        PRIMARY KEY,
    value      JSONB       NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

# ──────────────────────────────────────────────
# Ordered DDL sequence for create_schema()
# ──────────────────────────────────────────────

_DDL_SEQUENCE: list[str] = [
    # Extension
    _EXTENSION_SQL,
    # odds_ticks
    _CREATE_ODDS_TICKS_SQL,
    _HYPER_ODDS_TICKS_SQL,
    _COMPRESS_ODDS_TICKS_SQL,
    _RETAIN_ODDS_TICKS_SQL,
    _IDX_ODDS_TICKS_EVENT_TIME_SQL,
    _IDX_ODDS_TICKS_BOOK_SPORT_TIME_SQL,
    _IDX_ODDS_TICKS_SPORT_MARKET_TIME_SQL,
    # injuries
    _CREATE_INJURIES_SQL,
    _HYPER_INJURIES_SQL,
    _COMPRESS_INJURIES_SQL,
    _RETAIN_INJURIES_SQL,
    _IDX_INJURIES_PLAYER_TIME_SQL,
    _IDX_INJURIES_TEAM_TIME_SQL,
    # games
    _CREATE_GAMES_SQL,
    _IDX_GAMES_SPORT_SEASON_SQL,
    _IDX_GAMES_COMMENCE_TIME_SQL,
    _IDX_GAMES_STATUS_SQL,
    # game_results
    _CREATE_GAME_RESULTS_SQL,
    _IDX_GAME_RESULTS_EVENT_ID_SQL,
    # poller_runs
    _CREATE_POLLER_RUNS_SQL,
    _IDX_POLLER_RUNS_NAME_SQL,
    _IDX_POLLER_RUNS_STARTED_DESC_SQL,
    _IDX_POLLER_RUNS_STATUS_SQL,
    # poller_health
    _CREATE_POLLER_HEALTH_SQL,
    # poller_logs
    _CREATE_POLLER_LOGS_SQL,
    _IDX_POLLER_LOGS_RUN_TIME_SQL,
    _IDX_POLLER_LOGS_NAME_TIME_SQL,
    # db_metrics materialized view
    _CREATE_DB_METRICS_SQL,
    _IDX_DB_METRICS_TABLE_SQL,
    # schema_metadata
    _CREATE_SCHEMA_METADATA_SQL,
]

# ──────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────


async def verify_schema(pool: DatabasePool) -> dict[str, Any]:
    """Check that all expected tables, hypertables, and views exist.

    Queries ``information_schema.tables`` and the TimescaleDB
    ``timescaledb_information.hypertables`` view to determine which
    objects are present.  The result dict contains enough information
    for the caller to decide whether to run :func:`create_schema`.

    Args:
        pool: A connected :class:`~sportsquant.infra.db.connection.DatabasePool`.

    Returns:
        A dict with keys ``schema_version``, ``tables_present``,
        ``tables_missing``, ``hypertables_present``, ``hypertables_missing``,
        ``view_present``, ``is_valid``, and ``existing_schema_version``.
    """
    # --- tables ---
    table_rows = await pool.fetch("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    existing_tables = {row["tablename"] for row in table_rows}

    tables_present = sorted(EXPECTED_TABLES & existing_tables)
    tables_missing = sorted(EXPECTED_TABLES - existing_tables)

    # --- hypertables ---
    try:
        hyper_rows = await pool.fetch(
            "SELECT hypertable_name FROM timescaledb_information.hypertables"
        )
        existing_hypertables = {row["hypertable_name"] for row in hyper_rows}
    except Exception:
        # TimescaleDB extension not installed or hypertables view absent
        logger.warning("Could not query hypertables — TimescaleDB may not be enabled")
        existing_hypertables: set[str] = set()  # type: ignore[no-redef]

    hypertables_present = sorted(EXPECTED_HYPERTABLES & existing_hypertables)
    hypertables_missing = sorted(EXPECTED_HYPERTABLES - existing_hypertables)

    # --- materialized view ---
    view_rows = await pool.fetch(
        "SELECT matviewname FROM pg_matviews WHERE schemaname = 'public' AND matviewname = 'db_metrics'"
    )
    view_present = len(view_rows) > 0

    # --- schema_metadata version ---
    existing_version = await get_schema_version(pool)

    is_valid = len(tables_missing) == 0 and len(hypertables_missing) == 0 and view_present

    return {
        "schema_version": SCHEMA_VERSION,
        "tables_present": tables_present,
        "tables_missing": tables_missing,
        "hypertables_present": hypertables_present,
        "hypertables_missing": hypertables_missing,
        "view_present": view_present,
        "is_valid": is_valid,
        "existing_schema_version": existing_version,
    }


async def create_schema(pool: DatabasePool, if_not_exists: bool = True) -> None:
    """Programmatically create the full sportsquant schema.

    Mirrors the DDL in ``docker/init-db.sql``.  When *if_not_exists* is
    ``True`` (the default), every statement uses ``IF NOT EXISTS`` / the
    TimescaleDB ``if_not_exists`` flag so the function is idempotent.

    Args:
        pool: A connected :class:`~sportsquant.infra.db.connection.DatabasePool`.
        if_not_exists: When ``True`` (default), all DDL uses ``IF NOT EXISTS``
            clauses so repeated calls are safe.  When ``False``, duplicate
            objects will cause errors.
    """
    logger.info("Creating schema (if_not_exists=%s)", if_not_exists)

    for stmt in _DDL_SEQUENCE:
        # The SQL strings already include IF NOT EXISTS where applicable.
        # When if_not_exists is False we still execute the same statements;
        # the caller is responsible for understanding that errors may arise.
        stmt_stripped = stmt.strip()
        if not stmt_stripped or stmt_stripped.startswith("--"):
            continue
        try:
            await pool.execute(stmt_stripped)
        except Exception as exc:
            if if_not_exists:
                logger.warning("DDL statement failed (continuing): %s", exc)
            else:
                raise

    # Stamp the schema version
    await set_schema_version(pool, SCHEMA_VERSION)
    logger.info("Schema creation complete (version=%d)", SCHEMA_VERSION)


async def get_schema_version(pool: DatabasePool) -> int | None:
    """Read the current schema version from the ``schema_metadata`` table.

    If the table does not yet exist it is created first (idempotent).

    Args:
        pool: A connected :class:`~sportsquant.infra.db.connection.DatabasePool`.

    Returns:
        The integer version number, or ``None`` if it has never been set.
    """
    # Ensure the metadata table exists
    await pool.execute(_CREATE_SCHEMA_METADATA_SQL.strip())

    row = await pool.fetchrow("SELECT value FROM schema_metadata WHERE key = 'schema_version'")
    if row is None:
        return None
    version = row["value"]
    # value is JSONB — asyncpg returns it as a string/int depending on content
    if isinstance(version, int):
        return version
    try:
        import json

        return int(json.loads(version))  # type: ignore[arg-type]
    except (ValueError, TypeError):
        return None


async def set_schema_version(pool: DatabasePool, version: int) -> None:
    """Upsert the schema version into ``schema_metadata``.

    Creates the metadata table if it does not exist.

    Args:
        pool: A connected :class:`~sportsquant.infra.db.connection.DatabasePool`.
        version: The schema version number to record.
    """
    # Ensure the metadata table exists
    await pool.execute(_CREATE_SCHEMA_METADATA_SQL.strip())

    await pool.execute(
        """
        INSERT INTO schema_metadata (key, value)
        VALUES ('schema_version', $1::jsonb)
        ON CONFLICT (key)
        DO UPDATE SET value = $1::jsonb, updated_at = NOW()
        """,
        str(version),
    )
    logger.info("Schema version set to %d", version)


async def drop_schema(pool: DatabasePool, confirm: bool = False) -> None:
    """Drop all sportsquant tables, hypertables, and views.

    This is a **destructive** operation intended only for test teardown.
    It will not execute unless *confirm* is ``True``.

    Args:
        pool: A connected :class:`~sportsquant.infra.db.connection.DatabasePool`.
        confirm: Must be ``True`` for the drop to proceed.  Defaults to
            ``False`` as a safety check.

    Raises:
        RuntimeError: If *confirm* is not ``True``.
    """
    if not confirm:
        raise RuntimeError("drop_schema requires confirm=True to prevent accidental data loss")

    logger.warning("Dropping entire sportsquant schema!")

    # Drop order matters: views first, then tables with FK refs, then base tables.
    drop_statements: list[str] = [
        # Materialized view
        "DROP MATERIALIZED VIEW IF EXISTS db_metrics",
        # Tables with foreign keys (referencing other tables)
        "DROP TABLE IF EXISTS poller_logs CASCADE",
        "DROP TABLE IF EXISTS poller_health CASCADE",
        "DROP TABLE IF EXISTS game_results CASCADE",
        "DROP TABLE IF EXISTS poller_runs CASCADE",
        # Hypertables (timescaledb handles chunk drops)
        "DROP TABLE IF EXISTS odds_ticks CASCADE",
        "DROP TABLE IF EXISTS injuries CASCADE",
        # Regular tables
        "DROP TABLE IF EXISTS games CASCADE",
        # Metadata
        "DROP TABLE IF EXISTS schema_metadata CASCADE",
    ]

    for stmt in drop_statements:
        await pool.execute(stmt)

    logger.info("Schema dropped successfully")


async def get_table_stats(pool: DatabasePool) -> list[dict[str, Any]]:
    """Return row counts and disk sizes for all expected tables.

    Queries ``pg_tables`` and ``pg_stat_user_tables`` to produce a
    lightweight overview of table health.

    Args:
        pool: A connected :class:`~sportsquant.infra.db.connection.DatabasePool`.

    Returns:
        A list of dicts, each with keys ``schemaname``, ``tablename``,
        ``size``, and ``estimated_rows``.
    """
    rows = await pool.fetch(
        """
        SELECT
            schemaname,
            tablename,
            pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size,
            (SELECT n_live_tup
             FROM pg_stat_user_tables
             WHERE relname = tablename) AS estimated_rows
        FROM pg_tables
        WHERE schemaname = 'public'
          AND tablename = ANY($1)
        ORDER BY tablename
        """,
        list(EXPECTED_TABLES),
    )

    return [
        {
            "schemaname": row["schemaname"],
            "tablename": row["tablename"],
            "size": row["size"],
            "estimated_rows": row["estimated_rows"],
        }
        for row in rows
    ]
