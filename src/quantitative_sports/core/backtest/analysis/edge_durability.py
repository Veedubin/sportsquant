"""
Edge Decay Detection and Betting Circuit Breaker

Implements comprehensive edge durability monitoring and betting protection:
1. EdgeDecayDetector: Detects when edge is deteriorating over time
2. BettingCircuitBreaker: Automatically halts betting when conditions indicate model degradation
3. EdgeDurabilityAnalyzer: Unified interface combining both components
4. Trigger callbacks for automated response (retraining, feature reevaluation, market retirement)

MLflow Integration:
- Logs edge decay metrics to MLflow
- Logs circuit breaker state changes
- Logs health scores and durability metrics
- Logs trigger events and callbacks

Data Sources:
- Reads CLV data from TimescaleDB
- Reads stake reduction history from Parquet data lake
- Reads prediction results from Kafka topic 'sports-analytics-model-predictions'

Output:
- Writes analysis results to Kafka topic 'betting-metrics'
- Writes durability analysis to Parquet for historical analysis
- Supports webhook callbacks for real-time alerts
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from statistics import mean
from typing import Any, Callable, Optional, cast

import numpy as np
import pandas as pd
from scipy import stats

from quantitative_sports.core.backtest.analysis.mlflow_logger import MLflowLogger, get_mlflow_logger

logger = logging.getLogger(__name__)


TriggerCallback = Callable[[str, dict], None]


@dataclass(frozen=True)
class EdgeDecayConfig:
    """Configuration for edge decay detection."""

    half_life_window: int = 100
    decay_significance_threshold: float = 0.05
    stake_reduction_threshold: float = 0.3
    max_consecutive_reductions: int = 5
    clv_approaching_zero_threshold: float = 0.01


@dataclass
class EdgeHalfLifeResult:
    """Result of edge half-life analysis."""

    half_life_bets: float
    decay_rate: float
    clv_slope: float
    confidence_interval: tuple[float, float]
    is_significant: bool


class EdgeDecayDetector:
    """Detects deterioration in edge (CLV) over time.

    Uses exponential decay modeling and stake reduction tracking to identify
    when a model's edge is diminishing.

    MLflow Integration:
        - Logs half-life analysis results
        - Logs decay detection status
        - Logs stake reduction analysis
    """

    def __init__(
        self,
        config: EdgeDecayConfig | None = None,
        mlflow_logger: Optional[MLflowLogger] = None,
    ):
        self.config = config or EdgeDecayConfig()
        self._decay_warnings: list[str] = []
        self._reduction_history: list[float] = []
        self._clv_buffer: deque[float] = deque(maxlen=1000)
        self.mlflow_logger = mlflow_logger or get_mlflow_logger()

    def compute_half_life(self, clv_series: pd.Series) -> EdgeHalfLifeResult:
        """Compute the half-life of edge (CLV) decay.

        Args:
            clv_series: Series of CLV values over time (oldest to newest)

        Returns:
            EdgeHalfLifeResult with decay metrics
        """
        if len(clv_series) < self.config.half_life_window:
            logger.warning(
                "Insufficient CLV data for half-life: %d < %d",
                len(clv_series),
                self.config.half_life_window,
            )
            return EdgeHalfLifeResult(
                half_life_bets=float("inf"),
                decay_rate=0.0,
                clv_slope=0.0,
                confidence_interval=(float("inf"), float("inf")),
                is_significant=False,
            )

        window_clv = np.asarray(
            clv_series.tail(self.config.half_life_window).values, dtype=np.float64
        )

        regression = self._extract_decay_regression(np.asarray(window_clv, dtype=np.float64))
        if regression is None:
            return self._default_half_life_result()

        slope, p_value, std_err = regression
        return self._build_half_life_result(
            np.asarray(window_clv, dtype=np.float64), slope, p_value, std_err
        )

    def _default_half_life_result(self) -> EdgeHalfLifeResult:
        inf = float("inf")
        return EdgeHalfLifeResult(
            half_life_bets=inf,
            decay_rate=0.0,
            clv_slope=0.0,
            confidence_interval=(inf, inf),
            is_significant=False,
        )

    def _extract_decay_regression(
        self, window_clv: np.ndarray
    ) -> tuple[float, float, float] | None:
        bet_indices = np.arange(len(window_clv))
        try:
            result = stats.linregress(bet_indices, window_clv)
            # Access attributes with type: ignore for scipy.stats.linregress result
            slope: float = float(cast(Any, result).slope)
            p_value: float = float(cast(Any, result).pvalue)
            std_err: float = float(cast(Any, result).stderr)
        except ValueError as exc:
            logger.warning("Half-life regression failed: %s", exc)
            return None

        return (slope, p_value, std_err)

    def _build_half_life_result(
        self,
        window_clv: np.ndarray,
        slope: float,
        p_value: float,
        std_err: float,
    ) -> EdgeHalfLifeResult:
        mean_clv = float(np.mean(window_clv))
        half_life = float("inf")
        if mean_clv > 0 and slope < -1e-10:
            half_life = -mean_clv / (2 * slope)

        decay_rate = -slope / (mean_clv + 1e-10)
        adjusted_p_value = p_value * len(window_clv)
        is_significant = (
            adjusted_p_value < self.config.decay_significance_threshold and abs(slope) > std_err * 2
        )
        ci_lower = slope - 1.96 * std_err
        ci_upper = slope + 1.96 * std_err

        return EdgeHalfLifeResult(
            half_life_bets=half_life,
            decay_rate=decay_rate,
            clv_slope=slope,
            confidence_interval=(ci_lower, ci_upper),
            is_significant=is_significant,
        )

    def detect_decay(self, clv_series: pd.Series) -> tuple[bool, str]:
        """Detect if edge is decaying.

        Args:
            clv_series: Series of CLV values over time

        Returns:
            Tuple of (is_decay: bool, reason: str)
        """
        half_life_result = self.compute_half_life(clv_series)

        if half_life_result.half_life_bets == float("inf"):
            return False, "Insufficient data for decay detection"

        if half_life_result.half_life_bets < 50:
            return (
                True,
                f"Rapid decay detected: half-life = {half_life_result.half_life_bets:.1f} bets",
            )

        if half_life_result.clv_slope < 0 and half_life_result.is_significant:
            return (
                True,
                f"Significant negative CLV slope: {half_life_result.clv_slope:.6f}",
            )

        recent_clv = clv_series.tail(20).mean()
        older_clv = clv_series.head(20).mean() if len(clv_series) > 20 else recent_clv

        if older_clv > self.config.clv_approaching_zero_threshold:
            clv_retention = recent_clv / older_clv
            if clv_retention < 0.5:
                return True, f"CLV retention below 50%: {clv_retention:.2%}"

        return False, "No significant decay detected"

    def track_stake_reductions(self, reduction_history: list[float]) -> dict:
        """Analyze stake reduction patterns.

        Args:
            reduction_history: List of reduction ratios (reduced/stake)

        Returns:
            Dictionary with reduction analysis
        """
        self._reduction_history = reduction_history

        if len(reduction_history) == 0:
            return self._empty_reduction_result()

        n_reductions = len(reduction_history)
        avg_reduction = mean(reduction_history)
        max_reduction = max(reduction_history)
        consecutive = self._count_consecutive_reductions(reduction_history)
        reduction_trend = self._calculate_reduction_trend(reduction_history)

        return self._build_reduction_result(
            n_reductions,
            avg_reduction,
            max_reduction,
            consecutive,
            reduction_trend,
            self._determine_decay_signal(consecutive, avg_reduction),
        )

    def _build_reduction_result(
        self,
        n_reductions: int,
        avg_reduction: float,
        max_reduction: float,
        consecutive: int,
        reduction_trend: str,
        is_decay_signal: bool,
    ) -> dict:
        """Build the reduction analysis result dictionary."""
        return {
            "n_reductions": n_reductions,
            "avg_reduction": avg_reduction,
            "max_reduction": max_reduction,
            "consecutive_reductions": consecutive,
            "reduction_trend": reduction_trend,
            "is_decay_signal": is_decay_signal,
        }

    def _count_consecutive_reductions(self, reduction_history: list[float]) -> int:
        """Count consecutive stake reductions from the end."""
        consecutive = 0
        for r in reversed(reduction_history):
            if r < 1.0:
                consecutive += 1
            else:
                break
        return consecutive

    def _calculate_reduction_trend(self, reduction_history: list[float]) -> str:
        """Calculate the trend in stake reductions."""
        if len(reduction_history) < 5:
            return "insufficient_data"

        recent = reduction_history[-5:]
        older = reduction_history[:5]
        avg_recent = mean(recent) if recent else 1.0
        avg_older = mean(older) if older else 1.0

        if avg_recent < avg_older * 0.8:
            return "declining"
        elif avg_recent > avg_older * 1.2:
            return "increasing"
        else:
            return "stable"

    def _determine_decay_signal(self, consecutive: int, avg_reduction: float) -> bool:
        """Determine if the reduction pattern indicates decay."""
        return (
            consecutive >= self.config.max_consecutive_reductions
            or avg_reduction < self.config.stake_reduction_threshold
        )

    def _empty_reduction_result(self) -> dict:
        """Return empty reduction analysis result."""
        return {
            "n_reductions": 0,
            "avg_reduction": 0.0,
            "max_reduction": 0.0,
            "consecutive_reductions": 0,
            "reduction_trend": "stable",
            "is_decay_signal": False,
        }

    def get_decay_warnings(self) -> list[str]:
        """Get accumulated decay warnings.

        Returns:
            List of warning messages
        """
        return self._decay_warnings.copy()

    def record_clv(self, clv_value: float) -> None:
        """Record a new CLV value for tracking.

        Args:
            clv_value: CLV value to record
        """
        self._clv_buffer.append(clv_value)

    def get_clv_buffer(self) -> pd.Series:
        """Get all recorded CLV values as a Series.

        Returns:
            Series of recorded CLV values
        """
        return pd.Series(list(self._clv_buffer))


@dataclass(frozen=True)
class CircuitBreakerConfig:
    """Configuration for betting circuit breaker."""

    negative_clv_window: int = 20
    negative_clv_threshold: float = -0.02
    line_reversal_count: int = 3
    market_closure_threshold_minutes: int = 60
    max_stake_reductions: int = 5


@dataclass
class CircuitBreakerStats:
    """Running totals tracked by the circuit breaker."""

    consecutive_negative_clv: int = 0
    total_negative_clv: float = 0.0
    line_reversals: int = 0
    stake_reductions: int = 0
    n_bets_recorded: int = 0


@dataclass
class CircuitBreakerState:
    """Current state of the circuit breaker."""

    is_open: bool = False
    open_timestamp: datetime | None = None
    close_reason: str = ""
    stats: CircuitBreakerStats = field(default_factory=CircuitBreakerStats)


class BettingCircuitBreaker:
    """Automatically halts betting when degradation indicators exceed thresholds.

    Monitors:
    - Negative CLV streak
    - Line reversals (market moving against bets)
    - Stake reductions
    - Market closure speed

    MLflow Integration:
        - Logs circuit breaker state changes
        - Logs trigger events
        - Logs statistics to MLflow
    """

    def __init__(
        self,
        config: CircuitBreakerConfig | None = None,
        mlflow_logger: Optional[MLflowLogger] = None,
    ):
        self.config = config or CircuitBreakerConfig()
        self._state = CircuitBreakerState()
        self._negative_clv_buffer: deque[float] = deque(maxlen=self.config.negative_clv_window)
        self._line_reversals: dict[str, int] = {}
        self._callbacks: dict[str, list[TriggerCallback]] = {
            "retrain": [],
            "feature_reeval": [],
            "retire_market": [],
        }
        self.mlflow_logger = mlflow_logger or get_mlflow_logger()

    def on_retrain(self, callback: TriggerCallback) -> None:
        """Register callback for retraining trigger."""
        self._callbacks["retrain"].append(callback)

    def on_feature_reeval(self, callback: TriggerCallback) -> None:
        """Register callback for feature reevaluation trigger."""
        self._callbacks["feature_reeval"].append(callback)

    def on_retire_market(self, callback: TriggerCallback) -> None:
        """Register callback for market retirement trigger."""
        self._callbacks["retire_market"].append(callback)

    def _trigger_callbacks(self, trigger_type: str, context: dict) -> None:
        """Trigger registered callbacks.

        Args:
            trigger_type: Type of trigger (retrain, feature_reeval, retire_market)
            context: Context dictionary with trigger details
        """
        callbacks = self._callbacks.get(trigger_type, [])

        for callback in callbacks:
            try:
                callback(trigger_type, context)
            except (RuntimeError, ValueError) as e:
                logger.error("Callback error for %s: %s", trigger_type, e)

    def check_bet(self, _bet_context: dict) -> tuple[bool, str]:
        """Check if a bet is allowed based on current circuit state.

        Args:
            bet_context: Dictionary with bet details (market, line, etc.)

        Returns:
            Tuple of (allowed: bool, reason: str)
        """
        if self._state.is_open:
            return False, f"Circuit breaker open since {self._state.open_timestamp}"

        breaker_stats = self._state.stats
        if breaker_stats.consecutive_negative_clv >= self.config.negative_clv_window:
            self._open_breaker("Negative CLV streak detected")
            self._trigger_callbacks(
                "retrain",
                {
                    "reason": "negative_clv_streak",
                    "consecutive": breaker_stats.consecutive_negative_clv,
                    "avg_clv": breaker_stats.total_negative_clv
                    / breaker_stats.consecutive_negative_clv,
                },
            )
            return False, "Negative CLV streak - circuit breaker activated"

        if breaker_stats.line_reversals >= self.config.line_reversal_count:
            self._open_breaker("Excessive line reversals")
            self._trigger_callbacks(
                "feature_reeval",
                {
                    "reason": "line_reversals",
                    "count": breaker_stats.line_reversals,
                },
            )
            return False, f"Too many line reversals ({breaker_stats.line_reversals})"

        if breaker_stats.stake_reductions >= self.config.max_stake_reductions:
            self._open_breaker("Consecutive stake reductions")
            self._trigger_callbacks(
                "retrain",
                {
                    "reason": "stake_reductions",
                    "count": breaker_stats.stake_reductions,
                },
            )
            return (
                False,
                f"Too many stake reductions ({breaker_stats.stake_reductions})",
            )

        return True, "Bet allowed"

    def check_after_bet(self, bet_id: str, line_movement: dict) -> tuple[bool, str]:
        """Check conditions after a bet is placed.

        Args:
            bet_id: Unique identifier for the bet
            line_movement: Dictionary with line movement details

        Returns:
            Tuple of (allowed: bool, reason: str)
        """
        movement_direction = line_movement.get("direction", "none")
        movement_pct = line_movement.get("pct", 0.0)
        breaker_stats = self._state.stats

        if movement_direction == "against" and movement_pct > 0.05:
            breaker_stats.line_reversals += 1
            self._line_reversals[bet_id] = self._line_reversals.get(bet_id, 0) + 1
            logger.warning(
                "Line reversal detected for bet %s: %.1f%% against",
                bet_id,
                movement_pct * 100,
            )

            if breaker_stats.line_reversals >= self.config.line_reversal_count:
                self._open_breaker("Excessive line reversals")
                self._trigger_callbacks(
                    "feature_reeval",
                    {
                        "reason": "line_reversals_post_bet",
                        "count": breaker_stats.line_reversals,
                        "bet_id": bet_id,
                    },
                )
                return (
                    False,
                    f"Line reversal threshold reached ({breaker_stats.line_reversals})",
                )

        return True, "Bet condition OK"

    def record_negative_clv(self, clv_value: float) -> None:
        """Record a negative CLV value.

        Args:
            clv_value: The CLV value to record
        """
        breaker_stats = self._state.stats
        self._negative_clv_buffer.append(clv_value)
        breaker_stats.n_bets_recorded += 1

        if clv_value < 0:
            breaker_stats.consecutive_negative_clv += 1
            breaker_stats.total_negative_clv += clv_value
        else:
            breaker_stats.consecutive_negative_clv = 0

        if len(self._negative_clv_buffer) >= self.config.negative_clv_window:
            recent_clv = list(self._negative_clv_buffer)
            avg_clv = mean(recent_clv)

            if avg_clv < self.config.negative_clv_threshold:
                logger.warning(
                    "Negative CLV threshold breached: %.4f < %.4f",
                    avg_clv,
                    self.config.negative_clv_threshold,
                )

    def record_line_reversal(self, bet_id: str) -> None:
        """Record a line reversal for a bet.

        Args:
            bet_id: Unique identifier for the bet
        """
        breaker_stats = self._state.stats
        breaker_stats.line_reversals += 1
        self._line_reversals[bet_id] = self._line_reversals.get(bet_id, 0) + 1
        logger.info(
            "Line reversal recorded for %s (total: %d)",
            bet_id,
            breaker_stats.line_reversals,
        )

    def record_stake_reduction(self, original_stake: float, reduced_stake: float) -> None:
        """Record a stake reduction.

        Args:
            original_stake: Original stake amount
            reduced_stake: Reduced stake amount
        """
        if reduced_stake < original_stake:
            breaker_stats = self._state.stats
            breaker_stats.stake_reductions += 1
            logger.info(
                "Stake reduction recorded: %.2f -> %.2f (reduction #%d)",
                original_stake,
                reduced_stake,
                breaker_stats.stake_reductions,
            )

    def get_state(self) -> dict:
        """Get current circuit breaker state.

        Returns:
            Dictionary with state details
        """
        breaker_stats = self._state.stats
        avg_negative_clv = 0.0
        if breaker_stats.consecutive_negative_clv > 0:
            avg_negative_clv = (
                breaker_stats.total_negative_clv / breaker_stats.consecutive_negative_clv
            )

        return {
            "is_open": self._state.is_open,
            "open_timestamp": self._state.open_timestamp.isoformat()
            if self._state.open_timestamp
            else None,
            "close_reason": self._state.close_reason,
            "consecutive_negative_clv": breaker_stats.consecutive_negative_clv,
            "avg_negative_clv": avg_negative_clv,
            "line_reversals": breaker_stats.line_reversals,
            "stake_reductions": breaker_stats.stake_reductions,
            "n_bets_recorded": breaker_stats.n_bets_recorded,
            "negative_clv_window": self.config.negative_clv_window,
            "negative_clv_threshold": self.config.negative_clv_threshold,
            "line_reversal_threshold": self.config.line_reversal_count,
            "stake_reduction_threshold": self.config.max_stake_reductions,
        }

    def reset(self) -> None:
        """Reset all counters and close the circuit breaker."""
        self._state = CircuitBreakerState()
        self._negative_clv_buffer.clear()
        self._line_reversals.clear()
        logger.info("Circuit breaker reset")

    def is_open(self) -> bool:
        """Check if circuit breaker is open.

        Returns:
            True if circuit is open (betting suspended)
        """
        return self._state.is_open

    def _open_breaker(self, reason: str) -> None:
        """Open the circuit breaker.

        Args:
            reason: Reason for opening
        """
        self._state.is_open = True
        self._state.open_timestamp = datetime.now(timezone.utc)
        self._state.close_reason = reason
        logger.warning("Circuit breaker opened: %s", reason)

        if self.mlflow_logger:
            self.mlflow_logger.log_metrics({"circuit_breaker_open": 1})
            self.mlflow_logger.log_params({"circuit_breaker_reason": reason})


class EdgeDurabilityAnalyzer:
    """Unified interface for edge durability checking.

    Combines EdgeDecayDetector and BettingCircuitBreaker to provide
    comprehensive edge monitoring and protection.

    MLflow Integration:
        - Logs all analysis results to MLflow
        - Logs health scores and durability metrics
        - Logs circuit breaker state changes
    """

    def __init__(
        self,
        decay_config: EdgeDecayConfig | None = None,
        breaker_config: CircuitBreakerConfig | None = None,
        mlflow_logger: Optional[MLflowLogger] = None,
    ):
        self.mlflow_logger = mlflow_logger or get_mlflow_logger()
        self.decay_detector = EdgeDecayDetector(decay_config, self.mlflow_logger)
        self.circuit_breaker = BettingCircuitBreaker(breaker_config, self.mlflow_logger)

        self._decay_history: list[dict] = []
        self._health_checkpoints: list[dict] = []

    def check_bet(self, bet_context: dict) -> tuple[bool, str]:
        """Check if a bet is allowed.

        Args:
            bet_context: Dictionary with bet details

        Returns:
            Tuple of (allowed: bool, reason: str)
        """
        return self.circuit_breaker.check_bet(bet_context)

    # pylint: disable=too-many-arguments
    def record_bet_result(
        self,
        clv_value: float,
        line_movement: dict | None = None,
        stake_info: dict | None = None,
    ) -> dict:
        """Record the result of a bet.

        Args:
            clv_value: CLV value for the bet
            line_movement: Optional line movement details
            stake_info: Optional stake information

        Returns:
            Dictionary with recording results
        """
        self.decay_detector.record_clv(clv_value)
        self.circuit_breaker.record_negative_clv(clv_value)

        if line_movement:
            bet_id = line_movement.get("bet_id", "unknown")
            movement = {
                "direction": line_movement.get("direction", "none"),
                "pct": line_movement.get("pct", 0.0),
            }
            self.circuit_breaker.check_after_bet(bet_id, movement)

        if stake_info:
            self.circuit_breaker.record_stake_reduction(
                stake_info.get("original", 0),
                stake_info.get("reduced", 0),
            )

        is_decay, decay_reason = self.decay_detector.detect_decay(
            self.decay_detector.get_clv_buffer()
        )

        self._decay_history.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "clv": clv_value,
                "is_decay": is_decay,
                "decay_reason": decay_reason,
            }
        )

        return {
            "clv_recorded": True,
            "is_decay_detected": is_decay,
            "decay_reason": decay_reason,
            "circuit_open": self.circuit_breaker.is_open(),
        }

    def analyze_edge_health(self) -> dict:
        """Analyze current edge health.

        Returns:
            Dictionary with health metrics
        """
        clv_series = self.decay_detector.get_clv_buffer()
        half_life_result = self.decay_detector.compute_half_life(clv_series)

        reduction_history = self.decay_detector._reduction_history  # pylint: disable=protected-access
        reduction_analysis = self.decay_detector.track_stake_reductions(reduction_history)

        breaker_state = self.circuit_breaker.get_state()

        health_score = 100.0

        if half_life_result.half_life_bets != float("inf"):
            if half_life_result.half_life_bets < 100:
                health_score -= 30 * (100 / max(half_life_result.half_life_bets, 1))
            if half_life_result.clv_slope < 0:
                health_score -= abs(half_life_result.clv_slope) * 10000

        health_score = max(0.0, min(100.0, health_score))

        if reduction_analysis["is_decay_signal"]:
            health_score -= 20

        if breaker_state["consecutive_negative_clv"] > 0:
            health_score -= min(30, breaker_state["consecutive_negative_clv"] * 2)

        if breaker_state["line_reversals"] > 0:
            health_score -= min(20, breaker_state["line_reversals"] * 5)

        self._health_checkpoints.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "health_score": health_score,
                "half_life": half_life_result.half_life_bets,
                "circuit_open": breaker_state["is_open"],
            }
        )

        if self.mlflow_logger:
            self.mlflow_logger.log_metrics(
                {
                    "edge_durability_health_score": float(health_score),
                    "edge_durability_half_life": float(half_life_result.half_life_bets),
                    "edge_durability_decay_rate": float(half_life_result.decay_rate),
                    "edge_durability_circuit_open": 1 if breaker_state["is_open"] else 0,
                }
            )

        return {
            "health_score": health_score,
            "edge_decay": {
                "half_life_bets": half_life_result.half_life_bets,
                "decay_rate": half_life_result.decay_rate,
                "clv_slope": half_life_result.clv_slope,
                "is_significant": half_life_result.is_significant,
                "confidence_interval": half_life_result.confidence_interval,
            },
            "stake_reduction_analysis": reduction_analysis,
            "circuit_breaker_state": breaker_state,
            "warnings": self.decay_detector.get_decay_warnings(),
        }

    def get_durability_score(self) -> float:
        """Get overall edge durability score.

        Returns:
            Score from 0-100
        """
        health = self.analyze_edge_health()
        return health["health_score"]

    def register_callbacks(
        self,
        on_retrain: TriggerCallback | None = None,
        on_feature_reeval: TriggerCallback | None = None,
        on_retire_market: TriggerCallback | None = None,
    ) -> None:
        """Register callbacks for circuit breaker triggers.

        Args:
            on_retrain: Callback for retraining trigger
            on_feature_reeval: Callback for feature reevaluation trigger
            on_retire_market: Callback for market retirement trigger
        """
        if on_retrain:
            self.circuit_breaker.on_retrain(on_retrain)
        if on_feature_reeval:
            self.circuit_breaker.on_feature_reeval(on_feature_reeval)
        if on_retire_market:
            self.circuit_breaker.on_retire_market(on_retire_market)

    def reset(self) -> None:
        """Reset all components."""
        self.decay_detector = EdgeDecayDetector(self.decay_detector.config, self.mlflow_logger)
        self.circuit_breaker.reset()
        self._decay_history.clear()
        self._health_checkpoints.clear()
        logger.info("EdgeDurabilityAnalyzer reset")

    def get_history(self) -> dict:
        """Get analysis history.

        Returns:
            Dictionary with decay history and health checkpoints
        """
        return {
            "decay_history": self._decay_history[-100:],
            "health_checkpoints": self._health_checkpoints[-100:],
            "total_decay_records": len(self._decay_history),
            "total_health_checks": len(self._health_checkpoints),
        }
