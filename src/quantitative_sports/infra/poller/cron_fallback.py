"""Cron-style fallback scheduler for Quant-Sports poller.

Runs poller tasks on a fixed interval using a plain ``asyncio`` loop — no
Prefect required.  This is the lightweight scheduling mode activated by
setting ``QUANT_SPORTS_POLLER_SCHEDULER=cron``.

When to use
-----------
Use cron mode when you want **minimal infrastructure** — no Prefect server, no
dashboard, no Docker Compose stack.  The trade-off is no built-in retry
back-off, no live observability, and no per-source interval control.  All
enabled sources are polled together every ``min(odds_api.interval_seconds,
espn.interval_seconds)`` seconds.

How to switch
-------------
Set the environment variable::

    QUANT_SPORTS_POLLER_SCHEDULER=cron

Then start the poller via the ``main.py`` entry point (Wave 3).  The
:func:`run_cron_loop` function is the long-running coroutine that the
entry point will ``asyncio.run()``.
"""

from __future__ import annotations

import asyncio
import logging

from quantitative_sports.infra.poller.config import (
    PollerConfig,
    get_active_sports,
    is_espn_enabled,
    is_odds_api_enabled,
)
from quantitative_sports.infra.poller.tasks import TaskResult, run_poll_cycle

logger = logging.getLogger(__name__)

__all__ = [
    "compute_sleep_interval",
    "format_cycle_summary",
    "run_cron_loop",
]

# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────


def compute_sleep_interval(config: PollerConfig) -> float:
    """Return the minimum configured poll interval in seconds.

    The cron loop sleeps for the shortest interval so that no source waits
    longer than its configured cadence.  If no source is enabled, defaults
    to 60 seconds.

    Args:
        config: Fully populated :class:`PollerConfig` instance.

    Returns:
        The sleep interval in seconds (always > 0).
    """
    intervals: list[float] = []
    if is_odds_api_enabled(config):
        intervals.append(float(config.odds_api.interval_seconds))
    if is_espn_enabled(config):
        intervals.append(float(config.espn.interval_seconds))
    if not intervals:
        return 60.0
    return min(intervals)


def format_cycle_summary(results: list[TaskResult]) -> str:
    """Return a one-line human-readable summary of a poll cycle.

    Example::

        "[ok] 2/3 pollers succeeded, 1247 rows written in 12.3s"

    Args:
        results: The list of :class:`TaskResult` objects from
            :func:`~quantitative_sports.infra.poller.tasks.run_poll_cycle`.

    Returns:
        A formatted summary string suitable for logging.
    """
    succeeded = sum(1 for r in results if r.status == "success")
    total = len(results)
    rows = sum(r.rows_written for r in results)
    duration = sum(r.duration_seconds for r in results)
    tag = "ok" if succeeded == total else "degraded" if succeeded > 0 else "fail"
    return f"[{tag}] {succeeded}/{total} pollers succeeded, {rows} rows written in {duration:.1f}s"


# ──────────────────────────────────────────────
# Main loop
# ──────────────────────────────────────────────


async def run_cron_loop(config: PollerConfig) -> None:
    """Run the poller on a fixed interval in a plain asyncio loop.

    Performs one immediate poll cycle on startup, then sleeps for
    :func:`compute_sleep_interval` seconds between subsequent cycles.
    Exits cleanly on ``KeyboardInterrupt`` or :class:`asyncio.CancelledError`.

    Each individual task inside :func:`run_poll_cycle` already handles its own
    errors (returning a failed :class:`TaskResult`), so the loop continues
    even if one cycle fails entirely.

    Args:
        config: Fully populated :class:`PollerConfig` instance.
    """
    interval = compute_sleep_interval(config)
    active_sports = get_active_sports(config)

    logger.info(
        "run_cron_loop: starting — scheduler=cron, sports=%s, interval=%.0fs",
        ",".join(active_sports),
        interval,
    )

    # ── Immediate first cycle ──────────────────────────────────────────
    try:
        results = await run_poll_cycle(config)
        logger.info("run_cron_loop: initial cycle — %s", format_cycle_summary(results))
    except Exception:
        logger.exception("run_cron_loop: initial cycle failed")

    # ── Main loop ───────────────────────────────────────────────────────
    try:
        while True:
            logger.info("run_cron_loop: sleeping %.0fs until next cycle", interval)
            await asyncio.sleep(interval)

            try:
                results = await run_poll_cycle(config)
                logger.info("run_cron_loop: cycle — %s", format_cycle_summary(results))
            except Exception:
                logger.exception("run_cron_loop: cycle failed")

    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("run_cron_loop: exiting cleanly")
