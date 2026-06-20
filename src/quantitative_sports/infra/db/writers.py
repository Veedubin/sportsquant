"""Async batch writers for Quant-Sports TimescaleDB tables.

Provides high-throughput, idempotent write helpers for the poller pipeline.
Bulk inserts use asyncpg's ``COPY`` protocol via
:meth:`~quantitative_sports.infra.db.connection.DatabasePool.copy_records_to_table`
for maximum throughput on time-series hypertables (``odds_ticks``, ``injuries``).

Convention
----------
Every public writer function is ``async def`` and takes a
:class:`~quantitative_sports.infra.db.connection.DatabasePool` as its first argument.
Functions that insert rows return the **number of rows actually written** (after
skipping invalid input).  Functions that update or upsert return ``None`` unless
otherwise documented.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from quantitative_sports.infra.db.connection import DatabasePool

logger = logging.getLogger(__name__)

__all__ = [
    "write_odds_ticks",
    "write_injuries",
    "write_poller_run_start",
    "write_poller_run_finish",
    "update_poller_health",
    "write_poller_log",
    "write_poller_logs_batch",
]

# ──────────────────────────────────────────────
# Column definitions (order matters for COPY)
# ──────────────────────────────────────────────

_ODDS_TICKS_COLUMNS: list[str] = [
    "sport",
    "league",
    "event_id",
    "book",
    "market",
    "selection",
    "price",
    "line",
    "ts",
    "source_raw",
]

_ODDS_TICKS_REQUIRED: frozenset[str] = frozenset(
    {"sport", "event_id", "book", "market", "selection", "price", "ts"}
)

_INJURIES_COLUMNS: list[str] = [
    "sport",
    "player_id",
    "player_name",
    "team",
    "position",
    "status",
    "detail",
    "ts",
    "source_raw",
]

_INJURIES_REQUIRED: frozenset[str] = frozenset(
    {"sport", "player_id", "player_name", "team", "status", "ts"}
)

_POLLER_LOGS_COLUMNS: list[str] = [
    "poller_name",
    "run_id",
    "level",
    "message",
]


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────---------------


def _parse_source_raw(value: Any) -> str | None:
    """Normalise *source_raw* to a JSON string for JSONB insertion via COPY.

    asyncpg's ``copy_records_to_table`` uses the PostgreSQL COPY protocol, which
    requires JSONB values as **JSON-encoded strings** — not Python dicts.  This
    is the opposite of parameterised queries where asyncpg accepts dicts directly.

    If *value* is a dict it is serialised via :func:`json.dumps`.  If it is a
    string it is assumed to already be JSON (or passed through as-is if parsing
    fails).  ``None`` is returned as-is (the column is nullable).
    """
    if value is None:
        return None
    if isinstance(value, dict):
        return json.dumps(value)
    if isinstance(value, str):
        try:
            # Validate that it's valid JSON, then return the original string
            json.loads(value)
            return value
        except (json.JSONDecodeError, TypeError):
            # Not valid JSON — wrap it as a JSON string value
            return json.dumps(value)
    return json.dumps(value)


def _coerce_timestamp(value: Any) -> datetime | str:
    """Coerce a timestamp value to a :class:`datetime` for asyncpg.

    asyncpg requires a :class:`~datetime.datetime` instance for TIMESTAMPTZ
    columns.  The poller sources emit ISO-8601 strings (via
    :func:`~quantitative_sports.util.time_utils.utc_now_iso`), so we parse those here.
    If *value* is already a ``datetime`` it passes through unchanged.
    If parsing fails the original value is returned — asyncpg will raise a
    type error that the caller can catch.
    """
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        # Try standard ISO 8601 parsing.  Python 3.11+ supports Z suffix
        # natively; for older versions we handle it manually.
        try:
            # Handle trailing 'Z' → '+00:00'
            normalised = value.replace("Z", "+00:00")
            return datetime.fromisoformat(normalised)
        except (ValueError, TypeError):
            return value
    return value


# ──────────────────────────────────────────────
# Public API — odds_ticks
# ──────────────────────────────────────────────


async def write_odds_ticks(pool: DatabasePool, rows: list[dict[str, Any]]) -> int:
    """Bulk-insert odds tick rows into the ``odds_ticks`` hypertable.

    Uses the PostgreSQL ``COPY`` protocol for maximum throughput.  Rows missing
    any of the required fields (``sport``, ``event_id``, ``book``, ``market``,
    ``selection``, ``price``, ``ts``) are silently skipped with a WARNING log.

    The ``source_raw`` field is automatically converted from a JSON string to a
    Python dict when necessary — asyncpg requires a dict for JSONB columns.

    Args:
        pool: A connected :class:`~quantitative_sports.infra.db.connection.DatabasePool`.
        rows: List of dicts with keys matching the ``odds_ticks`` column names.

    Returns:
        The number of rows actually written to the database.
    """
    if not rows:
        return 0

    valid_records: list[tuple[Any, ...]] = []
    skipped = 0

    for row in rows:
        # Check required fields
        missing = _ODDS_TICKS_REQUIRED - row.keys()
        # Also check for None / empty-string required values
        has_empty = any(
            row.get(key) is None or row.get(key) == "" for key in _ODDS_TICKS_REQUIRED if key in row
        )
        if missing:
            skipped += 1
            logger.warning(
                "Skipping odds_ticks row: missing required fields %s",
                missing,
            )
            continue
        if has_empty:
            skipped += 1
            logger.warning("Skipping odds_ticks row: required field is empty/None")
            continue

        valid_records.append(
            (
                row["sport"],
                row.get("league", ""),
                row["event_id"],
                row["book"],
                row["market"],
                row["selection"],
                int(row["price"]),
                row.get("line"),
                _coerce_timestamp(row["ts"]),
                _parse_source_raw(row.get("source_raw")),
            )
        )

    if skipped:
        logger.warning(
            "write_odds_ticks: skipped %d of %d rows due to missing fields",
            skipped,
            len(rows),
        )

    if not valid_records:
        logger.warning("write_odds_ticks: no valid rows to insert")
        return 0

    try:
        await pool.copy_records_to_table(
            "odds_ticks",
            records=valid_records,
            columns=_ODDS_TICKS_COLUMNS,
        )
    except Exception:
        logger.exception("write_odds_ticks: COPY failed")
        raise

    logger.info("write_odds_ticks: inserted %d rows", len(valid_records))
    return len(valid_records)


# ──────────────────────────────────────────────
# Public API — injuries
# ──────────────────────────────────────────────


async def write_injuries(pool: DatabasePool, rows: list[dict[str, Any]]) -> int:
    """Bulk-insert injury rows into the ``injuries`` hypertable.

    Uses the PostgreSQL ``COPY`` protocol for maximum throughput.  Rows missing
    any of the required fields (``sport``, ``player_id``, ``player_name``,
    ``team``, ``status``, ``ts``) are silently skipped with a WARNING log.

    The ``position`` and ``detail`` columns are nullable — ``None`` is fine.
    The ``source_raw`` field is automatically converted from a JSON string to a
    Python dict when necessary.

    Args:
        pool: A connected :class:`~quantitative_sports.infra.db.connection.DatabasePool`.
        rows: List of dicts with keys matching the ``injuries`` column names.

    Returns:
        The number of rows actually written to the database.
    """
    if not rows:
        return 0

    valid_records: list[tuple[Any, ...]] = []
    skipped = 0

    for row in rows:
        missing = _INJURIES_REQUIRED - row.keys()
        has_empty = any(
            row.get(key) is None or row.get(key) == "" for key in _INJURIES_REQUIRED if key in row
        )
        if missing:
            skipped += 1
            logger.warning(
                "Skipping injuries row: missing required fields %s",
                missing,
            )
            continue
        if has_empty:
            skipped += 1
            logger.warning("Skipping injuries row: required field is empty/None")
            continue

        valid_records.append(
            (
                row["sport"],
                row["player_id"],
                row["player_name"],
                row["team"],
                row.get("position"),
                row["status"],
                row.get("detail"),
                _coerce_timestamp(row["ts"]),
                _parse_source_raw(row.get("source_raw")),
            )
        )

    if skipped:
        logger.warning(
            "write_injuries: skipped %d of %d rows due to missing fields",
            skipped,
            len(rows),
        )

    if not valid_records:
        logger.warning("write_injuries: no valid rows to insert")
        return 0

    try:
        await pool.copy_records_to_table(
            "injuries",
            records=valid_records,
            columns=_INJURIES_COLUMNS,
        )
    except Exception:
        logger.exception("write_injuries: COPY failed")
        raise

    logger.info("write_injuries: inserted %d rows", len(valid_records))
    return len(valid_records)


# ──────────────────────────────────────────────
# Public API — poller_runs
# ──────────────────────────────────────────────


async def write_poller_run_start(
    pool: DatabasePool,
    poller_name: str,
    source: str = "",
    sport: str = "",
) -> int:
    """Insert a new ``poller_runs`` row with ``status='running'``.

    The poller calls this at the start of each cycle, then updates the row
    with :func:`write_poller_run_finish` when done.

    Args:
        pool: A connected :class:`~quantitative_sports.infra.db.connection.DatabasePool`.
        poller_name: Identifier for the poller instance (e.g. ``"odds_api_nfl"``).
        source: Data source label (e.g. ``"odds_api"``). Defaults to empty string.
        sport: Sport filter for this run (e.g. ``"nfl"``). Defaults to empty string.

    Returns:
        The ``id`` of the newly created run row.
    """
    run_id: int = await pool.fetchval(
        """
        INSERT INTO poller_runs (poller_name, started_at, status, source, sport)
        VALUES ($1, NOW(), 'running', $2, $3)
        RETURNING id
        """,
        poller_name,
        source,
        sport,
    )
    logger.info("write_poller_run_start: created run %d for %s", run_id, poller_name)
    return run_id


async def write_poller_run_finish(
    pool: DatabasePool,
    run_id: int,
    status: str,
    rows_written: int,
    error: str | None = None,
) -> None:
    """Update a ``poller_runs`` row with completion details.

    Args:
        pool: A connected :class:`~quantitative_sports.infra.db.connection.DatabasePool`.
        run_id: The ``id`` returned by :func:`write_poller_run_start`.
        status: Final status — typically ``"success"`` or ``"failed"``.
        rows_written: Number of rows written during this run.
        error: Error message if the run failed, or ``None``.
    """
    await pool.execute(
        """
        UPDATE poller_runs
        SET finished_at = NOW(),
            status = $2,
            rows_written = $3,
            error = $4
        WHERE id = $1
        """,
        run_id,
        status,
        rows_written,
        error,
    )
    logger.info(
        "write_poller_run_finish: run %d → status=%s rows_written=%d",
        run_id,
        status,
        rows_written,
    )


# ──────────────────────────────────────────────
# Public API — poller_health
# ──────────────────────────────────────────────


async def update_poller_health(
    pool: DatabasePool,
    poller_name: str,
    status: str,
    last_run_id: int | None = None,
    consecutive_failures: int | None = None,
) -> None:
    """Upsert a row into ``poller_health``.

    On conflict (``poller_name`` already exists), updates ``last_heartbeat``,
    ``status``, ``last_run_id`` (if provided), and ``consecutive_failures``
    (if provided).  On insert, sets sensible defaults.

    Args:
        pool: A connected :class:`~quantitative_sports.infra.db.connection.DatabasePool`.
        poller_name: Unique identifier for the poller instance.
        status: Health status — one of ``"healthy"``, ``"degraded"``, ``"down"``,
            ``"unknown"``.
        last_run_id: Optional ``poller_runs.id`` to link to.
        consecutive_failures: Optional failure count to set explicitly.
    """
    # Build the UPDATE clause conditionally — only set last_run_id and
    # consecutive_failures if the caller provided them (COALESCE keeps the
    # existing value when NULL is passed).
    await pool.execute(
        """
        INSERT INTO poller_health (poller_name, last_heartbeat, status, last_run_id, consecutive_failures)
        VALUES ($1, NOW(), $2, $3, $4)
        ON CONFLICT (poller_name)
        DO UPDATE SET
            last_heartbeat      = NOW(),
            status              = $2,
            last_run_id         = COALESCE($3, poller_health.last_run_id),
            consecutive_failures = COALESCE($4, poller_health.consecutive_failures),
            updated_at           = NOW()
        """,
        poller_name,
        status,
        last_run_id,
        consecutive_failures,
    )
    logger.info(
        "update_poller_health: %s → status=%s run_id=%s failures=%s",
        poller_name,
        status,
        last_run_id,
        consecutive_failures,
    )


# ──────────────────────────────────────────────
# Public API — poller_logs
# ──────────────────────────────────────────────


async def write_poller_log(
    pool: DatabasePool,
    poller_name: str,
    run_id: int,
    level: str,
    message: str,
) -> None:
    """Insert a single log row into ``poller_logs``.

    For bulk logging, prefer :func:`write_poller_logs_batch` which uses the
    COPY protocol for higher throughput.

    Args:
        pool: A connected :class:`~quantitative_sports.infra.db.connection.DatabasePool`.
        poller_name: Identifier for the poller instance.
        run_id: The ``poller_runs.id`` this log belongs to.
        level: Log level — e.g. ``"INFO"``, ``"WARNING"``, ``"ERROR"``.
        message: The log message text.
    """
    await pool.execute(
        """
        INSERT INTO poller_logs (poller_name, run_id, level, message)
        VALUES ($1, $2, $3, $4)
        """,
        poller_name,
        run_id,
        level,
        message,
    )
    logger.debug("write_poller_log: %s/%s [%s] %s", poller_name, run_id, level, message)


async def write_poller_logs_batch(
    pool: DatabasePool,
    poller_name: str,
    run_id: int,
    logs: list[tuple[str, str]],
) -> int:
    """Bulk-insert log rows into ``poller_logs`` using the COPY protocol.

    Each tuple in *logs* is ``(level, message)``.  The *poller_name* and
    *run_id* are applied to every row.

    Args:
        pool: A connected :class:`~quantitative_sports.infra.db.connection.DatabasePool`.
        poller_name: Identifier for the poller instance.
        run_id: The ``poller_runs.id`` these logs belong to.
        logs: List of ``(level, message)`` tuples.

    Returns:
        The number of log rows written.
    """
    if not logs:
        return 0

    records: list[tuple[Any, ...]] = [
        (poller_name, run_id, level, message) for level, message in logs
    ]

    try:
        await pool.copy_records_to_table(
            "poller_logs",
            records=records,
            columns=_POLLER_LOGS_COLUMNS,
        )
    except Exception:
        logger.exception("write_poller_logs_batch: COPY failed")
        raise

    logger.info("write_poller_logs_batch: inserted %d log rows", len(records))
    return len(records)
