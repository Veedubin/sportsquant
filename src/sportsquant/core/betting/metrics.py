"""
Advanced performance metrics for betting strategy evaluation.

Provides comprehensive risk-adjusted metrics including Sharpe ratio, Sortino ratio,
maximum drawdown, win streaks, and other performance analytics.

Adapted from sports_analytics.betting.metrics
"""

# pylint: disable=too-many-instance-attributes,too-many-locals,duplicate-code

from dataclasses import dataclass
from typing import Sequence

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class PerformanceMetrics:
    """Comprehensive performance metrics for betting strategies."""

    # Basic metrics
    total_bets: int
    win_rate: float
    total_pnl: float
    mean_pnl_per_bet: float
    mean_ev_per_bet: float

    # Risk-adjusted metrics
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    profit_factor: float

    # Drawdown metrics
    max_drawdown: float
    max_drawdown_pct: float
    max_drawdown_duration: int  # Number of bets

    # Streak metrics
    max_win_streak: int
    max_loss_streak: int
    current_streak: int  # Positive for wins, negative for losses
    current_streak_type: str  # "win" or "loss"

    # Distribution metrics
    pnl_std: float
    pnl_skewness: float
    pnl_kurtosis: float

    # Return metrics
    total_return_pct: float  # Total P&L as % of total stakes
    return_on_risk: float  # Total return / max drawdown

    def to_dict(self) -> dict[str, float | int | str]:
        """Convert metrics to dictionary for serialization."""
        return {
            "total_bets": self.total_bets,
            "win_rate": self.win_rate,
            "total_pnl": self.total_pnl,
            "mean_pnl_per_bet": self.mean_pnl_per_bet,
            "mean_ev_per_bet": self.mean_ev_per_bet,
            "sharpe_ratio": self.sharpe_ratio,
            "sortino_ratio": self.sortino_ratio,
            "calmar_ratio": self.calmar_ratio,
            "profit_factor": self.profit_factor,
            "max_drawdown": self.max_drawdown,
            "max_drawdown_pct": self.max_drawdown_pct,
            "max_drawdown_duration": self.max_drawdown_duration,
            "max_win_streak": self.max_win_streak,
            "max_loss_streak": self.max_loss_streak,
            "current_streak": self.current_streak,
            "current_streak_type": self.current_streak_type,
            "pnl_std": self.pnl_std,
            "pnl_skewness": self.pnl_skewness,
            "pnl_kurtosis": self.pnl_kurtosis,
            "total_return_pct": self.total_return_pct,
            "return_on_risk": self.return_on_risk,
        }


def calculate_sharpe_ratio(
    returns: Sequence[float] | np.ndarray, risk_free_rate: float = 0.0, periods_per_year: int = 252
) -> float:
    """
    Calculate annualized Sharpe ratio.

    Args:
        returns: Sequence of per-period returns (e.g., per-bet P&L)
        risk_free_rate: Annual risk-free rate (default 0)
        periods_per_year: Number of periods per year for annualization

    Returns:
        Sharpe ratio (annualized)
    """
    if len(returns) == 0:
        return 0.0

    returns_array = np.asarray(returns, dtype=float)
    mean_return = float(np.mean(returns_array))
    std_return = float(np.std(returns_array, ddof=1))

    if std_return == 0:
        return 0.0

    # Annualize
    annual_return = mean_return * periods_per_year
    annual_std = std_return * np.sqrt(periods_per_year)

    sharpe = (annual_return - risk_free_rate) / annual_std
    return float(sharpe)


def calculate_sortino_ratio(
    returns: Sequence[float] | np.ndarray, risk_free_rate: float = 0.0, periods_per_year: int = 252
) -> float:
    """
    Calculate annualized Sortino ratio (downside risk only).

    Args:
        returns: Sequence of per-period returns
        risk_free_rate: Annual risk-free rate (default 0)
        periods_per_year: Number of periods per year for annualization

    Returns:
        Sortino ratio (annualized)
    """
    if len(returns) == 0:
        return 0.0

    returns_array = np.asarray(returns, dtype=float)
    mean_return = float(np.mean(returns_array))

    # Downside deviation (only negative returns)
    downside_returns = returns_array[returns_array < 0]
    if len(downside_returns) == 0:
        # No downside - infinite Sortino, cap at large number
        return 999.0

    downside_std = float(np.std(downside_returns, ddof=1))
    if downside_std == 0:
        return 0.0

    # Annualize
    annual_return = mean_return * periods_per_year
    annual_downside_std = downside_std * np.sqrt(periods_per_year)

    sortino = (annual_return - risk_free_rate) / annual_downside_std
    return float(sortino)


