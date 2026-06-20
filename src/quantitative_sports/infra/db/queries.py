"""Async read-side query helpers for the Quant-Sports web UI.

Mirrors the write-side layer in :mod:`~quantitative_sports.infra.db.writers` —
every function here is a ``SELECT`` (or ``REFRESH MATERIALIZED VIEW``) that
the Phase 3 web routes call to render Jinja2 templates for poller status,
run history, metrics, and log tails.

All functions are ``async def`` and accept a
:class:`~quantitative_sports.infra.db.connection.DatabasePool` as their first
argument.  Results are returned as plain dicts (via ``dict(row)`` on
asyncpg Records) so that Jinja2 templates and JSON serialisers can consume
them directly.  Timestamps are converted to ISO-8601 strings for safe
serialisation.  Empty results return ``[]`` (for multi-row queries) or
``{}`` (for single-row queries) — never ``None`` and never raising.
"""

from __future__ import annotations

import logging
from typing import Any

from quantitative_sports.infra.db.connection import DatabasePool

logger = logging.getLogger(__name__)

__all__ = [
    "get_poller_health_summary",
    "get_poller_runs",
    "get_poller_logs",
    "get_table_stats",
    "get_poller_success_rates",
    "get_recent_poll_volume",
    "get_db_size",
    "refresh_db_metrics",
]


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────


def _row_to_dict(row: Any) -> dict[str, Any]:
    """Convert an asyncpg Record to a JSON-serialisable dict.

    Datetime values are converted to ISO-8601 strings.  ``Decimal`` values
    from aggregate functions (e.g. ``AVG``) are converted to ``float``.
    Other types pass through unchanged (asyncpg already returns native
    Python types for integers, floats, strings, and ``None``).
    """
    from decimal import Decimal

    d: dict[str, Any] = dict(row)
    for key, value in d.items():
        if hasattr(value, "isoformat"):
            d[key] = value.isoformat()
        elif isinstance(value, Decimal):
            d[key] = float(value)
    return d


# ──────────────────────────────────────────────
# Public API — poller_health
# ──────────────────────────────────────────────


async def get_poller_health_summary(pool: DatabasePool) -> list[dict[str, Any]]:
    """Return one row per poller, joined with its latest run.

    Each dict contains:

    - ``poller_name``
    - ``status`` (health status: healthy / degraded / down / unknown)
    - ``last_heartbeat`` (ISO-8601)
    - ``consecutive_failures``
    - ``last_run_started_at`` (ISO-8601, or ``None``)
    - ``last_run_status`` (running / success / failed, or ``None``)
    - ``last_run_rows`` (int or ``None``)
    - ``last_run_error`` (str or ``None``)

    Args:
        pool: A connected :class:`~quantitative_sports.infra.db.connection.DatabasePool`.

    Returns:
        A list of dicts ordered by ``poller_name``.
    """
    rows = await pool.fetch(
        """
        SELECT
            ph.poller_name,
            ph.status,
            ph.last_heartbeat,
            ph.consecutive_failures,
            pr.started_at AS last_run_started_at,
            pr.status     AS last_run_status,
            pr.rows_written AS last_run_rows,
            pr.error      AS last_run_error
        FROM poller_health ph
        LEFT JOIN LATERAL (
            SELECT *
            FROM poller_runs
            WHERE poller_name = ph.poller_name
            ORDER BY started_at DESC
            LIMIT 1
        ) pr ON true
        ORDER BY ph.poller_name
        """
    )
    return [_row_to_dict(row) for row in rows]


# ──────────────────────────────────────────────
# Public API — poller_runs
# ──────────────────────────────────────────────


