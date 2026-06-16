"""Backtest engine for strategy simulation on historical data.

This module provides the BacktestEngine class that simulates betting
strategies on historical projection data to evaluate performance.
"""

import random
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Optional

from sportsquant.models.analysis.backtest_result import BacktestResult
from sportsquant.models.analysis.strategies import Strategy


@dataclass
class BacktestConfig:
    """Configuration for backtest run."""

    strategy: Strategy
    start_date: date
    end_date: date
    initial_bankroll: float = 10000.0
    use_actual_results: bool = True  # Use real game results if available


class BacktestEngine:
    """Strategy simulation engine for historical data.

    Runs backtesting by:
    1. Querying historical projections from TimescaleDB for date range
    2. For each projection, applying strategy filter
    3. Simulating bet placement (flat stake or Kelly)
    4. Determining outcome (actual results or Monte Carlo simulation)
    5. Calculating cumulative P&L
    """

    def __init__(
        self,
        strategy: Strategy,
        start_date: date,
        end_date: date,
        initial_bankroll: float = 10000.0,
    ):
        """Initialize backtest engine.

        Args:
            strategy: Strategy to simulate
            start_date: Backtest start date
            end_date: Backtest end date
            initial_bankroll: Starting bankroll for Kelly calculations
        """
        self.strategy = strategy
        self.start_date = start_date
        self.end_date = end_date
        self.initial_bankroll = initial_bankroll

    async def run(
        self,
        projections: list[dict[str, Any]],
        actual_results: Optional[dict[str, dict[str, Any]]] = None,
    ) -> BacktestResult:
        """Run backtest simulation.

        Args:
            projections: List of historical projection dicts with:
                - player_name: str
                - stat_type: str
                - line_score: float
                - site: str
                - odds: int (American odds)
                - ev: float (expected value as decimal)
                - confidence: float (0-100)
                - game_date: date
                - recommendation: str ("OVER" or "UNDER")
            actual_results: Optional dict mapping (player, stat, date) to
                actual outcomes. If provided, use real results instead of
                Monte Carlo simulation.

        Returns:
            BacktestResult with all metrics
        """
        # Sort projections by date to simulate chronological execution
        sorted_projections = sorted(
            projections,
            key=lambda x: x.get("game_date", date.min),
        )

        # Filter projections to date range
        date_filtered = [p for p in sorted_projections if self._in_date_range(p.get("game_date"))]

        # Apply strategy filters and simulate bets
        bets = []
        current_bankroll = self.initial_bankroll

        for projection in date_filtered:
            # Check if this projection meets strategy criteria
            if not self._meets_strategy_criteria(projection):
                continue

            # Simulate outcome
            outcome, actual_stat = self._simulate_outcome(
                projection,
                actual_results,
            )

            # Calculate stake
            stake = self._calculate_stake(
                current_bankroll,
                projection.get("model_prob", 0.5),
                projection.get("odds", -110),
            )

            # Calculate profit based on outcome
            profit = self._calculate_profit(
                outcome,
                stake,
                projection.get("odds", -110),
            )

            # Record bet
            bet_record = {
                "player_name": projection.get("player_name"),
                "stat_type": projection.get("stat_type"),
                "site": projection.get("site"),
                "line": projection.get("line_score"),
                "odds": projection.get("odds"),
                "ev": projection.get("ev"),
                "confidence": projection.get("confidence"),
                "recommendation": projection.get("recommendation"),
                "stake": stake,
                "profit": profit,
                "outcome": outcome,
                "actual_stat": actual_stat,
                "date": projection.get("game_date"),
            }
            bets.append(bet_record)

            # Update bankroll for Kelly calculations
            current_bankroll += profit

        return BacktestResult.calculate(
            strategy=self.strategy,
            start_date=self.start_date,
            end_date=self.end_date,
            bets=bets,
        )

    def _in_date_range(self, game_date: Optional[date]) -> bool:
        """Check if game date is within backtest range.

        Args:
            game_date: Game date to check

        Returns:
            True if date is within range
        """
        if game_date is None:
            return False
        return self.start_date <= game_date <= self.end_date

    def _meets_strategy_criteria(self, projection: dict[str, Any]) -> bool:
        """Check if projection meets strategy filter criteria.

        Args:
            projection: Projection dict

        Returns:
            True if strategy should bet on this projection
        """
        return self.strategy.should_bet(
            ev=projection.get("ev", 0.0),
            confidence=projection.get("confidence", 0.0),
            odds=projection.get("odds", 0),
            site=projection.get("site", ""),
            stat_type=projection.get("stat_type", ""),
        )

    def _simulate_outcome(
        self,
        projection: dict[str, Any],
        actual_results: Optional[dict[str, dict[str, Any]]],
    ) -> tuple[str, Optional[float]]:
        """Simulate bet outcome using model probability.

        Uses actual game results if available, otherwise falls back
        to Monte Carlo simulation based on model probability.

        Args:
            projection: Projection dict
            actual_results: Optional actual results dict

        Returns:
            Tuple of (outcome: str, actual_stat: Optional[float])
            outcome is "win", "loss", or "push"
        """
        player = projection.get("player_name")
        stat_type = projection.get("stat_type")
        game_date = projection.get("game_date")
        model_prob = projection.get("model_prob", 0.5)
        recommendation = projection.get("recommendation", "OVER")

        # Check for actual results first (avoid look-ahead bias)
        if actual_results and game_date:
            result_key = (player, stat_type, game_date)
            if result_key in actual_results:
                actual = actual_results[result_key]
                actual_stat = actual.get("actual_stat")
                line = projection.get("line_score", 0)

                if actual_stat is None:
                    return "loss", None

                # Determine if bet won
                if recommendation == "OVER":
                    won = actual_stat > line
                elif recommendation == "UNDER":
                    won = actual_stat < line
                else:
                    return "loss", actual_stat

                # Check for push
                if actual_stat == line:
                    return "push", actual_stat

                return "win" if won else "loss", actual_stat

        # Monte Carlo simulation using model probability
        random_draw = random.random()
        if abs(random_draw - model_prob) < 0.001:  # Essentially equal = push
            return "push", None

        return "win" if random_draw < model_prob else "loss", None

    def _calculate_stake(
        self,
        bankroll: float,
        probability: float,
        odds: int,
    ) -> float:
        """Calculate stake amount based on staking method.

        Args:
            bankroll: Current bankroll
            probability: Win probability
            odds: American odds

        Returns:
            Stake amount
        """
        return self.strategy.calculate_stake(bankroll, probability, odds)

    def _calculate_profit(
        self,
        outcome: str,
        stake: float,
        odds: int,
    ) -> float:
        """Calculate profit/loss from bet outcome.

        Args:
            outcome: "win", "loss", or "push"
            stake: Amount wagered
            odds: American odds

        Returns:
            Profit/loss amount
        """
        if outcome == "push":
            return 0.0

        if outcome == "loss":
            return -stake

        # Win - calculate payout
        if odds >= 0:
            payout = stake * (odds / 100)
        else:
            payout = stake * (100 / abs(odds))

        return payout


