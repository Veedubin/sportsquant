"""
Advanced performance metrics for betting strategy evaluation.

Provides comprehensive risk-adjusted metrics including Sharpe ratio, Sortino ratio,
maximum drawdown, win streaks, and other performance analytics.
"""

from dataclasses import dataclass
from typing import Sequence

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class CoreMetrics:
    """Core performance metrics for betting strategies."""

    total_bets: int
    win_rate: float
    total_pnl: float
    mean_pnl_per_bet: float
    mean_ev_per_bet: float


@dataclass(frozen=True)
class RiskAdjustedMetrics:
    """Risk-adjusted performance ratios."""

    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    profit_factor: float


@dataclass(frozen=True)
class DrawdownMetrics:
    """Drawdown-related metrics."""

    max_drawdown: float
    max_drawdown_pct: float
    max_drawdown_duration: int


@dataclass(frozen=True)
class StreakMetrics:
    """Streak-related metrics."""

    max_win_streak: int
    max_loss_streak: int
    current_streak: int
    current_streak_type: str


@dataclass(frozen=True)
class DistributionMetrics:
    """PnL distribution statistics."""

    pnl_std: float
    pnl_skewness: float
    pnl_kurtosis: float


@dataclass(frozen=True)
class ReturnMetrics:
    """Return-related metrics."""

    total_return_pct: float
    return_on_risk: float


@dataclass(frozen=True)
class PerformanceMetrics:
    """Comprehensive performance metrics for betting strategies."""

    core: CoreMetrics
    risk_adjusted: RiskAdjustedMetrics
    drawdown: DrawdownMetrics
    streaks: StreakMetrics
    distribution: DistributionMetrics
    returns: ReturnMetrics

    def to_dict(self) -> dict[str, float | int | str]:
        """Convert metrics to dictionary."""
        return {
            **self.core.__dict__,
            **self.risk_adjusted.__dict__,
            **self.drawdown.__dict__,
            **self.streaks.__dict__,
            **self.distribution.__dict__,
            **self.returns.__dict__,
        }


def calculate_sharpe_ratio(
    returns: Sequence[float] | np.ndarray,
    risk_free_rate: float = 0.0,
    periods_per_year: int = 252,
) -> float:
    """Calculate Sharpe ratio for returns.

    Args:
        returns: Sequence of return values.
        risk_free_rate: Annual risk-free rate (default 0.0).
        periods_per_year: Number of trading periods per year (default 252).

    Returns:
        Annualized Sharpe ratio.
    """
    if len(returns) == 0:
        return 0.0

    returns_array = np.array(returns, dtype=float)
    mean_return = float(np.mean(returns_array))
    std_return = float(np.std(returns_array, ddof=1))

    if std_return == 0:
        return 0.0

    annual_return = mean_return * periods_per_year
    annual_std = std_return * np.sqrt(periods_per_year)

    sharpe = (annual_return - risk_free_rate) / annual_std
    return float(sharpe)


def calculate_sortino_ratio(
    returns: Sequence[float] | np.ndarray,
    risk_free_rate: float = 0.0,
    periods_per_year: int = 252,
) -> float:
    """Calculate Sortino ratio for returns.

    Args:
        returns: Sequence of return values.
        risk_free_rate: Annual risk-free rate (default 0.0).
        periods_per_year: Number of trading periods per year (default 252).

    Returns:
        Annualized Sortino ratio.
    """
    if len(returns) == 0:
        return 0.0

    returns_array = np.array(returns, dtype=float)
    mean_return = float(np.mean(returns_array))

    downside_returns = returns_array[returns_array < 0]
    if len(downside_returns) == 0:
        return 999.0

    downside_std = float(np.std(downside_returns, ddof=1))
    if downside_std == 0:
        return 0.0

    annual_return = mean_return * periods_per_year
    annual_downside_std = downside_std * np.sqrt(periods_per_year)

    sortino = (annual_return - risk_free_rate) / annual_downside_std
    return float(sortino)