def calculate_max_drawdown(
    cumulative_pnl: Sequence[float] | np.ndarray,
) -> tuple[float, float, int]:
    """
    Calculate maximum drawdown from cumulative P&L series.

    Args:
        cumulative_pnl: Cumulative P&L over time

    Returns:
        Tuple of (max_drawdown_absolute, max_drawdown_pct, duration_in_periods)
    """
    if len(cumulative_pnl) == 0:
        return 0.0, 0.0, 0

    cumulative = np.asarray(cumulative_pnl, dtype=float)

    # Running maximum
    running_max = np.maximum.accumulate(cumulative)

    # Drawdown at each point
    drawdown = running_max - cumulative

    # Max drawdown (absolute)
    max_dd = float(np.max(drawdown))

    # Max drawdown percentage (relative to peak)
    max_dd_idx = int(np.argmax(drawdown))
    peak_value = running_max[max_dd_idx]
    if peak_value > 0:
        max_dd_pct = (max_dd / peak_value) * 100.0
    else:
        max_dd_pct = 0.0

    # Duration: count how long it took to recover from max drawdown
    # Find when drawdown started and when it recovered
    duration = 0
    if max_dd > 0:
        # Find the peak before max drawdown
        peak_idx = max_dd_idx
        while peak_idx > 0 and cumulative[peak_idx - 1] >= cumulative[peak_idx]:
            peak_idx -= 1

        # Find recovery point (when cumulative >= peak again)
        recovery_idx = max_dd_idx
        while (
            recovery_idx < len(cumulative) - 1
            and cumulative[recovery_idx] < running_max[max_dd_idx]
        ):
            recovery_idx += 1

        duration = recovery_idx - peak_idx

    return max_dd, max_dd_pct, duration


def calculate_profit_factor(pnl_series: Sequence[float] | np.ndarray) -> float:
    """
    Calculate profit factor (gross profit / gross loss).

    Args:
        pnl_series: Series of per-bet P&L values

    Returns:
        Profit factor (ratio of wins to losses)
    """
    if len(pnl_series) == 0:
        return 0.0

    pnl_array = np.asarray(pnl_series, dtype=float)

    gross_profit = float(np.sum(pnl_array[pnl_array > 0]))
    gross_loss = float(np.abs(np.sum(pnl_array[pnl_array < 0])))

    if gross_loss == 0:
        # No losses - infinite profit factor, cap at large number
        return 999.0 if gross_profit > 0 else 0.0

    return gross_profit / gross_loss


def _update_streak(current: int, outcome: bool) -> tuple[int, int]:
    """Update current streak and return (new_current, streak_length).

    Args:
        current: Current streak value (positive for wins, negative for losses)
        outcome: The outcome (True = win, False = loss)

    Returns:
        Tuple of (new_current_streak, streak_length_for_max)
    """
    if outcome:  # Win
        if current > 0:
            new_current = current + 1
        else:
            new_current = 1
        streak_length = new_current
    else:  # Loss
        if current < 0:
            new_current = current - 1
        else:
            new_current = -1
        streak_length = abs(new_current)
    return new_current, streak_length


def _get_streak_type(current: int) -> str:
    """Get the streak type from current streak value.

    Args:
        current: Current streak value (positive for wins, negative for losses)

    Returns:
        Streak type string: "win", "loss", or "none"
    """
    if current == 0:
        return "none"
    elif current > 0:
        return "win"
    else:
        return "loss"


def calculate_streaks(outcomes: Sequence[bool] | np.ndarray) -> tuple[int, int, int, str]:
    """
    Calculate win/loss streaks.

    Args:
        outcomes: Boolean sequence (True = win, False = loss)

    Returns:
        Tuple of (max_win_streak, max_loss_streak, current_streak, current_type)
    """
    if len(outcomes) == 0:
        return 0, 0, 0, "none"

    max_win = 0
    max_loss = 0
    current = 0

    for outcome in outcomes:
        current, streak_length = _update_streak(current, outcome)
        if outcome:
            max_win = max(max_win, streak_length)
        else:
            max_loss = max(max_loss, streak_length)

    current_type = _get_streak_type(current)

    return max_win, max_loss, current, current_type


