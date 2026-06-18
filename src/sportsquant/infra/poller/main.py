"""Poller entrypoint for SportsQuant v0.2.0.

This module is the console-script entrypoint registered as ``sportsquant-poller``
in ``pyproject.toml``.  It reads :class:`~sportsquant.infra.poller.config.PollerConfig`,
dispatches to the appropriate scheduler backend, and provides a Click CLI for
manual invocation.

Scheduler dispatch
-------------------
The ``SPORTSQUANT_POLLER_SCHEDULER`` environment variable (default: ``"prefect"``)
selects the scheduling backend:

- ``"prefect"`` — calls :func:`~sportsquant.infra.poller.flows.serve_flows` which
  starts a long-running Prefect serve loop with interval deployments.  If Prefect
  is not installed, it falls back to
  :func:`~sportsquant.infra.poller.flows.run_flows_forever`.

- ``"cron"`` — calls :func:`~sportsquant.infra.poller.cron_fallback.run_cron_loop`
  which runs all enabled pollers in a plain ``asyncio`` loop on a fixed interval.

CLI subcommands
---------------
The module can also be invoked directly as ``python -m sportsquant.infra.poller.main``
with the following subcommands:

- ``start``   — Start the poller in the foreground (same as the console script).
- ``status``  — Query the DB for the latest ``poller_runs`` and ``poller_health``.
- ``once``    — Run a single poll cycle and print results.
- ``health``  — Run a single health check and print results.
"""

from __future__ import annotations

import asyncio
import logging
import sys

import click
from rich.console import Console
from rich.table import Table

from sportsquant.infra.poller.config import (
    PollerConfig,
    get_active_sports,
    is_espn_enabled,
    is_odds_api_enabled,
)
from sportsquant.infra.poller.cron_fallback import format_cycle_summary, run_cron_loop
from sportsquant.infra.poller.tasks import run_health_check, run_poll_cycle

logger = logging.getLogger(__name__)

__all__ = [
    "main",
    "main_async",
    "poller_cli",
]


# ──────────────────────────────────────────────
# Async entrypoint
# ──────────────────────────────────────────────


async def main_async() -> int:
    """Async entrypoint — read config and dispatch to the chosen scheduler.

    Returns:
        0 on graceful shutdown, 1 on fatal error.
    """
    try:
        config = PollerConfig()
    except Exception:
        logger.exception("main_async: failed to load PollerConfig")
        return 1

    # Set up logging if no handlers exist (allows downstream config to override).
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=getattr(logging, config.log_level.upper(), logging.INFO),
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        )

    active_sports = get_active_sports(config)
    sources: list[str] = []
    if is_odds_api_enabled(config):
        sources.append("odds_api")
    if is_espn_enabled(config):
        sources.append("espn")

    logger.info(
        "SportsQuant poller starting — scheduler=%s, sports=%s, sources=%s, db_host=%s",
        config.scheduler,
        ",".join(active_sports),
        ",".join(sources) or "(none)",
        config.db.host,
    )

    try:
        if config.scheduler == "prefect":
            try:
                from sportsquant.infra.poller.flows import serve_flows

                logger.info("main_async: starting Prefect serve loop")
                serve_flows(config)  # blocks until interrupted
            except ImportError:
                logger.warning(
                    "main_async: Prefect not installed — falling back to run_flows_forever"
                )
                from sportsquant.infra.poller.flows import run_flows_forever

                await run_flows_forever(config)
        elif config.scheduler == "cron":
            logger.info("main_async: starting cron loop")
            await run_cron_loop(config)
        else:
            logger.error("main_async: unsupported scheduler %r", config.scheduler)
            return 1
    except KeyboardInterrupt:
        logger.info("main_async: interrupted — shutting down")
    except Exception:
        logger.exception("main_async: fatal error")
        return 1

    return 0


# ──────────────────────────────────────────────
# Sync wrapper (console-script entrypoint)
# ──────────────────────────────────────────────


def main() -> None:
    """Sync wrapper called by the ``sportsquant-poller`` console script.

    If invoked with extra CLI args (e.g. ``sportsquant-poller once`` or
    ``sportsquant-poller status``), dispatches to the Click :func:`poller_cli`
    group. Otherwise (no args, the container ``CMD`` case), runs the main
    async loop in the foreground.
    """
    if len(sys.argv) > 1:
        poller_cli()
    else:
        sys.exit(asyncio.run(main_async()))


# ──────────────────────────────────────────────
# CLI — Click group with subcommands
# ──────────────────────────────────────────────

console = Console()


@click.group()
def poller_cli() -> None:
    """SportsQuant poller — data collection scheduler and CLI."""


@poller_cli.command()
def start() -> None:
    """Start the poller in the foreground (same as the console script)."""
    sys.exit(asyncio.run(main_async()))


@poller_cli.command()
def status() -> None:
    """Query the DB for the latest poller_runs and poller_health rows."""
    try:
        config = PollerConfig()
    except Exception as exc:
        console.print(f"[red]Error:[/red] Failed to load config: {exc}")
        sys.exit(1)

    try:
        from sportsquant.infra.db.connection import get_pool

        pool = asyncio.get_event_loop().run_until_complete(get_pool(config.db))

        # Latest poller_runs
        runs = asyncio.get_event_loop().run_until_complete(
            pool.fetch(
                "SELECT poller_name, status, rows_written, started_at, finished_at "
                "FROM poller_runs ORDER BY started_at DESC LIMIT 10"
            )
        )

        table = Table(title="Latest poller_runs")
        table.add_column("Poller", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Rows", style="green")
        table.add_column("Started At", style="dim")
        table.add_column("Finished At", style="dim")
        for row in runs:
            status_str = row["status"]
            style = (
                "[green]success[/green]" if status_str == "success" else f"[red]{status_str}[/red]"
            )
            table.add_row(
                row["poller_name"],
                style,
                str(row["rows_written"]),
                str(row["started_at"]),
                str(row["finished_at"]),
            )
        console.print(table)

        # Latest poller_health
        health = asyncio.get_event_loop().run_until_complete(
            pool.fetch(
                "SELECT poller_name, status, consecutive_failures, last_checked_at "
                "FROM poller_health ORDER BY last_checked_at DESC LIMIT 10"
            )
        )

        htable = Table(title="Latest poller_health")
        htable.add_column("Poller", style="cyan")
        htable.add_column("Status", style="green")
        htable.add_column("Failures", style="yellow")
        htable.add_column("Last Checked", style="dim")
        for row in health:
            status_str = row["status"]
            if status_str == "healthy":
                style = "[green]healthy[/green]"
            elif status_str == "degraded":
                style = "[yellow]degraded[/yellow]"
            else:
                style = f"[red]{status_str}[/red]"
            htable.add_row(
                row["poller_name"],
                style,
                str(row["consecutive_failures"]),
                str(row["last_checked_at"]),
            )
        console.print(htable)

    except Exception as exc:
        console.print(f"[red]Error:[/red] Failed to query database: {exc}")
        sys.exit(1)


@poller_cli.command()
def once() -> None:
    """Run a single poll cycle and print results (no loop)."""
    try:
        config = PollerConfig()
    except Exception as exc:
        console.print(f"[red]Error:[/red] Failed to load config: {exc}")
        sys.exit(1)

    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=getattr(logging, config.log_level.upper(), logging.INFO),
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        )

    results = asyncio.run(run_poll_cycle(config))

    table = Table(title="Poll Cycle Results")
    table.add_column("Poller", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Rows", style="green")
    table.add_column("Duration", style="dim")
    table.add_column("Error", style="red")

    for r in results:
        status_str = "[green]success[/green]" if r.status == "success" else f"[red]{r.status}[/red]"
        table.add_row(
            r.poller_name,
            status_str,
            str(r.rows_written),
            f"{r.duration_seconds:.2f}s",
            r.error or "",
        )

    console.print(table)
    console.print(f"\n{format_cycle_summary(results)}")


@poller_cli.command()
def health() -> None:
    """Run a single health check and print results."""
    try:
        config = PollerConfig()
    except Exception as exc:
        console.print(f"[red]Error:[/red] Failed to load config: {exc}")
        sys.exit(1)

    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=getattr(logging, config.log_level.upper(), logging.INFO),
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        )

    result = asyncio.run(run_health_check(config))

    table = Table(title="Health Check Result")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Poller", result.poller_name)
    status_str = (
        "[green]success[/green]" if result.status == "success" else f"[red]{result.status}[/red]"
    )
    table.add_row("Status", status_str)
    table.add_row("Rows Written", str(result.rows_written))
    table.add_row("Duration", f"{result.duration_seconds:.2f}s")
    if result.error:
        table.add_row("Error", f"[red]{result.error}[/red]")

    console.print(table)


if __name__ == "__main__":
    poller_cli()
