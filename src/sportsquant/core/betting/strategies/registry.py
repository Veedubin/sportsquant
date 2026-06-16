"""
Strategy registry for managing and comparing multiple betting strategies.

Provides utilities for running backtests with multiple strategies simultaneously
and comparing their performance.
"""

# pylint: disable=too-many-locals

from typing import Any

import pandas as pd

from sportsquant.core.betting.metrics import (
    calculate_performance_metrics,
    empty_performance_metrics,
)
from sportsquant.core.betting.strategies.base import BettingOpportunity, BettingStrategy


class StrategyRegistry:
    """
    Registry for managing multiple betting strategies.

    Allows running multiple strategies on the same data and comparing results.
    """

    def __init__(self):
        """Initialize empty registry."""
        self._strategies: dict[str, BettingStrategy] = {}

    def register(self, strategy: BettingStrategy) -> None:
        """
        Register a strategy.

        Args:
            strategy: Strategy to register
        """
        self._strategies[strategy.name] = strategy

    def unregister(self, name: str) -> None:
        """
        Unregister a strategy by name.

        Args:
            name: Strategy name to remove
        """
        if name in self._strategies:
            del self._strategies[name]

    def get(self, name: str) -> BettingStrategy | None:
        """
        Get strategy by name.

        Args:
            name: Strategy name

        Returns:
            Strategy instance or None if not found
        """
        return self._strategies.get(name)

    def list_strategies(self) -> list[str]:
        """
        List all registered strategy names.

        Returns:
            List of strategy names
        """
        return list(self._strategies.keys())

    def run_strategies(
        self, opportunities: list[BettingOpportunity], outcomes: list[bool]
    ) -> dict[str, dict[str, Any]]:
        """
        Run all registered strategies on a list of opportunities.

        Args:
            opportunities: List of betting opportunities
            outcomes: List of actual outcomes (True = over, False = under)

        Returns:
            Dict mapping strategy names to their results and metrics
        """
        if len(opportunities) != len(outcomes):
            raise ValueError("opportunities and outcomes must have same length")

        results: dict[str, dict[str, Any]] = {}

        for strategy_name, strategy in self._strategies.items():
            # Reset strategy bankroll
            initial_bankroll = strategy.bankroll

            bets_placed = []
            pnls = []
            evs = []
            bet_outcomes = []

            for opp, outcome in zip(opportunities, outcomes):
                # Get strategy decision
                decision = strategy.evaluate_opportunity(opp)

                if not decision.should_bet or decision.stake == 0:
                    continue  # Skip this opportunity

                # Determine if bet won
                if decision.side == "over":
                    win = outcome  # outcome is True if over
                    odds = opp.odds_over_decimal
                    ev = opp.ev_over
                elif decision.side == "under":
                    win = not outcome  # outcome is False if under
                    odds = opp.odds_under_decimal
                    ev = opp.ev_under
                else:
                    continue  # Invalid side

                # Calculate P&L
                if win:
                    pnl = decision.stake * (odds - 1.0)  # Net profit
                else:
                    pnl = -decision.stake  # Loss

                # Update strategy bankroll
                strategy.update_bankroll(pnl)

                # Record bet
                bets_placed.append(
                    {
                        "side": decision.side,
                        "stake": decision.stake,
                        "odds": odds,
                        "win": win,
                        "pnl": pnl,
                        "ev": ev,
                        "reason": decision.reason,
                    }
                )
                pnls.append(pnl)
                evs.append(ev)
                bet_outcomes.append(win)

            # Calculate performance metrics
            if len(pnls) > 0:
                metrics = calculate_performance_metrics(
                    pnl_series=pd.Series(pnls),
                    ev_series=pd.Series(evs),
                    outcome_series=pd.Series(bet_outcomes),
                    stake_series=pd.Series([b["stake"] for b in bets_placed]),
                )
            else:
                metrics = empty_performance_metrics()

            # Store results
            results[strategy_name] = {
                "bets": bets_placed,
                "metrics": metrics.to_dict(),
                "initial_bankroll": initial_bankroll,
                "final_bankroll": strategy.bankroll,
                "bankroll_change": strategy.bankroll - initial_bankroll,
            }

        return results

    def compare_strategies(
        self, opportunities: list[BettingOpportunity], outcomes: list[bool]
    ) -> pd.DataFrame:
        """
        Run all strategies and return comparison DataFrame.

        Args:
            opportunities: List of betting opportunities
            outcomes: List of actual outcomes

        Returns:
            DataFrame with strategy comparison
        """
        results = self.run_strategies(opportunities, outcomes)

        comparison_data = []
        for strategy_name, result in results.items():
            metrics = result["metrics"]
            row = {
                "strategy": strategy_name,
                "total_bets": metrics["total_bets"],
                "win_rate": metrics["win_rate"],
                "total_pnl": metrics["total_pnl"],
                "mean_pnl": metrics["mean_pnl_per_bet"],
                "sharpe_ratio": metrics["sharpe_ratio"],
                "sortino_ratio": metrics["sortino_ratio"],
                "max_drawdown": metrics["max_drawdown"],
                "profit_factor": metrics["profit_factor"],
                "final_bankroll": result["final_bankroll"],
            }
            comparison_data.append(row)

        return pd.DataFrame(comparison_data)
