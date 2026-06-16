"""
Walk-Forward and Regime-Aware Backtesting (V3)

Adapted from sports_analytics.betting.backtest_v3
Changes: Replaced sports_analytics imports with sportsquant imports

This module provides advanced backtesting capabilities:
1. Expanding window walk-forward validation
2. Regime-aware backtesting
3. Sensitivity analysis
4. Market regime detection and tracking
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import numpy as np
from pandas import DataFrame, Series
from sklearn.metrics import log_loss
from sklearn.model_selection import TimeSeriesSplit

from sportsquant.util.metrics import (
    BACKTEST_ROI,
    BACKTEST_PNL,
    BACKTEST_WIN_RATE,
    BACKTEST_N_BETS,
    BACKTEST_SHARPE_RATIO,
    BACKTEST_MAX_DRAWDOWN,
    BACKTEST_AVG_ODDS,
    BACKTEST_KELLY_FRACTION,
    BACKTEST_TURNOVER,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RegimePeriod:
    """Represents a time period with a specific market regime."""

    start_date: str
    end_date: str
    regime_type: str
    description: str = ""


@dataclass(frozen=True)
class WalkForwardConfig:
    """Configuration for walk-forward backtesting."""

    train_window: int = 82
    test_window: int = 20
    min_train_samples: int = 50
    step_size: int = 1
    verbose: bool = False


@dataclass(frozen=True)
# pylint: disable=too-many-instance-attributes
class FoldResult:
    """Result from a single walk-forward fold."""

    fold_index: int
    train_start: int
    train_end: int
    test_start: int
    test_end: int
    n_train_samples: int
    n_test_samples: int
    model_params: dict[str, Any]
    metrics: dict[str, float]
    predictions: Optional[DataFrame] = None
    feature_importance: Optional[dict[str, float]] = None


@dataclass(frozen=True)
# pylint: disable=too-many-instance-attributes
class WalkForwardResults:
    """Results from walk-forward backtesting."""

    config: WalkForwardConfig
    fold_results: list[FoldResult]
    total_folds: int
    overall_metrics: dict[str, float | str]
    by_regime: dict[str, list[FoldResult]] = field(default_factory=dict)
    timestamp: str = ""


@dataclass(frozen=True)
class RegimeAwareResults:
    """Results from regime-aware backtesting."""

    regime_periods: list[RegimePeriod]
    fold_results: list[FoldResult]
    regime_metrics: dict[str, dict[str, float | str]]
    cross_regime_comparison: dict[str, dict[str, float | str]]
    total_folds: int


# pylint: disable=too-few-public-methods
@dataclass(frozen=True)
class RegimeDetector(ABC):
    """Abstract base class for regime detection."""

    @abstractmethod
    def detect_regimes(self, features: DataFrame, y: Series) -> list[RegimePeriod]:
        """Detect regime periods in the data."""

    @abstractmethod
    def classify_regime(self, x_row: Series) -> str:
        """Classify a single sample into a regime."""

    @abstractmethod
    def get_current_regime(self, features: DataFrame) -> str:
        """Get the current regime for the dataset."""


@dataclass(frozen=True)
# pylint: disable=too-many-instance-attributes
class RegimeBacktestResults:
    """Results from regime-aware backtesting."""

    regime_detector_name: str
    regime_periods: list[RegimePeriod]
    fold_results: list[FoldResult]
    regime_performance: dict[str, dict[str, float | str]]
    regime_transitions: list[tuple[str, str, str]]
    stability_score: float


@dataclass(frozen=True)
class SensitivityConfig:
    """Configuration for sensitivity analysis."""

    cv_folds: int = 5
    cv_strategy: str = "time_series"
    metrics: list[str] = field(default_factory=lambda: ["log_loss", "roi"])
    random_state: int = 42
    n_jobs: int = 1
    verbose: bool = False


@dataclass
# pylint: disable=too-many-instance-attributes
class SensitivityResult:
    """Result from a single sensitivity test."""

    param_name: str
    param_values: list[Any]
    metric_name: str
    metric_values: list[float]
    metric_std: list[float]
    best_value: Any
    best_score: float
    sensitivity_score: float


@dataclass(frozen=True)
class SensitivityReport:
    """Comprehensive sensitivity analysis report."""

    analysis_type: str
    config: SensitivityConfig
    results: list[SensitivityResult]
    summary: dict[str, Any]
    recommendations: list[str]


class WalkForwardBacktest:
    """Expanding window walk-forward validation engine."""

    def __init__(
        self,
        features: DataFrame,
        y: Series,
        train_window: int = 82,
        test_window: int = 20,
    ) -> None:
        """Initialize walk-forward backtest."""
        self.features = features.reset_index(drop=True) if features is not None else None
        self.y = y.reset_index(drop=True) if y is not None else None
        self.train_window = train_window
        self.test_window = test_window
        self.config = WalkForwardConfig(
            train_window=train_window,
            test_window=test_window,
        )

    def run(  # pylint: disable=too-many-locals
        self,
        model_factory: Callable[[], Any],
        _odds_df: Optional[DataFrame] = None,
        feature_names: Optional[list[str]] = None,
    ) -> WalkForwardResults:
        """Run walk-forward backtest across all periods."""
        if self.features is None or self.y is None:
            raise ValueError("features and y must be provided")

        n_samples = len(self.features)
        fold_results: list[FoldResult] = []
        fold_index = 0
        current_position = self.train_window

        while current_position + self.test_window <= n_samples:
            train_end = current_position
            test_start = train_end
            test_end = min(train_end + self.test_window, n_samples)

            if train_end < self.config.min_train_samples:
                current_position += self.config.step_size
                continue

            x_train = self.features.iloc[:train_end]
            y_train = self.y.iloc[:train_end]
            x_test = self.features.iloc[test_start:test_end]
            y_test = self.y.iloc[test_start:test_end]

            try:
                model = model_factory()
                model.fit(x_train, y_train)

                y_pred_proba = model.predict_proba(x_test)

                if hasattr(y_pred_proba, "shape") and len(y_pred_proba.shape) > 1:
                    y_pred_proba = y_pred_proba[:, 1]
                else:
                    y_pred_proba = np.asarray(y_pred_proba).flatten()

                metrics = self._compute_metrics(y_test, y_pred_proba)

                feature_importance = None
                if hasattr(model, "feature_importances_"):
                    importance = model.feature_importances_
                    if feature_names is None:
                        feature_names = list(x_train.columns)
                    feature_importance = dict(zip(feature_names, importance))

                fold_result = FoldResult(
                    fold_index=fold_index,
                    train_start=0,
                    train_end=train_end,
                    test_start=test_start,
                    test_end=test_end,
                    n_train_samples=len(x_train),
                    n_test_samples=len(x_test),
                    model_params=model.get_params() if hasattr(model, "get_params") else {},
                    metrics=metrics,
                    predictions=DataFrame(
                        {
                            "y_true": y_test.values,
                            "y_pred_proba": y_pred_proba,
                        }
                    ),
                    feature_importance=feature_importance,
                )
                fold_results.append(fold_result)
                fold_index += 1

                if self.config.verbose:
                    logger.info(
                        "Fold %d: train=[%d,%d], test=[%d,%d], n_bets=%d, ROI=%.2f%%",
                        fold_index,
                        0,
                        train_end,
                        test_start,
                        test_end,
                        metrics.get("n_bets", 0),
                        metrics.get("roi_pct", 0.0),
                    )

            except (ValueError, TypeError, KeyError) as e:
                logger.error("Fold %d failed: %s", fold_index, e)
                fold_result = FoldResult(
                    fold_index=fold_index,
                    train_start=0,
                    train_end=train_end,
                    test_start=test_start,
                    test_end=test_end,
                    n_train_samples=len(x_train),
                    n_test_samples=len(x_test),
                    model_params={},
                    metrics={"error": np.nan},
                )
                fold_results.append(fold_result)
                fold_index += 1

            current_position += self.config.step_size

        overall_metrics = self._aggregate_metrics(fold_results)

        return WalkForwardResults(
            config=self.config,
            fold_results=fold_results,
            total_folds=len(fold_results),
            overall_metrics=overall_metrics,
        )

    def run_with_regimes(
        self,
        model_factory: Callable[[], Any],
        regimes: list[RegimePeriod],
        odds_df: Optional[DataFrame] = None,
        feature_names: Optional[list[str]] = None,
    ) -> RegimeAwareResults:
        """Run backtest with regime-specific analysis."""
        walkforward_results = self.run(model_factory, odds_df, feature_names)

        regime_folds: dict[str, list[FoldResult]] = {}
        for fold in walkforward_results.fold_results:
            fold_regime = self._get_regime_for_fold(fold, regimes)
            if fold_regime not in regime_folds:
                regime_folds[fold_regime] = []
            regime_folds[fold_regime].append(fold)

        regime_metrics: dict[str, dict[str, float | str]] = {}
        for regime, folds in regime_folds.items():
            regime_metrics[regime] = self._aggregate_metrics(folds)

        cross_regime_comparison = self._compare_regimes(regime_metrics)

        return RegimeAwareResults(
            regime_periods=regimes,
            fold_results=walkforward_results.fold_results,
            regime_metrics=regime_metrics,
            cross_regime_comparison=cross_regime_comparison,
            total_folds=walkforward_results.total_folds,
        )

    def _compute_metrics(
        self,
        y_true: Series,
        y_pred_proba: np.ndarray,
    ) -> dict[str, float]:
        """Compute evaluation metrics for predictions."""
        y_true_arr = np.asarray(y_true)
        y_pred_clipped = np.clip(y_pred_proba, 1e-15, 1 - 1e-15)

        logloss = log_loss(y_true_arr, y_pred_clipped)

        y_pred_binary = (y_pred_proba >= 0.5).astype(int)
        accuracy = (y_pred_binary == y_true_arr).mean()

        n_samples = len(y_true_arr)
        return {
            "log_loss": logloss,
            "accuracy": accuracy,
            "n_samples": n_samples,
            "mean_prob": y_pred_proba.mean(),
            "std_prob": y_pred_proba.std(),
        }

    def _aggregate_metrics(self, fold_results: list[FoldResult]) -> dict[str, float | str]:
        """Aggregate metrics across all folds."""
        if not fold_results:
            return {}

        valid_folds = [f for f in fold_results if "error" not in f.metrics]

        if not valid_folds:
            return {"error": "All folds failed"}  # type: ignore[return-value]

        metrics_to_aggregate = ["log_loss", "accuracy"]

        aggregated: dict[str, float | str] = {}
        for metric in metrics_to_aggregate:
            values = [f.metrics.get(metric, np.nan) for f in valid_folds]
            float_values: list[float] = [
                v for v in values if isinstance(v, (int, float)) and not np.isnan(v)
            ]
            if float_values:
                aggregated[f"{metric}_mean"] = float(np.mean(float_values))
                aggregated[f"{metric}_std"] = float(np.std(float_values))
                aggregated[f"{metric}_min"] = float(np.min(float_values))
                aggregated[f"{metric}_max"] = float(np.max(float_values))

        aggregated["total_folds"] = len(valid_folds)
        aggregated["total_samples"] = sum(f.n_test_samples for f in valid_folds)

        return aggregated

    def _get_regime_for_fold(
        self,
        fold: FoldResult,
        regimes: list[RegimePeriod],
    ) -> str:
        """Determine regime for a fold based on test period."""
        test_middle = (fold.test_start + fold.test_end) // 2

        for regime in regimes:
            if regime.start_date <= str(test_middle) <= regime.end_date:
                return regime.regime_type

        return "unknown"

    def _compare_regimes(
        self,
        regime_metrics: dict[str, dict[str, float | str]],
    ) -> dict[str, dict[str, float | str]]:
        """Compare performance across different regimes."""
        comparison: dict[str, dict[str, float | str]] = {}

        regime_list = list(regime_metrics.keys())
        for i, regime_a in enumerate(regime_list):
            for regime_b in regime_list[i + 1 :]:
                key = f"{regime_a}_vs_{regime_b}"
                metric_a_val = regime_metrics[regime_a].get("log_loss_mean", np.nan)
                metric_b_val = regime_metrics[regime_b].get("log_loss_mean", np.nan)
                metric_a = (
                    float(metric_a_val)
                    if isinstance(metric_a_val, (int, float)) and not np.isnan(metric_a_val)
                    else 0.0
                )
                metric_b = (
                    float(metric_b_val)
                    if isinstance(metric_b_val, (int, float)) and not np.isnan(metric_b_val)
                    else 0.0
                )

                comparison[key] = {
                    "diff": metric_a - metric_b,
                    "regime_a_advantage": metric_a < metric_b,
                }

        return comparison


class RegimeAwareBacktest:
    """Backtest that tracks performance by market regime."""

    def __init__(
        self,
        features: DataFrame,
        y: Series,
        odds_df: Optional[DataFrame] = None,
    ) -> None:
        """Initialize regime-aware backtest."""
        self.features = features
        self.y = y
        self.odds_df = odds_df

    def run(  # pylint: disable=too-many-locals
        self,
        regime_detector: RegimeDetector,
        model_factory: Callable[[], Any],
    ) -> RegimeBacktestResults:
        """Run backtest with regime tracking."""
        x_with_idx = self.features.reset_index(drop=True)
        y_with_idx = self.y.reset_index(drop=True)

        regimes = regime_detector.detect_regimes(x_with_idx, y_with_idx)

        fold_results: list[FoldResult] = []
        fold_index = 0

        regime_transitions: list[tuple[str, str, str]] = []
        current_regime = None

        for i in range(len(x_with_idx)):
            row = x_with_idx.iloc[i]
            sample_regime = regime_detector.classify_regime(row)

            if current_regime is not None and sample_regime != current_regime:
                regime_transitions.append((str(i), current_regime, sample_regime))

            current_regime = sample_regime

        test_indices = list(range(len(x_with_idx)))
        test_size = min(20, len(test_indices) // 5)

        for start in range(0, len(test_indices) - test_size + 1, test_size):
            end = start + test_size
            test_idx = test_indices[start:end]

            x_train = x_with_idx.iloc[: test_idx[0]]
            y_train = y_with_idx.iloc[: test_idx[0]]
            x_test = x_with_idx.iloc[test_idx]
            y_test = y_with_idx.iloc[test_idx]

            try:
                model = model_factory()
                model.fit(x_train, y_train)

                y_pred_proba = model.predict_proba(x_test)

                if hasattr(y_pred_proba, "shape") and len(y_pred_proba.shape) > 1:
                    y_pred_proba = y_pred_proba[:, 1]

                metrics = self._compute_metrics(y_test, y_pred_proba)

                fold_result = FoldResult(
                    fold_index=fold_index,
                    train_start=0,
                    train_end=test_idx[0],
                    test_start=test_idx[0],
                    test_end=test_idx[-1] + 1,
                    n_train_samples=len(x_train),
                    n_test_samples=len(x_test),
                    model_params=model.get_params() if hasattr(model, "get_params") else {},
                    metrics=metrics,
                )
                fold_results.append(fold_result)
                fold_index += 1

            except (ValueError, TypeError, KeyError) as e:
                logger.error("Fold %d failed: %s", fold_index, e)
                fold_results.append(
                    FoldResult(
                        fold_index=fold_index,
                        train_start=0,
                        train_end=test_idx[0] if test_idx else 0,
                        test_start=test_idx[0] if test_idx else 0,
                        test_end=test_idx[-1] + 1 if test_idx else 0,
                        n_train_samples=len(x_train) if "x_train" in dir() else 0,
                        n_test_samples=len(x_test) if "x_test" in dir() else 0,
                        model_params={},
                        metrics={"error": np.nan},
                    )
                )
                fold_index += 1

        regime_performance: dict[str, dict[str, float | str]] = {}
        for regime in regime_detector.detect_regimes(x_with_idx, y_with_idx):
            regime_folds = [f for f in fold_results if "error" not in f.metrics]
            regime_performance[regime.regime_type] = self._aggregate_fold_metrics(regime_folds)

        stability_score = self._compute_stability(regime_transitions)

        return RegimeBacktestResults(
            regime_detector_name=type(regime_detector).__name__,
            regime_periods=regimes,
            fold_results=fold_results,
            regime_performance=regime_performance,
            regime_transitions=regime_transitions,
            stability_score=stability_score,
        )

    def _compute_metrics(
        self,
        y_true: Series,
        y_pred_proba: np.ndarray,
    ) -> dict[str, float]:
        """Compute metrics for predictions."""
        y_true_arr = np.asarray(y_true)
        y_pred_clipped = np.clip(np.asarray(y_pred_proba), 1e-15, 1 - 1e-15)

        logloss = log_loss(y_true_arr, y_pred_clipped)
        accuracy = (np.round(y_pred_proba) == y_true_arr).mean()

        return {
            "log_loss": logloss,
            "accuracy": accuracy,
            "n_samples": len(y_true),
        }

    def _aggregate_fold_metrics(
        self,
        fold_results: list[FoldResult],
    ) -> dict[str, float | str]:
        """Aggregate metrics for a set of folds."""
        if not fold_results:
            return {"error": "No valid folds"}  # type: ignore[return-value]

        log_losses = [f.metrics.get("log_loss", np.nan) for f in fold_results]
        float_losses = [
            ll for ll in log_losses if isinstance(ll, (int, float)) and not np.isnan(ll)
        ]

        return {
            "n_folds": len(fold_results),
            "log_loss_mean": float(np.mean(float_losses)) if float_losses else 0.0,
            "log_loss_std": float(np.std(float_losses)) if float_losses else 0.0,
        }

    def _compute_stability(
        self,
        transitions: list[tuple[str, str, str]],
    ) -> float:
        """Compute regime stability score."""
        if not transitions:
            return 1.0

        total_transitions = len(transitions)
        if total_transitions == 0:
            return 1.0

        return 1.0 / (1.0 + np.log1p(total_transitions))


class SensitivityAnalyzer:
    """Test model robustness across parameter and feature variations."""

    def __init__(
        self,
        model_class: type,
        features: DataFrame,
        y: Series,
    ) -> None:
        """Initialize sensitivity analyzer."""
        self.model_class = model_class
        self.features = features
        self.y = y
        self.config = SensitivityConfig()

    def run_parameter_sensitivity(  # pylint: disable=too-many-locals
        self,
        param_grid: dict[str, list[Any]],
        metric: str = "log_loss",
        cv_folds: int = 5,
    ) -> SensitivityReport:
        """Test performance across parameter grid."""
        results: list[SensitivityResult] = []
        param_names = list(param_grid.keys())

        for param_name in param_names:
            param_values = param_grid[param_name]
            metric_values: list[float] = []
            metric_std: list[float] = []

            for value in param_values:
                params = {param_name: value}
                fold_scores = self._cv_with_params(params, cv_folds)

                mean_score = float(np.mean(fold_scores))
                std_score = float(np.std(fold_scores))

                metric_values.append(mean_score)
                metric_std.append(std_score)

            best_idx = (
                np.argmin(metric_values) if metric == "log_loss" else np.argmax(metric_values)
            )
            sensitivity_score = self._compute_sensitivity_score(metric_values)

            result = SensitivityResult(
                param_name=param_name,
                param_values=param_values,
                metric_name=metric,
                metric_values=metric_values,
                metric_std=metric_std,
                best_value=param_values[best_idx],
                best_score=metric_values[best_idx],
                sensitivity_score=sensitivity_score,
            )
            results.append(result)

        summary = self._generate_summary(results)
        recommendations = self._generate_recommendations(results)

        return SensitivityReport(
            analysis_type="parameter_sensitivity",
            config=self.config,
            results=results,
            summary=summary,
            recommendations=recommendations,
        )

    def run_feature_sensitivity(  # pylint: disable=too-many-locals
        self,
        feature_subsets: list[list[str]],
        metric: str = "log_loss",
        cv_folds: int = 5,
    ) -> SensitivityReport:
        """Test performance with different feature subsets."""
        results: list[SensitivityResult] = []
        all_features = list(self.features.columns)

        for i, subset in enumerate(feature_subsets):
            _x_subset = self.features[subset]
            fold_scores = self._cv_with_features(subset, cv_folds)

            mean_score = float(np.mean(fold_scores))
            std_score = float(np.std(fold_scores))

            result = SensitivityResult(
                param_name=f"feature_subset_{i}",
                param_values=[len(subset)],
                metric_name=metric,
                metric_values=[mean_score],
                metric_std=[std_score],
                best_value=subset,
                best_score=mean_score,
                sensitivity_score=0.0,
            )
            results.append(result)

        full_set_scores = self._cv_with_features(all_features, cv_folds)
        full_score = float(np.mean(full_set_scores))

        for result in results:
            result.sensitivity_score = abs(result.best_score - full_score) / full_score

        summary = self._generate_summary(results)
        recommendations = self._generate_feature_recommendations(results, feature_subsets)

        return SensitivityReport(
            analysis_type="feature_sensitivity",
            config=self.config,
            results=results,
            summary=summary,
            recommendations=recommendations,
        )

    def _cv_with_params(
        self,
        params: dict[str, Any],
        cv_folds: int,
    ) -> list[float]:
        """Run cross-validation with given parameters."""
        scores = []
        tscv = TimeSeriesSplit(n_splits=cv_folds)

        for train_idx, test_idx in tscv.split(self.features):
            x_train = self.features.iloc[train_idx]
            y_train = self.y.iloc[train_idx]
            x_test = self.features.iloc[test_idx]
            y_test = self.y.iloc[test_idx]

            try:
                model = self.model_class(**params)
                model.fit(x_train, y_train)

                y_pred_proba = model.predict_proba(x_test)

                if hasattr(y_pred_proba, "shape") and len(y_pred_proba.shape) > 1:
                    y_pred_proba = y_pred_proba[:, 1]

                score = log_loss(y_test, y_pred_proba)
                scores.append(score)

            except (ValueError, TypeError) as e:
                logger.warning("CV fold failed with params %s: %s", params, e)
                scores.append(np.nan)

        return [s for s in scores if not np.isnan(s)]

    def _cv_with_features(  # pylint: disable=too-many-locals
        self,
        features: list[str],
        cv_folds: int,
    ) -> list[float]:
        """Run cross-validation with given features."""
        x_subset = self.features[features]
        scores = []
        tscv = TimeSeriesSplit(n_splits=cv_folds)

        for train_idx, test_idx in tscv.split(x_subset):
            x_train = x_subset.iloc[train_idx]
            y_train = self.y.iloc[train_idx]
            x_test = x_subset.iloc[test_idx]
            y_test = self.y.iloc[test_idx]

            try:
                model = self.model_class()
                model.fit(x_train, y_train)

                y_pred_proba = model.predict_proba(x_test)

                if hasattr(y_pred_proba, "shape") and len(y_pred_proba.shape) > 1:
                    y_pred_proba = y_pred_proba[:, 1]

                score = log_loss(y_test, y_pred_proba)
                scores.append(score)

            except (ValueError, TypeError) as e:
                logger.warning("CV fold failed with features %s: %s", features, e)
                scores.append(np.nan)

        return [s for s in scores if not np.isnan(s)]

    def _compute_sensitivity_score(self, values: list[float]) -> float:
        """Compute sensitivity score as coefficient of variation."""
        mean_val = float(np.mean(values))
        if mean_val == 0:
            return 0.0
        std_val = float(np.std(values))
        return std_val / abs(mean_val)

    def _generate_summary(self, results: list[SensitivityResult]) -> dict[str, Any]:
        """Generate summary from sensitivity results."""
        most_sensitive = max(results, key=lambda r: r.sensitivity_score, default=None)
        least_sensitive = min(results, key=lambda r: r.sensitivity_score, default=None)

        return {
            "n_parameters_tested": len(results),
            "most_sensitive_param": most_sensitive.param_name if most_sensitive else None,
            "most_sensitive_score": most_sensitive.sensitivity_score if most_sensitive else None,
            "least_sensitive_param": least_sensitive.param_name if least_sensitive else None,
            "least_sensitive_score": least_sensitive.sensitivity_score if least_sensitive else None,
        }

    def _generate_recommendations(self, results: list[SensitivityResult]) -> list[str]:
        """Generate recommendations based on parameter sensitivity."""
        recommendations = []

        for result in results:
            if result.sensitivity_score > 0.1:
                recommendations.append(
                    f"Parameter '{result.param_name}' has high sensitivity "
                    f"({result.sensitivity_score:.3f}). Consider careful tuning."
                )
            elif result.sensitivity_score < 0.01:
                recommendations.append(
                    f"Parameter '{result.param_name}' is robust across values. "
                    f"Default value is likely acceptable."
                )

        return recommendations

    def _generate_feature_recommendations(
        self,
        results: list[SensitivityResult],
        _feature_subsets: list[list[str]],
    ) -> list[str]:
        """Generate recommendations based on feature sensitivity."""
        recommendations = []

        best_result = min(results, key=lambda r: r.best_score, default=None)
        if best_result:
            recommendations.append(
                f"Best feature subset has {len(best_result.best_value)} features "
                f"with log_loss={best_result.best_score:.4f}"
            )

        return recommendations


def record_backtest_metrics(
    results: dict[str, Any],
    model: str = "default",
    market: str = "default",
) -> None:
    """Record backtest results as Prometheus metrics.

    Args:
        results: Dictionary containing backtest metrics (roi, pnl, win_rate, etc.)
        model: Model name for attribution
        market: Market name for attribution
    """
    roi = results.get("roi", results.get("roi_pct", 0.0))
    pnl = results.get("pnl", 0.0)
    win_rate = results.get("win_rate", 0.0)
    n_bets = results.get("n_bets", 0)
    sharpe = results.get("sharpe_ratio", results.get("sharpe", None))
    max_drawdown = results.get("max_drawdown", results.get("max_dd_pct", None))
    avg_odds = results.get("avg_odds", None)
    kelly_fraction = results.get("kelly_fraction", results.get("avg_kelly", None))
    turnover = results.get("turnover", 0.0)

    labels = {"model": model, "market": market}
    BACKTEST_ROI.labels(**labels).set(roi)
    BACKTEST_PNL.labels(**labels).set(pnl)
    BACKTEST_WIN_RATE.labels(**labels).set(win_rate)
    BACKTEST_N_BETS.labels(**labels).set(n_bets)

    if sharpe is not None:
        BACKTEST_SHARPE_RATIO.labels(model=model).set(sharpe)
    if max_drawdown is not None:
        BACKTEST_MAX_DRAWDOWN.labels(**labels).set(max_drawdown)
    if avg_odds is not None:
        BACKTEST_AVG_ODDS.labels(**labels).set(avg_odds)
    if kelly_fraction is not None:
        BACKTEST_KELLY_FRACTION.labels(model=model).set(kelly_fraction)
    if turnover > 0:
        BACKTEST_TURNOVER.labels(**labels).set(turnover)


__all__ = [
    "RegimePeriod",
    "WalkForwardConfig",
    "FoldResult",
    "WalkForwardResults",
    "RegimeAwareResults",
    "RegimeDetector",
    "RegimeBacktestResults",
    "SensitivityConfig",
    "SensitivityResult",
    "SensitivityReport",
    "WalkForwardBacktest",
    "RegimeAwareBacktest",
    "SensitivityAnalyzer",
]