def calculate_max_drawdown(
    cumulative_pnl: Sequence[float] | np.ndarray,
) -> tuple[float, float, int]:
    """Calculate maximum drawdown from cumulative PnL.

    Args:
        cumulative_pnl: Sequence of cumulative profit/loss values.

    Returns:
        Tuple of (max_drawdown, max_drawdown_pct, duration).
    """
    if len(cumulative_pnl) == 0:
        return 0.0, 0.0, 0

    cumulative = np.array(cumulative_pnl, dtype=float)
    running_max = np.maximum.accumulate(cumulative)
    drawdown = running_max - cumulative

    max_dd = float(np.max(drawdown))

    max_dd_idx = int(np.argmax(drawdown))
    peak_value = running_max[max_dd_idx]
    if peak_value > 0:
        max_dd_pct = (max_dd / peak_value) * 100.0
    else:
        max_dd_pct = 0.0

    duration = 0
    if max_dd > 0:
        peak_idx = max_dd_idx
        while peak_idx > 0 and cumulative[peak_idx - 1] >= cumulative[peak_idx]:
            peak_idx -= 1

        recovery_idx = max_dd_idx
        while (
            recovery_idx < len(cumulative) - 1
            and cumulative[recovery_idx] < running_max[max_dd_idx]
        ):
            recovery_idx += 1

        duration = recovery_idx - peak_idx

    return max_dd, max_dd_pct, duration


def calculate_profit_factor(pnl_series: Sequence[float] | np.ndarray) -> float:
    """Calculate profit factor (gross profit / gross loss)."""
    if len(pnl_series) == 0:
        return 0.0

    pnl_array = np.array(pnl_series, dtype=float)
    gross_profit = float(np.sum(pnl_array[pnl_array > 0]))
    gross_loss = float(np.abs(np.sum(pnl_array[pnl_array < 0])))

    if gross_loss == 0:
        return 999.0 if gross_profit > 0 else 0.0

    return gross_profit / gross_loss


def calculate_streaks(
    outcomes: Sequence[bool] | np.ndarray,
) -> tuple[int, int, int, str]:
    """Calculate win/loss streaks from outcomes.

    Args:
        outcomes: Sequence of True (win) / False (loss) values.

    Returns:
        Tuple of (max_win_streak, max_loss_streak, current_streak, streak_type).
    """
    if len(outcomes) == 0:
        return 0, 0, 0, "none"

    max_win = 0
    max_loss = 0
    current = 0

    for outcome in outcomes:
        if outcome:
            if current > 0:
                current += 1
            else:
                current = 1
            max_win = max(max_win, current)
        else:
            if current < 0:
                current -= 1
            else:
                current = -1
            max_loss = max(max_loss, abs(current))

    if current == 0:
        current_type = "none"
    elif current > 0:
        current_type = "win"
    else:
        current_type = "loss"

    return max_win, max_loss, current, current_type