async def query_historical_projections(
    db,
    start_date: date,
    end_date: date,
    sites: Optional[list[str]] = None,
) -> list[dict[str, Any]]:
    """Query historical projections from TimescaleDB.

    Args:
        db: TimescaleDB instance
        start_date: Start of date range
        end_date: End of date range
        sites: Optional list of sites to filter

    Returns:
        List of projection dicts
    """
    projections = []

    # Query each site's evaluations table
    site_list = sites or ["prizepicks", "underdog", "fanduel", "draftkings"]

    async with db.acquire() as conn:
        for site in site_list:
            table = f"{site}.evaluations"

            # Check if table exists and has data
            query = f"""
                SELECT
                    time,
                    player_name,
                    stat_type,
                    line_score,
                    recommendation,
                    confidence,
                    ev,
                    hit_probability,
                    model_prob,
                    market_prob
                FROM {table}
                WHERE time >= $1
                  AND time <= $2
                ORDER BY time
            """

            try:
                rows = await conn.fetch(
                    query,
                    datetime.combine(start_date, datetime.min.time()),
                    datetime.combine(end_date, datetime.max.time()),
                )

                for row in rows:
                    projections.append(
                        {
                            "player_name": row["player_name"],
                            "stat_type": row["stat_type"],
                            "line_score": row["line_score"],
                            "site": site,
                            "odds": _site_to_odds(site, row["line_score"]),
                            "ev": row["ev"] or 0.0,
                            "confidence": (row["confidence"] or 0.0),
                            "model_prob": row["model_prob"] or 0.5,
                            "recommendation": (row["recommendation"] or "OVER").upper(),
                            "game_date": row["time"].date() if row["time"] else None,
                        }
                    )
            except Exception as e:
                print(f"Error querying {site} evaluations: {e}")
                continue

    return projections


def _site_to_odds(site: str, line: float) -> int:
    """Get typical American odds for a site.

    Args:
        site: Site name
        line: Line score

    Returns:
        American odds (default -110)
    """
    # Most sites use standard -110 lines
    default_odds = {
        "prizepicks": -110,
        "underdog": -110,
        "fanduel": -110,
        "draftkings": -110,
    }
    return default_odds.get(site, -110)


async def query_actual_results(
    db,
    start_date: date,
    end_date: date,
) -> dict[tuple[str, str, date], dict[str, Any]]:
    """Query actual game results from TimescaleDB.

    Args:
        db: TimescaleDB instance
        start_date: Start of date range
        end_date: End of date range

    Returns:
        Dict mapping (player, stat_type, date) to result dict
    """
    results = {}

    async with db.acquire() as conn:
        query = """
            SELECT
                player_name,
                stat_type,
                stat_value,
                game_id,
                time
            FROM public.player_stats
            WHERE time >= $1
              AND time <= $2
        """

        try:
            rows = await conn.fetch(
                query,
                datetime.combine(start_date, datetime.min.time()),
                datetime.combine(end_date, datetime.max.time()),
            )

            for row in rows:
                key = (
                    row["player_name"],
                    row["stat_type"],
                    row["time"].date() if row["time"] else None,
                )
                results[key] = {
                    "actual_stat": row["stat_value"],
                    "game_id": row["game_id"],
                }
        except Exception as e:
            print(f"Error querying player_stats: {e}")

    return results