def calculate_performance_metrics(
    pnl_series: pd.Series,
    ev_series: pd.Series,
    outcome_series: pd.Series,
    stake_series: pd.Series | None = None,
    risk_free_rate: float = 0.0,
) -> PerformanceMetrics:
    """
    Calculate comprehensive performance metrics from backtest results.

    Args:
        pnl_series: Per-bet P&L (profit/loss per $1 or actual stake)
        ev_series: Per-bet expected value
        outcome_series: Per-bet outcomes (True for win, False for loss)
        stake_series: Optional per-bet stakes (for return calculation)
        risk_free_rate: Annual risk-free rate for Sharpe/Sortino

    Returns:
        PerformanceMetrics object with all calculated metrics
    """
    # Convert to numpy arrays
    pnl = np.asarray(pnl_series.values, dtype=float)
    ev = np.asarray(ev_series.values, dtype=float)
    outcomes = np.asarray(outcome_series.values, dtype=bool)

    # Basic metrics
    total_bets = len(pnl)
    if total_bets == 0:
        # Return zero metrics for empty series
        return PerformanceMetrics(
            total_bets=0,
            win_rate=0.0,
            total_pnl=0.0,
            mean_pnl_per_bet=0.0,
            mean_ev_per_bet=0.0,
            sharpe_ratio=0.0,
            sortino_ratio=0.0,
            calmar_ratio=0.0,
            profit_factor=0.0,
            max_drawdown=0.0,
            max_drawdown_pct=0.0,
            max_drawdown_duration=0,
            max_win_streak=0,
            max_loss_streak=0,
            current_streak=0,
            current_streak_type="none",
            pnl_std=0.0,
            pnl_skewness=0.0,
            pnl_kurtosis=0.0,
            total_return_pct=0.0,
            return_on_risk=0.0,
        )

    win_rate = float(np.mean(outcomes))
    total_pnl = float(np.sum(pnl))
    mean_pnl = float(np.mean(pnl))
    mean_ev = float(np.mean(ev))

    # Risk-adjusted metrics
    sharpe = calculate_sharpe_ratio(pnl, risk_free_rate)
    sortino = calculate_sortino_ratio(pnl, risk_free_rate)

    # Drawdown metrics
    cumulative_pnl = np.cumsum(pnl)
    max_dd, max_dd_pct, dd_duration = calculate_max_drawdown(cumulative_pnl)

    # Calmar ratio: annual return / max drawdown
    annual_return = mean_pnl * 252  # Assume daily betting
    calmar = annual_return / max_dd if max_dd > 0 else 0.0

    # Profit factor
    profit_factor = calculate_profit_factor(pnl)

    # Streaks
    max_win_streak, max_loss_streak, current_streak, streak_type = calculate_streaks(outcomes)

    # Distribution metrics
    pnl_array = np.asarray(pnl, dtype=float)
    pnl_std = float(np.std(pnl_array, ddof=1))
    pnl_skewness = float(pd.Series(pnl).skew()) if len(pnl) > 2 else 0.0
    pnl_kurtosis = float(pd.Series(pnl).kurtosis()) if len(pnl) > 3 else 0.0

    # Return metrics
    if stake_series is not None and len(stake_series) > 0:
        total_stakes = float(stake_series.sum())
        total_return_pct = (total_pnl / total_stakes * 100.0) if total_stakes > 0 else 0.0
    else:
        # Assume unit stakes
        total_return_pct = (total_pnl / total_bets * 100.0) if total_bets > 0 else 0.0

    return_on_risk = total_pnl / max_dd if max_dd > 0 else 0.0

    return PerformanceMetrics(
        total_bets=total_bets,
        win_rate=win_rate,
        total_pnl=total_pnl,
        mean_pnl_per_bet=mean_pnl,
        mean_ev_per_bet=mean_ev,
        sharpe_ratio=sharpe,
        sortino_ratio=sortino,
        calmar_ratio=calmar,
        profit_factor=profit_factor,
        max_drawdown=max_dd,
        max_drawdown_pct=max_dd_pct,
        max_drawdown_duration=dd_duration,
        max_win_streak=max_win_streak,
        max_loss_streak=max_loss_streak,
        current_streak=current_streak,
        current_streak_type=streak_type,
        pnl_std=pnl_std,
        pnl_skewness=pnl_skewness,
        pnl_kurtosis=pnl_kurtosis,
        total_return_pct=total_return_pct,
        return_on_risk=return_on_risk,
    )


def ranked_probability_score(predictions: np.ndarray, outcomes: np.ndarray) -> float:
    """Compute Ranked Probability Score (RPS) for binary outcomes.

    RPS measures how well predicted probabilities match the actual outcome
    distribution. Lower is better, with 0 being perfect.

    For binary outcomes (over/under), RPS simplifies to:
    RPS = (P(over) - O)^2 + (P(under) - U)^2

    Where O = 1 if over hit, 0 otherwise and U = 1 - O.

    Args:
        predictions: Predicted probabilities for over (shape: n_samples,)
        outcomes: Actual outcomes (1 = over, 0 = under) (shape: n_samples,)

    Returns:
        RPS value (lower is better, 0 = perfect)
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
    """Compute RPS for multi-class (more than 2 outcomes).

    For NBA props, this could be used for markets with multiple lines
    (e.g., different point totals) or for comparing across markets.

    Args:
        predictions: Predicted probabilities (shape: n_samples, n_classes)
        outcomes: One-hot encoded outcomes (shape: n_samples, n_classes)

    Returns:
        Multi-class RPS value
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
    """Compute RPS broken down by market.

    Args:
        predictions: Predicted probabilities
        outcomes: Actual outcomes
        market_labels: Market labels for each prediction

    Returns:
        Dictionary mapping market to RPS value
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


__all__ = [
    "PerformanceMetrics",
    "calculate_sharpe_ratio",
    "calculate_sortino_ratio",
    "calculate_max_drawdown",
    "calculate_profit_factor",
    "calculate_streaks",
    "calculate_performance_metrics",
    "ranked_probability_score",
    "multi_class_rps",
    "compute_rps_by_market",
]