def calculate_performance_metrics(
    pnl_series: pd.Series,
    ev_series: pd.Series,
    outcome_series: pd.Series,
    stake_series: pd.Series | None = None,
    risk_free_rate: float = 0.0,
) -> PerformanceMetrics:
    """Calculate comprehensive performance metrics from bet results.

    Args:
        pnl_series: Series of profit/loss values.
        ev_series: Series of expected values.
        outcome_series: Series of win/loss outcomes.
        stake_series: Optional series of stake amounts.
        risk_free_rate: Annual risk-free rate (default 0.0).

    Returns:
        PerformanceMetrics dataclass with all calculated metrics.
    """
    # pylint: disable=R0914
    pnl = np.asarray(pnl_series.values, dtype=float)
    ev = np.asarray(ev_series.values, dtype=float)
    outcomes = np.asarray(outcome_series.values, dtype=bool)

    total_bets = len(pnl)
    if total_bets == 0:
        return PerformanceMetrics(
            core=CoreMetrics(
                total_bets=0,
                win_rate=0.0,
                total_pnl=0.0,
                mean_pnl_per_bet=0.0,
                mean_ev_per_bet=0.0,
            ),
            risk_adjusted=RiskAdjustedMetrics(
                sharpe_ratio=0.0,
                sortino_ratio=0.0,
                calmar_ratio=0.0,
                profit_factor=0.0,
            ),
            drawdown=DrawdownMetrics(
                max_drawdown=0.0,
                max_drawdown_pct=0.0,
                max_drawdown_duration=0,
            ),
            streaks=StreakMetrics(
                max_win_streak=0,
                max_loss_streak=0,
                current_streak=0,
                current_streak_type="none",
            ),
            distribution=DistributionMetrics(
                pnl_std=0.0,
                pnl_skewness=0.0,
                pnl_kurtosis=0.0,
            ),
            returns=ReturnMetrics(
                total_return_pct=0.0,
                return_on_risk=0.0,
            ),
        )

    win_rate = float(np.mean(outcomes))
    total_pnl = float(np.sum(pnl))
    mean_pnl = float(np.mean(pnl))
    mean_ev = float(np.mean(ev))

    sharpe = calculate_sharpe_ratio(pnl, risk_free_rate)
    sortino = calculate_sortino_ratio(pnl, risk_free_rate)

    cumulative_pnl = np.cumsum(pnl)
    max_dd, max_dd_pct, dd_duration = calculate_max_drawdown(cumulative_pnl)

    annual_return = mean_pnl * 252
    calmar = annual_return / max_dd if max_dd > 0 else 0.0

    profit_factor = calculate_profit_factor(pnl)

    max_win_streak, max_loss_streak, current_streak, streak_type = calculate_streaks(outcomes)

    pnl_std = float(np.std(pnl, ddof=1))
    pnl_skewness = float(pd.Series(pnl).skew()) if len(pnl) > 2 else 0.0
    pnl_kurtosis = float(pd.Series(pnl).kurtosis()) if len(pnl) > 3 else 0.0

    if stake_series is not None and len(stake_series) > 0:
        total_stakes = float(stake_series.sum())
        total_return_pct = (total_pnl / total_stakes * 100.0) if total_stakes > 0 else 0.0
    else:
        total_return_pct = (total_pnl / total_bets * 100.0) if total_bets > 0 else 0.0

    return_on_risk = total_pnl / max_dd if max_dd > 0 else 0.0

    return PerformanceMetrics(
        core=CoreMetrics(
            total_bets=total_bets,
            win_rate=win_rate,
            total_pnl=total_pnl,
            mean_pnl_per_bet=mean_pnl,
            mean_ev_per_bet=mean_ev,
        ),
        risk_adjusted=RiskAdjustedMetrics(
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            calmar_ratio=calmar,
            profit_factor=profit_factor,
        ),
        drawdown=DrawdownMetrics(
            max_drawdown=max_dd,
            max_drawdown_pct=max_dd_pct,
            max_drawdown_duration=dd_duration,
        ),
        streaks=StreakMetrics(
            max_win_streak=max_win_streak,
            max_loss_streak=max_loss_streak,
            current_streak=current_streak,
            current_streak_type=streak_type,
        ),
        distribution=DistributionMetrics(
            pnl_std=pnl_std,
            pnl_skewness=pnl_skewness,
            pnl_kurtosis=pnl_kurtosis,
        ),
        returns=ReturnMetrics(
            total_return_pct=total_return_pct,
            return_on_risk=return_on_risk,
        ),
    )


