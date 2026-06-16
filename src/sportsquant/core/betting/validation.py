"""
Validation Framework

Adapted from sports_analytics.model.validation
Changes: Replaced sports_analytics.util.logging with standard logging

This module provides comprehensive model validation for betting predictions:
1. Walk-forward validation (time-series proper)
2. Probability calibration (ECE/MCE metrics)
3. CLV (Closing Line Value) tracking
4. Model persistence and comparison
"""

from __future__ import annotations

# pylint: disable=C0302

import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats
from pandas import DataFrame, Series
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import (
    brier_score_loss,
    log_loss,
    mean_absolute_error,
    mean_squared_error,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WalkForwardConfig:
    """Configuration for walk-forward validation."""

    train_window: int = 82
    test_window: int = 20
    min_train_samples: int = 50
    expanding_window: bool = True


@dataclass(frozen=True)
class CalibrationConfig:
    """Configuration for probability calibration."""

    method: str = "isotonic"
    cv_folds: int = 5
    min_samples_for_calibration: int = 30


@dataclass(frozen=True)
class CLVConfig:
    """Configuration for CLV tracking."""

    clv_smoothing_window: int = 50
    min_bets_for_clv: int = 10
    clv_significance_threshold: float = 0.02


@dataclass(frozen=True)
class WeightedCLVConfig:
    """Configuration for weighted CLV calculation."""

    stake_weight: float = 1.0
    time_weight: float = 0.5
    liquidity_weight: float = 0.3
    smoothing_window: int = 50
    min_bets_for_weighted: int = 10


@dataclass(frozen=True)
# pylint: disable=too-many-instance-attributes
class CLVRecord:
    """Immutable record for storing weighted CLV data."""

    bet_id: str
    weighted_clv: float
    raw_clv: float
    stake_weight_factor: float
    time_weight_factor: float
    liquidity_weight_factor: float
    stake: float
    time_to_close: float
    liquidity: float
    market: str
    book: str
    timestamp: datetime


@dataclass(frozen=True)
class CLVTrend:
    """Trend direction and confidence for CLV analysis."""

    direction: str
    confidence: float
    slope: float
    acceleration: float
    n_bets: int


@dataclass
# pylint: disable=too-many-instance-attributes
class MarketCLVStats:
    """Aggregated CLV statistics by market."""

    market: str
    clv_mean: float
    clv_std: float
    weighted_clv_mean: float
    n_bets: int
    market_beating_rate: float
    improving_bets: int
    degrading_bets: int
    avg_stake: float
    avg_time_to_close: float


class MetricsPriority(Enum):
    """Metrics hierarchy - primary to secondary indicators."""

    CLV = 1
    DRAWDOWN_DEPTH = 2
    EDGE_HALF_LIFE = 3
    WIN_RATE = 4
    ROI = 5


@dataclass(frozen=True)
class MetricsDashboardConfig:
    """Configuration for metrics dashboard."""

    clv_window_bets: int = 100
    drawdown_window_days: int = 30
    half_life_window_bets: int = 200
    win_rate_window_bets: int = 50


class WalkForwardValidator:
    """Walk-forward validation for time-series proper evaluation."""

    def __init__(self, config: Optional[WalkForwardConfig] = None):
        self.config = config or WalkForwardConfig()

    def generate_splits(
        self,
        df: DataFrame,
        date_col: str = "game_date",
    ) -> list[tuple[int, int]]:
        """Generate train/test split indices for walk-forward validation.

        Returns:
            List of (train_end_idx, test_end_idx) tuples
        """
        if date_col in df.columns:
            df = df.sort_values(date_col).reset_index(drop=True)

        n = len(df)
        splits = []

        if self.config.expanding_window:
            start_test = self.config.train_window
            while start_test < n:
                train_end = start_test - self.config.test_window
                if train_end >= self.config.min_train_samples:
                    splits.append((train_end, min(start_test, n)))
                start_test += self.config.test_window
        else:
            current_train = self.config.train_window
            while current_train + self.config.test_window <= n:
                splits.append((current_train, current_train + self.config.test_window))
                current_train += self.config.test_window

        logger.info("Generated %d walk-forward splits", len(splits))
        return splits

    def run_walk_forward(  # pylint: disable=too-many-arguments,too-many-locals,too-many-positional-arguments
        self,
        df: DataFrame,
        feature_cols: list[str],
        target_col: str,
        model_factory,
        date_col: str = "game_date",
    ) -> DataFrame:
        """Run walk-forward validation and return predictions.

        Args:
            df: DataFrame with features, target, and date
            feature_cols: List of feature column names
            target_col: Target column name
            model_factory: Function that returns a fresh model instance
            date_col: Name of date column

        Returns:
            DataFrame with predictions and actuals for each test fold
        """
        df = df.sort_values(date_col).reset_index(drop=True)
        splits = self.generate_splits(df, date_col)

        all_predictions = []

        for train_end, test_end in splits:
            train_df = df.iloc[:train_end]
            test_df = df.iloc[train_end:test_end]

            if len(train_df) < self.config.min_train_samples:
                continue

            x_train = train_df[feature_cols]
            y_train = train_df[target_col]
            x_test = test_df[feature_cols]
            y_test = test_df[target_col]

            try:
                model = model_factory()
                model.fit(x_train, y_train)
                predictions = model.predict(x_test)

                fold_results = test_df[[date_col]].copy()
                fold_results["train_start"] = 0
                fold_results["train_end"] = train_end
                fold_results["test_start"] = train_end
                fold_results["test_end"] = test_end
                fold_results["y_true"] = y_test.values
                fold_results["y_pred"] = predictions
                fold_results["fold"] = len(all_predictions)

                all_predictions.append(fold_results)

            except (RuntimeError, ValueError):
                logger.warning("Fold %d failed", len(all_predictions))
                continue

        if all_predictions:
            return pd.concat(all_predictions, ignore_index=True)

        return DataFrame()

    def compute_walk_forward_metrics(self, predictions_df: DataFrame) -> dict:
        """Compute metrics from walk-forward predictions."""
        if predictions_df.empty:
            return {"error": "No predictions to evaluate"}

        y_true = predictions_df["y_true"]
        y_pred = predictions_df["y_pred"]

        mae = mean_absolute_error(y_true, y_pred)
        rmse = np.sqrt(mean_squared_error(y_true, y_pred))
        bias = (y_pred - y_true).mean()

        return {
            "mae": mae,
            "rmse": rmse,
            "bias": bias,
            "n_predictions": len(predictions_df),
            "n_folds": predictions_df["fold"].nunique(),
        }


class ProbabilityCalibrator:
    """Probability calibration for prop outcome predictions."""

    def __init__(self, config: Optional[CalibrationConfig] = None):
        self.config = config or CalibrationConfig()
        self.calibrator: Optional[IsotonicRegression] = None
        self.is_fitted = False

    def convert_to_probabilities(
        self,
        predictions: np.ndarray,
        lines: np.ndarray,
    ) -> np.ndarray:
        """Convert point predictions to over/under probabilities using normal CDF.

        Assumes prediction errors follow a normal distribution.
        """
        pred_diff = predictions - lines

        z_scores = pred_diff / np.std(pred_diff + 1e-6)

        over_probs = 1 - stats.norm.cdf(z_scores)

        return np.clip(over_probs, 0.001, 0.999)

    def fit_calibrator(
        self,
        predictions: np.ndarray,
        actual_outcomes: np.ndarray,
    ) -> "ProbabilityCalibrator":
        """Fit probability calibrator on predictions and outcomes.

        Args:
            predictions: Raw model predictions
            actual_outcomes: Binary outcomes (1 = over, 0 = under)
        """
        if len(predictions) < self.config.min_samples_for_calibration:
            logger.warning(
                "Insufficient samples for calibration: %d < %s",
                len(predictions),
                self.config.min_samples_for_calibration,
            )
            return self

        if self.config.method == "isotonic":
            self.calibrator = IsotonicRegression(increasing=True)
            self.calibrator.fit(predictions, actual_outcomes)
        else:
            self.calibrator = IsotonicRegression(increasing=True)

        self.is_fitted = True
        logger.info("Fitted %s calibrator on %d samples", self.config.method, len(predictions))
        return self

    def calibrate(self, predictions: np.ndarray) -> np.ndarray:
        """Apply calibration to predictions."""
        if not self.is_fitted or self.calibrator is None:
            return predictions

        calibrated = self.calibrator.transform(predictions)
        return np.clip(calibrated, 0.001, 0.999)

    def compute_ece(
        self,
        predictions: np.ndarray,
        actual_outcomes: np.ndarray,
        n_bins: int = 10,
    ) -> float:
        """Compute Expected Calibration Error (ECE).

        Lower is better. Perfect calibration = 0.
        """
        predictions = np.clip(predictions, 0.001, 0.999)

        bin_edges = np.linspace(0, 1, n_bins + 1)
        ece = 0.0

        for i in range(n_bins):
            bin_lower = bin_edges[i]
            bin_upper = bin_edges[i + 1]

            in_bin = (predictions >= bin_lower) & (predictions < bin_upper)
            if in_bin.sum() == 0:
                continue

            bin_accuracy = actual_outcomes[in_bin].mean()
            bin_confidence = predictions[in_bin].mean()
            bin_weight = in_bin.sum() / len(predictions)

            ece += bin_weight * abs(bin_accuracy - bin_confidence)

        return ece

    def compute_mce(
        self,
        predictions: np.ndarray,
        actual_outcomes: np.ndarray,
        n_bins: int = 10,
    ) -> float:
        """Compute Maximum Calibration Error (MCE).

        Measures worst-case calibration error across bins.
        """
        predictions = np.clip(predictions, 0.001, 0.999)

        bin_edges = np.linspace(0, 1, n_bins + 1)
        max_error = 0.0

        for i in range(n_bins):
            bin_lower = bin_edges[i]
            bin_upper = bin_edges[i + 1]

            in_bin = (predictions >= bin_lower) & (predictions < bin_upper)
            if in_bin.sum() == 0:
                continue

            bin_accuracy = abs(actual_outcomes[in_bin].mean() - predictions[in_bin].mean())
            max_error = max(max_error, bin_accuracy)

        return max_error

    def compute_brier_score(
        self,
        predictions: np.ndarray,
        actual_outcomes: np.ndarray,
    ) -> float:
        """Compute Brier Score.

        Measures mean squared error between predictions and outcomes.
        Lower is better. Perfect = 0.
        """
        predictions = np.clip(predictions, 0.001, 0.999)
        return brier_score_loss(actual_outcomes, predictions)

    def compute_log_loss(
        self,
        predictions: pd.Series,
        actual_outcomes: pd.Series,
    ) -> float:
        """Compute Log Loss for probability predictions.

        Measures the negative log-likelihood of predictions.
        Lower is better. Perfect = 0.
        """
        return float(log_loss(actual_outcomes, predictions))

    def compute_all_calibration_metrics(
        self,
        predictions: np.ndarray,
        actual_outcomes: np.ndarray,
    ) -> dict:
        """Compute all calibration metrics."""
        return {
            "ece": self.compute_ece(predictions, actual_outcomes),
            "mce": self.compute_mce(predictions, actual_outcomes),
            "brier_score": self.compute_brier_score(predictions, actual_outcomes),
            "log_loss": log_loss(actual_outcomes, predictions),
            "n_samples": len(predictions),
        }


class CLVTracker:
    """Closing Line Value (CLV) tracking and analysis.

    CLV measures how well you beat the market:
    - Positive CLV: You consistently get better odds than closing line
    - Negative CLV: Market outperforms your projections
    """

    def __init__(self, config: Optional[CLVConfig] = None):
        self.config = config or CLVConfig()

    def compute_clv(
        self,
        closing_line: float,
        our_line: float,
        outcome: Optional[int] = None,
    ) -> float:
        """Compute Closing Line Value (CLV) for a bet.

        CLV measures how much better our odds were compared to the closing line.
        Positive CLV = we beat the market (got better odds)
        Negative CLV = market beat us (closing line was better)

        Args:
            closing_line: Market closing odds (decimal)
            our_line: Odds we got (decimal)
            outcome: Bet outcome (1=won, 0=lost). If provided, CLV is adjusted by outcome.

        Returns:
            CLV value (positive = we beat the market)
        """
        closing_implied = 1 / closing_line
        our_implied = 1 / our_line

        clv = closing_implied - our_implied

        if outcome is not None:
            clv = clv * outcome

        return clv

    def compute_clv_roi(
        self,
        clv_values: pd.Series,
        outcomes: Optional[pd.Series] = None,
    ) -> float:
        """Compute ROI adjusted for CLV.

        Args:
            clv_values: Series of CLV values
            outcomes: Optional Series of bet outcomes (1=won, 0=lost)
        """
        if outcomes is not None:
            clv_values = clv_values * outcomes

        if len(clv_values) < self.config.min_bets_for_clv:
            return 0.0

        avg_clv = clv_values.mean()

        roi_per_unit = avg_clv * 100

        return roi_per_unit

    def compute_market_beating_rate(
        self,
        clv_values: Series,
    ) -> float:
        """Compute percentage of bets that beat the closing line."""
        if len(clv_values) < self.config.min_bets_for_clv:
            return 0.5

        return (clv_values > 0).mean()

    def compute_clv_trend(
        self,
        clv_df: DataFrame,
        date_col: str = "game_date",
    ) -> DataFrame:
        """Compute rolling CLV trends over time."""
        clv_df = clv_df.sort_values(date_col).copy()

        clv_df["clv_cumulative"] = clv_df["clv"].cumsum()
        clv_df["clv_rolling_mean"] = (
            clv_df["clv"].rolling(self.config.clv_smoothing_window, min_periods=10).mean()
        )
        clv_df["clv_rolling_std"] = (
            clv_df["clv"].rolling(self.config.clv_smoothing_window, min_periods=10).std()
        )

        clv_df["clv_z_score"] = clv_df["clv_rolling_mean"] / clv_df["clv_rolling_std"]

        return clv_df

    def compute_clv_by_market(
        self,
        clv_df: DataFrame,
        market_col: str = "market",
    ) -> DataFrame:
        """Compute CLV statistics by market (pts, reb, ast, pra)."""
        stats_df = (
            clv_df.groupby(market_col)
            .agg(
                {
                    "clv": ["mean", "std", "count"],
                    "roi": "mean",
                }
            )
            .round(4)
        )

        stats_df.columns = ["clv_mean", "clv_std", "n_bets", "roi_mean"]
        stats_df["market_beating_rate"] = clv_df.groupby(market_col).apply(
            lambda x: (x["clv"] > 0).mean(), include_groups=False
        )

        return stats_df.reset_index()

    def compute_clv_by_book(
        self,
        clv_df: DataFrame,
        book_col: str = "book",
    ) -> DataFrame:
        """Compute CLV statistics by sportsbook."""
        stats_df = (
            clv_df.groupby(book_col)
            .agg(
                {
                    "clv": ["mean", "std", "count"],
                    "roi": "mean",
                }
            )
            .round(4)
        )

        stats_df.columns = ["clv_mean", "clv_std", "n_bets", "roi_mean"]
        stats_df["book_beating_rate"] = clv_df.groupby(book_col).apply(
            lambda x: (x["clv"] > 0).mean(), include_groups=False
        )

        return stats_df.reset_index()

    def is_clv_significant(
        self,
        clv_mean: float,
        clv_std: float,
        n_bets: int,
    ) -> bool:
        """Check if CLV is statistically significant."""
        if n_bets < self.config.min_bets_for_clv:
            return False

        se = clv_std / np.sqrt(n_bets)
        z_score = clv_mean / se

        return abs(z_score) > 1.96 and abs(clv_mean) > self.config.clv_significance_threshold

    def compute_all_clv_stats(self, clv_df: DataFrame) -> dict:
        """Compute comprehensive CLV statistics."""
        if clv_df.empty or "clv" not in clv_df.columns:
            return {"error": "No CLV data available"}

        clv_col = clv_df["clv"]
        if not isinstance(clv_col, pd.Series):
            clv_col = pd.Series(clv_col)

        odds_col = clv_df.get("odds_decimal")
        if not isinstance(odds_col, pd.Series):
            odds_col = pd.Series([2.0] * len(clv_df))

        clv_mean_val = float(clv_col.mean())
        clv_std_val = float(clv_col.std())

        return {
            "total_bets": len(clv_df),
            "clv_mean": clv_mean_val,
            "clv_std": clv_std_val,
            "clv_cumulative": float(clv_col.sum()),
            "market_beating_rate": self.compute_market_beating_rate(clv_col),
            "roi_estimate": self.compute_clv_roi(clv_col, odds_col),
            "significant_edge": self.is_clv_significant(
                clv_mean_val,
                clv_std_val,
                len(clv_df),
            ),
        }

    def compute_weighted_clv(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        closing_line: float,
        our_line: float,
        stake: float,
        time_to_close: float,
        liquidity: float,
        outcome: Optional[int] = None,
        config: Optional[WeightedCLVConfig] = None,
    ) -> float:
        """Compute weighted Closing Line Value (CLV).

        Applies stake, time, and liquidity weights to raw CLV.

        Args:
            closing_line: Market closing odds (decimal)
            our_line: Odds we got (decimal)
            stake: Amount wagered
            time_to_close: Hours until game starts
            liquidity: Market liquidity score (0-1)
            outcome: Bet outcome (1=won, 0=lost)
            config: WeightedCLVConfig for customization

        Returns:
            Weighted CLV value
        """
        cfg = config or WeightedCLVConfig()
        raw_clv = self.compute_clv(closing_line, our_line, outcome)

        stake_normalized = np.log1p(stake) / np.log1p(10000)
        time_weight_factor = np.exp(-cfg.time_weight * time_to_close / 24)
        liquidity_weight_factor = cfg.liquidity_weight * liquidity + (1 - cfg.liquidity_weight)
        stake_weight_factor = cfg.stake_weight * stake_normalized + (1 - cfg.stake_weight) * 0.5

        weighted_clv = raw_clv * stake_weight_factor * time_weight_factor * liquidity_weight_factor

        return weighted_clv

    def compute_rolling_clv_mean(
        self,
        clv_series: Series,
        window: int = 50,
        min_periods: int = 10,
    ) -> pd.Series:
        """Compute rolling mean of CLV values."""
        result = clv_series.rolling(window=window, min_periods=min_periods).mean()
        return pd.Series(result) if not isinstance(result, pd.Series) else result

    def compute_rolling_clv_std(
        self,
        clv_series: Series,
        window: int = 50,
        min_periods: int = 10,
    ) -> pd.Series:
        """Compute rolling standard deviation of CLV values."""
        result = clv_series.rolling(window=window, min_periods=min_periods).std()
        return pd.Series(result) if not isinstance(result, pd.Series) else result

    def compute_clv_z_score(
        self,
        clv_series: Series,
        window: int = 50,
    ) -> pd.Series:
        """Compute rolling Z-score of CLV values."""
        rolling_mean = self.compute_rolling_clv_mean(clv_series, window)
        rolling_std = self.compute_rolling_clv_std(clv_series, window)

        with np.errstate(divide="ignore", invalid="ignore"):
            z_score = (clv_series - rolling_mean) / rolling_std

        return z_score

    def compute_clv_by_period(
        self,
        clv_df: DataFrame,
        date_col: str = "timestamp",
        period: str = "day",
    ) -> DataFrame:
        """Aggregate CLV statistics by time period."""
        if clv_df.empty or date_col not in clv_df.columns:
            return DataFrame()

        clv_df = clv_df.copy()
        clv_df["period"] = pd.to_datetime(clv_df[date_col]).dt.to_period(period)

        stats_df = (
            clv_df.groupby("period")
            .agg(
                {
                    "clv": ["mean", "std", "count"],
                    "weighted_clv": "mean" if "weighted_clv" in clv_df.columns else "mean",
                }
            )
            .round(6)
        )
        stats_df.columns = ["clv_mean", "clv_std", "n_bets", "weighted_clv_mean"]
        stats_df["market_beating_rate"] = clv_df.groupby("period").apply(
            lambda x: (x["clv"] > 0).mean(), include_groups=False
        )

        return stats_df.reset_index()

    def detect_clv_trend(
        self,
        clv_series: Series,
        window: int = 10,
        min_periods: int = 3,
    ) -> str:
        """Detect CLV trend direction.

        Args:
            clv_series: Series of CLV values
            window: Rolling window for trend analysis

        Returns:
            Trend direction: 'improving', 'flat', or 'degrading'
        """
        if len(clv_series) < window:
            return "flat"

        rolling_mean = self.compute_rolling_clv_mean(clv_series, window, min_periods)
        rolling_mean = rolling_mean.dropna()

        if len(rolling_mean) < 2:
            return "flat"

        first_half = rolling_mean.iloc[: len(rolling_mean) // 2].mean()
        second_half = rolling_mean.iloc[len(rolling_mean) // 2 :].mean()

        diff = second_half - first_half
        threshold = clv_series.std() * 0.05

        if diff > threshold:
            return "improving"
        if diff < -threshold:
            return "degrading"
        return "flat"

    def compute_clv_acceleration(
        self,
        clv_series: Series,
        window: int = 50,
    ) -> float:
        """Compute CLV acceleration (rate of change of the trend)."""
        if len(clv_series) < window * 2:
            return 0.0

        rolling_mean = self.compute_rolling_clv_mean(clv_series, window)
        rolling_mean = rolling_mean.dropna()

        if len(rolling_mean) < 2:
            return 0.0

        slope_values = rolling_mean.diff()
        acceleration = slope_values.diff().mean()

        return float(acceleration)


class ModelValidator:
    """Comprehensive model validation combining all components."""

    def __init__(self):
        self.wf_validator = WalkForwardValidator()
        self.calibrator = ProbabilityCalibrator()
        self.clv_tracker = CLVTracker()

    def fit_calibrator(
        self,
        predictions: np.ndarray,
        actual_outcomes: np.ndarray,
        n_bins: int = 5,
    ) -> "ModelValidator":
        """Fit probability calibrator on predictions and outcomes."""
        config = CalibrationConfig(cv_folds=n_bins)
        self.calibrator = ProbabilityCalibrator(config)
        self.calibrator.fit_calibrator(predictions, actual_outcomes)
        return self

    def run_full_validation(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        df: DataFrame,
        feature_cols: list[str],
        target_col: str,
        model_factory,
        lines_df: Optional[DataFrame] = None,
        date_col: str = "game_date",
    ) -> dict:
        """Run complete validation pipeline."""
        logger.info("Running walk-forward validation...")
        wf_preds = self.wf_validator.run_walk_forward(
            df, feature_cols, target_col, model_factory, date_col
        )
        wf_metrics = self.wf_validator.compute_walk_forward_metrics(wf_preds)

        results = {
            "walk_forward": wf_metrics,
            "n_predictions": len(wf_preds),
        }

        if lines_df is not None and not wf_preds.empty:
            logger.info("Computing CLV metrics...")
            merged = wf_preds.merge(
                lines_df[[date_col, "odds_decimal", "actual_over"]],
                on=date_col,
                how="inner",
            )

            if not merged.empty and "y_pred" in merged.columns:
                merged["projected_prob"] = self.calibrator.convert_to_probabilities(
                    merged["y_pred"].to_numpy(),
                    merged["line"].to_numpy(),
                )
                merged["clv"] = merged.apply(
                    lambda row: self.clv_tracker.compute_clv(
                        row["projected_prob"],
                        row["odds_decimal"],
                        row["actual_over"],
                    ),
                    axis=1,
                )

                clv_stats = self.clv_tracker.compute_all_clv_stats(merged)
                results["clv"] = clv_stats

                if "projected_prob" in merged.columns and "actual_over" in merged.columns:
                    cal_metrics = self.calibrator.compute_all_calibration_metrics(
                        merged["projected_prob"].to_numpy(),
                        merged["actual_over"].to_numpy(),
                    )
                    results["calibration"] = cal_metrics

        return results

    def get_metrics_dashboard(self, bet_history: list[dict]) -> dict:
        """Get comprehensive metrics dashboard."""
        if not bet_history:
            return {"error": "No bet history provided"}

        df = pd.DataFrame(bet_history)
        clv_raw = df.get("clv")
        profit_raw = df.get("profit_loss")
        outcomes_raw = df.get("actual_result")

        clv_list = list(clv_raw) if clv_raw is not None and len(clv_raw) > 0 else []
        profit_list = list(profit_raw) if profit_raw is not None and len(profit_raw) > 0 else []
        outcomes_list = (
            list(outcomes_raw) if outcomes_raw is not None and len(outcomes_raw) > 0 else []
        )

        clv_series = (
            pd.Series(clv_list, dtype=float) if len(clv_list) > 0 else pd.Series([], dtype=float)
        )
        profit_series = (
            pd.Series(profit_list, dtype=float)
            if len(profit_list) > 0
            else pd.Series([], dtype=float)
        )
        outcomes = (
            pd.Series(outcomes_list, dtype=str)
            if len(outcomes_list) > 0
            else pd.Series([], dtype=str)
        )

        config = MetricsDashboardConfig()

        clv_trend = self.clv_tracker.detect_clv_trend(clv_series, config.clv_window_bets)
        clv_acceleration = self.clv_tracker.compute_clv_acceleration(
            clv_series, config.half_life_window_bets
        )

        win_rate = 0.0
        if len(outcomes) > 0:
            win_rate = (
                (outcomes == "win").mean()
                if isinstance(outcomes, pd.Series)
                else outcomes.count("win") / len(outcomes)
            )

        roi = 0.0
        if len(profit_series) > 0 and "stake" in df.columns:
            total_stake = df["stake"].sum()
            roi = float(profit_series.sum()) / total_stake if total_stake > 0 else 0.0

        profit_cumsum = profit_series.cumsum()
        drawdown = self._compute_max_drawdown(profit_cumsum)

        half_life = self._estimate_edge_half_life(clv_series)

        clv_len = len(clv_series)
        clv_mean_val = float(clv_series.mean()) if clv_len > 0 else 0.0
        clv_std_val = float(clv_series.std()) if clv_len > 0 else 0.0

        profit_len = len(profit_series)
        current_drawdown = float(profit_cumsum.iloc[-1]) if profit_len > 0 else 0.0
        total_profit_val = float(profit_series.sum()) if profit_len > 0 else 0.0

        return {
            "primary_metrics": {
                "clv": {
                    "mean": clv_mean_val,
                    "std": clv_std_val,
                    "trend": clv_trend,
                    "acceleration": float(clv_acceleration),
                    "market_beating_rate": self.clv_tracker.compute_market_beating_rate(clv_series),
                },
                "drawdown": {
                    "max_drawdown": float(drawdown),
                    "current_drawdown": current_drawdown,
                },
                "edge_half_life": {
                    "estimated_half_life": half_life,
                    "confidence": min(1.0, clv_len / config.half_life_window_bets),
                },
            },
            "secondary_metrics": {
                "win_rate": win_rate,
                "roi": roi,
                "total_bets": len(bet_history),
                "total_profit": total_profit_val,
            },
            "config": {
                "clv_window_bets": config.clv_window_bets,
                "drawdown_window_days": config.drawdown_window_days,
                "half_life_window_bets": config.half_life_window_bets,
                "win_rate_window_bets": config.win_rate_window_bets,
            },
        }

    def get_metrics_priority_report(self, bet_history: list[dict]) -> dict:
        """Get metrics ranked by priority."""
        dashboard = self.get_metrics_dashboard(bet_history)

        if "error" in dashboard:
            return dashboard

        priority_order = [
            ("clv", MetricsPriority.CLV.value),
            ("drawdown", MetricsPriority.DRAWDOWN_DEPTH.value),
            ("edge_half_life", MetricsPriority.EDGE_HALF_LIFE.value),
            ("win_rate", MetricsPriority.WIN_RATE.value),
            ("roi", MetricsPriority.ROI.value),
        ]

        ranked_metrics = {}
        for metric_name, priority in priority_order:
            if metric_name in dashboard.get("primary_metrics", {}):
                ranked_metrics[metric_name] = {
                    "priority": priority,
                    "data": dashboard["primary_metrics"][metric_name],
                }
            elif metric_name in dashboard.get("secondary_metrics", {}):
                ranked_metrics[metric_name] = {
                    "priority": priority,
                    "data": dashboard["secondary_metrics"][metric_name],
                }

        return {
            "ranked_metrics": ranked_metrics,
            "summary": self._generate_priority_summary(ranked_metrics),
        }

    def compute_edge_confidence_score(
        self,
        clv_trend: str,
        half_life: float,
        drawdown: float,
        win_rate: float,
    ) -> float:
        """Compute composite edge confidence score (0-1)."""
        clv_score = 0.5
        if clv_trend == "improving":
            clv_score = 1.0
        elif clv_trend == "degrading":
            clv_score = 0.0

        half_life_score = min(1.0, half_life / 100)

        drawdown_score = max(0.0, 1.0 - drawdown)

        confidence = (
            0.40 * clv_score + 0.30 * half_life_score + 0.20 * drawdown_score + 0.10 * win_rate
        )

        return round(max(0.0, min(1.0, confidence)), 4)

    def _compute_max_drawdown(self, cumulative_pnl: pd.Series) -> float:
        """Compute maximum drawdown from cumulative P&L series."""
        if cumulative_pnl.empty:
            return 0.0

        running_max = cumulative_pnl.cummax()
        drawdown = running_max - cumulative_pnl

        return float(drawdown.max())

    def _estimate_edge_half_life(self, clv_series: pd.Series) -> float:
        """Estimate how many bets until edge decays by half."""
        if len(clv_series) < 10:
            return 0.0

        clv_rolling = self.clv_tracker.compute_rolling_clv_mean(clv_series, window=20)
        clv_rolling = clv_rolling.dropna()

        if len(clv_rolling) < 5:
            return 0.0

        initial_clv = clv_rolling.iloc[:5].mean()
        if abs(initial_clv) < 0.001:
            return float(len(clv_series))

        half_value = initial_clv / 2
        for i, val in enumerate(clv_rolling):
            if abs(val - initial_clv) < abs(half_value):
                return float(i * 20)

        return float(len(clv_series))

    def _generate_priority_summary(self, ranked_metrics: dict) -> str:
        """Generate human-readable summary from ranked metrics."""
        if not ranked_metrics:
            return "Insufficient data"

        summary_parts = []

        if "clv" in ranked_metrics:
            clv_data = ranked_metrics["clv"]["data"]
            trend = clv_data.get("trend", "unknown")
            mean = clv_data.get("mean", 0)
            if trend == "improving" and mean > 0:
                summary_parts.append(f"CLV trending up ({mean:.4f})")
            elif trend == "degrading" or mean < 0:
                summary_parts.append(f"CLV declining ({mean:.4f})")

        if "drawdown" in ranked_metrics:
            dd_data = ranked_metrics["drawdown"]["data"]
            max_dd = dd_data.get("max_drawdown", 0)
            if max_dd > 0.1:
                summary_parts.append(f"Deep drawdown ({max_dd:.2%})")
            elif max_dd < 0.02:
                summary_parts.append("Low drawdown risk")

        if "edge_half_life" in ranked_metrics:
            hl_data = ranked_metrics["edge_half_life"]["data"]
            half_life = hl_data.get("estimated_half_life", 0)
            if half_life > 100:
                summary_parts.append("Sustained edge")
            elif half_life < 20:
                summary_parts.append("Edge decaying quickly")

        return "; ".join(summary_parts) if summary_parts else "Collecting data..."


def compute_edge_durability_score(
    clv_series: pd.Series,
    stake_history: list[float] | None = None,
) -> float:
    """Compute edge durability score from CLV and stake history."""
    if len(clv_series) < 10:
        return 50.0

    score = 100.0

    recent_clv = clv_series.tail(20).mean()
    older_clv = clv_series.head(20).mean() if len(clv_series) > 20 else recent_clv

    if older_clv > 0:
        retention = recent_clv / older_clv
        if retention < 1.0:
            score -= (1.0 - retention) * 50

    if len(clv_series) >= 50:
        bet_indices = np.arange(len(clv_series))
        try:
            linreg = stats.linregress(bet_indices, clv_series.values)
            slope: float = float(linreg.slope)  # type: ignore[attr-defined]
            r_value: float = float(linreg.rvalue)  # type: ignore[attr-defined]
            if slope < 0:
                score -= abs(slope) * 5000
                score += r_value**2 * 10
        except (ValueError, TypeError, AttributeError):
            pass

    if stake_history:
        reductions = sum(
            1 for i in range(1, len(stake_history)) if stake_history[i] < stake_history[i - 1]
        )
        if len(stake_history) > 1:
            reduction_rate = reductions / (len(stake_history) - 1)
            score -= reduction_rate * 30

    score = max(0.0, min(100.0, score))
    return float(score)


def get_edge_health_summary(  # pylint: disable=too-many-locals
    clv_series: pd.Series,
    stake_history: list[float] | None = None,
) -> dict:
    """Get comprehensive edge health summary."""
    if len(clv_series) < 10:
        return {
            "health_score": 50.0,
            "status": "insufficient_data",
            "message": f"Need at least 10 bets, have {len(clv_series)}",
            "half_life_bets": None,
            "clv_slope": None,
            "retention_rate": None,
            "recommendations": ["Collect more bet data for accurate analysis"],
        }

    durability_score = compute_edge_durability_score(clv_series, stake_history)

    recent_clv = clv_series.tail(20).mean()
    older_clv = clv_series.head(20).mean() if len(clv_series) > 20 else recent_clv
    retention_rate = recent_clv / older_clv if older_clv > 0 else None

    bet_indices = np.arange(len(clv_series))
    clv_slope = 0.0
    slope = 0.0
    r_value = 0.0
    p_value = 1.0
    std_err = 0.0
    try:
        linreg = stats.linregress(bet_indices, clv_series.values)
        slope = float(linreg.slope)  # type: ignore[attr-defined]
        r_value = float(linreg.rvalue)  # type: ignore[attr-defined]
        p_value = float(linreg.pvalue)  # type: ignore[attr-defined]
        std_err = float(linreg.stderr)  # type: ignore[attr-defined]
        clv_slope = slope
    except (ValueError, AttributeError):
        pass

    half_life = float("inf")
    if slope < 0 < recent_clv:
        half_life = -recent_clv / (2 * slope)

    status = "healthy"
    if durability_score < 40:
        status = "critical"
    elif durability_score < 60:
        status = "warning"
    elif durability_score < 80:
        status = "caution"

    recommendations = []
    if durability_score < 60:
        recommendations.append("Consider retraining model with recent data")
    if clv_slope < 0 and abs(clv_slope) > std_err * 2:
        recommendations.append("Edge is degrading - investigate feature drift")
    if retention_rate is not None and retention_rate < 0.7:
        recommendations.append("CLV retention low - review market efficiency")
    if stake_history:
        reductions = sum(
            1 for i in range(1, len(stake_history)) if stake_history[i] < stake_history[i - 1]
        )
        if reductions > len(stake_history) * 0.3:
            recommendations.append("Frequent stake reductions detected")

    return {
        "health_score": durability_score,
        "status": status,
        "message": f"Edge health: {status} (score: {durability_score:.1f})",
        "half_life_bets": half_life if half_life != float("inf") else None,
        "clv_slope": clv_slope,
        "clv_r_squared": r_value**2,
        "clv_p_value": p_value,
        "retention_rate": retention_rate,
        "recent_clv_mean": recent_clv,
        "older_clv_mean": older_clv,
        "n_bets_analyzed": len(clv_series),
        "recommendations": recommendations,
    }


__all__ = [
    "WalkForwardConfig",
    "CalibrationConfig",
    "CLVConfig",
    "WalkForwardValidator",
    "ProbabilityCalibrator",
    "CLVTracker",
    "ModelValidator",
    "compute_edge_durability_score",
    "get_edge_health_summary",
]
