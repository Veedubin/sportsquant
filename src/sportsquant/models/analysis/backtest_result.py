"""Backtest result model and calculations.

This module defines the BacktestResult dataclass that holds
all results and metrics from a backtest simulation.
"""

import math
from dataclasses import dataclass, field
from datetime import date

from sportsquant.models.analysis.strategies import Strategy


@dataclass
class BacktestResult:
    """Results of a backtest simulation.

    Attributes:
        strategy: The strategy used for this backtest
        start_date: Backtest start date
        end_date: Backtest end date
        total_bets: Total number of bets placed
        wins: Number of winning bets
        losses: Number of losing bets
        pushes: Number of pushes (refunded bets)
        total_stake: Total amount wagered
        total_profit: Net profit/loss
        roi_percent: Return on investment as percentage
        win_rate: Win rate as decimal (0-1)
        sharpe_ratio: Risk-adjusted return metric
        max_drawdown: Maximum peak-to-trough decline
        avg_odds: Average American odds
        profit_over_time: List of daily/cumulative profit dicts
        bets: List of individual bet results
    """

    strategy: Strategy
    start_date: date
    end_date: date
    total_bets: int = 0
    wins: int = 0
    losses: int = 0
    pushes: int = 0
    total_stake: float = 0.0
    total_profit: float = 0.0
    roi_percent: float = 0.0
    win_rate: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    avg_odds: float = 0.0
    profit_over_time: list[dict] = field(default_factory=list)
    bets: list[dict] = field(default_factory=list)

    @classmethod
    def calculate(
        cls,
        strategy: Strategy,
        start_date: date,
        end_date: date,
        bets: list[dict],
    ) -> "BacktestResult":
        """Calculate all metrics from a list of bet results.

        Args:
            strategy: Strategy that was used
            start_date: Backtest start date
            end_date: Backtest end date
            bets: List of bet dicts with keys: stake, profit, odds, outcome, date

        Returns:
            BacktestResult with all calculated metrics
        """
        total_bets = len(bets)
        if total_bets == 0:
            return cls(
                strategy=strategy,
                start_date=start_date,
                end_date=end_date,
                total_bets=0,
            )

        # Count outcomes
        wins = sum(1 for b in bets if b.get("outcome") == "win")
        losses = sum(1 for b in bets if b.get("outcome") == "loss")
        pushes = sum(1 for b in bets if b.get("outcome") == "push")

        # Calculate financials
        total_stake = sum(b.get("stake", 0) for b in bets)
        total_profit = sum(b.get("profit", 0) for b in bets)

        # Win rate
        win_rate = wins / total_bets if total_bets > 0 else 0.0

        # ROI
        roi_percent = (total_profit / total_stake * 100) if total_stake > 0 else 0.0

        # Average odds
        avg_odds = sum(b.get("odds", 0) for b in bets) / total_bets

        # Calculate profit over time for charting
        profit_over_time = cls._calculate_profit_timeline(bets)

        # Sharpe ratio (assuming 0 risk-free rate)
        sharpe_ratio = cls._calculate_sharpe_ratio(profit_over_time)

        # Max drawdown
        max_drawdown = cls._calculate_max_drawdown(profit_over_time)

        return cls(
            strategy=strategy,
            start_date=start_date,
            end_date=end_date,
            total_bets=total_bets,
            wins=wins,
            losses=losses,
            pushes=pushes,
            total_stake=total_stake,
            total_profit=total_profit,
            roi_percent=roi_percent,
            win_rate=win_rate,
            sharpe_ratio=sharpe_ratio,
            max_drawdown=max_drawdown,
            avg_odds=avg_odds,
            profit_over_time=profit_over_time,
            bets=bets,
        )

    @staticmethod
    def _calculate_profit_timeline(bets: list[dict]) -> list[dict]:
        """Calculate cumulative profit over time.

        Args:
            bets: List of bet dicts sorted by date

        Returns:
            List of dicts with date and cumulative profit
        """
        if not bets:
            return []

        # Sort by date if not already sorted
        sorted_bets = sorted(bets, key=lambda x: x.get("date", ""))

        timeline = []
        cumulative_profit = 0.0

        for bet in sorted_bets:
            cumulative_profit += bet.get("profit", 0)
            timeline.append(
                {
                    "date": bet.get("date", ""),
                    "cumulative_profit": round(cumulative_profit, 2),
                    "bet_count": len(timeline) + 1,
                }
            )

        return timeline

    @staticmethod
    def _calculate_sharpe_ratio(profit_over_time: list[dict]) -> float:
        """Calculate Sharpe ratio from profit timeline.

        Args:
            profit_over_time: List of daily profit dicts

        Returns:
            Sharpe ratio (or 0 if insufficient data)
        """
        if len(profit_over_time) < 2:
            return 0.0

        # Calculate daily returns
        returns = []
        for i in range(1, len(profit_over_time)):
            prev = profit_over_time[i - 1]["cumulative_profit"]
            curr = profit_over_time[i]["cumulative_profit"]
            daily_return = curr - prev
            returns.append(daily_return)

        if not returns:
            return 0.0

        # Mean return
        mean_return = sum(returns) / len(returns)

        # Standard deviation
        variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
        std_dev = math.sqrt(variance)

        if std_dev == 0:
            return 0.0

        # Annualized Sharpe (assuming 365 days, daily returns)
        sharpe = (mean_return / std_dev) * math.sqrt(365)

        return round(sharpe, 2)

    @staticmethod
    def _calculate_max_drawdown(profit_over_time: list[dict]) -> float:
        """Calculate maximum drawdown from profit timeline.

        Args:
            profit_over_time: List of cumulative profit dicts

        Returns:
            Maximum drawdown as positive number
        """
        if not profit_over_time:
            return 0.0

        peak = profit_over_time[0]["cumulative_profit"]
        max_dd = 0.0

        for entry in profit_over_time:
            profit = entry["cumulative_profit"]
            if profit > peak:
                peak = profit
            drawdown = peak - profit
            if drawdown > max_dd:
                max_dd = drawdown

        return round(max_dd, 2)

    def to_dict(self) -> dict:
        """Convert to dict for JSON serialization.

        Returns:
            Dictionary representation
        """
        return {
            "strategy_name": self.strategy.name,
            "strategy_params": {
                "min_ev": self.strategy.min_ev,
                "min_confidence": self.strategy.min_confidence,
                "max_odds": self.strategy.max_odds,
                "sites": self.strategy.sites,
                "stats": self.strategy.stats,
                "stake_method": self.strategy.stake_method,
                "flat_stake": self.strategy.flat_stake,
                "kelly_fraction": self.strategy.kelly_fraction,
            },
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "total_bets": self.total_bets,
            "wins": self.wins,
            "losses": self.losses,
            "pushes": self.pushes,
            "total_stake": round(self.total_stake, 2),
            "total_profit": round(self.total_profit, 2),
            "roi_percent": round(self.roi_percent, 2),
            "win_rate": round(self.win_rate * 100, 1),
            "sharpe_ratio": self.sharpe_ratio,
            "max_drawdown": self.max_drawdown,
            "avg_odds": round(self.avg_odds, 1),
            "profit_over_time": self.profit_over_time,
            "bets": self.bets,
        }

    def summary(self) -> dict:
        """Get summary metrics only (no individual bets).

        Returns:
            Dictionary with summary stats
        """
        return {
            "strategy_name": self.strategy.name,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "total_bets": self.total_bets,
            "wins": self.wins,
            "losses": self.losses,
            "pushes": self.pushes,
            "total_stake": round(self.total_stake, 2),
            "total_profit": round(self.total_profit, 2),
            "roi_percent": round(self.roi_percent, 2),
            "win_rate": round(self.win_rate * 100, 1),
            "sharpe_ratio": self.sharpe_ratio,
            "max_drawdown": self.max_drawdown,
            "avg_odds": round(self.avg_odds, 1),
        }
