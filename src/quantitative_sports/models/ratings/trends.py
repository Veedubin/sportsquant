"""
Trend Features for Time Series Analysis

Provides rolling trend, momentum, and volatility features for player statistics.

Key components:
1. Rolling slope and trend computation
2. Momentum features (short vs long-term averages)
3. Volatility and acceleration features
4. Rate of change indicators

Data Sources:
- Player stats: TimescaleDB (player_stats table)
- Game data: Kafka topic 'sports-analytics-player-stats'
- Caching: Apache Ignite for computed features

Usage:
    >>> from quantitative_sports.models.ratings.trends import TrendFeatures
    >>> features = TrendFeatures()
    >>> trends = features.compute_all_trends(df, ['PTS', 'REB', 'AST'])
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

import numpy as np
import pandas as pd
from scipy import stats


@dataclass(frozen=True)
class TrendConfig:
    """Configuration for trend feature computation.

    Attributes:
        windows: Rolling window sizes for trend computation.
        min_periods: Minimum observations required for calculation.
        trend_col: Prefix for trend column names.
        include_acceleration: Whether to compute acceleration features.
        include_volatility: Whether to compute volatility features.
    """

    windows: tuple[int, ...] = (5, 10, 20)
    min_periods: int = 3
    trend_col: str = "trend"
    include_acceleration: bool = True
    include_volatility: bool = True


@dataclass(frozen=True)
class RollingTrendConfig:
    """Configuration for rolling trend analysis.

    Attributes:
        window: Rolling window size.
        min_periods: Minimum observations required.
        order: Order of polynomial for trend (1=linear, 2=quadratic).
        robust: Whether to use robust regression (less sensitive to outliers).
    """

    window: int = 10
    min_periods: int = 3
    order: int = 1
    robust: bool = False


def compute_rolling_slope(
    series: pd.Series,
    window: int = 10,
    min_periods: int = 3,
    order: int = 1,
) -> pd.Series:
    """Compute rolling slope using linear regression.

    Args:
        series: Input time series.
        window: Rolling window size.
        min_periods: Minimum observations required.
        order: Order of polynomial (1=linear, 2=quadratic).

    Returns:
        Series with rolling slopes (trend).
    """
    if series.empty:
        return pd.Series(dtype=float)

    def rolling_slope(windowed: np.ndarray) -> float:
        if len(windowed) < min_periods or len(windowed) < 2:
            return np.nan

        x = np.arange(len(windowed))
        y = windowed

        if order == 1:
            slope, _, _, _, _ = stats.linregress(x, y)
            return slope  # type: ignore[return-value]
        coeffs = np.polyfit(x, y, min(order, len(x) - 1))
        return float(coeffs[-2]) if len(coeffs) > 1 else np.nan

    return cast(
        pd.Series,
        series.rolling(window=window, min_periods=min_periods).apply(rolling_slope, raw=True),
    )


def compute_rolling_acceleration(
    series: pd.Series,
    window: int = 10,
    min_periods: int = 3,
) -> pd.Series:
    """Compute rolling acceleration (change in slope).

    Args:
        series: Input time series.
        window: Rolling window size.
        min_periods: Minimum observations required.

    Returns:
        Series with rolling acceleration values.
    """
    slopes = compute_rolling_slope(series, window, min_periods)

    if slopes.empty:
        return pd.Series(dtype=float)

    acceleration = slopes.diff()

    return acceleration


def compute_rolling_intercept(
    series: pd.Series,
    window: int = 10,
    min_periods: int = 3,
) -> pd.Series:
    """Compute rolling intercept from linear regression.

    Args:
        series: Input time series.
        window: Rolling window size.
        min_periods: Minimum observations required.

    Returns:
        Series with rolling intercept values.
    """
    if series.empty:
        return pd.Series(dtype=float)

    def rolling_intercept(windowed: np.ndarray) -> float:
        if len(windowed) < min_periods or len(windowed) < 2:
            return np.nan

        x = np.arange(len(windowed))
        y = windowed

        _, intercept, _, _, _ = stats.linregress(x, y)
        return intercept  # type: ignore[return-value]

    return cast(
        pd.Series,
        series.rolling(window=window, min_periods=min_periods).apply(rolling_intercept, raw=True),
    )


def compute_rolling_r_squared(
    series: pd.Series,
    window: int = 10,
    min_periods: int = 3,
) -> pd.Series:
    """Compute rolling R-squared (coefficient of determination).

    Args:
        series: Input time series.
        window: Rolling window size.
        min_periods: Minimum observations required.

    Returns:
        Series with rolling R-squared values (0-1).
    """
    if series.empty:
        return pd.Series(dtype=float)

    def rolling_r_squared(windowed: np.ndarray) -> float:
        if len(windowed) < min_periods or len(windowed) < 2:
            return np.nan

        x = np.arange(len(windowed))
        y = windowed

        _, _, r_value, _, _ = stats.linregress(x, y)
        return float(np.asarray(r_value, dtype=float) ** 2)

    return cast(
        pd.Series,
        series.rolling(window=window, min_periods=min_periods).apply(rolling_r_squared, raw=True),
    )


def compute_rolling_volatility(
    series: pd.Series,
    window: int = 10,
    min_periods: int = 3,
) -> pd.Series:
    """Compute rolling volatility (standard deviation).

    Args:
        series: Input time series.
        window: Rolling window size.
        min_periods: Minimum observations required.

    Returns:
        Series with rolling volatility values.
    """
    return cast(pd.Series, series.rolling(window=window, min_periods=min_periods).std())


def compute_rolling_range(
    series: pd.Series,
    window: int = 10,
    min_periods: int = 3,
) -> pd.Series:
    """Compute rolling range (max - min).

    Args:
        series: Input time series.
        window: Rolling window size.
        min_periods: Minimum observations required.

    Returns:
        Series with rolling range values.
    """
    return (
        series.rolling(window=window, min_periods=min_periods).max()
        - series.rolling(window=window, min_periods=min_periods).min()
    )


def compute_rolling_cagr(
    series: pd.Series,
    window: int = 10,
    min_periods: int = 3,
) -> pd.Series:
    """Compute rolling compound annual growth rate.

    Args:
        series: Input time series.
        window: Rolling window size.
        min_periods: Minimum observations required.

    Returns:
        Series with rolling CAGR values.
    """
    if series.empty:
        return pd.Series(dtype=float)

    def rolling_cagr(windowed: np.ndarray) -> float:
        if len(windowed) < min_periods or windowed[0] <= 0:
            return np.nan

        end_value = windowed[-1]
        start_value = windowed[0]

        if start_value == 0:
            return np.nan

        periods = len(windowed) - 1
        if periods == 0:
            return np.nan

        cagr = (end_value / start_value) ** (1 / periods) - 1
        return cagr

    return cast(
        pd.Series,
        series.rolling(window=window, min_periods=min_periods).apply(rolling_cagr, raw=True),
    )


@dataclass(frozen=True)
class AddTrendFeaturesConfig:
    """Configuration for add_trend_features function.

    Attributes:
        windows: Window sizes for rolling calculations.
        prefix: Prefix for new column names.
        include_acceleration: Whether to compute acceleration.
        include_volatility: Whether to compute volatility.
    """

    windows: tuple[int, ...] = (5, 10, 20)
    prefix: str = "trend"
    include_acceleration: bool = True
    include_volatility: bool = True


def add_trend_features(
    df: pd.DataFrame,
    value_cols: list[str],
    config: AddTrendFeaturesConfig | None = None,
) -> pd.DataFrame:
    """Add trend, acceleration, and volatility features for specified columns.

    Args:
        df: Input DataFrame.
        value_cols: Columns to compute trend features for.
        config: Configuration for trend features.

    Returns:
        DataFrame with added trend features.
    """
    cfg = config or AddTrendFeaturesConfig()
    result = df.copy()

    for col in value_cols:
        if col not in df.columns:
            continue

        for window in cfg.windows:
            slope = compute_rolling_slope(cast(pd.Series, df[col]), window=window)
            result[f"{cfg.prefix}_{col}_slope_{window}"] = slope

            intercept = compute_rolling_intercept(cast(pd.Series, df[col]), window=window)
            result[f"{cfg.prefix}_{col}_intercept_{window}"] = intercept

            r_squared = compute_rolling_r_squared(cast(pd.Series, df[col]), window=window)
            result[f"{cfg.prefix}_{col}_r_squared_{window}"] = r_squared

            if cfg.include_acceleration:
                acceleration = compute_rolling_acceleration(cast(pd.Series, df[col]), window=window)
                result[f"{cfg.prefix}_{col}_acceleration_{window}"] = acceleration

            if cfg.include_volatility:
                volatility = compute_rolling_volatility(cast(pd.Series, df[col]), window=window)
                result[f"{cfg.prefix}_{col}_volatility_{window}"] = volatility

                rolling_range = compute_rolling_range(cast(pd.Series, df[col]), window=window)
                result[f"{cfg.prefix}_{col}_range_{window}"] = rolling_range

    return result


def compute_momentum(
    series: pd.Series,
    short_window: int = 5,
    long_window: int = 20,
) -> pd.Series:
    """Compute momentum as difference between short and long-term trends.

    Args:
        series: Input time series.
        short_window: Short-term window.
        long_window: Long-term window.

    Returns:
        Series with momentum values.
    """
    short_ma = series.rolling(window=short_window, min_periods=1).mean()
    long_ma = series.rolling(window=long_window, min_periods=1).mean()

    return short_ma - long_ma


def compute_rate_of_change(
    series: pd.Series,
    window: int = 10,
    min_periods: int = 3,
) -> pd.Series:
    """Compute rate of change (percentage change over window).

    Args:
        series: Input time series.
        window: Lookback window.
        min_periods: Minimum observations required.

    Returns:
        Series with rate of change values.
    """
    if series.empty:
        return pd.Series(dtype=float)

    def rolling_roc(windowed: np.ndarray) -> float:
        if len(windowed) < min_periods or windowed[0] == 0:
            return np.nan

        return (windowed[-1] - windowed[0]) / abs(windowed[0])

    return cast(
        pd.Series,
        series.rolling(window=window, min_periods=min_periods).apply(rolling_roc, raw=True),
    )


class TrendFeatures:
    """Computes trend-based features for time series data.

    Provides methods for computing rolling slopes, acceleration,
    volatility, and momentum features for NBA player statistics.

    All feature calculation logic is preserved from the original implementation.
    Data sources have been adapted to use TimescaleDB and Kafka instead of Redis.
    """

    def __init__(self, config: TrendConfig | None = None) -> None:
        """Initialize trend features computer.

        Args:
            config: Configuration for trend computation.
        """
        self.config = config or TrendConfig()

    def compute_all_trends(self, df: pd.DataFrame, value_cols: list[str]) -> pd.DataFrame:
        """Compute all trend features for specified columns.

        Args:
            df: Input DataFrame.
            value_cols: Columns to compute trends for.

        Returns:
            DataFrame with added trend features.
        """
        config = AddTrendFeaturesConfig(
            windows=self.config.windows,
            prefix=self.config.trend_col,
            include_acceleration=self.config.include_acceleration,
            include_volatility=self.config.include_volatility,
        )
        return add_trend_features(df, value_cols, config=config)

    def compute_momentum_features(self, df: pd.DataFrame, value_cols: list[str]) -> pd.DataFrame:
        """Compute momentum features for specified columns.

        Args:
            df: Input DataFrame.
            value_cols: Columns to compute momentum for.

        Returns:
            DataFrame with added momentum features.
        """
        result = df.copy()

        for col in value_cols:
            if col not in df.columns:
                continue

            result[f"momentum_{col}_5_20"] = compute_momentum(cast(pd.Series, df[col]), 5, 20)
            result[f"roc_{col}_5"] = compute_rate_of_change(cast(pd.Series, df[col]), window=5)
            result[f"roc_{col}_10"] = compute_rate_of_change(cast(pd.Series, df[col]), window=10)

        return result

    def extract_trend_direction(self, slope: float, threshold: float = 0.1) -> str:
        """Classify trend direction based on slope.

        Args:
            slope: Slope value from trend computation.
            threshold: Threshold for considering a trend significant.

        Returns:
            Trend direction: 'increasing', 'decreasing', or 'stable'.
        """
        if pd.isna(slope):
            return "unknown"
        if slope > threshold:
            return "increasing"
        if slope < -threshold:
            return "decreasing"
        return "stable"
