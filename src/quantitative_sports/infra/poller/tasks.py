"""Poller task orchestration for Quant-Sports v0.2.0.

Provides self-contained async functions that execute one full work cycle for a
single poller source.  Each task follows the same pattern:

1. Open a database pool (or reuse the singleton).
2. Insert a ``poller_runs`` row with ``status='running'``.
3. Fetch and parse data from the upstream source.
4. Write the parsed rows to the database.
5. Update the run row with final status and row count.
6. Upsert the ``poller_health`` row (healthy / degraded / down).
7. Return a :class:`TaskResult` summarising the cycle.

Error handling
--------------
Source-specific exceptions (e.g. :class:`OddsAPIError`,
:class:`ESPNInjuriesError`) and catch-all exceptions are trapped inside each
task so that one failing poller never kills the others.  On failure the run
row is marked ``status='failed'``, health is set to ``'degraded'`` (or
``'down'`` after repeated failures), and the error message is captured in the
:class:`TaskResult`.

These functions are **plain async callables** — they are *not* Prefect tasks.
The :mod:`~quantitative_sports.infra.poller.flows` module (Wave 2) will wrap them as
Prefect tasks/flows; :mod:`~quantitative_sports.infra.poller.cron_fallback` will call
them in a loop.
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass, field
from typing import Optional

from quantitative_sports.infra.db.connection import DatabasePool, get_pool
from quantitative_sports.infra.db.writers import (
    update_poller_health,
    write_injuries,
    write_odds_ticks,
    write_poller_run_finish,
    write_poller_run_start,
)
from quantitative_sports.infra.poller.config import (
    PollerConfig,
    get_active_sports,
    is_espn_enabled,
    is_odds_api_enabled,
)
from quantitative_sports.infra.poller.sources.espn_injuries import (
    ESPNInjuriesError,
    fetch_and_parse as espn_fetch_and_parse,
)
from quantitative_sports.infra.poller.sources.odds_api import (
    OddsAPIError,
    fetch_and_parse as odds_api_fetch_and_parse,
)
from quantitative_sports.util.time_utils import utc_now_iso

logger = logging.getLogger(__name__)

__all__ = [
    "TaskResult",
    "run_odds_api_poll",
    "run_espn_poll",
    "run_health_check",
    "run_poll_cycle",
]

# ──────────────────────────────────────────────
# Failure threshold — 3 consecutive failures → "down"
# ──────────────────────────────────────────────

_DOWN_THRESHOLD: int = 3


# ──────────────────────────────────────────────
# Result dataclass
# ──────────────────────────────────────────────


@dataclass(frozen=True)
class TaskResult:
    """Summary of a single poller task cycle.

    Attributes:
        poller_name: Identifier for the poller (e.g. ``"odds_api_nfl"``).
        status: ``"success"`` or ``"failed"``.
        rows_written: Number of rows written to the database.
        started_at: ISO 8601 timestamp when the cycle started.
        finished_at: ISO 8601 timestamp when the cycle finished.
        duration_seconds: Wall-clock duration of the cycle.
        error: Error message if the cycle failed, otherwise ``None``.
    """

    poller_name: str
    status: str
    rows_written: int
    started_at: str
    finished_at: str
    duration_seconds: float
    error: Optional[str] = field(default=None)

    def to_dict(self) -> dict[str, object]:
        """Serialise the result to a plain dict.

        Returns:
            A JSON-compatible dictionary representation.
        """
        return asdict(self)


# ──────────────────────────────────────────────
# Health helpers
# ──────────────────────────────────────────────


async def _get_consecutive_failures(pool: DatabasePool, poller_name: str) -> int:
    """Query the current consecutive failure count for a poller.

    Args:
        pool: A connected :class:`~quantitative_sports.infra.db.connection.DatabasePool`.
        poller_name: Identifier for the poller instance.

    Returns:
        The current consecutive failure count, or 0 if no row exists.
    """
    row = await pool.fetchrow(
        "SELECT consecutive_failures FROM poller_health WHERE poller_name = $1",
        poller_name,
    )
    if row is None:
        return 0
    return int(row["consecutive_failures"])


def _compute_health_status(consecutive_failures: int) -> str:
    """Determine the health status string from the failure count.

    Args:
        consecutive_failures: Number of consecutive failures.

    Returns:
        ``"down"`` if failures exceed the threshold, ``"degraded"`` if there
        is at least one failure, or ``"healthy"`` for zero failures.
    """
    if consecutive_failures >= _DOWN_THRESHOLD:
        return "down"
    if consecutive_failures > 0:
        return "degraded"
    return "healthy"


# ──────────────────────────────────────────────
# Odds API poll cycle
# ──────────────────────────────────────────────


async def run_odds_api_poll(config: PollerConfig, sport: str) -> TaskResult:
    """Execute one Odds API poll cycle for a single sport.

    Opens a database pool, fetches odds from the Odds API, writes the parsed
    ticks to the ``odds_ticks`` hypertable, and updates run/health metadata.

    Args:
        config: Fully populated :class:`~quantitative_sports.infra.poller.config.PollerConfig`.
        sport: Sport key (e.g. ``"nfl"``, ``"nba"``).

    Returns:
        A :class:`TaskResult` summarising the cycle.  The task never raises —
        errors are captured in the result.
    """
    poller_name = f"odds_api_{sport}"
    started_at = utc_now_iso()
    start = time.monotonic()

    pool: DatabasePool | None = None
    run_id: int | None = None

    try:
        pool = await get_pool(config.db)
        run_id = await write_poller_run_start(pool, poller_name, source="odds_api", sport=sport)

        ticks = await odds_api_fetch_and_parse(sport, config.odds_api)
        rows_written = await write_odds_ticks(pool, ticks)

        finished_at = utc_now_iso()
        duration = time.monotonic() - start

        await write_poller_run_finish(pool, run_id, status="success", rows_written=rows_written)
        await update_poller_health(
            pool, poller_name, status="healthy", last_run_id=run_id, consecutive_failures=0
        )

        logger.info(
            "run_odds_api_poll: %s success — %d rows in %.2fs",
            poller_name,
            rows_written,
            duration,
        )

        return TaskResult(
            poller_name=poller_name,
            status="success",
            rows_written=rows_written,
            started_at=started_at,
            finished_at=finished_at,
            duration_seconds=round(duration, 3),
            error=None,
        )

    except OddsAPIError as exc:
        finished_at = utc_now_iso()
        duration = time.monotonic() - start
        error_msg = str(exc)
        logger.error("run_odds_api_poll: %s OddsAPIError — %s", poller_name, error_msg)

        if pool is not None and run_id is not None:
            await write_poller_run_finish(
                pool, run_id, status="failed", rows_written=0, error=error_msg
            )
            prev_failures = await _get_consecutive_failures(pool, poller_name)
            new_failures = prev_failures + 1
            await update_poller_health(
                pool,
                poller_name,
                status=_compute_health_status(new_failures),
                last_run_id=run_id,
                consecutive_failures=new_failures,
            )

        return TaskResult(
            poller_name=poller_name,
            status="failed",
            rows_written=0,
            started_at=started_at,
            finished_at=finished_at,
            duration_seconds=round(duration, 3),
            error=error_msg,
        )

    except Exception as exc:
        finished_at = utc_now_iso()
        duration = time.monotonic() - start
        error_msg = f"{type(exc).__name__}: {exc}"
        logger.exception("run_odds_api_poll: %s unexpected error", poller_name)

        if pool is not None and run_id is not None:
            await write_poller_run_finish(
                pool, run_id, status="failed", rows_written=0, error=error_msg
            )
            prev_failures = await _get_consecutive_failures(pool, poller_name)
            new_failures = prev_failures + 1
            await update_poller_health(
                pool,
                poller_name,
                status=_compute_health_status(new_failures),
                last_run_id=run_id,
                consecutive_failures=new_failures,
            )

        return TaskResult(
            poller_name=poller_name,
            status="failed",
            rows_written=0,
            started_at=started_at,
            finished_at=finished_at,
            duration_seconds=round(duration, 3),
            error=error_msg,
        )


# ──────────────────────────────────────────────
# ESPN injuries poll cycle
# ──────────────────────────────────────────────


async def run_espn_poll(config: PollerConfig, sport: str) -> TaskResult:
    """Execute one ESPN injuries poll cycle for a single sport.

    Opens a database pool, fetches injury data from the ESPN site API, writes
    the parsed rows to the ``injuries`` hypertable, and updates run/health
    metadata.

    Args:
        config: Fully populated :class:`~quantitative_sports.infra.poller.config.PollerConfig`.
        sport: Sport slug (e.g. ``"nfl"``, ``"nba"``).

    Returns:
        A :class:`TaskResult` summarising the cycle.  The task never raises —
        errors are captured in the result.
    """
    poller_name = f"espn_injuries_{sport}"
    started_at = utc_now_iso()
    start = time.monotonic()

    pool: DatabasePool | None = None
    run_id: int | None = None

    try:
        pool = await get_pool(config.db)
        run_id = await write_poller_run_start(pool, poller_name, source="espn", sport=sport)

        rows = await espn_fetch_and_parse(sport, config.espn)
        rows_written = await write_injuries(pool, rows)

        finished_at = utc_now_iso()
        duration = time.monotonic() - start

        await write_poller_run_finish(pool, run_id, status="success", rows_written=rows_written)
        await update_poller_health(
            pool, poller_name, status="healthy", last_run_id=run_id, consecutive_failures=0
        )

        logger.info(
            "run_espn_poll: %s success — %d rows in %.2fs",
            poller_name,
            rows_written,
            duration,
        )

        return TaskResult(
            poller_name=poller_name,
            status="success",
            rows_written=rows_written,
            started_at=started_at,
            finished_at=finished_at,
            duration_seconds=round(duration, 3),
            error=None,
        )

    except ESPNInjuriesError as exc:
        finished_at = utc_now_iso()
        duration = time.monotonic() - start
        error_msg = str(exc)
        logger.error("run_espn_poll: %s ESPNInjuriesError — %s", poller_name, error_msg)

        if pool is not None and run_id is not None:
            await write_poller_run_finish(
                pool, run_id, status="failed", rows_written=0, error=error_msg
            )
            prev_failures = await _get_consecutive_failures(pool, poller_name)
            new_failures = prev_failures + 1
            await update_poller_health(
                pool,
                poller_name,
                status=_compute_health_status(new_failures),
                last_run_id=run_id,
                consecutive_failures=new_failures,
            )

        return TaskResult(
            poller_name=poller_name,
            status="failed",
            rows_written=0,
            started_at=started_at,
            finished_at=finished_at,
            duration_seconds=round(duration, 3),
            error=error_msg,
        )

    except Exception as exc:
        finished_at = utc_now_iso()
        duration = time.monotonic() - start
        error_msg = f"{type(exc).__name__}: {exc}"
        logger.exception("run_espn_poll: %s unexpected error", poller_name)

        if pool is not None and run_id is not None:
            await write_poller_run_finish(
                pool, run_id, status="failed", rows_written=0, error=error_msg
            )
            prev_failures = await _get_consecutive_failures(pool, poller_name)
            new_failures = prev_failures + 1
            await update_poller_health(
                pool,
                poller_name,
                status=_compute_health_status(new_failures),
                last_run_id=run_id,
                consecutive_failures=new_failures,
            )

        return TaskResult(
            poller_name=poller_name,
            status="failed",
            rows_written=0,
            started_at=started_at,
            finished_at=finished_at,
            duration_seconds=round(duration, 3),
            error=error_msg,
        )


# ──────────────────────────────────────────────
# Health check cycle
# ──────────────────────────────────────────────


async def run_health_check(config: PollerConfig) -> TaskResult:
    """Update heartbeat for all known pollers.

    Iterates over every poller name derived from the active sports list and
    upserts a ``poller_health`` row with status ``"healthy"``.  This is a
    lightweight tick that does not fetch any upstream data.

    Args:
        config: Fully populated :class:`~quantitative_sports.infra.poller.config.PollerConfig`.

    Returns:
        A :class:`TaskResult` summarising the cycle.
    """
    started_at = utc_now_iso()
    start = time.monotonic()
    active_sports = get_active_sports(config)

    poller_names = [f"odds_api_{s}" for s in active_sports] + [
        f"espn_injuries_{s}" for s in active_sports
    ]

    try:
        pool = await get_pool(config.db)
        for name in poller_names:
            await update_poller_health(pool, name, status="healthy")

        finished_at = utc_now_iso()
        duration = time.monotonic() - start

        logger.info(
            "run_health_check: updated %d pollers in %.2fs",
            len(poller_names),
            duration,
        )

        return TaskResult(
            poller_name="health_check",
            status="success",
            rows_written=len(poller_names),
            started_at=started_at,
            finished_at=finished_at,
            duration_seconds=round(duration, 3),
            error=None,
        )

    except Exception as exc:
        finished_at = utc_now_iso()
        duration = time.monotonic() - start
        error_msg = f"{type(exc).__name__}: {exc}"
        logger.exception("run_health_check: unexpected error")

        return TaskResult(
            poller_name="health_check",
            status="failed",
            rows_written=0,
            started_at=started_at,
            finished_at=finished_at,
            duration_seconds=round(duration, 3),
            error=error_msg,
        )


# ──────────────────────────────────────────────
# Full poll cycle
# ──────────────────────────────────────────────


async def run_poll_cycle(config: PollerConfig) -> list[TaskResult]:
    """Run all enabled pollers once and return their results.

    Iterates through the active sports list and runs the Odds API and/or
    ESPN poller for each sport, depending on which sources are enabled.
    Always finishes with a health check.  Each task is wrapped in its own
    try/except so that a single failure does not prevent the others from
    running.

    Args:
        config: Fully populated :class:`~quantitative_sports.infra.poller.config.PollerConfig`.

    Returns:
        A list of :class:`TaskResult` objects — one per poller plus the
        health check.
    """
    results: list[TaskResult] = []
    active_sports = get_active_sports(config)

    # Odds API — one task per active sport
    if is_odds_api_enabled(config):
        for sport in active_sports:
            try:
                result = await run_odds_api_poll(config, sport)
                results.append(result)
            except Exception:
                # Should not happen (run_odds_api_poll catches all errors),
                # but guard against programming errors.
                logger.exception("run_poll_cycle: odds_api_%s raised unexpectedly", sport)
    else:
        logger.info("run_poll_cycle: Odds API source disabled — skipping")

    # ESPN injuries — one task per active sport
    if is_espn_enabled(config):
        for sport in active_sports:
            try:
                result = await run_espn_poll(config, sport)
                results.append(result)
            except Exception:
                logger.exception("run_poll_cycle: espn_injuries_%s raised unexpectedly", sport)
    else:
        logger.info("run_poll_cycle: ESPN source disabled — skipping")

    # Health check — always runs
    try:
        health_result = await run_health_check(config)
        results.append(health_result)
    except Exception:
        logger.exception("run_poll_cycle: health_check raised unexpectedly")

    # Summary log
    succeeded = sum(1 for r in results if r.status == "success")
    failed = sum(1 for r in results if r.status == "failed")
    logger.info(
        "run_poll_cycle: complete — %d tasks, %d success, %d failed",
        len(results),
        succeeded,
        failed,
    )

    return results
