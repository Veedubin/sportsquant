-- ============================================================================
-- quantitative_sports — TimescaleDB Init Script
-- ============================================================================
-- Target image:  timescale/timescaledb:latest-pg18
-- Purpose:      Bootstrap the quantitative_sports persistent storage layer for
--               odds ticks, injuries, games, game results, poller health,
--               and aggregated metrics.
-- Date:         2026-06-18
-- Version:      v0.2.0 refactor
--
-- Mount this file at /docker-entrypoint-initdb.d/01-init.sql in the
-- TimescaleDB container. It runs once on a fresh database.
-- ============================================================================

-- ───── Enable TimescaleDB Extension ─────────────────────────────────────────

CREATE EXTENSION IF NOT EXISTS timescaledb;

-- ───── 1. odds_ticks ────────────────────────────────────────────────────────
-- Time-series of every price observation from every bookmaker.
-- Each row is one snapshot of one market/selection at one point in time.

CREATE TABLE IF NOT EXISTS odds_ticks (
    id          BIGSERIAL,
    sport       TEXT        NOT NULL,                       -- 'nfl', 'nba', 'mlb', 'nhl'
    league      TEXT        NOT NULL,                       -- 'NFL', 'NBA', etc.
    event_id    TEXT        NOT NULL,                       -- external game ID
    book        TEXT        NOT NULL,                       -- 'pinnacle', 'fanduel', 'draftkings', 'odds_api', etc.
    market      TEXT        NOT NULL,                       -- 'h2h', 'spreads', 'totals', 'player_props'
    selection   TEXT        NOT NULL,                       -- 'over', 'under', 'home', 'away', or player name
    price       INTEGER     NOT NULL,                       -- American odds: -110, +105, etc.
    line        DOUBLE PRECISION,                           -- point spread or total line; NULL for moneyline
    ts          TIMESTAMPTZ NOT NULL DEFAULT NOW(),         -- observation timestamp
    source_raw  JSONB,                                      -- original API response for audit/debug
    PRIMARY KEY (id, ts)                                    -- TimescaleDB requires partition col in PK
);

-- Convert to hypertable with 1-day chunk intervals for efficient time-range scans
SELECT create_hypertable(
    'odds_ticks',
    'ts',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists       => TRUE
);

-- Enable columnstore (TimescaleDB 2.18+ API; replaces old compression API)
ALTER TABLE odds_ticks SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'event_id',
    timescaledb.compress_orderby = 'ts DESC'
);

-- Compress chunks older than 7 days to save disk on historical data
CALL add_columnstore_policy(
    'odds_ticks',
    INTERVAL '7 days',
    if_not_exists => TRUE
);

-- Drop chunks older than 2 years — old odds data has diminishing analytical value
SELECT add_retention_policy(
    'odds_ticks',
    INTERVAL '2 years',
    if_not_exists => TRUE
);

-- Index: lookup latest odds for a specific game
CREATE INDEX IF NOT EXISTS idx_odds_ticks_event_time
    ON odds_ticks (event_id, ts DESC);

-- Index: filter by bookmaker within a sport
CREATE INDEX IF NOT EXISTS idx_odds_ticks_book_sport_time
    ON odds_ticks (book, sport, ts DESC);

-- Index: market-specific queries across a sport
CREATE INDEX IF NOT EXISTS idx_odds_ticks_sport_market_time
    ON odds_ticks (sport, market, ts DESC);

-- ───── 2. injuries ───────────────────────────────────────────────────────────
-- Time-series of every injury status observation.
-- Each row is one snapshot of a player's injury status at a point in time.

CREATE TABLE IF NOT EXISTS injuries (
    id          BIGSERIAL,
    sport       TEXT        NOT NULL,                       -- 'nfl', 'nba', 'mlb', 'nhl'
    player_id   TEXT        NOT NULL,                       -- external player ID (ESPN ID)
    player_name TEXT        NOT NULL,
    team        TEXT        NOT NULL,                       -- team abbreviation
    position    TEXT,                                       -- 'QB', 'PG', etc.
    status      TEXT        NOT NULL,                       -- 'Out', 'Doubtful', 'Questionable', 'Probable', 'Active'
    detail      TEXT,                                       -- free-text injury description
    ts          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_raw  JSONB,
    PRIMARY KEY (id, ts)
);

-- Same hypertable config as odds_ticks: 1d chunks, 7d compression, 2y retention
SELECT create_hypertable(
    'injuries',
    'ts',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists       => TRUE
);

-- Enable columnstore (TimescaleDB 2.18+ API; replaces old compression API)
ALTER TABLE injuries SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'player_id',
    timescaledb.compress_orderby = 'ts DESC'
);

CALL add_columnstore_policy(
    'injuries',
    INTERVAL '7 days',
    if_not_exists => TRUE
);

SELECT add_retention_policy(
    'injuries',
    INTERVAL '2 years',
    if_not_exists => TRUE
);

-- Index: player injury history over time
CREATE INDEX IF NOT EXISTS idx_injuries_player_time
    ON injuries (player_id, ts DESC);

-- Index: team injury report at a glance
CREATE INDEX IF NOT EXISTS idx_injuries_team_time
    ON injuries (team, ts DESC);

-- ───── 3. games ─────────────────────────────────────────────────────────────
-- Schedule of upcoming and past games.
-- Regular (non-hypertable) table — relatively small, accessed by event_id.

