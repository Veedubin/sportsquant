"""
Regime Analysis Module

Detects and analyzes market regimes for sports betting predictions.

MLflow Integration:
- Logs regime classification results to MLflow
- Logs regime performance metrics
- Logs edge analysis by regime type
- Logs regime transition statistics

Data Sources:
- Reads historical game data from TimescaleDB
- Reads predictions from Kafka topic 'sports-analytics-model-predictions'
- Reads regime indicators from Parquet data lake

Output:
- Writes analysis results to Kafka topic 'betting-metrics'
- Writes regime analysis to Parquet for historical analysis
- Supports webhook callbacks for real-time alerts
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any, Optional

import numpy as np
import pandas as pd
from scipy import stats

from quantitative_sports.core.backtest.analysis.mlflow_logger import MLflowLogger, get_mlflow_logger

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ThresholdConfig:
    """Threshold configuration for regime classification."""

    pace_high: float | None = None
    pace_low: float | None = None
    variance_high: float | None = None
    variance_low: float | None = None


class RegimeType(Enum):
    """Types of market regimes."""

    HIGH_PACE = "high_pace"
    LOW_PACE = "low_pace"
    HIGH_VARIANCE = "high_variance"
    LOW_VARIANCE = "low_variance"
    NEUTRAL = "neutral"


@dataclass(frozen=True)
class RegimeChange:
    """Regime change event."""

    game_id: str
    timestamp: datetime
    previous_regime: RegimeType | None
    new_regime: RegimeType
    confidence: float
    change_magnitude: float


@dataclass(frozen=True)
class RegimeStats:
    """Combined stats for a regime period."""

    avg_pace: float
    pace_std: float
    avg_total: float
    total_std: float


@dataclass(frozen=True)
class RegimePeriod:
    """Represents a period of consistent game regime."""

    regime_type: RegimeType
    start_date: date
    end_date: date | None
    game_count: int
    stats: RegimeStats
    characteristics: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class RegimeModel:
    """Regime-specific model parameters."""

    regime_type: RegimeType
    model_params: dict[str, Any]
    adjustment_factor: float
    confidence_interval: tuple[float, float]
    sample_size: int
    performance_metrics: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class RegimeAdjustedPrediction:
    """Prediction adjusted for current regime."""

    base_prediction: float
    adjusted_prediction: float
    regime_adjustment: float
    regime_type: RegimeType
    confidence: float
    adjustment_reason: str


@dataclass(frozen=True)
class RegimeComparison:
    """Comparison of performance across regimes."""

    regime_performance: dict[RegimeType, dict[str, float]]
    best_regime: RegimeType
    worst_regime: RegimeType
    overall_edge: float
    regime_std: float
    sample_sizes: dict[RegimeType, int]


@dataclass(frozen=True)
class RegimeEdgeResult:
    """Edge analysis result for a regime."""

    regime_type: RegimeType
    edge: float
    edge_ci: tuple[float, float]
    sample_size: int
    win_rate: float
    roi: float
    clv_avg: float
    profitability_score: float


class RegimeDetector:
    """Detects market regimes from historical game data.

    MLflow Integration:
        - Logs regime detection results
        - Logs regime change events
        - Logs regime stability metrics
    """

    # pylint: disable=R0902

    def __init__(
        self,
        historical_games: pd.DataFrame,
        mlflow_logger: Optional[MLflowLogger] = None,
    ):
        self.historical_games = historical_games
        self._thresholds = ThresholdConfig()
        self.mlflow_logger = mlflow_logger or get_mlflow_logger()
        self._regime_changes: list[RegimeChange] = []
        self._regime_periods: list[RegimePeriod] = []

    @property
    def regime_periods(self) -> list[RegimePeriod]:
        """Get identified regime periods (computed on demand)."""
        if not self._regime_changes:
            self.detect_regime_changes()
        if not self._regime_periods:
            self._compute_regime_periods()
        return self._regime_periods

    def _compute_regime_periods(self) -> None:
        """Compute regime periods from detected changes."""
        current_period_start: date | None = None
        current_regime: RegimeType | None = None

        for _idx, row in self.historical_games.iterrows():
            game_regime = self.classify_regime(row)
            game_date = pd.to_datetime(row.get("game_date", datetime.now())).date()

            if current_regime is None:
                current_regime = game_regime
                current_period_start = game_date
            elif game_regime != current_regime:
                period_games = self.historical_games[
                    (
                        pd.to_datetime(self.historical_games["game_date"]).dt.date
                        >= current_period_start
                    )
                    & (pd.to_datetime(self.historical_games["game_date"]).dt.date < game_date)
                ]

                period = self._create_regime_period(
                    current_regime, current_period_start, game_date, period_games
                )
                self._regime_periods.append(period)

                current_regime = game_regime
                current_period_start = game_date

        if current_regime is not None and current_period_start is not None:
            period_games = self.historical_games[
                pd.to_datetime(self.historical_games["game_date"]).dt.date >= current_period_start
            ]
            period = self._create_regime_period(
                current_regime, current_period_start, None, period_games
            )
            self._regime_periods.append(period)

        logger.info("Identified %s regime periods", len(self._regime_periods))

    def detect_regime_changes(self) -> list[RegimeChange]:
        """Detect regime changes in historical data.

        Returns:
            List of regime change events
        """
        if self.historical_games.empty:
            logger.warning("No historical games provided for regime detection")
            return []

        self._calculate_thresholds()

        if "game_id" not in self.historical_games.columns:
            raise ValueError("Historical games must contain 'game_id' column")

        if "game_date" not in self.historical_games.columns:
            raise ValueError("Historical games must contain 'game_date' column")

        if (
            "pace" not in self.historical_games.columns
            and "total_points" not in self.historical_games.columns
        ):
            raise ValueError("Historical games must contain 'pace' or 'total_points' column")

        self._regime_changes = []
        current_regime: RegimeType | None = None
        previous_regime: RegimeType | None = None

        for idx, row in self.historical_games.iterrows():
            game_regime = self.classify_regime(row)

            if current_regime is None:
                current_regime = game_regime
            elif game_regime != current_regime:
                confidence = self._calculate_regime_confidence(row)
                change_magnitude = self._calculate_change_magnitude(row, previous_regime)

                change = RegimeChange(
                    game_id=str(row.get("game_id", idx)),
                    timestamp=pd.to_datetime(row.get("game_date", datetime.now())),
                    previous_regime=previous_regime,
                    new_regime=game_regime,
                    confidence=confidence,
                    change_magnitude=change_magnitude,
                )
                self._regime_changes.append(change)
                previous_regime = current_regime
                current_regime = game_regime

        logger.info("Detected %s regime changes", len(self._regime_changes))

        if self.mlflow_logger and self._regime_changes:
            self.mlflow_logger.log_metrics(
                {
                    "regime_changes_detected": len(self._regime_changes),
                    "regime_stability": self.measure_regime_stability(),
                }
            )

        return self._regime_changes

    def classify_regime(self, game: pd.Series) -> RegimeType:
        """Classify a game's regime type.

        Args:
            game: Game data Series

        Returns:
            RegimeType classification
        """
        if self._thresholds.pace_high is None or self._thresholds.pace_low is None:
            self._calculate_thresholds()

        pace = game.get("pace", None)
        total_points = game.get("total_points", None)
        variance = game.get("variance", None)

        if pace is None and total_points is not None:
            pace = total_points / 2

        if pace is None:
            return RegimeType.NEUTRAL

        pace_mean = self.historical_games["pace"].mean()
        pace_std = self.historical_games["pace"].std()
        pace_z = (pace - pace_mean) / pace_std if pace_std > 0 else 0

        if variance is not None:
            variance_series = self.historical_games.get("variance", pd.Series([variance]))
            variance_mean = variance_series.mean()
            variance_std = variance_series.std()
            variance_z = (variance - variance_mean) / variance_std if variance_std > 0 else 0

            if pace_z > 1.0 and variance_z > 0.5:
                return RegimeType.HIGH_PACE
            if pace_z < -1.0 and variance_z < -0.5:
                return RegimeType.LOW_PACE
            if variance_z > 1.0:
                return RegimeType.HIGH_VARIANCE
            if variance_z < -1.0:
                return RegimeType.LOW_VARIANCE

        if pace_z > 1.0:
            return RegimeType.HIGH_PACE
        if pace_z < -1.0:
            return RegimeType.LOW_PACE

        return RegimeType.NEUTRAL

    def measure_regime_stability(self) -> float:
        """Measure stability of detected regimes.

        Returns:
            Stability score (0-1)
        """
        periods = self.regime_periods
        if len(periods) < 2:
            return 1.0

        if "game_date" not in self.historical_games.columns:
            return 1.0

        total_duration = 0
        weighted_stability = 0

        for period in periods:
            if period.end_date is None:
                end_date = pd.to_datetime(self.historical_games["game_date"]).max().date()
            else:
                end_date = period.end_date

            duration = (end_date - period.start_date).days
            total_duration += duration

            regime_consistency = 1.0 - (period.stats.pace_std / (period.stats.avg_pace + 1e-6))
            weighted_stability += duration * max(0, regime_consistency)

        if total_duration == 0:
            return 1.0

        stability = weighted_stability / total_duration
        logger.info("Regime stability score: %.3f", stability)
        return stability

    def _calculate_thresholds(self) -> None:
        """Calculate regime classification thresholds."""
        if "pace" in self.historical_games.columns:
            pace_series = self.historical_games["pace"].dropna()
            pace_high = np.percentile(pace_series, 75)
            pace_low = np.percentile(pace_series, 25)
        elif "total_points" in self.historical_games.columns:
            total_series = self.historical_games["total_points"].dropna()
            pace_estimated = total_series / 2
            pace_high = np.percentile(pace_estimated, 75)
            pace_low = np.percentile(pace_estimated, 25)
        else:
            pace_high = None
            pace_low = None

        if "variance" in self.historical_games.columns:
            variance_series = self.historical_games["variance"].dropna()
            variance_high = np.percentile(variance_series, 75)
            variance_low = np.percentile(variance_series, 25)
        else:
            variance_high = None
            variance_low = None

        self._thresholds = ThresholdConfig(
            pace_high=pace_high,
            pace_low=pace_low,
            variance_high=variance_high,
            variance_low=variance_low,
        )

    def _calculate_regime_confidence(self, game: pd.Series) -> float:
        """Calculate confidence in regime classification.

        Args:
            game: Game data Series

        Returns:
            Confidence score (0-1)
        """
        pace = game.get("pace", 0)
        if pace == 0:
            return 0.5

        if self._thresholds.pace_high is None or self._thresholds.pace_low is None:
            return 0.5

        threshold_range = self._thresholds.pace_high - self._thresholds.pace_low
        if threshold_range == 0:
            return 0.5

        distance_from_mid = abs(pace - (self._thresholds.pace_high + self._thresholds.pace_low) / 2)
        confidence = min(1.0, distance_from_mid / (threshold_range / 2))

        return confidence

    def _calculate_change_magnitude(
        self, game: pd.Series, previous_regime: RegimeType | None
    ) -> float:
        """Calculate magnitude of regime change.

        Args:
            game: Game data Series
            previous_regime: Previous regime type

        Returns:
            Change magnitude (0-1)
        """
        if previous_regime is None:
            return 0.0

        pace = game.get("pace", 0)
        if pace == 0:
            return 1.0

        pace_mean = self.historical_games["pace"].mean()
        pace_std = self.historical_games["pace"].std()

        if pace_std == 0:
            return 1.0

        z_score = abs((pace - pace_mean) / pace_std)
        magnitude = min(1.0, z_score / 3.0)

        return magnitude

    def _create_regime_period(
        self,
        regime_type: RegimeType,
        start_date: date,
        end_date: date | None,
        games: pd.DataFrame,
    ) -> RegimePeriod:
        """Create a regime period from games.

        Args:
            regime_type: Type of regime
            start_date: Start date of period
            end_date: End date of period
            games: Games in this period

        Returns:
            RegimePeriod instance
        """
        if games.empty:
            pace_data = self.historical_games.get("pace", pd.Series([0]))
            total_data = self.historical_games.get("total_points", pd.Series([0]))
            avg_pace = float(pace_data.mean()) if len(pace_data) > 0 else 0.0
            pace_std = float(pace_data.std()) if len(pace_data) > 0 else 0.0
            avg_total = float(total_data.mean()) if len(total_data) > 0 else 0.0
            total_std = float(total_data.std()) if len(total_data) > 0 else 0.0
        else:
            if "pace" in games.columns:
                avg_pace = float(games["pace"].mean())
                pace_std = float(games["pace"].std())
            elif "total_points" in games.columns:
                avg_pace = float((games["total_points"] / 2).mean())
                pace_std = float((games["total_points"] / 2).std())
            else:
                avg_pace = 0.0
                pace_std = 0.0

            if "total_points" in games.columns:
                avg_total = float(games["total_points"].mean())
                total_std = float(games["total_points"].std())
            else:
                avg_total = 0.0
                total_std = 0.0

        characteristics = self._calculate_period_characteristics(games)

        return RegimePeriod(
            regime_type=regime_type,
            start_date=start_date,
            end_date=end_date,
            game_count=len(games),
            stats=RegimeStats(
                avg_pace=avg_pace,
                pace_std=pace_std,
                avg_total=avg_total,
                total_std=total_std,
            ),
            characteristics=characteristics,
        )

    def _calculate_period_characteristics(self, games: pd.DataFrame) -> dict[str, float]:
        """Calculate characteristics of a regime period.

        Args:
            games: Games in the period

        Returns:
            Dictionary of characteristics
        """
        characteristics: dict[str, float] = {}

        if games.empty:
            return characteristics

        if "pace" in games.columns:
            characteristics["pace_median"] = games["pace"].median()
            characteristics["pace_skewness"] = float(stats.skew(games["pace"].dropna()))
            characteristics["pace_kurtosis"] = float(stats.kurtosis(games["pace"].dropna()))

        if "total_points" in games.columns:
            characteristics["total_median"] = games["total_points"].median()
            characteristics["total_skewness"] = float(stats.skew(games["total_points"].dropna()))

        if "home_score" in games.columns and "away_score" in games.columns:
            characteristics["home_win_rate"] = (games["home_score"] > games["away_score"]).mean()

        return characteristics


class RegimeAwarePredictor:
    """Provides regime-adjusted predictions.

    MLflow Integration:
        - Logs regime-adjusted predictions
        - Logs regime detection confidence
    """

    # pylint: disable=too-many-arguments
    def __init__(
        self,
        base_model: Any,
        regimes: list[RegimeModel],
        mlflow_logger: Optional[MLflowLogger] = None,
    ):
        self.base_model = base_model
        self.regimes = {r.regime_type: r for r in regimes}
        self._current_regime: RegimeType | None = None
        self._regime_history: list[tuple[datetime, RegimeType]] = []
        self.mlflow_logger = mlflow_logger or get_mlflow_logger()

    def detect_current_regime(self) -> RegimeType:
        """Detect the current market regime.

        Returns:
            Current regime type
        """
        if self._current_regime is not None:
            return self._current_regime

        if not self.regimes:
            return RegimeType.NEUTRAL

        best_regime = RegimeType.NEUTRAL
        best_confidence = 0.0

        for regime_type, regime_model in self.regimes.items():
            if regime_type == RegimeType.NEUTRAL:
                continue

            confidence = regime_model.confidence_interval[1] - regime_model.confidence_interval[0]
            confidence = 1.0 / (confidence + 0.1)

            if confidence > best_confidence:
                best_confidence = confidence
                best_regime = regime_type

        self._current_regime = best_regime
        self._regime_history.append((datetime.now(), best_regime))

        logger.info("Detected current regime: %s", best_regime.value)
        return best_regime

    def get_regime_adjustment(self, base_prediction: float, regime: RegimeType) -> float:
        """Get adjustment factor for a regime.

        Args:
            base_prediction: Base prediction value
            regime: Regime type

        Returns:
            Adjustment value
        """
        if regime not in self.regimes:
            logger.warning("Unknown regime type: %s, using neutral adjustment", regime)
            return 0.0

        regime_model = self.regimes[regime]
        adjustment = base_prediction * (regime_model.adjustment_factor - 1.0)
        logger.debug("Regime adjustment for %s: %.3f", regime.value, adjustment)
        return adjustment

    def predict(self, features: pd.DataFrame) -> RegimeAdjustedPrediction:
        """Make regime-adjusted prediction.

        Args:
            features: Feature DataFrame

        Returns:
            RegimeAdjustedPrediction with adjustment details
        """
        base_prediction = self.base_model.predict(features)[0]

        current_regime = self.detect_current_regime()

        if current_regime not in self.regimes:
            return RegimeAdjustedPrediction(
                base_prediction=base_prediction,
                adjusted_prediction=base_prediction,
                regime_adjustment=0.0,
                regime_type=RegimeType.NEUTRAL,
                confidence=0.5,
                adjustment_reason="Unknown regime, no adjustment applied",
            )

        regime_model = self.regimes[current_regime]
        regime_adjustment = self.get_regime_adjustment(base_prediction, current_regime)
        adjusted_prediction = base_prediction + regime_adjustment

        ci_width = regime_model.confidence_interval[1] - regime_model.confidence_interval[0]
        confidence = 1.0 / (ci_width + 0.1)
        confidence = min(0.95, max(0.5, confidence))

        if abs(regime_adjustment) < 0.1:
            adjustment_reason = (
                f"Minimal regime effect in {current_regime.value} "
                f"(adjustment: {regime_adjustment:.3f})"
            )
        else:
            adjustment_reason = (
                f"Adjusted for {current_regime.value} regime "
                f"(factor: {regime_model.adjustment_factor:.3f})"
            )

        logger.info(
            "Regime-adjusted prediction: %.2f -> %.2f (%s)",
            base_prediction,
            adjusted_prediction,
            current_regime.value,
        )

        return RegimeAdjustedPrediction(
            base_prediction=base_prediction,
            adjusted_prediction=adjusted_prediction,
            regime_adjustment=regime_adjustment,
            regime_type=current_regime,
            confidence=confidence,
            adjustment_reason=adjustment_reason,
        )


class RegimePerformanceAnalyzer:
    """Analyzes performance across different regimes.

    MLflow Integration:
        - Logs regime performance metrics
        - Logs edge analysis by regime
        - Logs best/worst regime identification
    """

    def __init__(
        self,
        historical_predictions: pd.DataFrame,
        mlflow_logger: Optional[MLflowLogger] = None,
    ):
        self.historical_predictions = historical_predictions
        self._performance_by_regime: dict[RegimeType, dict[str, float]] = {}
        self.mlflow_logger = mlflow_logger or get_mlflow_logger()

    def measure_performance_by_regime(
        self, predictions: pd.DataFrame, regime: RegimeType
    ) -> dict[str, float]:
        """Measure performance for a specific regime.

        Args:
            predictions: Predictions DataFrame
            regime: Regime type to analyze

        Returns:
            Performance metrics dictionary
        """
        if predictions.empty:
            logger.warning("Empty predictions DataFrame")
            return {}

        regime_predictions = predictions[predictions.get("regime") == regime]

        if regime_predictions.empty:
            logger.warning("No predictions found for regime: %s", regime.value)
            return {}

        performance: dict[str, float] = {}

        if "actual" in regime_predictions.columns and "predicted" in regime_predictions.columns:
            errors = regime_predictions["actual"] - regime_predictions["predicted"]
            performance["mae"] = float(np.abs(errors).mean())
            performance["rmse"] = float(np.sqrt((errors**2).mean()))
            performance["bias"] = float(errors.mean())

        if "win" in regime_predictions.columns:
            wins = regime_predictions["win"].sum()
            total = len(regime_predictions)
            performance["win_rate"] = wins / total if total > 0 else 0
            performance["sample_size"] = total

        if "profit" in regime_predictions.columns:
            performance["roi"] = float(regime_predictions["profit"].sum())
            performance["avg_profit"] = (
                float(regime_predictions["profit"].mean())
                if "profit" in regime_predictions.columns
                else 0
            )

        if "clv" in regime_predictions.columns:
            performance["avg_clv"] = float(regime_predictions["clv"].mean())

        logger.info("Performance for %s: %s", regime.value, performance)
        return performance

    def compare_regime_performance(self) -> RegimeComparison:
        """Compare performance across all regimes.

        Returns:
            RegimeComparison with all regime metrics
        """
        if self.historical_predictions.empty:
            raise ValueError("No historical predictions provided")

        self._performance_by_regime = {}

        unique_regimes = self.historical_predictions.get("regime", pd.Series()).unique()

        for regime_str in unique_regimes:
            try:
                regime = RegimeType(regime_str)
            except (ValueError, TypeError):
                continue

            performance = self.measure_performance_by_regime(self.historical_predictions, regime)
            if performance:
                self._performance_by_regime[regime] = performance

        if not self._performance_by_regime:
            logger.warning("No regime performance data available")
            return RegimeComparison(
                regime_performance={},
                best_regime=RegimeType.NEUTRAL,
                worst_regime=RegimeType.NEUTRAL,
                overall_edge=0.0,
                regime_std=0.0,
                sample_sizes={},
            )

        sample_sizes = {r: p.get("sample_size", 0) for r, p in self._performance_by_regime.items()}

        if self._performance_by_regime:
            best_regime = max(
                self._performance_by_regime.keys(),
                key=lambda r: self._performance_by_regime[r].get("win_rate", 0),
            )
            worst_regime = min(
                self._performance_by_regime.keys(),
                key=lambda r: self._performance_by_regime[r].get("win_rate", 0),
            )
        else:
            best_regime = RegimeType.NEUTRAL
            worst_regime = RegimeType.NEUTRAL

        win_rates = [p.get("win_rate", 0) for p in self._performance_by_regime.values()]
        overall_edge = np.mean(win_rates) - 0.5 if win_rates else 0.0
        regime_std = np.std(win_rates) if win_rates else 0.0

        logger.info(
            "Regime comparison complete. Best: %s, Worst: %s",
            best_regime.value,
            worst_regime.value,
        )

        if self.mlflow_logger:
            self.mlflow_logger.log_metrics(
                {
                    "regime_overall_edge": overall_edge,
                    "regime_std": regime_std,
                    f"best_regime_{best_regime.value}_win_rate": self._performance_by_regime.get(
                        best_regime, {}
                    ).get("win_rate", 0),
                }
            )

        return RegimeComparison(
            regime_performance=self._performance_by_regime,
            best_regime=best_regime,
            worst_regime=worst_regime,
            overall_edge=overall_edge,
            regime_std=regime_std,
            sample_sizes=sample_sizes,
        )

    def find_regime_edge(self, regime: RegimeType) -> RegimeEdgeResult:
        """Find edge analysis for a specific regime.

        Args:
            regime: Regime type to analyze

        Returns:
            RegimeEdgeResult with edge metrics
        """
        performance = self.measure_performance_by_regime(self.historical_predictions, regime)

        if not performance:
            return RegimeEdgeResult(
                regime_type=regime,
                edge=0.0,
                edge_ci=(0.0, 0.0),
                sample_size=0,
                win_rate=0.0,
                roi=0.0,
                clv_avg=0.0,
                profitability_score=0.0,
            )

        win_rate = performance.get("win_rate", 0.5)
        sample_size = int(performance.get("sample_size", 1))
        roi = performance.get("roi", 0.0)
        clv_avg = performance.get("avg_clv", 0.0)

        edge = win_rate - 0.5

        if sample_size > 1:
            std_error = np.sqrt(win_rate * (1 - win_rate) / sample_size)
            edge_ci = (
                max(-0.5, edge - 1.96 * std_error),
                min(0.5, edge + 1.96 * std_error),
            )
        else:
            edge_ci = (edge, edge)

        profitability_score = edge * sample_size / 100 + clv_avg * 0.1

        logger.info("Edge analysis for %s: edge=%.3f, CI=%s", regime.value, edge, edge_ci)

        if self.mlflow_logger:
            self.mlflow_logger.log_regime_analysis(
                regime_type=regime.value,
                edge=edge,
                edge_ci_lower=edge_ci[0],
                edge_ci_upper=edge_ci[1],
                win_rate=win_rate,
                sample_size=sample_size,
            )

        return RegimeEdgeResult(
            regime_type=regime,
            edge=edge,
            edge_ci=edge_ci,
            sample_size=sample_size,
            win_rate=win_rate,
            roi=roi,
            clv_avg=clv_avg,
            profitability_score=profitability_score,
        )


class RegimeAnalyzer:
    """Unified interface for regime analysis.

    MLflow Integration:
        - Logs all regime analysis results to MLflow
        - Logs regime performance comparisons
    """

    def __init__(
        self,
        historical_games: pd.DataFrame,
        mlflow_logger: Optional[MLflowLogger] = None,
    ):
        """Initialize regime analyzer.

        Args:
            historical_games: DataFrame with historical game data
            mlflow_logger: Optional MLflow logger
        """
        self.mlflow_logger = mlflow_logger or get_mlflow_logger()
        self.detector = RegimeDetector(historical_games, self.mlflow_logger)

    def analyze(self) -> dict:
        """Run full regime analysis.

        Returns:
            Dictionary with analysis results
        """
        changes = self.detector.detect_regime_changes()
        periods = self.detector.regime_periods
        stability = self.detector.measure_regime_stability()

        return {
            "n_regime_changes": len(changes),
            "n_regime_periods": len(periods),
            "regime_stability": stability,
            "regime_changes": [
                {
                    "game_id": c.game_id,
                    "from": c.previous_regime.value if c.previous_regime else None,
                    "to": c.new_regime.value,
                    "confidence": c.confidence,
                }
                for c in changes
            ],
        }

    def get_regime_periods(self) -> list[dict]:
        """Get regime periods for analysis.

        Returns:
            List of regime period dictionaries
        """
        periods = self.detector.regime_periods

        return [
            {
                "regime_type": p.regime_type.value,
                "start_date": str(p.start_date),
                "end_date": str(p.end_date) if p.end_date else None,
                "game_count": p.game_count,
                "avg_pace": p.stats.avg_pace,
                "pace_std": p.stats.pace_std,
                "avg_total": p.stats.avg_total,
                "total_std": p.stats.total_std,
            }
            for p in periods
        ]
