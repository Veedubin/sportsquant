"""
Bootstrap P&L Distribution Estimator

Implements bootstrap resampling for estimating the distribution of P&L outcomes
from betting backtest results. Based on BowTiedBettor's "The Power Of Simulations".

MLflow Integration:
- Logs P&L distribution statistics to MLflow
- Logs bootstrap confidence intervals
- Logs Sharpe ratio metrics
- Logs ROI convergence analysis

Data Sources:
- Reads P&L data from TimescaleDB or Parquet data lake
- Reads bet records from Kafka topic 'sports-analytics-model-predictions'

Output:
- Writes analysis results to Kafka topic 'betting-metrics'
- Writes bootstrap results to Parquet for historical analysis
- Supports webhook callbacks for real-time alerts
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

import numpy as np
from pandas import DataFrame
from scipy import stats

if TYPE_CHECKING:
    from sportsquant.core.backtest.analysis.mlflow_logger import (
        BootstrapResultsConfig,
        MLflowLogger,
    )

logger = logging.getLogger(__name__)

NO_BACKTEST_RESULTS = "No backtest results provided"


def _get_mlflow_logger() -> "MLflowLogger | None":
    """Get MLflow logger, returning None if not available."""
    try:
        from sportsquant.util.mlflow_utils import get_mlflow_logger

        return get_mlflow_logger()
    except ImportError:
        return None


@dataclass(frozen=True)
class BootstrapConfig:
    """Configuration for bootstrap P&L analysis."""

    n_bootstrap_samples: int = 1000
    min_bets_per_sample: int = 100
    confidence_levels: tuple[float, ...] = (0.05, 0.50, 0.95)
    random_state: int = 42


@dataclass(frozen=True)
class ColumnMapping:
    """Column mapping for bet DataFrame."""

    stake: str = "stake"
    odds: str = "odds_decimal"
    outcome: str = "outcome"


@dataclass(frozen=True)
class BacktestColumnConfig:
    """Configuration for backtest column names."""

    stake: str = "stake"
    odds: str = "odds_decimal"
    outcome: str = "outcome"


class BootstrapPNLAnalyzer:
    """Bootstrap-based P&L distribution analysis for betting strategies.

    MLflow Integration:
        - Logs P&L distribution statistics
        - Logs confidence intervals at multiple levels
        - Logs Sharpe ratio and other risk metrics
        - Logs ROI convergence analysis
    """

    def __init__(
        self,
        config: Optional[BootstrapConfig] = None,
        mlflow_logger: "Optional[MLflowLogger]" = None,
    ):
        self.config = config or BootstrapConfig()
        self.rng = np.random.default_rng(self.config.random_state)
        self.mlflow_logger = mlflow_logger if mlflow_logger is not None else _get_mlflow_logger()

    def _compute_sample_pnl(
        self,
        bets_df: DataFrame,
        columns: ColumnMapping | None = None,
    ) -> float:
        """Compute total P&L for a sample of bets.

        Args:
            bets_df: DataFrame with bet records
            columns: Column mapping for stake, odds, outcome

        Returns:
            Total P&L for the sample
        """
        if bets_df.empty:
            return 0.0

        cols = columns or ColumnMapping()
        stakes = np.asarray(bets_df[cols.stake].values, dtype=float)
        odds = np.asarray(bets_df[cols.odds].values, dtype=float)
        outcomes = np.asarray(bets_df[cols.outcome].values, dtype=int)

        pnl = np.zeros(len(bets_df), dtype=float)
        win_mask = outcomes == 1
        loss_mask = ~win_mask
        pnl[win_mask] = stakes[win_mask] * (odds[win_mask] - 1)
        pnl[loss_mask] = -stakes[loss_mask]

        return float(np.sum(pnl))

    def _compute_sample_roi(
        self,
        bets_df: DataFrame,
        columns: ColumnMapping | None = None,
    ) -> float:
        """Compute ROI for a sample of bets.

        Args:
            bets_df: DataFrame with bet records
            columns: Column mapping for stake, odds, outcome

        Returns:
            ROI as a percentage (e.g., 5.0 for 5%)
        """
        if bets_df.empty:
            return 0.0

        cols = columns or ColumnMapping()
        total_stake = bets_df[cols.stake].sum()
        if total_stake == 0:
            return 0.0

        pnl = self._compute_sample_pnl(bets_df, columns=cols)
        return float((pnl / total_stake) * 100)

    def _resample_with_replacement(self, bets_df: DataFrame, n_samples: int) -> DataFrame:
        """Create a bootstrap sample with replacement.

        Args:
            bets_df: Original bet DataFrame
            n_samples: Number of samples to draw

        Returns:
            Resampled DataFrame
        """
        n_bets = len(bets_df)
        if n_bets == 0:
            return bets_df.copy()

        indices = self.rng.integers(0, n_bets, size=n_samples)
        return bets_df.iloc[indices].copy().reset_index(drop=True)

    # pylint: disable=too-many-locals
    def analyze_pnl_distribution(
        self,
        backtest_results: DataFrame,
        *,
        target_n_bets: Optional[int] = None,
        columns: BacktestColumnConfig | None = None,
    ) -> dict:
        """Bootstrap resample to estimate P&L distribution.

        Args:
            backtest_results: DataFrame with backtest results
            target_n_bets: Target number of bets per sample (None = use actual count)
            columns: Column configuration for stake, odds, outcome

        Returns:
            Dictionary with distribution statistics and confidence intervals
        """
        if backtest_results.empty:
            return {"error": NO_BACKTEST_RESULTS}

        cols = columns or BacktestColumnConfig()
        col_mapping = ColumnMapping(stake=cols.stake, odds=cols.odds, outcome=cols.outcome)

        n_bets = len(backtest_results)
        sample_size = target_n_bets or n_bets

        if sample_size < self.config.min_bets_per_sample:
            logger.warning(
                "Sample size %d below minimum %d",
                sample_size,
                self.config.min_bets_per_sample,
            )

        n_samples = self.config.n_bootstrap_samples

        pnl_samples = []
        roi_samples = []
        win_rate_samples = []

        logger.info("Running %d bootstrap samples...", n_samples)

        for _ in range(n_samples):
            sample = self._resample_with_replacement(backtest_results, sample_size)

            pnl = self._compute_sample_pnl(sample, columns=col_mapping)
            roi = self._compute_sample_roi(sample, columns=col_mapping)
            win_rate = sample[col_mapping.outcome].mean()

            pnl_samples.append(pnl)
            roi_samples.append(roi)
            win_rate_samples.append(win_rate)

        pnl_array = np.array(pnl_samples)
        roi_array = np.array(roi_samples)
        win_rate_array = np.array(win_rate_samples)

        results = {
            "n_bootstrap_samples": n_samples,
            "sample_size": sample_size,
            "original_n_bets": n_bets,
            "pnl": {
                "mean": float(np.mean(pnl_array)),
                "std": float(np.std(pnl_array)),
                "min": float(np.min(pnl_array)),
                "max": float(np.max(pnl_array)),
                "median": float(np.median(pnl_array)),
            },
            "roi": {
                "mean": float(np.mean(roi_array)),
                "std": float(np.std(roi_array)),
                "min": float(np.min(roi_array)),
                "max": float(np.max(roi_array)),
                "median": float(np.median(roi_array)),
            },
            "win_rate": {
                "mean": float(np.mean(win_rate_array)),
                "std": float(np.std(win_rate_array)),
            },
            "confidence_intervals": {},
        }

        for conf_level in self.config.confidence_levels:
            alpha = 1 - conf_level
            pnl_ci = np.percentile(pnl_array, [alpha / 2 * 100, (1 - alpha / 2) * 100])
            roi_ci = np.percentile(roi_array, [alpha / 2 * 100, (1 - alpha / 2) * 100])
            wr_ci = np.percentile(win_rate_array, [alpha / 2 * 100, (1 - alpha / 2) * 100])

            results["confidence_intervals"][conf_level] = {
                "pnl_lower": float(pnl_ci[0]),
                "pnl_upper": float(pnl_ci[1]),
                "roi_lower": float(roi_ci[0]),
                "roi_upper": float(roi_ci[1]),
                "win_rate_lower": float(wr_ci[0]),
                "win_rate_upper": float(wr_ci[1]),
            }

        pnl_sharpened = self._sharpe_ratio_bootstrapped(pnl_array, backtest_results, cols.stake)
        results["sharpe_ratio"] = pnl_sharpened

        logger.info(
            "Bootstrap complete: mean ROI = %.2f%%, 95%% CI = [%.2f%%, %.2f%%]",
            results["roi"]["mean"],
            results["confidence_intervals"][0.95]["roi_lower"],
            results["confidence_intervals"][0.95]["roi_upper"],
        )

        if self.mlflow_logger is not None:
            self.mlflow_logger.log_bootstrap_results(
                roi_mean=results["roi"]["mean"],
                win_rate_mean=results["win_rate"]["mean"],
                config=BootstrapResultsConfig(  # type: ignore[arg-type]
                    roi_ci_lower=results["confidence_intervals"][0.95]["roi_lower"],
                    roi_ci_upper=results["confidence_intervals"][0.95]["roi_upper"],
                    n_bootstrap_samples=n_samples,
                    pnl_mean=results["pnl"]["mean"],
                    pnl_std=results["pnl"]["std"],
                ),
            )

        return results

    def _sharpe_ratio_bootstrapped(
        self,
        pnl_samples: np.ndarray,
        backtest_results: DataFrame,
        stake_col: str = "stake",
    ) -> float:
        """Compute Sharpe ratio from bootstrap samples.

        Args:
            pnl_samples: Array of P&L samples
            backtest_results: Original backtest DataFrame
            stake_col: Column name for stake

        Returns:
            Sharpe ratio estimate
        """
        if len(pnl_samples) == 0:
            return 0.0

        mean_pnl = np.mean(pnl_samples)
        std_pnl = np.std(pnl_samples)

        if std_pnl == 0:
            return 0.0

        total_stake = (
            backtest_results[stake_col].sum()
            if stake_col in backtest_results.columns
            else len(backtest_results)
        )
        periods_per_year = 252

        annual_return = (mean_pnl / total_stake) * periods_per_year * 100 if total_stake > 0 else 0
        annual_std = (
            (std_pnl / total_stake) * np.sqrt(periods_per_year) * 100 if total_stake > 0 else 0
        )

        if annual_std == 0:
            return 0.0

        return float(annual_return / annual_std)

    def compute_roi_convergence(
        self,
        backtest_results: DataFrame,
        *,
        max_n_bets: int = 10000,
        columns: BacktestColumnConfig | None = None,
    ) -> DataFrame:
        """Compute how fast ROI converges to EV as n_bets increases.

        Args:
            backtest_results: DataFrame with backtest results
            max_n_bets: Maximum number of bets to simulate
            columns: Column configuration for stake, odds, outcome

        Returns:
            DataFrame with convergence statistics at different sample sizes
        """
        if backtest_results.empty:
            return DataFrame()

        cols = columns or BacktestColumnConfig()
        col_mapping = ColumnMapping(stake=cols.stake, odds=cols.odds, outcome=cols.outcome)

        n_bets = len(backtest_results)
        actual_max = min(max_n_bets, n_bets)

        sample_sizes = []
        mean_rois = []
        std_rois = []
        ci_widths = []

        n_samples = min(200, self.config.n_bootstrap_samples)

        sizes_to_check = []
        for s in [10, 25, 50, 100, 200, 500, 1000]:
            if s <= actual_max:
                sizes_to_check.append(s)
        if actual_max > 1000 and actual_max not in sizes_to_check:
            sizes_to_check.append(actual_max)

        for sample_size in sizes_to_check:
            roi_samples = []
            for _ in range(n_samples):
                sample = self._resample_with_replacement(backtest_results, sample_size)
                roi = self._compute_sample_roi(sample, columns=col_mapping)
                roi_samples.append(roi)

            roi_array = np.array(roi_samples)
            sample_sizes.append(sample_size)
            mean_rois.append(float(np.mean(roi_array)))
            std_rois.append(float(np.std(roi_array)))
            ci_widths.append(float(np.percentile(roi_array, 97.5) - np.percentile(roi_array, 2.5)))

        convergence_df = DataFrame(
            {
                "n_bets": sample_sizes,
                "mean_roi": mean_rois,
                "std_roi": std_rois,
                "ci_width_95": ci_widths,
            }
        )

        convergence_df["convergence_ratio"] = (
            convergence_df["std_roi"] / convergence_df["mean_roi"].abs()
        ).replace([np.inf, -np.inf], np.nan)

        logger.info("ROI convergence analysis complete for %d sample sizes", len(convergence_df))

        if self.mlflow_logger:
            self.mlflow_logger.log_table(convergence_df, "roi_convergence.csv")

        return convergence_df

    def compute_probability_of_profit(
        self,
        backtest_results: DataFrame,
        *,
        n_simulations: int = 1000,
        columns: BacktestColumnConfig | None = None,
    ) -> dict:
        """Compute probability of profit over different time horizons.

        Args:
            backtest_results: DataFrame with backtest results
            n_simulations: Number of simulations to run
            columns: Column configuration for stake, odds, outcome

        Returns:
            Dictionary with probability of profit at different horizons
        """
        if backtest_results.empty:
            return {"error": NO_BACKTEST_RESULTS}

        cols = columns or BacktestColumnConfig()
        col_mapping = ColumnMapping(stake=cols.stake, odds=cols.odds, outcome=cols.outcome)

        n_bets = len(backtest_results)
        total_stake = (
            backtest_results[col_mapping.stake].sum()
            if col_mapping.stake in backtest_results.columns
            else n_bets
        )

        horizons = [100, 250, 500, 1000, 2000, 5000]
        horizons = [h for h in horizons if h <= n_bets * 2]

        prob_profit = {}

        for horizon in horizons:
            profits = []
            for _ in range(n_simulations):
                sample = self._resample_with_replacement(backtest_results, horizon)
                pnl = self._compute_sample_pnl(sample, columns=col_mapping)
                profits.append(pnl)

            profits = np.array(profits)
            prob_profit[horizon] = {
                "prob_profit": float((profits > 0).mean()),
                "mean_pnl": float(np.mean(profits)),
                "std_pnl": float(np.std(profits)),
                "var_5": float(np.percentile(profits, 5)),
                "var_1": float(np.percentile(profits, 1)),
            }

        result = {
            "n_simulations": n_simulations,
            "total_stake_per_bet_unit": total_stake / n_bets if n_bets > 0 else 1,
            "horizons": prob_profit,
        }

        if self.mlflow_logger:
            self.mlflow_logger.log_metrics(
                {
                    "prob_profit_100": prob_profit.get(100, {}).get("prob_profit", 0),
                    "prob_profit_500": prob_profit.get(500, {}).get("prob_profit", 0),
                    "prob_profit_1000": prob_profit.get(1000, {}).get("prob_profit", 0),
                }
            )

        return result

    # pylint: disable=too-many-locals
    def compute_value_at_risk(
        self,
        backtest_results: DataFrame,
        *,
        confidence_levels: tuple[float, ...] = (0.95, 0.99),
        columns: BacktestColumnConfig | None = None,
    ) -> dict:
        """Compute Value at Risk (VaR) from bootstrap distribution.

        Args:
            backtest_results: DataFrame with backtest results
            confidence_levels: Confidence levels for VaR
            columns: Column configuration for stake, odds, outcome

        Returns:
            Dictionary with VaR at different confidence levels
        """
        if backtest_results.empty:
            return {"error": NO_BACKTEST_RESULTS}

        cols = columns or BacktestColumnConfig()
        col_mapping = ColumnMapping(stake=cols.stake, odds=cols.odds, outcome=cols.outcome)

        n_samples = self.config.n_bootstrap_samples
        pnl_samples = []

        for _ in range(n_samples):
            sample = self._resample_with_replacement(backtest_results, len(backtest_results))
            pnl = self._compute_sample_pnl(sample, columns=col_mapping)
            pnl_samples.append(pnl)

        pnl_array = np.array(pnl_samples)

        var_results = {}
        for conf in confidence_levels:
            var_results[f"var_{int(conf * 100)}"] = {
                "var": float(np.percentile(pnl_array, (1 - conf) * 100)),
                "cvar": float(
                    np.mean(pnl_array[pnl_array <= np.percentile(pnl_array, (1 - conf) * 100)])
                ),
            }

        result = {
            "var_results": var_results,
            "mean_pnl": float(np.mean(pnl_array)),
            "std_pnl": float(np.std(pnl_array)),
            "skewness": float(stats.skew(pnl_array)),
            "kurtosis": float(stats.kurtosis(pnl_array)),
        }

        if self.mlflow_logger:
            self.mlflow_logger.log_metrics(
                {
                    "var_95": var_results.get("var_95", {}).get("var", 0),
                    "var_99": var_results.get("var_99", {}).get("var", 0),
                    "cvar_95": var_results.get("var_95", {}).get("cvar", 0),
                    "skewness": result["skewness"],
                    "kurtosis": result["kurtosis"],
                }
            )

        return result
