"""Parameter sweep for strategy optimization.

This module provides the ParameterSweep class that runs multiple
backtests with varying parameters to find optimal strategy settings.
"""

from datetime import date
from typing import Any, Optional

from sportsquant.models.analysis.backtest import BacktestEngine
from sportsquant.models.analysis.backtest_result import BacktestResult
from sportsquant.models.analysis.strategies import Strategy


class ParameterSweep:
    """Run multiple backtests with varying parameters.

    Performs systematic parameter sweeps to find optimal strategy
    settings based on historical performance.
    """

    def __init__(
        self,
        base_strategy: Strategy,
        projections: list[dict[str, Any]],
        actual_results: Optional[dict[str, dict[str, Any]]] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ):
        """Initialize parameter sweep.

        Args:
            base_strategy: Base strategy to modify
            projections: Historical projections to backtest on
            actual_results: Optional actual game results
            start_date: Optional start date for backtest (uses projection dates if not provided)
            end_date: Optional end date for backtest (uses projection dates if not provided)
        """
        self.base_strategy = base_strategy
        self.projections = projections
        self.actual_results = actual_results

        # Compute date range from projections if not provided
        if start_date and end_date:
            self.start_date = start_date
            self.end_date = end_date
        elif projections:
            dates = [p.get("game_date") for p in projections if p.get("game_date")]
            if dates:
                self.start_date = min(dates)
                self.end_date = max(dates)
            else:
                self.start_date = date.today()
                self.end_date = date.today()
        else:
            self.start_date = date.today()
            self.end_date = date.today()

    async def sweep_ev_threshold(
        self,
        start: float = 0.0,
        end: float = 0.25,
        step: float = 0.05,
    ) -> list[BacktestResult]:
        """Test different EV thresholds.

        Args:
            start: Starting EV threshold
            end: Ending EV threshold
            step: Step size between tests

        Returns:
            List of BacktestResult for each EV threshold tested
        """
        results = []
        ev = start

        while ev <= end + 0.001:  # Small epsilon for float comparison
            strategy = Strategy(
                name=f"{self.base_strategy.name}_ev_{ev:.2f}",
                min_ev=ev,
                min_confidence=self.base_strategy.min_confidence,
                max_odds=self.base_strategy.max_odds,
                sites=self.base_strategy.sites,
                stats=self.base_strategy.stats,
                stake_method=self.base_strategy.stake_method,
                flat_stake=self.base_strategy.flat_stake,
                kelly_fraction=self.base_strategy.kelly_fraction,
            )

            engine = BacktestEngine(
                strategy=strategy,
                start_date=self.start_date,
                end_date=self.end_date,
            )

            result = await engine.run(self.projections, self.actual_results)
            results.append(result)

            ev += step

        return results

    async def sweep_confidence(
        self,
        start: float = 0,
        end: float = 100,
        step: float = 10,
    ) -> list[BacktestResult]:
        """Test different confidence thresholds.

        Args:
            start: Starting confidence threshold
            end: Ending confidence threshold
            step: Step size between tests

        Returns:
            List of BacktestResult for each confidence threshold tested
        """
        results = []
        confidence = start

        while confidence <= end + 0.001:
            strategy = Strategy(
                name=f"{self.base_strategy.name}_conf_{confidence:.0f}",
                min_ev=self.base_strategy.min_ev,
                min_confidence=confidence,
                max_odds=self.base_strategy.max_odds,
                sites=self.base_strategy.sites,
                stats=self.base_strategy.stats,
                stake_method=self.base_strategy.stake_method,
                flat_stake=self.base_strategy.flat_stake,
                kelly_fraction=self.base_strategy.kelly_fraction,
            )

            engine = BacktestEngine(
                strategy=strategy,
                start_date=self.start_date,
                end_date=self.end_date,
            )

            result = await engine.run(self.projections, self.actual_results)
            results.append(result)

            confidence += step

        return results

    async def sweep_stake_size(
        self,
        sizes: list[float] = None,
    ) -> list[BacktestResult]:
        """Test different flat stake sizes.

        Args:
            sizes: List of stake amounts to test

        Returns:
            List of BacktestResult for each stake size tested
        """
        if sizes is None:
            sizes = [5.0, 10.0, 25.0, 50.0, 100.0]

        results = []

        for stake in sizes:
            strategy = Strategy(
                name=f"{self.base_strategy.name}_stake_{stake:.0f}",
                min_ev=self.base_strategy.min_ev,
                min_confidence=self.base_strategy.min_confidence,
                max_odds=self.base_strategy.max_odds,
                sites=self.base_strategy.sites,
                stats=self.base_strategy.stats,
                stake_method="flat",
                flat_stake=stake,
                kelly_fraction=self.base_strategy.kelly_fraction,
            )

            engine = BacktestEngine(
                strategy=strategy,
                start_date=self.start_date,
                end_date=self.end_date,
            )

            result = await engine.run(self.projections, self.actual_results)
            results.append(result)

        return results

    async def sweep_kelly_fraction(
        self,
        fractions: list[float] = None,
    ) -> list[BacktestResult]:
        """Test different Kelly fractions.

        Args:
            fractions: List of Kelly fractions to test

        Returns:
            List of BacktestResult for each Kelly fraction tested
        """
        if fractions is None:
            fractions = [0.1, 0.15, 0.25, 0.33, 0.5]

        results = []

        for kelly_frac in fractions:
            strategy = Strategy(
                name=f"{self.base_strategy.name}_kelly_{kelly_frac:.2f}",
                min_ev=self.base_strategy.min_ev,
                min_confidence=self.base_strategy.min_confidence,
                max_odds=self.base_strategy.max_odds,
                sites=self.base_strategy.sites,
                stats=self.base_strategy.stats,
                stake_method="kelly",
                flat_stake=self.base_strategy.flat_stake,
                kelly_fraction=kelly_frac,
            )

            engine = BacktestEngine(
                strategy=strategy,
                start_date=self.start_date,
                end_date=self.end_date,
            )

            result = await engine.run(self.projections, self.actual_results)
            results.append(result)

        return results

    async def sweep_combined(
        self,
        ev_values: list[float] = None,
        confidence_values: list[float] = None,
    ) -> list[BacktestResult]:
        """Test combinations of EV and confidence thresholds.

        Args:
            ev_values: List of EV thresholds to test
            confidence_values: List of confidence thresholds to test

        Returns:
            List of BacktestResult for each combination
        """
        if ev_values is None:
            ev_values = [0.0, 0.05, 0.10, 0.15, 0.20]

        if confidence_values is None:
            confidence_values = [0, 40, 50, 60, 70]

        results = []

        for ev in ev_values:
            for conf in confidence_values:
                strategy = Strategy(
                    name=f"{self.base_strategy.name}_ev{ev:.2f}_conf{conf:.0f}",
                    min_ev=ev,
                    min_confidence=conf,
                    max_odds=self.base_strategy.max_odds,
                    sites=self.base_strategy.sites,
                    stats=self.base_strategy.stats,
                    stake_method=self.base_strategy.stake_method,
                    flat_stake=self.base_strategy.flat_stake,
                    kelly_fraction=self.base_strategy.kelly_fraction,
                )

                engine = BacktestEngine(
                    strategy=strategy,
                    start_date=self.start_date,
                    end_date=self.end_date,
                )

                result = await engine.run(self.projections, self.actual_results)
                results.append(result)

        return results


def summarize_sweep_results(results: list[BacktestResult]) -> dict[str, Any]:
    """Summarize parameter sweep results.

    Args:
        results: List of BacktestResult from sweep

    Returns:
        Summary dict with best parameters
    """
    if not results:
        return {"error": "No results to summarize"}

    # Find best by ROI
    best_roi = max(results, key=lambda r: r.roi_percent)

    # Find best by Sharpe ratio
    best_sharpe = max(results, key=lambda r: r.sharpe_ratio)

    # Find best by total profit
    best_profit = max(results, key=lambda r: r.total_profit)

    # Find most bets (highest volume)
    most_bets = max(results, key=lambda r: r.total_bets)

    return {
        "total_strategies_tested": len(results),
        "best_roi": {
            "strategy": best_roi.strategy.name,
            "roi_percent": best_roi.roi_percent,
            "total_bets": best_roi.total_bets,
        },
        "best_sharpe": {
            "strategy": best_sharpe.strategy.name,
            "sharpe_ratio": best_sharpe.sharpe_ratio,
            "roi_percent": best_sharpe.roi_percent,
        },
        "best_profit": {
            "strategy": best_profit.strategy.name,
            "total_profit": best_profit.total_profit,
            "roi_percent": best_profit.roi_percent,
        },
        "most_bets": {
            "strategy": most_bets.strategy.name,
            "total_bets": most_bets.total_bets,
        },
        "all_results": [r.summary() for r in results],
    }
