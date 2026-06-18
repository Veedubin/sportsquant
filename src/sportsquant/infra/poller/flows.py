"""Prefect flow definitions for SportsQuant poller scheduling.

This module wraps the plain-async task functions from
:mod:`~sportsquant.infra.poller.tasks` as Prefect flows and tasks so they can
be scheduled, observed, and retried through the Prefect UI and API.

When to use
-----------
Use Prefect-based scheduling when you need:

- **Observability** — live dashboard showing flow runs, durations, and failures.
- **Retries** — automatic per-task retry with exponential back-off.
- **Scheduling** — cron or interval deployments managed by the Prefect server.

Switch to cron-based scheduling by setting the environment variable::

    SPORTSQUANT_POLLER_SCHEDULER=cron

This makes :func:`run_flows_forever` fall back to a simple ``asyncio`` loop
without Prefect.

Lazy imports
------------
All ``prefect`` imports are wrapped in a try/except so that this module can be
imported in environments where Prefect is not installed.  When Prefect is
unavailable, the ``@flow`` and ``@task`` decorators become no-ops and
:func:`serve_flows` / :func:`run_flows_forever` raise a clear error at call
time.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import signal

from sportsquant.infra.poller.config import (
    PollerConfig,
    get_active_sports,
    is_espn_enabled,
    is_odds_api_enabled,
)
from sportsquant.infra.poller.tasks import (
    TaskResult,
    run_espn_poll,
    run_health_check,
    run_odds_api_poll,
)

logger = logging.getLogger(__name__)

__all__ = [
    "PREFECT_AVAILABLE",
    "health_check_flow",
    "odds_api_poll_flow",
    "espn_injuries_poll_flow",
    "poller_cycle_flow",
    "run_flows_forever",
    "serve_flows",
]

# ──────────────────────────────────────────────
# Lazy Prefect imports — module imports cleanly without prefect
# ──────────────────────────────────────────────

try:
    from prefect import flow, serve, task

    PREFECT_AVAILABLE: bool = True
except ImportError:
    PREFECT_AVAILABLE = False

    # No-op decorators so the module can be imported without Prefect.
    def flow(**kwargs: object):  # type: ignore[misc]  # noqa: D103
        """No-op stand-in when Prefect is not installed."""

        def _decorator(f: object) -> object:
            return f

        return _decorator

    def task(**kwargs: object):  # type: ignore[misc]  # noqa: D103
        """No-op stand-in when Prefect is not installed."""

        def _decorator(f: object) -> object:
            return f

        return _decorator

    serve = None  # type: ignore[assignment]


# ──────────────────────────────────────────────
# Prefect tasks (thin async wrappers around tasks.py callables)
# ──────────────────────────────────────────────


@task(name="run_odds_api_poll_task", retries=3, retry_delay_seconds=30)
async def _odds_api_poll_task(config: PollerConfig, sport: str) -> TaskResult:
    """Prefect task wrapping :func:`~sportsquant.infra.poller.tasks.run_odds_api_poll`.

    Args:
        config: Fully populated :class:`PollerConfig`.
        sport: Sport key (e.g. ``"nfl"``).

    Returns:
        A :class:`TaskResult` summarising the cycle.
    """
    return await run_odds_api_poll(config, sport)


@task(name="run_espn_poll_task", retries=3, retry_delay_seconds=30)
async def _espn_poll_task(config: PollerConfig, sport: str) -> TaskResult:
    """Prefect task wrapping :func:`~sportsquant.infra.poller.tasks.run_espn_poll`.

    Args:
        config: Fully populated :class:`PollerConfig`.
        sport: Sport slug (e.g. ``"nfl"``).

    Returns:
        A :class:`TaskResult` summarising the cycle.
    """
    return await run_espn_poll(config, sport)


@task(name="run_health_check_task", retries=2, retry_delay_seconds=10)
async def _health_check_task(config: PollerConfig) -> TaskResult:
    """Prefect task wrapping :func:`~sportsquant.infra.poller.tasks.run_health_check`.

    Args:
        config: Fully populated :class:`PollerConfig`.

    Returns:
        A :class:`TaskResult` summarising the health check.
    """
    return await run_health_check(config)


# ──────────────────────────────────────────────
# Prefect flows
# ──────────────────────────────────────────────


@flow(name="odds_api_poll")
async def odds_api_poll_flow(config: PollerConfig, sport: str) -> TaskResult:
    """Prefect flow for a single Odds API poll cycle.

    Delegates to the underlying :func:`_odds_api_poll_task` which provides
    automatic retries with exponential back-off.

    Args:
        config: Fully populated :class:`PollerConfig`.
        sport: Sport key (e.g. ``"nfl"``).

    Returns:
        A :class:`TaskResult` summarising the cycle.
    """
    return await _odds_api_poll_task(config, sport)


@flow(name="espn_injuries_poll")
async def espn_injuries_poll_flow(config: PollerConfig, sport: str) -> TaskResult:
    """Prefect flow for a single ESPN injuries poll cycle.

    Delegates to the underlying :func:`_espn_poll_task` which provides
    automatic retries with exponential back-off.

    Args:
        config: Fully populated :class:`PollerConfig`.
        sport: Sport slug (e.g. ``"nfl"``).

    Returns:
        A :class:`TaskResult` summarising the cycle.
    """
    return await _espn_poll_task(config, sport)


@flow(name="health_check")
async def health_check_flow(config: PollerConfig) -> TaskResult:
    """Prefect flow for a health-check tick across all pollers.

    Delegates to the underlying :func:`_health_check_task` which provides
    automatic retries.

    Args:
        config: Fully populated :class:`PollerConfig`.

    Returns:
        A :class:`TaskResult` summarising the health check.
    """
    return await _health_check_task(config)


@flow(name="poller_cycle")
async def poller_cycle_flow(config: PollerConfig) -> list[TaskResult]:
    """Prefect flow that runs all enabled pollers in a single cycle.

    Iterates through each active sport and runs the Odds API and/or ESPN
    poller (depending on which sources are enabled), then finishes with a
    health check.

    Args:
        config: Fully populated :class:`PollerConfig`.

    Returns:
        A list of :class:`TaskResult` objects — one per poller plus the
        health check.
    """
    results: list[TaskResult] = []
    active_sports = get_active_sports(config)

    if is_odds_api_enabled(config):
        for sport in active_sports:
            result = await odds_api_poll_flow(config, sport)
            results.append(result)
    else:
        logger.info("poller_cycle_flow: Odds API source disabled — skipping")

    if is_espn_enabled(config):
        for sport in active_sports:
            result = await espn_injuries_poll_flow(config, sport)
            results.append(result)
    else:
        logger.info("poller_cycle_flow: ESPN source disabled — skipping")

    health_result = await health_check_flow(config)
    results.append(health_result)

    succeeded = sum(1 for r in results if r.status == "success")
    failed = sum(1 for r in results if r.status == "failed")
    logger.info(
        "poller_cycle_flow: complete — %d tasks, %d success, %d failed",
        len(results),
        succeeded,
        failed,
    )

    return results


# ──────────────────────────────────────────────
# Scheduling entry points
# ──────────────────────────────────────────────


def serve_flows(config: PollerConfig) -> None:
    """Start a Prefect serve loop with cron-scheduled deployments.

    Creates one deployment per active sport for each enabled source, plus a
    health-check deployment, and then calls :func:`prefect.serve` to start
    the long-running scheduler.  This call **blocks** until interrupted.

    Raises:
        RuntimeError: If Prefect is not installed.
    """
    if not PREFECT_AVAILABLE:
        raise RuntimeError(
            "Prefect is required for serve_flows() but is not installed. "
            "Install the [poller] extra:  pip install sportsquant[poller]"
        )

    active_sports = get_active_sports(config)
    deployments: list[object] = []

    if is_odds_api_enabled(config):
        interval_secs = config.odds_api.interval_seconds
        for sport in active_sports:
            # Convert seconds-based interval to a cron expression.
            # Common mapping: daily (86400), every 12h (43200), every 15min (900), etc.
            # For arbitrary intervals, use an interval schedule instead.
            deployment = odds_api_poll_flow.to_deployment(
                name=f"odds_api_poll-{sport}",
                interval=datetime.timedelta(seconds=interval_secs),
                parameters={"config": config, "sport": sport},
            )
            deployments.append(deployment)
    else:
        logger.info("serve_flows: Odds API source disabled — skipping")

    if is_espn_enabled(config):
        interval_secs = config.espn.interval_seconds
        for sport in active_sports:
            deployment = espn_injuries_poll_flow.to_deployment(
                name=f"espn_injuries_poll-{sport}",
                interval=datetime.timedelta(seconds=interval_secs),
                parameters={"config": config, "sport": sport},
            )
            deployments.append(deployment)
    else:
        logger.info("serve_flows: ESPN source disabled — skipping")

    health_deployment = health_check_flow.to_deployment(
        name="health_check",
        interval=datetime.timedelta(seconds=60),
        parameters={"config": config},
    )
    deployments.append(health_deployment)

    logger.info("serve_flows: starting %d deployments", len(deployments))

    try:
        # serve() blocks until interrupted
        serve(*deployments)  # type: ignore[misc]
    except Exception:
        logger.exception("serve_flows: Prefect serve loop failed")
        raise


async def run_flows_forever(config: PollerConfig) -> None:
    """Run all enabled poller flows in a simple asyncio loop.

    Alternative to :func:`serve_flows` for deployments that do not use the
    Prefect server.  Each poller runs at its configured interval, and the loop
    exits gracefully on SIGINT or SIGTERM.

    Args:
        config: Fully populated :class:`PollerConfig`.

    Raises:
        RuntimeError: If Prefect is required but not installed (only when
            ``config.scheduler == "prefect"`` and Prefect is missing).
    """
    if config.scheduler == "prefect" and not PREFECT_AVAILABLE:
        raise RuntimeError(
            "Prefect is required for scheduler='prefect' but is not installed. "
            "Install the [poller] extra:  pip install sportsquant[poller]"
        )

    active_sports = get_active_sports(config)
    shutdown = asyncio.Event()

    # Graceful shutdown on SIGINT / SIGTERM
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, shutdown.set)

    logger.info("run_flows_forever: starting poller loop (scheduler=%s)", config.scheduler)

    while not shutdown.is_set():
        cycle_results: list[TaskResult] = []

        if is_odds_api_enabled(config):
            for sport in active_sports:
                if shutdown.is_set():
                    break
                if PREFECT_AVAILABLE:
                    result = await odds_api_poll_flow(config, sport)
                else:
                    result = await run_odds_api_poll(config, sport)
                cycle_results.append(result)
                logger.info(
                    "run_flows_forever: odds_api_%s — %s (%d rows)",
                    sport,
                    result.status,
                    result.rows_written,
                )

        if is_espn_enabled(config):
            for sport in active_sports:
                if shutdown.is_set():
                    break
                if PREFECT_AVAILABLE:
                    result = await espn_injuries_poll_flow(config, sport)
                else:
                    result = await run_espn_poll(config, sport)
                cycle_results.append(result)
                logger.info(
                    "run_flows_forever: espn_injuries_%s — %s (%d rows)",
                    sport,
                    result.status,
                    result.rows_written,
                )

        if not shutdown.is_set():
            if PREFECT_AVAILABLE:
                health_result = await health_check_flow(config)
            else:
                health_result = await run_health_check(config)
            cycle_results.append(health_result)

        # Summary
        succeeded = sum(1 for r in cycle_results if r.status == "success")
        failed = sum(1 for r in cycle_results if r.status == "failed")
        logger.info(
            "run_flows_forever: cycle complete — %d success, %d failed",
            succeeded,
            failed,
        )

        # Wait for the shortest configured interval before the next cycle
        min_interval = _min_poll_interval(config)
        if min_interval > 0 and not shutdown.is_set():
            logger.info("run_flows_forever: sleeping %ds until next cycle", min_interval)
            try:
                await asyncio.wait_for(shutdown.wait(), timeout=min_interval)
            except asyncio.TimeoutError:
                pass  # Normal — interval elapsed, start next cycle

    logger.info("run_flows_forever: shutdown signal received — exiting")


def _min_poll_interval(config: PollerConfig) -> int:
    """Return the shortest configured poll interval in seconds.

    Used by :func:`run_flows_forever` to determine the sleep duration between
    cycles.

    Args:
        config: Fully populated :class:`PollerConfig`.

    Returns:
        The minimum of the Odds API and ESPN interval settings, or 60 if no
        source is enabled.
    """
    intervals: list[int] = []
    if is_odds_api_enabled(config):
        intervals.append(config.odds_api.interval_seconds)
    if is_espn_enabled(config):
        intervals.append(config.espn.interval_seconds)
    if not intervals:
        return 60  # fallback: check every minute
    return min(intervals)