CREATE TABLE IF NOT EXISTS games (
    id              BIGSERIAL       PRIMARY KEY,
    sport           TEXT            NOT NULL,               -- 'nfl', 'nba', 'mlb', 'nhl'
    league          TEXT            NOT NULL,               -- 'NFL', 'NBA', etc.
    event_id        TEXT            NOT NULL UNIQUE,        -- external game ID
    home_team       TEXT            NOT NULL,               -- team abbreviation or full name
    away_team       TEXT            NOT NULL,
    commence_time   TIMESTAMPTZ     NOT NULL,               -- scheduled start time (UTC)
    season          INTEGER         NOT NULL,               -- e.g. 2024
    week            INTEGER,                                 -- NFL week number; NULL for other sports
    status          TEXT            NOT NULL DEFAULT 'scheduled',
                                                                -- 'scheduled', 'in_progress', 'completed', 'cancelled'
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

-- Index: season schedule lookups
CREATE INDEX IF NOT EXISTS idx_games_sport_season
    ON games (sport, season);

-- Index: upcoming games by start time
CREATE INDEX IF NOT EXISTS idx_games_commence_time
    ON games (commence_time);

-- Index: filter games by status (e.g. all in-progress)
CREATE INDEX IF NOT EXISTS idx_games_status
    ON games (status);

-- ───── 4. game_results ──────────────────────────────────────────────────────
-- Final scores and closing lines for bet settlement and CLV measurement.
-- Regular table — one row per settled game.

CREATE TABLE IF NOT EXISTS game_results (
    id              BIGSERIAL       PRIMARY KEY,
    event_id        TEXT            NOT NULL REFERENCES games(event_id),
    home_score      INTEGER,                                -- final home score
    away_score      INTEGER,                                -- final away score
    winner          TEXT,                                   -- 'home' or 'away'
    closing_spread  DOUBLE PRECISION,                       -- closing spread from Pinnacle
    closing_total   DOUBLE PRECISION,                       -- closing total from Pinnacle
    spread_result   TEXT,                                   -- 'home_covered', 'away_covered', 'push'
    total_result    TEXT,                                   -- 'over', 'under', 'push'
    settled_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

-- Index: look up result by event
CREATE INDEX IF NOT EXISTS idx_game_results_event_id
    ON game_results (event_id);

-- ───── 5. poller_runs ────────────────────────────────────────────────────────
-- Record of every poller execution — start time, end time, status, rows written.
-- Used for health tracking and ops dashboards.

CREATE TABLE IF NOT EXISTS poller_runs (
    id              BIGSERIAL       PRIMARY KEY,
    poller_name     TEXT            NOT NULL,               -- 'pinnacle_odds', 'espn_injuries', 'odds_api', 'health_check'
    started_at      TIMESTAMPTZ     NOT NULL,
    finished_at     TIMESTAMPTZ,
    status          TEXT            NOT NULL DEFAULT 'running',
                                                                -- 'running', 'success', 'failed'
    rows_written    INTEGER         DEFAULT 0,
    error           TEXT,                                   -- error message if failed
    source          TEXT,                                   -- 'pinnacle', 'espn', 'odds_api'
    sport           TEXT,                                   -- sport filtered on this run
    config_snapshot JSONB                                  -- poller config at time of run
);

-- Index: filter runs by poller name
CREATE INDEX IF NOT EXISTS idx_poller_runs_name
    ON poller_runs (poller_name);

-- Index: recent runs first
CREATE INDEX IF NOT EXISTS idx_poller_runs_started_desc
    ON poller_runs (started_at DESC);

-- Index: find failed runs quickly
CREATE INDEX IF NOT EXISTS idx_poller_runs_status
    ON poller_runs (status);

-- ───── 6. poller_health ─────────────────────────────────────────────────────
-- Current health status of each poller — one row per poller (UNIQUE name).
-- Updated on every heartbeat cycle.

CREATE TABLE IF NOT EXISTS poller_health (
    id                  BIGSERIAL   PRIMARY KEY,
    poller_name         TEXT        NOT NULL UNIQUE,        -- one row per poller
    last_heartbeat      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_run_id         BIGINT      REFERENCES poller_runs(id),
    status              TEXT        NOT NULL DEFAULT 'unknown',
                                                            -- 'healthy', 'degraded', 'down', 'unknown'
    consecutive_failures INTEGER    DEFAULT 0,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ───── 7. poller_logs ───────────────────────────────────────────────────────
-- Log lines for the web UI log-tail feature.
-- Regular table — appended continuously by pollers.

CREATE TABLE IF NOT EXISTS poller_logs (
    id          BIGSERIAL   PRIMARY KEY,
    poller_name TEXT        NOT NULL,
    run_id      BIGINT      REFERENCES poller_runs(id),
    level       TEXT        NOT NULL DEFAULT 'INFO',        -- 'DEBUG', 'INFO', 'WARNING', 'ERROR'
    message     TEXT        NOT NULL,
    ts          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index: tail logs for a specific run
CREATE INDEX IF NOT EXISTS idx_poller_logs_run_time
    ON poller_logs (run_id, ts DESC);

-- Index: recent logs per poller
CREATE INDEX IF NOT EXISTS idx_poller_logs_name_time
    ON poller_logs (poller_name, ts DESC);

-- ───── 8. db_metrics (Materialized View) ────────────────────────────────────
-- Aggregated metrics for the web UI metrics page.
-- Refresh periodically (e.g. every 5 min) or on-demand from the app layer.

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

-- Unique index on table_name so REFRESH MATERIALIZED VIEW CONCURRENTLY works
CREATE UNIQUE INDEX IF NOT EXISTS idx_db_metrics_table
    ON db_metrics (table_name);

-- ───── Schema Metadata ───────────────────────────────────────────────────────
-- Track the current schema version so Python's schema.py can verify it.

CREATE TABLE IF NOT EXISTS schema_metadata (
    key        TEXT PRIMARY KEY,
    value      JSONB,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO schema_metadata (key, value)
VALUES ('schema_version', to_jsonb(1))
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW();