"""SportsQuant CLI — quantitative sports betting toolkit.

Command-line interface wrapping the major public API functions from
core/betting, core/risk, core/backtest, models/ratings, models/analysis,
and data/sources modules.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Optional

import click
import pandas as pd
from rich.console import Console
from rich.table import Table

# Lazy import helper — avoids ModuleNotFoundError at import time
# when transitive dependencies (e.g. sportsquant.util.metrics) are
# not yet available.

console = Console()


def _import(module: str, name: str):
    """Import a single name from a module, with a friendly error on failure."""
    try:
        mod = importlib.import_module(module)
        return getattr(mod, name)
    except (ImportError, AttributeError) as exc:
        click.echo(f"Error: could not import {name} from {module}: {exc}", err=True)
        sys.exit(1)


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────


def _american_to_odds(american: int):
    """Parse American odds (e.g. -110, +105) into an Odds object."""
    Odds = _import("sportsquant.core.betting.odds", "Odds")
    return Odds(american=american)


def _fmt_pct(value: float) -> str:
    """Format a float as a percentage string."""
    return f"{value:.1%}"


def _fmt_dec(value: float, places: int = 4) -> str:
    """Format a float with given decimal places."""
    return f"{value:.{places}f}"


# ──────────────────────────────────────────────
# Root group
# ──────────────────────────────────────────────


@click.group()
@click.version_option(version="0.1.0", prog_name="sportsquant")
def app() -> None:
    """SportsQuant — quantitative sports betting toolkit."""


# ──────────────────────────────────────────────
# ev — Expected Value
# ──────────────────────────────────────────────


@app.command()
@click.option("--line", type=float, required=True, help="Betting line (e.g. 40.5)")
@click.option("--odds", type=int, required=True, help="American odds (e.g. -110)")
@click.option("--prob", type=float, required=True, help="Your estimated true probability (0-1)")
def ev(line: float, odds: int, prob: float) -> None:
    """Calculate expected value for an over/under bet.

    Computes EV per $1 staked and shows the Kelly fraction recommendation.
    """
    from sportsquant.core.betting.engine import expected_value, kelly_fraction

    try:
        odds_obj = _american_to_odds(odds)
    except ValueError as exc:
        console.print(f"[red]Error:[/red] Invalid odds: {exc}")
        sys.exit(1)

    try:
        ev_val = expected_value(prob, odds_obj, prob)
        kf = kelly_fraction(prob, odds_obj)
        implied = odds_obj.implied_prob()
        dec = odds_obj.to_decimal()
    except (ValueError, ZeroDivisionError) as exc:
        console.print(f"[red]Error:[/red] {exc}")
        sys.exit(1)

    table = Table(title=f"EV Analysis — Line {line}")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Line", str(line))
    table.add_row("American Odds", str(odds))
    table.add_row("Decimal Odds", _fmt_dec(dec))
    table.add_row("Implied Probability", _fmt_pct(implied))
    table.add_row("True Probability", _fmt_pct(prob))
    table.add_row("EV per $1", _fmt_dec(ev_val))
    table.add_row("Kelly Fraction", _fmt_pct(kf))

    if ev_val > 0:
        table.add_row("Signal", "[green]+EV (bet)[/green]")
    elif ev_val == 0:
        table.add_row("Signal", "[yellow]Neutral[/yellow]")
    else:
        table.add_row("Signal", "[red]-EV (pass)[/red]")

    console.print(table)


# ──────────────────────────────────────────────
# kelly — Kelly Criterion
# ──────────────────────────────────────────────


@app.command()
@click.option("--edge", type=float, required=True, help="Your edge over the market (0-1)")
@click.option("--odds", type=int, required=True, help="American odds (e.g. -110)")
@click.option("--bankroll", type=float, required=True, help="Current bankroll size")
@click.option(
    "--fractional", type=float, default=None, help="Fractional Kelly multiplier (e.g. 0.25)"
)
@click.option("--adaptive", is_flag=True, help="Use adaptive Kelly with volatility adjustment")
@click.option(
    "--volatility", type=float, default=0.3, help="Volatility factor for adaptive Kelly (0-1)"
)
def kelly(
    edge: float,
    odds: int,
    bankroll: float,
    fractional: Optional[float],
    adaptive: bool,
    volatility: float,
) -> None:
    """Calculate Kelly criterion bet sizing.

    Supports full Kelly, fractional Kelly, and adaptive Kelly with
    volatility adjustment.
    """
    from sportsquant.core.betting.kelly import KellyCalculator, AdaptiveKellyContext

    try:
        odds_obj = _american_to_odds(odds)
    except ValueError as exc:
        console.print(f"[red]Error:[/red] Invalid odds: {exc}")
        sys.exit(1)

    try:
        dec = odds_obj.to_decimal()
        implied = odds_obj.implied_prob()
    except ValueError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        sys.exit(1)

    # Derive true probability from edge and implied probability
    true_prob = implied + edge
    true_prob = max(0.001, min(0.999, true_prob))

    calc = KellyCalculator()
    full_kelly = calc.compute_kelly(true_prob, dec)

    if fractional is not None:
        kelly_used = calc.compute_fractional_kelly(true_prob, dec, fractional)
        mode = f"Fractional Kelly (×{fractional})"
    elif adaptive:
        ctx = AdaptiveKellyContext(
            probability=true_prob,
            odds=dec,
            fraction=0.25,
            volatility=volatility,
        )
        kelly_used = calc.compute_adaptive_kelly(ctx)
        mode = f"Adaptive Kelly (vol={volatility})"
    else:
        kelly_used = full_kelly
        mode = "Full Kelly"

    bet_size = max(0.0, kelly_used) * bankroll

    table = Table(title="Kelly Criterion Analysis")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Mode", mode)
    table.add_row("American Odds", str(odds))
    table.add_row("Decimal Odds", _fmt_dec(dec))
    table.add_row("Implied Probability", _fmt_pct(implied))
    table.add_row("True Probability", _fmt_pct(true_prob))
    table.add_row("Edge", _fmt_pct(edge))
    table.add_row("Full Kelly Fraction", _fmt_pct(full_kelly))
    table.add_row("Recommended Kelly Fraction", _fmt_pct(kelly_used))
    table.add_row("Bankroll", f"${bankroll:,.2f}")
    table.add_row("Recommended Bet Size", f"${bet_size:,.2f}")

    console.print(table)


# ──────────────────────────────────────────────
# arbitrage — Arbitrage Detection
# ──────────────────────────────────────────────


@app.command()
@click.option("--odds-over", type=int, required=True, help="American odds for Over (e.g. -110)")
@click.option("--odds-under", type=int, required=True, help="American odds for Under (e.g. +105)")
def arbitrage(odds_over: int, odds_under: int) -> None:
    """Detect arbitrage opportunities between over and under odds.

    If the combined implied probability is less than 1.0, an arbitrage
    opportunity exists and the guaranteed profit is shown.
    """
    try:
        over = _american_to_odds(odds_over)
        under = _american_to_odds(odds_under)
        dec_over = over.to_decimal()
        dec_under = under.to_decimal()
        implied_over = over.implied_prob()
        implied_under = under.implied_prob()
    except ValueError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        sys.exit(1)

    combined = implied_over + implied_under
    is_arb = combined < 1.0

    table = Table(title="Arbitrage Check")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Over Odds (American)", str(odds_over))
    table.add_row("Over Odds (Decimal)", _fmt_dec(dec_over))
    table.add_row("Over Implied Probability", _fmt_pct(implied_over))
    table.add_row("Under Odds (American)", str(odds_under))
    table.add_row("Under Odds (Decimal)", _fmt_dec(dec_under))
    table.add_row("Under Implied Probability", _fmt_pct(implied_under))
    table.add_row("Combined Implied Probability", _fmt_pct(combined))

    if is_arb:
        vig = 1.0 - combined
        profit_per_dollar = 1.0 / combined - 1.0
        table.add_row("Arbitrage", "[green]YES ✓[/green]")
        table.add_row("Vig", _fmt_pct(vig))
        table.add_row("Guaranteed Profit per $1", f"${profit_per_dollar:.4f}")

        # Calculate optimal stakes for $100 total
        stake_over = (implied_over / combined) * 100
        stake_under = (implied_under / combined) * 100
        table.add_row("Optimal Stake Over (on $100)", f"${stake_over:.2f}")
        table.add_row("Optimal Stake Under (on $100)", f"${stake_under:.2f}")
    else:
        vig = combined - 1.0
        table.add_row("Arbitrage", "[red]NO ✗[/red]")
        table.add_row("Vig (bookmaker edge)", _fmt_pct(vig))

    console.print(table)


# ──────────────────────────────────────────────
# backtest group
# ──────────────────────────────────────────────


@app.group()
def backtest() -> None:
    """Backtesting commands for historical strategy evaluation."""


@backtest.command("run")
@click.option("--csv", type=click.Path(exists=True), required=True, help="Path to lines CSV file")
@click.option(
    "--strategy", type=click.Choice(["value", "kelly"]), default="value", help="Betting strategy"
)
@click.option("--walk-forward", is_flag=True, help="Use walk-forward validation")
@click.option("--regime-aware", is_flag=True, help="Use regime-aware backtesting")
@click.option("--init-cash", type=float, default=10000.0, help="Starting bankroll")
@click.option("--stake", type=float, default=50.0, help="Fixed stake per bet")
@click.option("--n-sims", type=int, default=5000, help="Number of simulations")
@click.option("--output", type=click.Path(), default=None, help="Output CSV path")
def backtest_run(
    csv: str,
    strategy: str,
    walk_forward: bool,
    regime_aware: bool,
    init_cash: float,
    stake: float,
    n_sims: int,
    output: Optional[str],
) -> None:
    """Run a backtest on historical betting lines.

    Loads lines from CSV and runs the selected strategy.
    """
    from sportsquant.core.backtest.engine import PraBacktestConfig, backtest_pra_lines
    from sportsquant.core.backtest.parallel import backtest_summary

    csv_path = Path(csv)

    console.print(f"[cyan]Loading lines from[/cyan] {csv_path}")

    try:
        df = pd.read_csv(csv_path)
    except Exception as exc:
        console.print(f"[red]Error:[/red] Failed to read CSV: {exc}")
        sys.exit(1)

    console.print(f"[cyan]Loaded[/cyan] {len(df)} rows")

    if regime_aware or walk_forward:
        from sportsquant.core.backtest.regime import (
            WalkForwardBacktest,
            WalkForwardConfig,
        )

        config = WalkForwardConfig()
        wf = WalkForwardBacktest(config)

        try:
            results = wf.run(df)
            console.print("[green]Walk-forward backtest complete[/green]")
            if hasattr(results, "metrics") and results.metrics:
                table = Table(title="Walk-Forward Results")
                table.add_column("Metric", style="cyan")
                table.add_column("Value", style="green")
                for k, v in results.metrics.items():
                    if isinstance(v, float):
                        table.add_row(k, _fmt_dec(v))
                    else:
                        table.add_row(k, str(v))
                console.print(table)
        except Exception as exc:
            console.print(f"[red]Error:[/red] Walk-forward backtest failed: {exc}")
            sys.exit(1)
    else:
        config = PraBacktestConfig(
            league="NBA",
            season="2024-25",
            cache_root=csv_path.parent,
            lines_csv=csv_path,
            n_sims=n_sims,
        )

        try:
            result_df = backtest_pra_lines(config)
            if result_df is not None and not result_df.empty:
                summary = backtest_summary(result_df)
                table = Table(title="Backtest Results")
                table.add_column("Metric", style="cyan")
                table.add_column("Value", style="green")
                for k, v in summary.items():
                    if isinstance(v, float):
                        table.add_row(k, _fmt_dec(v))
                    else:
                        table.add_row(k, str(v))
                console.print(table)
            else:
                console.print("[yellow]No results returned from backtest.[/yellow]")
        except Exception as exc:
            console.print(f"[red]Error:[/red] Backtest failed: {exc}")
            sys.exit(1)

    if output:
        try:
            df.to_csv(output, index=False)
            console.print(f"[green]Results saved to[/green] {output}")
        except Exception as exc:
            console.print(f"[red]Error:[/red] Failed to save results: {exc}")


@backtest.command("analyze")
@click.option("--csv", type=click.Path(exists=True), required=True, help="Path to results CSV file")
def backtest_analyze(csv: str) -> None:
    """Analyze existing backtest results from CSV.

    Loads a previously saved backtest results CSV and computes summary
    statistics.
    """
    from sportsquant.core.backtest.parallel import backtest_summary

    try:
        df = pd.read_csv(csv)
    except Exception as exc:
        console.print(f"[red]Error:[/red] Failed to read CSV: {exc}")
        sys.exit(1)

    console.print(f"[cyan]Loaded[/cyan] {len(df)} rows from {csv}")

    try:
        summary = backtest_summary(df)
        table = Table(title="Backtest Analysis")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        for k, v in summary.items():
            if isinstance(v, float):
                table.add_row(k, _fmt_dec(v))
            else:
                table.add_row(k, str(v))
        console.print(table)
    except Exception as exc:
        console.print(f"[red]Error:[/red] Analysis failed: {exc}")
        sys.exit(1)


# ──────────────────────────────────────────────
# scrape group
# ──────────────────────────────────────────────


@app.group()
def scrape() -> None:
    """Data scraping commands for odds and injury reports."""


@scrape.command("pinnacle")
@click.option("--sport", type=str, default="nba", help="Sport to scrape (default: nba)")
@click.option("--max-games", type=int, default=15, help="Maximum number of games to fetch")
def scrape_pinnacle(sport: str, max_games: int) -> None:
    """Scrape odds data from Pinnacle.

    Note: Requires the Pinnacle scraper module to be configured with
    valid credentials and dependencies.
    """
    console.print(f"[cyan]Scraping Pinnacle odds[/cyan] — sport={sport}, max_games={max_games}")

    try:
        from sportsquant.data.sources.pinnacle import __dict__ as pinnacle_exports

        scraper_classes = [
            v
            for v in pinnacle_exports.values()
            if isinstance(v, type) and hasattr(v, "scrape") or hasattr(v, "fetch")
        ]
    except (ImportError, AttributeError):
        scraper_classes = []

    if not scraper_classes:
        console.print(
            "[yellow]Pinnacle scraper not yet implemented.[/yellow]\n"
            "The data.sources.pinnacle module is a placeholder.\n"
            "Configure the scraper and re-run."
        )
        return

    console.print(f"[green]Found {len(scraper_classes)} scraper class(es)[/green]")


@scrape.command("injuries")
@click.option("--league", type=str, default="nba", help="League to scrape (default: nba)")
def scrape_injuries(league: str) -> None:
    """Scrape injury reports from ESPN.

    Note: Requires the ESPN injuries scraper module to be configured.
    """
    console.print(f"[cyan]Scraping ESPN injuries[/cyan] — league={league}")

    try:
        from sportsquant.data.sources.espn_injuries import __dict__ as espn_exports

        scraper_classes = [
            v
            for v in espn_exports.values()
            if isinstance(v, type) and hasattr(v, "scrape") or hasattr(v, "fetch")
        ]
    except (ImportError, AttributeError):
        scraper_classes = []

    if not scraper_classes:
        console.print(
            "[yellow]ESPN injuries scraper not yet implemented.[/yellow]\n"
            "The data.sources.espn_injuries module is a placeholder.\n"
            "Configure the scraper and re-run."
        )
        return

    console.print(f"[green]Found {len(scraper_classes)} scraper class(es)[/green]")


# ──────────────────────────────────────────────
# predict group
# ──────────────────────────────────────────────


@app.group()
def predict() -> None:
    """Prediction commands for player and game projections."""


@predict.command("pra")
@click.option("--player", type=str, required=True, help="Player name (e.g. 'LeBron James')")
@click.option("--game-date", type=str, default=None, help="Game date (YYYY-MM-DD)")
@click.option("--stat", type=str, default="pra", help="Stat type (pts, reb, ast, pra)")
@click.option("--blend", type=float, default=0.3, help="Model blend weight (0-1)")
def predict_pra(player: str, game_date: Optional[str], stat: str, blend: float) -> None:
    """Predict player PRA (Points + Rebounds + Assists) or individual stat.

    Uses Bayesian priors and statistical modeling to generate projections.
    """
    from sportsquant.models.ratings.bayesian_priors import (
        BayesianPlayerPrior,
        PlayerPriorConfig,
    )

    # Normalize stat type
    stat_normalized = stat.lower().strip()
    valid_stats = ("pts", "reb", "ast", "pra", "stl", "blk", "to")
    if stat_normalized not in valid_stats:
        console.print(
            f"[red]Error:[/red] Invalid stat type '{stat}'. Choose from: {', '.join(valid_stats)}"
        )
        sys.exit(1)

    config = PlayerPriorConfig()
    BayesianPlayerPrior(config)

    table = Table(title=f"Prediction — {player}")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Player", player)
    table.add_row("Stat Type", stat_normalized)
    table.add_row("Game Date", game_date or "Next available")
    table.add_row("Model Blend", _fmt_pct(blend))

    console.print(table)
    console.print(
        "[yellow]Note:[/yellow] Full prediction requires game data. "
        "Use the analysis pipeline for complete +EV analysis."
    )


@predict.command("game")
@click.option("--home", type=str, required=True, help="Home team abbreviation (e.g. LAL)")
@click.option("--away", type=str, required=True, help="Away team abbreviation (e.g. BOS)")
@click.option("--season", type=str, default="2024-25", help="Season identifier")
def predict_game(home: str, away: str, season: str) -> None:
    """Predict game outcome using rating systems.

    Uses Massey and PageRank ratings to estimate game outcomes.
    """

    console.print(f"[cyan]Game Prediction:[/cyan] {away} @ {home} ({season})")
    console.print(
        "[yellow]Note:[/yellow] Game prediction requires historical game data. "
        "Provide game data via CSV for full analysis."
    )

    table = Table(title=f"Game Prediction — {away} @ {home}")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Home Team", home)
    table.add_row("Away Team", away)
    table.add_row("Season", season)
    table.add_row("Status", "Requires game data input")

    console.print(table)


# ──────────────────────────────────────────────
# optimize-slip — Parlay Optimization
# ──────────────────────────────────────────────


@app.command("optimize-slip")
@click.option("--legs", type=int, default=4, help="Number of legs in the slip (2-6)")
@click.option(
    "--site",
    type=click.Choice(["prizepicks", "underdog", "fanduel"]),
    default="prizepicks",
    help="DFS site",
)
@click.option(
    "--tier",
    type=click.Choice(["standard", "goblin", "demon"]),
    default="standard",
    help="PrizePicks tier",
)
@click.option("--n-sims", type=int, default=80000, help="Monte Carlo simulations")
@click.option("--min-ev", type=float, default=0.0, help="Minimum EV threshold")
def optimize_slip(legs: int, site: str, tier: str, n_sims: int, min_ev: float) -> None:
    """Optimize parlay slip for maximum expected value.

    Uses Monte Carlo simulation with correlation modeling to find
    the optimal combination of legs.
    """
    from sportsquant.models.analysis.slip_optimizer import SlipOptimizer

    if not 2 <= legs <= 6:
        console.print("[red]Error:[/red] Number of legs must be between 2 and 6")
        sys.exit(1)

    SlipOptimizer(n_sims=n_sims)

    table = Table(title="Slip Optimizer Configuration")
    table.add_column("Parameter", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Site", site)
    table.add_row("Legs", str(legs))
    table.add_row("Tier", tier.capitalize())
    table.add_row("Simulations", f"{n_sims:,}")
    table.add_row("Min EV Threshold", _fmt_dec(min_ev))

    if site == "prizepicks":
        from sportsquant.models.analysis.slip_optimizer import PAYOUT_POWER, PAYOUT_FLEX

        table.add_row("Power Payout (example)", str(PAYOUT_POWER.get((legs, legs), "N/A")))
        table.add_row("Flex Payout (example)", str(PAYOUT_FLEX.get((legs, legs), "N/A")))

    console.print(table)
    console.print(
        "\n[yellow]Note:[/yellow] Full optimization requires market data and player projections. "
        "Use the analysis pipeline for end-to-end +EV analysis."
    )


# ──────────────────────────────────────────────
# ratings group
# ──────────────────────────────────────────────


@app.group()
def ratings() -> None:
    """Team and player rating system commands."""


@ratings.command("raptor")
@click.option("--season", type=str, default="2024-25", help="Season identifier")
@click.option("--min-games", type=int, default=5, help="Minimum games for rating")
def ratings_raptor(season: str, min_games: int) -> None:
    """Compute RAPTOR composite ratings.

    Combines box-score, on-off, and priors components into a final
    RAPTOR rating for each player.
    """
    from sportsquant.models.ratings.raptor_composite import (
        RaptorCompositeFeatures,
        RaptorCompositeConfig,
    )

    config = RaptorCompositeConfig(min_games_for_raptor=min_games)
    RaptorCompositeFeatures(composite_config=config)

    table = Table(title="RAPTOR Ratings Configuration")
    table.add_column("Parameter", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Season", season)
    table.add_row("Min Games", str(min_games))
    table.add_row("Box Weight", _fmt_dec(config.box_weight))
    table.add_row("On-Off Weight", _fmt_dec(config.onoff_weight))
    table.add_row("Priors Weight", _fmt_dec(config.priors_weight))

    console.print(table)
    console.print(
        "\n[yellow]Note:[/yellow] Full RAPTOR computation requires player DataFrame input. "
        "Provide data via CSV or database connection."
    )


@ratings.command("massey")
@click.option("--season", type=str, default="2024-25", help="Season identifier")
@click.option("--home-advantage", type=float, default=3.0, help="Home court advantage in points")
@click.option("--min-games", type=int, default=5, help="Minimum games for rating")
def ratings_massey(season: str, home_advantage: float, min_games: int) -> None:
    """Compute Massey ratings with attack/defense decomposition.

    Solves r = M^{-1} * p for team rating vector.
    """
    from sportsquant.models.ratings.massey_ratings import MasseyRatings

    MasseyRatings(home_advantage=home_advantage)

    table = Table(title="Massey Ratings Configuration")
    table.add_column("Parameter", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Season", season)
    table.add_row("Home Advantage", f"{home_advantage} pts")
    table.add_row("Min Games", str(min_games))

    console.print(table)
    console.print(
        "\n[yellow]Note:[/yellow] Full Massey computation requires game results DataFrame. "
        "Provide data via CSV with columns: HOME_TEAM, AWAY_TEAM, HOME_SCORE, AWAY_SCORE."
    )


@ratings.command("pagerank")
@click.option("--season", type=str, default="2024-25", help="Season identifier")
@click.option("--damping", type=float, default=0.85, help="Damping factor (0-1)")
@click.option("--max-iterations", type=int, default=100, help="Max iterations for convergence")
def ratings_pagerank(season: str, damping: float, max_iterations: int) -> None:
    """Compute PageRank-style team ratings.

    Uses transitive opponent strength for iterative rating.
    """
    from sportsquant.models.ratings.pagerank_ratings import PageRankRatings

    try:
        PageRankRatings(
            damping=damping,
            max_iterations=max_iterations,
        )
    except ValueError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        sys.exit(1)

    table = Table(title="PageRank Ratings Configuration")
    table.add_column("Parameter", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Season", season)
    table.add_row("Damping Factor", _fmt_dec(damping))
    table.add_row("Max Iterations", str(max_iterations))

    console.print(table)
    console.print(
        "\n[yellow]Note:[/yellow] Full PageRank computation requires game results DataFrame. "
        "Provide data via CSV with columns: WINNER, LOSER, WINNER_SCORE, LOSER_SCORE."
    )


# ──────────────────────────────────────────────
# portfolio group
# ──────────────────────────────────────────────


@app.group()
def portfolio() -> None:
    """Portfolio and bankroll management commands."""


@portfolio.command("analyze")
@click.option("--bankroll", type=float, required=True, help="Current bankroll size")
@click.option(
    "--csv",
    type=click.Path(exists=True),
    default=None,
    help="Path to bets CSV for portfolio analysis",
)
def portfolio_analyze(bankroll: float, csv: Optional[str]) -> None:
    """Analyze portfolio risk and bankroll allocation.

    Shows current portfolio health metrics including exposure limits,
    risk parameters, and position sizing recommendations.
    """
    from sportsquant.core.risk.portfolio import (
        KellyConfig,
        PortfolioRiskConfig,
    )
    from sportsquant.core.betting.kelly import (
        ExposureLimits,
    )

    risk_config = PortfolioRiskConfig()
    kelly_config = KellyConfig()
    ExposureLimits()

    table = Table(title="Portfolio Analysis")
    table.add_column("Parameter", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Bankroll", f"${bankroll:,.2f}")
    table.add_row("Max Position Size", _fmt_pct(risk_config.max_position_size))
    table.add_row("Max Portfolio Exposure", _fmt_pct(risk_config.max_portfolio_exposure))
    table.add_row("Max Daily Loss", _fmt_pct(risk_config.max_daily_loss_pct))
    table.add_row("Max Drawdown", _fmt_pct(risk_config.max_drawdown_pct))
    table.add_row("Max Correlated Exposure", _fmt_pct(risk_config.max_correlated_exposure))
    table.add_row("VaR Confidence", _fmt_pct(risk_config.var_confidence))
    table.add_row("Kelly Fraction", _fmt_pct(kelly_config.kelly_fraction))
    table.add_row("Min Edge for Bet", _fmt_pct(kelly_config.min_edge_for_bet))

    max_position = bankroll * risk_config.max_position_size
    max_exposure = bankroll * risk_config.max_portfolio_exposure
    table.add_row("Max Position ($)", f"${max_position:,.2f}")
    table.add_row("Max Portfolio Exposure ($)", f"${max_exposure:,.2f}")

    if csv:
        try:
            df = pd.read_csv(csv)
            table.add_row("Bets Loaded", str(len(df)))
        except Exception as exc:
            console.print(f"[yellow]Warning:[/yellow] Failed to load bets CSV: {exc}")

    console.print(table)


@portfolio.command("size")
@click.option("--edge", type=float, required=True, help="Your edge over the market (0-1)")
@click.option("--odds", type=int, required=True, help="American odds (e.g. -110)")
@click.option("--bankroll", type=float, required=True, help="Current bankroll size")
@click.option("--fractional", type=float, default=0.25, help="Kelly fraction (0-1)")
def portfolio_size(edge: float, odds: int, bankroll: float, fractional: float) -> None:
    """Calculate optimal position size based on Kelly criterion.

    Uses risk management limits including max position size, portfolio
    exposure, and market exposure constraints.
    """
    from sportsquant.core.risk.portfolio import (
        KellyBettor,
        KellyConfig,
        PositionSizer,
    )

    try:
        odds_obj = _american_to_odds(odds)
        dec = odds_obj.to_decimal()
        implied = odds_obj.implied_prob()
    except ValueError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        sys.exit(1)

    true_prob = implied + edge
    true_prob = max(0.001, min(0.999, true_prob))

    kelly_config = KellyConfig(kelly_fraction=fractional)
    bettor = KellyBettor(kelly_config)
    kf = bettor.compute_kelly(true_prob, dec, fractional)

    ev = bettor.compute_expected_value(true_prob, dec)
    roi = bettor.compute_roi(true_prob, dec, fractional)
    computed_edge = bettor.compute_edge(true_prob, dec)

    sizer = PositionSizer()
    position = sizer.compute_position_size(
        kelly_fraction=kf,
        edge=computed_edge,
        bankroll=bankroll,
    )

    table = Table(title="Position Sizing")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Bankroll", f"${bankroll:,.2f}")
    table.add_row("American Odds", str(odds))
    table.add_row("Decimal Odds", _fmt_dec(dec))
    table.add_row("Implied Probability", _fmt_pct(implied))
    table.add_row("True Probability", _fmt_pct(true_prob))
    table.add_row("Edge", _fmt_pct(computed_edge))
    table.add_row("Kelly Fraction", _fmt_pct(kf))
    table.add_row("Expected Value", _fmt_dec(ev))
    table.add_row("Expected ROI", _fmt_pct(roi))
    table.add_row("Recommended Position", f"${position:,.2f}")

    if position <= 0:
        table.add_row("Verdict", "[red]PASS — No edge or below minimum[/red]")
    else:
        table.add_row("Verdict", f"[green]BET ${position:,.2f}[/green]")

    console.print(table)


# ──────────────────────────────────────────────
# odds — Odds Conversion Utility
# ──────────────────────────────────────────────


@app.command()
@click.option("--american", type=int, default=None, help="American odds (e.g. -110)")
@click.option("--decimal", type=float, default=None, help="Decimal odds (e.g. 1.91)")
def odds(american: Optional[int], decimal: Optional[float]) -> None:
    """Convert odds between American and Decimal formats.

    Provide either --american or --decimal and get full conversion.
    """
    from sportsquant.core.betting.odds import Odds

    if american is None and decimal is None:
        console.print("[red]Error:[/red] Provide either --american or --decimal")
        sys.exit(1)

    try:
        if american is not None:
            odds_obj = Odds(american=american)
        else:
            odds_obj = Odds(decimal=decimal)

        dec = odds_obj.to_decimal()
        implied = odds_obj.implied_prob()

        # Convert decimal back to American
        if dec >= 2.0:
            am = int((dec - 1) * 100)
        else:
            am = int(-100 / (dec - 1))

        table = Table(title="Odds Conversion")
        table.add_column("Format", style="cyan")
        table.add_column("Value", style="green")
        table.add_row("American", f"{am:+d}")
        table.add_row("Decimal", _fmt_dec(dec, 2))
        table.add_row("Fractional", f"{_frac_str(dec)}")
        table.add_row("Implied Probability", _fmt_pct(implied))

        console.print(table)
    except ValueError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        sys.exit(1)


def _frac_str(dec: float) -> str:
    """Convert decimal odds to a rough fractional string."""
    profit = dec - 1.0
    # Find closest simple fraction
    for denom in range(1, 21):
        numer = round(profit * denom)
        if abs(profit - numer / denom) < 0.02 and numer > 0:
            from math import gcd

            g = gcd(numer, denom)
            return f"{numer // g}/{denom // g}"
    return f"{profit:.2f}/1"


# ──────────────────────────────────────────────
# metrics — Performance Metrics
# ──────────────────────────────────────────────


@app.command()
@click.option("--csv", type=click.Path(exists=True), required=True, help="Path to bet results CSV")
@click.option("--pnl-col", type=str, default="pnl", help="Column name for PnL values")
def metrics(csv: str, pnl_col: str) -> None:
    """Compute performance metrics from bet results CSV.

    Calculates Sharpe ratio, Sortino ratio, max drawdown, profit factor,
    and streak statistics.
    """
    from sportsquant.core.betting.metrics import (
        calculate_sharpe_ratio,
        calculate_sortino_ratio,
        calculate_max_drawdown,
        calculate_profit_factor,
        calculate_streaks,
    )

    try:
        df = pd.read_csv(csv)
    except Exception as exc:
        console.print(f"[red]Error:[/red] Failed to read CSV: {exc}")
        sys.exit(1)

    if pnl_col not in df.columns:
        console.print(
            f"[red]Error:[/red] Column '{pnl_col}' not found. Available: {', '.join(df.columns)}"
        )
        sys.exit(1)

    pnl = df[pnl_col].dropna()

    table = Table(title="Performance Metrics")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")

    try:
        table.add_row("Total Bets", str(len(pnl)))
        table.add_row("Total PnL", f"${pnl.sum():,.2f}")
        table.add_row("Win Rate", _fmt_pct((pnl > 0).mean()))

        sharpe = calculate_sharpe_ratio(pnl)
        table.add_row("Sharpe Ratio", _fmt_dec(sharpe))

        sortino = calculate_sortino_ratio(pnl)
        table.add_row("Sortino Ratio", _fmt_dec(sortino))

        max_dd = calculate_max_drawdown(pnl)
        table.add_row("Max Drawdown", _fmt_pct(abs(max_dd)) if max_dd < 0 else _fmt_dec(max_dd))

        pf = calculate_profit_factor(pnl)
        table.add_row("Profit Factor", _fmt_dec(pf))

        streaks = calculate_streaks(pnl)
        if streaks:
            table.add_row("Win Streak (max)", str(streaks.get("max_win_streak", "N/A")))
            table.add_row("Lose Streak (max)", str(streaks.get("max_lose_streak", "N/A")))

    except Exception as exc:
        console.print(f"[red]Error:[/red] Metric calculation failed: {exc}")
        sys.exit(1)

    console.print(table)


# ──────────────────────────────────────────────
# edge — Edge Calculator
# ──────────────────────────────────────────────


@app.command()
@click.option("--prob", type=float, required=True, help="Your estimated true probability (0-1)")
@click.option("--odds", type=int, required=True, help="American odds (e.g. -110)")
def edge(prob: float, odds: int) -> None:
    """Calculate edge over the market for a given probability and odds.

    Edge = true_probability - implied_probability
    """
    from sportsquant.core.betting.kelly import EdgeCalculator

    try:
        odds_obj = _american_to_odds(odds)
        dec = odds_obj.to_decimal()
        implied = odds_obj.implied_prob()
    except ValueError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        sys.exit(1)

    calc = EdgeCalculator()
    edge_val = calc.compute_edge(prob, dec)

    table = Table(title="Edge Analysis")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("American Odds", str(odds))
    table.add_row("Decimal Odds", _fmt_dec(dec))
    table.add_row("Implied Probability", _fmt_pct(implied))
    table.add_row("True Probability", _fmt_pct(prob))
    table.add_row("Edge", _fmt_pct(edge_val))

    if edge_val > 0.02:
        table.add_row("Signal", "[green]+EV (strong edge)[/green]")
    elif edge_val > 0:
        table.add_row("Signal", "[yellow]+EV (thin edge)[/yellow]")
    else:
        table.add_row("Signal", "[red]-EV (no edge)[/red]")

    console.print(table)


# ──────────────────────────────────────────────
# bankroll — Bankroll Management
# ──────────────────────────────────────────────


@app.command()
@click.option("--initial", type=float, required=True, help="Initial bankroll amount")
@click.option("--min-bet", type=float, default=1.0, help="Minimum bet size")
@click.option("--max-bet", type=float, default=10000.0, help="Maximum bet size")
@click.option("--kelly-fraction", type=float, default=0.25, help="Kelly fraction for sizing")
def bankroll(initial: float, min_bet: float, max_bet: float, kelly_fraction: float) -> None:
    """Initialize and display bankroll management configuration.

    Shows bankroll parameters, exposure limits, and position constraints.
    """
    from sportsquant.core.betting.kelly import (
        BankrollManager,
        BankrollManagerConfig,
        ExposureLimits,
    )

    limits = ExposureLimits()
    config = BankrollManagerConfig(
        min_bet_size=min_bet,
        max_bet_size=max_bet,
        min_bankroll=100.0,
        kelly_fraction=kelly_fraction,
        exposure_limits=limits,
    )
    BankrollManager(bankroll=initial, config=config)

    table = Table(title="Bankroll Management")
    table.add_column("Parameter", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Initial Bankroll", f"${initial:,.2f}")
    table.add_row("Min Bet Size", f"${min_bet:,.2f}")
    table.add_row("Max Bet Size", f"${max_bet:,.2f}")
    table.add_row("Kelly Fraction", _fmt_pct(kelly_fraction))
    table.add_row("Max Position Exposure", _fmt_pct(limits.max_position_pct))
    table.add_row("Max Portfolio Exposure", _fmt_pct(limits.max_portfolio_exposure))
    table.add_row("Max Market Exposure", _fmt_pct(limits.max_market_exposure))
    table.add_row("Max Book Exposure", _fmt_pct(limits.max_book_exposure))

    console.print(table)


# ──────────────────────────────────────────────
# decide — Over/Under Decision
# ──────────────────────────────────────────────


@app.command()
@click.option("--line", type=float, required=True, help="Betting line (e.g. 40.5)")
@click.option("--p-over", type=float, required=True, help="Probability of going over (0-1)")
@click.option("--odds-over", type=int, required=True, help="American odds for Over")
@click.option("--odds-under", type=int, required=True, help="American odds for Under")
@click.option(
    "--true-prob-over",
    type=float,
    default=None,
    help="True probability for Over (defaults to p-over)",
)
@click.option(
    "--true-prob-under",
    type=float,
    default=None,
    help="True probability for Under (defaults to 1-p-over)",
)
def decide(
    line: float,
    p_over: float,
    odds_over: int,
    odds_under: int,
    true_prob_over: Optional[float],
    true_prob_under: Optional[float],
) -> None:
    """Make an over/under betting decision.

    Evaluates both sides and recommends the better bet based on
    expected value and Kelly criterion.
    """
    from sportsquant.core.betting.engine import decide_over_under, _detect_arbitrage

    try:
        over = _american_to_odds(odds_over)
        under = _american_to_odds(odds_under)
    except ValueError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        sys.exit(1)

    if true_prob_over is None:
        true_prob_over = p_over
    if true_prob_under is None:
        true_prob_under = 1.0 - p_over

    try:
        decision = decide_over_under(
            line=line,
            p_over=p_over,
            odds_over=over,
            odds_under=under,
            true_prob_over=true_prob_over,
            true_prob_under=true_prob_under,
        )
    except (ValueError, ZeroDivisionError) as exc:
        console.print(f"[red]Error:[/red] Decision failed: {exc}")
        sys.exit(1)

    # Check for arbitrage
    try:
        is_arb = _detect_arbitrage(over.to_decimal(), under.to_decimal())
    except Exception:
        is_arb = False

    table = Table(title=f"Over/Under Decision — Line {line}")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Recommended Side", f"[bold]{decision.side.upper()}[/bold]")
    table.add_row("Line", str(decision.line))
    table.add_row("Win Probability", _fmt_pct(decision.p_win))
    table.add_row("Decimal Odds", _fmt_dec(decision.decimal_odds))
    table.add_row("Expected Value", _fmt_dec(decision.ev))
    table.add_row("Kelly Fraction", _fmt_pct(decision.kelly_fraction))

    if is_arb:
        table.add_row("Arbitrage", "[bold green]DETECTED ✓[/bold green]")

    if decision.ev > 0:
        table.add_row("Signal", "[green]+EV[/green]")
    else:
        table.add_row("Signal", "[red]-EV (pass)[/red]")

    console.print(table)


# ──────────────────────────────────────────────
# nfl group — NFL-Specific Commands
# ──────────────────────────────────────────────


@app.group()
def nfl() -> None:
    """NFL-specific betting analysis commands.

    Leverages nflfastR data and NFL-specific statistical models
    for player prop evaluation, backtesting, and power ratings.
    """


@nfl.command("ev")
@click.option("--player", type=str, required=True, help="Player name (e.g. 'Patrick Mahomes')")
@click.option("--stat", type=str, required=True, help="Stat type (e.g. passing_yards, rushing_tds)")
@click.option("--line", type=float, required=True, help="Projection line (e.g. 280.5)")
@click.option(
    "--position", type=click.Choice(["QB", "RB", "WR", "TE"]), default="QB", help="Player position"
)
@click.option(
    "--site",
    type=click.Choice(["prizepicks", "underdog", "fanduel"]),
    default="prizepicks",
    help="DFS site",
)
@click.option("--odds-over", type=int, default=-110, help="American odds for Over")
@click.option("--odds-under", type=int, default=-110, help="American odds for Under")
@click.option("--blend", type=float, default=0.30, help="Model blend weight (0-1)")
@click.option("--lookback", type=int, default=10, help="Number of games to look back")
@click.option(
    "--cache-dir", type=click.Path(), default=None, help="Cache directory for nflfastR data"
)
def nfl_ev(
    player: str,
    stat: str,
    line: float,
    position: str,
    site: str,
    odds_over: int,
    odds_under: int,
    blend: float,
    lookback: int,
    cache_dir: Optional[str],
) -> None:
    """Calculate expected value for an NFL player prop.

    Uses nflfastR data and NFL-specific statistical modeling to
    estimate true probability and compute EV/Kelly.
    """
    from sportsquant.models.analysis.evaluators.nfl_eval import (
        NFLStatisticalModel,
        NFLDataProvider,
        NFLPrizePicksEvaluator,
        NFLUnderdogEvaluator,
        NFLFanDuelEvaluator,
    )
    from sportsquant.models.analysis.rules.nfl import get_nfl_stat_key

    cache_path = Path(cache_dir) if cache_dir else None

    try:
        provider = NFLDataProvider(cache_dir=cache_path, n_lookback=lookback)
        stat_model = NFLStatisticalModel(data_provider=provider, base_blend=blend)

        # Select evaluator based on site
        if site == "prizepicks":
            evaluator = NFLPrizePicksEvaluator(model_weight=blend, stat_model=stat_model)
        elif site == "underdog":
            evaluator = NFLUnderdogEvaluator(model_weight=blend, stat_model=stat_model)
        else:
            evaluator = NFLFanDuelEvaluator(model_weight=blend, stat_model=stat_model)

        # Build model and get probability
        stat_key = get_nfl_stat_key(stat)
        models = stat_model.build_model(player, [stat_key], position=position)

        if not models or stat_key not in models:
            console.print(f"[red]Error:[/red] Could not build model for {player} ({stat})")
            sys.exit(1)

        model_dict = models[stat_key]
        model_prob = stat_model.calc_prob_over(model_dict, line)

        # Evaluate
        market_odds = {"over": odds_over, "under": odds_under}
        result = evaluator.evaluate_projection(
            projection=None,
            market_odds=market_odds,
            model_prob=model_prob,
            site=site,
        )

        # Display results
        table = Table(title=f"NFL EV Analysis — {player} {stat}")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        table.add_row("Player", player)
        table.add_row("Position", position)
        table.add_row("Stat Type", stat_key)
        table.add_row("Line", str(line))
        table.add_row("Site", site.capitalize())
        table.add_row("Model Probability", _fmt_pct(model_prob))
        table.add_row("Edge", _fmt_pct(result.edge))
        table.add_row("EV per $1", _fmt_dec(result.ev))
        table.add_row("Kelly Fraction", _fmt_pct(result.kelly_fraction))
        table.add_row("Confidence", f"{result.confidence:.1f}%")
        table.add_row("Recommended Side", f"[bold]{result.recommended_side}[/bold]")

        if result.ev > 0:
            table.add_row("Signal", "[green]+EV (bet)[/green]")
        else:
            table.add_row("Signal", "[red]-EV (pass)[/red]")

        console.print(table)

    except Exception as exc:
        console.print(f"[red]Error:[/red] NFL EV calculation failed: {exc}")
        console.print("[yellow]Tip:[/yellow] Ensure nflfastR data is cached or available.")
        sys.exit(1)


@nfl.command("kelly")
@click.option("--player", type=str, required=True, help="Player name")
@click.option("--stat", type=str, required=True, help="Stat type")
@click.option("--line", type=float, required=True, help="Projection line")
@click.option("--position", type=click.Choice(["QB", "RB", "WR", "TE"]), default="QB")
@click.option("--bankroll", type=float, required=True, help="Current bankroll size")
@click.option("--fractional", type=float, default=0.25, help="Kelly fraction multiplier")
@click.option("--blend", type=float, default=0.30, help="Model blend weight")
@click.option("--lookback", type=int, default=10, help="Games to look back")
def nfl_kelly(
    player: str,
    stat: str,
    line: float,
    position: str,
    bankroll: float,
    fractional: float,
    blend: float,
    lookback: int,
) -> None:
    """Calculate Kelly criterion bet sizing for NFL props.

    Computes full Kelly, fractional Kelly, and recommended bet size
    based on NFL statistical model probabilities.
    """
    from sportsquant.models.analysis.evaluators.nfl_eval import (
        NFLStatisticalModel,
        NFLDataProvider,
    )
    from sportsquant.models.analysis.rules.nfl import get_nfl_stat_key
    from sportsquant.core.betting.kelly import KellyCalculator

    try:
        provider = NFLDataProvider(n_lookback=lookback)
        stat_model = NFLStatisticalModel(data_provider=provider, base_blend=blend)
        stat_key = get_nfl_stat_key(stat)

        models = stat_model.build_model(player, [stat_key], position=position)
        if not models or stat_key not in models:
            console.print(f"[red]Error:[/red] Could not build model for {player}")
            sys.exit(1)

        model_prob = stat_model.calc_prob_over(models[stat_key], line)

        # Assume -110 odds for Kelly calculation
        odds_obj = _american_to_odds(-110)
        dec = odds_obj.to_decimal()

        calc = KellyCalculator()
        full_kelly = calc.compute_kelly(model_prob, dec)
        frac_kelly = calc.compute_fractional_kelly(model_prob, dec, fractional)
        bet_size = max(0.0, frac_kelly) * bankroll

        table = Table(title=f"NFL Kelly Criterion — {player} {stat}")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        table.add_row("Player", player)
        table.add_row("Stat", stat_key)
        table.add_row("Line", str(line))
        table.add_row("Model Probability", _fmt_pct(model_prob))
        table.add_row("Full Kelly", _fmt_pct(full_kelly))
        table.add_row(f"Fractional Kelly (×{fractional})", _fmt_pct(frac_kelly))
        table.add_row("Bankroll", f"${bankroll:,.2f}")
        table.add_row("Recommended Bet", f"${bet_size:,.2f}")

        console.print(table)

    except Exception as exc:
        console.print(f"[red]Error:[/red] NFL Kelly calculation failed: {exc}")
        sys.exit(1)


@nfl.command("backtest")
@click.option("--csv", type=click.Path(exists=True), required=True, help="Path to NFL lines CSV")
@click.option("--strategy", type=click.Choice(["value", "kelly"]), default="value")
@click.option("--walk-forward", is_flag=True, help="Use walk-forward validation")
@click.option("--init-cash", type=float, default=10000.0, help="Starting bankroll")
@click.option("--n-sims", type=int, default=5000, help="Number of simulations")
@click.option("--output", type=click.Path(), default=None, help="Output CSV path")
def nfl_backtest(
    csv: str,
    strategy: str,
    walk_forward: bool,
    init_cash: float,
    n_sims: int,
    output: Optional[str],
) -> None:
    """Backtest NFL betting strategies on historical lines.

    Uses NFL-specific configuration with appropriate season format
    and game count expectations.
    """
    from sportsquant.core.backtest.engine import PraBacktestConfig, backtest_pra_lines
    from sportsquant.core.backtest.parallel import backtest_summary

    csv_path = Path(csv)
    console.print(f"[cyan]Loading NFL lines from[/cyan] {csv_path}")

    try:
        df = pd.read_csv(csv_path)
    except Exception as exc:
        console.print(f"[red]Error:[/red] Failed to read CSV: {exc}")
        sys.exit(1)

    console.print(f"[cyan]Loaded[/cyan] {len(df)} rows")

    if walk_forward:
        try:
            from sportsquant.core.backtest.regime import WalkForwardBacktest, WalkForwardConfig

            config = WalkForwardConfig()
            wf = WalkForwardBacktest(config)
            _ = wf.run(df)
            console.print("[green]Walk-forward backtest complete[/green]")
        except Exception as exc:
            console.print(f"[red]Error:[/red] Walk-forward backtest failed: {exc}")
            sys.exit(1)
    else:
        config = PraBacktestConfig(
            league="NFL",
            season="2024",
            cache_root=csv_path.parent,
            lines_csv=csv_path,
            n_sims=n_sims,
        )
        try:
            result_df = backtest_pra_lines(config)
            if result_df is not None and not result_df.empty:
                summary = backtest_summary(result_df)
                table = Table(title="NFL Backtest Results")
                table.add_column("Metric", style="cyan")
                table.add_column("Value", style="green")
                for k, v in summary.items():
                    if isinstance(v, float):
                        table.add_row(k, _fmt_dec(v))
                    else:
                        table.add_row(k, str(v))
                console.print(table)
            else:
                console.print("[yellow]Backtest returned empty results[/yellow]")
        except Exception as exc:
            console.print(f"[red]Error:[/red] Backtest failed: {exc}")
            sys.exit(1)

    if output:
        try:
            df.to_csv(output, index=False)
            console.print(f"[green]Results saved to[/green] {output}")
        except Exception as exc:
            console.print(f"[red]Error:[/red] Failed to save output: {exc}")


@nfl.command("ratings")
@click.option("--season", type=str, default="2024", help="NFL season year")
@click.option("--method", type=click.Choice(["massey", "pagerank"]), default="massey")
@click.option("--home-advantage", type=float, default=2.5, help="NFL home advantage in points")
@click.option("--csv", type=click.Path(exists=True), default=None, help="Path to game results CSV")
def nfl_ratings(season: str, method: str, home_advantage: float, csv: Optional[str]) -> None:
    """Compute NFL team power ratings.

    Uses Massey or PageRank methods with NFL-specific home advantage.
    """
    console.print(f"[cyan]NFL Ratings[/cyan] — {season} season, method={method}")

    if csv:
        try:
            df = pd.read_csv(csv)
            console.print(f"[cyan]Loaded[/cyan] {len(df)} game results")
        except Exception as exc:
            console.print(f"[red]Error:[/red] Failed to read CSV: {exc}")
            sys.exit(1)
    else:
        console.print(
            "\n[yellow]Note:[/yellow] Provide game results CSV with columns: "
            "HOME_TEAM, AWAY_TEAM, HOME_SCORE, AWAY_SCORE"
        )
        return

    try:
        if method == "massey":
            from sportsquant.models.ratings.massey_ratings import MasseyRatings

            massey = MasseyRatings(home_advantage=home_advantage)
            ratings = massey.compute_ratings(df)
        else:
            from sportsquant.models.ratings.pagerank_ratings import PageRankRatings

            pagerank = PageRankRatings(damping=0.85, max_iterations=100)
            ratings = pagerank.compute_ratings(df)

        if ratings is not None and not ratings.empty:
            table = Table(title=f"NFL {method.capitalize()} Ratings — {season}")
            table.add_column("Rank", style="cyan")
            table.add_column("Team", style="green")
            table.add_column("Rating", style="yellow")

            # Sort by rating column
            rating_col = (
                "overall_rating" if "overall_rating" in ratings.columns else ratings.columns[-1]
            )
            sorted_ratings = ratings.sort_values(rating_col, ascending=False)

            for i, row in enumerate(sorted_ratings.head(20).itertuples(), 1):
                team = getattr(row, "team", getattr(row, "Index", "?"))
                rating_val = getattr(row, rating_col, 0.0)
                table.add_row(str(i), str(team), _fmt_dec(rating_val))

            console.print(table)
        else:
            console.print("[yellow]No ratings computed[/yellow]")

    except Exception as exc:
        console.print(f"[red]Error:[/red] Ratings computation failed: {exc}")
        sys.exit(1)


@nfl.command("props")
@click.option("--player", type=str, default=None, help="Filter by player name")
@click.option("--stat", type=str, default=None, help="Filter by stat type")
@click.option(
    "--site", type=click.Choice(["prizepicks", "underdog", "fanduel"]), default="prizepicks"
)
@click.option("--min-ev", type=float, default=0.03, help="Minimum EV threshold")
@click.option("--limit", type=int, default=20, help="Maximum results to show")
def nfl_props(
    player: Optional[str], stat: Optional[str], site: str, min_ev: float, limit: int
) -> None:
    """List and evaluate available NFL player props.

    Fetches current projections and ranks them by expected value.
    """
    console.print(f"[cyan]NFL Props[/cyan] — site={site}, min_ev={min_ev}")

    table = Table(title="NFL Props Configuration")
    table.add_column("Parameter", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Site", site.capitalize())
    table.add_row("Min EV", _fmt_dec(min_ev))
    table.add_row("Max Results", str(limit))
    if player:
        table.add_row("Player Filter", player)
    if stat:
        table.add_row("Stat Filter", stat)

    console.print(table)
    console.print(
        "\n[yellow]Note:[/yellow] Live prop listing requires a data source module. "
        "See Phase 3: NFL Data Source Module."
    )