async def get_poller_runs(
    pool: DatabasePool,
    poller_name: str,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Return recent run history for a single poller.

    Args:
        pool: A connected :class:`~quantitative_sports.infra.db.connection.DatabasePool`.
        poller_name: The poller to query (e.g. ``"odds_api_nfl"``).
        limit: Maximum rows to return.  Defaults to 50.

    Returns:
        A list of dicts ordered by ``started_at`` descending.
    """
    rows = await pool.fetch(
        """
        SELECT
            id, poller_name, started_at, finished_at,
            status, rows_written, error, source, sport
        FROM poller_runs
        WHERE poller_name = $1
        ORDER BY started_at DESC
        LIMIT $2
        """,
        poller_name,
        limit,
    )
    return [_row_to_dict(row) for row in rows]


# ──────────────────────────────────────────────
# Public API — poller_logs
# ──────────────────────────────────────────────


async def get_poller_logs(
    pool: DatabasePool,
    poller_name: str,
    limit: int = 100,
    since_id: int = 0,
) -> list[dict[str, Any]]:
    """Return log lines for a poller, optionally starting after a given ID.

    The web UI polls for new log lines by passing the last-seen ``id`` as
    ``since_id``, so only incremental lines are fetched.

    Args:
        pool: A connected :class:`~quantitative_sports.infra.db.connection.DatabasePool`.
        poller_name: The poller to query.
        limit: Maximum rows to return.  Defaults to 100.
        since_id: Only return rows with ``id > since_id``.  Defaults to 0
            (return all).

    Returns:
        A list of dicts ordered by ``id`` ascending.
    """
    rows = await pool.fetch(
        """
        SELECT id, poller_name, run_id, level, message, ts
        FROM poller_logs
        WHERE poller_name = $1
          AND id > $2
        ORDER BY id ASC
        LIMIT $3
        """,
        poller_name,
        since_id,
        limit,
    )
    return [_row_to_dict(row) for row in rows]


# ──────────────────────────────────────────────
# Public API — table stats / metrics
# ──────────────────────────────────────────────


async def get_table_stats(pool: DatabasePool) -> list[dict[str, Any]]:
    """Return per-table row counts, 24h deltas, timestamp bounds, and disk sizes.

    Combines the ``db_metrics`` materialised view with
    ``pg_total_relation_size`` for human-readable disk sizes.

    Each dict contains:

    - ``table_name``
    - ``total_rows``
    - ``rows_24h``
    - ``oldest_ts`` (ISO-8601 or ``None``)
    - ``newest_ts`` (ISO-8601 or ``None``)
    - ``size_pretty`` (e.g. ``"128 MB"``)

    Args:
        pool: A connected :class:`~quantitative_sports.infra.db.connection.DatabasePool`.

    Returns:
        A list of dicts ordered by ``table_name``.
    """
    rows = await pool.fetch(
        """
        SELECT
            dm.table_name,
            dm.total_rows,
            dm.rows_24h,
            dm.oldest_ts,
            dm.newest_ts,
            pg_size_pretty(
                pg_total_relation_size(dm.table_name::regclass)
            ) AS size_pretty
        FROM db_metrics dm
        ORDER BY dm.table_name
        """
    )
    return [_row_to_dict(row) for row in rows]


# ──────────────────────────────────────────────
# Public API — success rates
# ──────────────────────────────────────────────


async def get_poller_success_rates(
    pool: DatabasePool,
    hours: int = 24,
) -> list[dict[str, Any]]:
    """Return success-rate statistics per poller for the last *hours*.

    Each dict contains:

    - ``poller_name``
    - ``total_runs``
    - ``successful_runs``
    - ``failed_runs``
    - ``success_rate`` (float 0–1)
    - ``avg_duration_seconds`` (float or ``None``)
    - ``total_rows_written``

    Args:
        pool: A connected :class:`~quantitative_sports.infra.db.connection.DatabasePool`.
        hours: Look-back window in hours.  Defaults to 24.

    Returns:
        A list of dicts ordered by ``poller_name``.
    """
    rows = await pool.fetch(
        """
        SELECT
            poller_name,
            COUNT(*)                                AS total_runs,
            COUNT(*) FILTER (WHERE status = 'success') AS successful_runs,
            COUNT(*) FILTER (WHERE status = 'failed')  AS failed_runs,
            CASE WHEN COUNT(*) > 0
                 THEN COUNT(*) FILTER (WHERE status = 'success')::float / COUNT(*)
                 ELSE 0
            END                                    AS success_rate,
            AVG(
                EXTRACT(EPOCH FROM (finished_at - started_at))
            ) FILTER (WHERE finished_at IS NOT NULL) AS avg_duration_seconds,
            COALESCE(SUM(rows_written), 0)          AS total_rows_written
        FROM poller_runs
        WHERE started_at > NOW() - ($1 || ' hours')::INTERVAL
        GROUP BY poller_name
        ORDER BY poller_name
        """,
        str(hours),
    )
    return [_row_to_dict(row) for row in rows]


# ──────────────────────────────────────────────
# Public API — pull volume
# ──────────────────────────────────────────────


async def get_recent_poll_volume(
    pool: DatabasePool,
    hours: int = 24,
) -> list[dict[str, Any]]:
    """Return rows-written volume per source per hour for the last *hours*.

    Each dict contains:

    - ``bucket`` (ISO-8601 truncated hour)
    - ``source``
    - ``total_rows``

    Args:
        pool: A connected :class:`~quantitative_sports.infra.db.connection.DatabasePool`.
        hours: Look-back window in hours.  Defaults to 24.

    Returns:
        A list of dicts ordered by ``bucket`` ascending then ``source``.
    """
    rows = await pool.fetch(
        """
        SELECT
            date_trunc('hour', started_at) AS bucket,
            source,
            SUM(rows_written) AS total_rows
        FROM poller_runs
        WHERE started_at > NOW() - ($1 || ' hours')::INTERVAL
        GROUP BY 1, 2
        ORDER BY 1, 2
        """,
        str(hours),
    )
    return [_row_to_dict(row) for row in rows]


# ──────────────────────────────────────────────
# Public API — database size
# ──────────────────────────────────────────────


async def get_db_size(pool: DatabasePool) -> dict[str, Any]:
    """Return total database size and per-table sizes.

    Returns a dict with:

    - ``database_size_pretty`` — e.g. ``"1.2 GB"``
    - ``table_sizes`` — list of dicts with ``table_name``, ``size_pretty``,
      and ``row_estimate``

    Args:
        pool: A connected :class:`~quantitative_sports.infra.db.connection.DatabasePool`.

    Returns:
        A dict with ``database_size_pretty`` and ``table_sizes``.
    """
    db_size_row = await pool.fetchrow(
        "SELECT pg_size_pretty(pg_database_size(current_database())) AS database_size_pretty"
    )
    database_size_pretty: str = db_size_row["database_size_pretty"] if db_size_row else "unknown"

    table_rows = await pool.fetch(
        """
        SELECT
            c.relname AS table_name,
            pg_size_pretty(pg_total_relation_size(c.oid)) AS size_pretty,
            COALESCE(s.n_live_tup, 0) AS row_estimate
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        LEFT JOIN pg_stat_user_tables s ON s.relid = c.oid
        WHERE n.nspname = 'public'
          AND c.relkind = 'r'
        ORDER BY c.relname
        """
    )

    table_sizes = [
        {
            "table_name": row["table_name"],
            "size_pretty": row["size_pretty"],
            "row_estimate": row["row_estimate"],
        }
        for row in table_rows
    ]

    return {
        "database_size_pretty": database_size_pretty,
        "table_sizes": table_sizes,
    }


# ──────────────────────────────────────────────
# Public API — refresh materialised view
# ──────────────────────────────────────────────


async def refresh_db_metrics(pool: DatabasePool) -> None:
    """Refresh the ``db_metrics`` materialised view.

    Call this from the web UI metrics page when data is stale.  Uses
    ``CONCURRENTLY`` so readers are not blocked.

    Args:
        pool: A connected :class:`~quantitative_sports.infra.db.connection.DatabasePool`.
    """
    await pool.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY db_metrics")
    logger.info("Refreshed db_metrics materialised view")