def empty_performance_metrics() -> PerformanceMetrics:
    """Return a zero-valued PerformanceMetrics instance.

    Used by :class:`sportsquant.core.betting.strategies.registry.StrategyRegistry`
    when a strategy produced no bets and the normal
    :func:`calculate_performance_metrics` pipeline has no series to crunch.

    Returns:
        A :class:`PerformanceMetrics` with all numeric fields set to 0.0
        and streak/type fields set to safe empty values.
    """
    zero_core = CoreMetrics(
        total_bets=0,
        win_rate=0.0,
        total_pnl=0.0,
        mean_pnl_per_bet=0.0,
        mean_ev_per_bet=0.0,
    )
    zero_risk = RiskAdjustedMetrics(
        sharpe_ratio=0.0,
        sortino_ratio=0.0,
        calmar_ratio=0.0,
        profit_factor=0.0,
    )
    zero_dd = DrawdownMetrics(
        max_drawdown=0.0,
        max_drawdown_pct=0.0,
        max_drawdown_duration=0,
    )
    zero_streak = StreakMetrics(
        max_win_streak=0,
        max_loss_streak=0,
        current_streak=0,
        current_streak_type="none",
    )
    zero_dist = DistributionMetrics(
        pnl_std=0.0,
        pnl_skewness=0.0,
        pnl_kurtosis=0.0,
    )
    zero_returns = ReturnMetrics(
        total_return_pct=0.0,
        return_on_risk=0.0,
    )
    return PerformanceMetrics(
        core=zero_core,
        risk_adjusted=zero_risk,
        drawdown=zero_dd,
        streaks=zero_streak,
        distribution=zero_dist,
        returns=zero_returns,
    )


def ranked_probability_score(predictions: np.ndarray, outcomes: np.ndarray) -> float:
    """Calculate ranked probability score for binary predictions.

    Args:
        predictions: Array of predicted probabilities.
        outcomes: Array of actual outcomes (0 or 1).

    Returns:
        RPS score (lower is better).
    """
    predictions = np.asarray(predictions)
    outcomes = np.asarray(outcomes)

    if len(predictions) != len(outcomes):
        raise ValueError("Predictions and outcomes must have the same length")

    predictions = np.clip(predictions, 0.001, 0.999)

    p_over = predictions
    p_under = 1 - predictions

    o_over = outcomes
    o_under = 1 - outcomes

    rps = np.mean((p_over - o_over) ** 2 + (p_under - o_under) ** 2)

    return float(rps)


def multi_class_rps(predictions: np.ndarray, outcomes: np.ndarray) -> float:
    """Calculate multi-class ranked probability score.

    Args:
        predictions: 2D array of predicted probabilities (n_samples, n_classes).
        outcomes: 2D array of one-hot encoded outcomes.

    Returns:
        Multi-class RPS score (lower is better).
    """
    predictions = np.asarray(predictions)
    outcomes = np.asarray(outcomes)

    if predictions.shape != outcomes.shape:
        raise ValueError("Predictions and outcomes must have the same shape")

    predictions = np.clip(predictions, 0.001, 0.999)
    predictions = predictions / predictions.sum(axis=1, keepdims=True)

    cum_pred = np.cumsum(predictions, axis=1)
    cum_actual = np.cumsum(outcomes, axis=1)

    rps = np.mean(np.sum((cum_pred - cum_actual) ** 2, axis=1) / (predictions.shape[1] - 1))

    return float(rps)


def compute_rps_by_market(
    predictions: np.ndarray,
    outcomes: np.ndarray,
    market_labels: list[str],
) -> dict[str, float]:
    """Compute RPS scores grouped by market.

    Args:
        predictions: Array of predicted probabilities.
        outcomes: Array of actual outcomes.
        market_labels: Labels identifying which market each prediction belongs to.

    Returns:
        Dictionary mapping market names to RPS scores.
    """
    markets = set(market_labels)
    rps_by_market = {}

    for market in markets:
        mask = [m == market for m in market_labels]
        market_preds = predictions[mask]
        market_outcomes = outcomes[mask]

        if len(market_preds) > 0:
            rps_by_market[market] = ranked_probability_score(market_preds, market_outcomes)

    return rps_by_market
