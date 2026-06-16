"""
Backtest-specific visualizations including equity curves, heatmaps, and performance analysis.
"""

# pylint: disable=too-many-arguments

from pathlib import Path
from typing import cast

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.figure import Figure

from sportsquant.models.predictive.viz.plot_helpers import finalize_figure


def plot_equity_curve(
    backtest_df: pd.DataFrame,
    *,
    title: str = "Equity Curve",
    figsize: tuple[int, int] = (14, 7),
    output_path: Path | None = None,
) -> Figure:
    """
    Plot comprehensive equity curve with drawdown visualization.

    Args:
        backtest_df: Backtest DataFrame with 'cumulative_pnl' column
        title: Chart title
        figsize: Figure size
        output_path: Optional save path

    Returns:
        Matplotlib Figure
    """
    if "cumulative_pnl" not in backtest_df.columns:
        raise ValueError("backtest_df must contain 'cumulative_pnl' column")

    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=figsize, sharex=True, gridspec_kw={"height_ratios": [2, 1]}
    )

    cum_pnl = backtest_df["cumulative_pnl"].to_numpy(dtype=float, copy=False)
    bet_numbers = np.arange(1, len(cum_pnl) + 1)

    # Top plot: Cumulative P&L
    ax1.plot(bet_numbers, cum_pnl, linewidth=2, color="#2E86AB")
    ax1.fill_between(bet_numbers, cum_pnl, 0, where=(cum_pnl >= 0), alpha=0.3, color="green")
    ax1.fill_between(bet_numbers, cum_pnl, 0, where=(cum_pnl < 0), alpha=0.3, color="red")
    ax1.axhline(y=0, color="black", linestyle="--", linewidth=1, alpha=0.5)
    ax1.set_ylabel("Cumulative P&L ($)", fontsize=12)
    ax1.set_title(title, fontsize=14, fontweight="bold")
    ax1.grid(True, alpha=0.3)

    # Bottom plot: Underwater (drawdown) chart
    running_max = np.maximum.accumulate(cum_pnl)
    drawdown = running_max - cum_pnl
    drawdown_pct = np.where(running_max > 0, (drawdown / running_max) * 100, 0)

    ax2.fill_between(bet_numbers, -drawdown_pct, 0, alpha=0.5, color="red")
    ax2.plot(bet_numbers, -drawdown_pct, linewidth=1.5, color="darkred")
    ax2.axhline(y=0, color="black", linestyle="-", linewidth=1)
    ax2.set_xlabel("Bet Number", fontsize=12)
    ax2.set_ylabel("Drawdown (%)", fontsize=12)
    ax2.grid(True, alpha=0.3)

    return finalize_figure(fig, output_path=output_path)


def plot_underwater_chart(
    backtest_df: pd.DataFrame,
    *,
    title: str = "Underwater Chart (Drawdown %)",
    figsize: tuple[int, int] = (12, 5),
    output_path: Path | None = None,
) -> Figure:
    """
    Plot underwater chart showing percentage drawdown from peak.

    Args:
        backtest_df: Backtest DataFrame
        title: Chart title
        figsize: Figure size
        output_path: Optional save path

    Returns:
        Matplotlib Figure
    """
    if "cumulative_pnl" not in backtest_df.columns:
        raise ValueError("backtest_df must contain 'cumulative_pnl' column")

    fig, ax = plt.subplots(figsize=figsize)

    cum_pnl = backtest_df["cumulative_pnl"].to_numpy(dtype=float, copy=False)
    running_max = np.maximum.accumulate(cum_pnl)
    drawdown_pct = np.where(running_max > 0, ((running_max - cum_pnl) / running_max) * 100, 0)

    bet_numbers = np.arange(1, len(cum_pnl) + 1)

    ax.fill_between(bet_numbers, -drawdown_pct, 0, alpha=0.6, color="#E63946")
    ax.plot(bet_numbers, -drawdown_pct, linewidth=2, color="#D62828")
    ax.axhline(y=0, color="black", linestyle="-", linewidth=1.5)

    # Highlight max drawdown
    max_dd_pct = np.max(drawdown_pct)
    max_dd_idx = int(np.argmax(drawdown_pct))
    ax.scatter([max_dd_idx + 1], [-max_dd_pct], color="darkred", s=150, zorder=5, marker="v")
    ax.annotate(
        f"Max DD: {max_dd_pct:.1f}%",
        xy=(max_dd_idx + 1, -max_dd_pct),
        xytext=(10, 10),
        textcoords="offset points",
        fontsize=10,
        bbox={"boxstyle": "round,pad=0.5", "facecolor": "yellow", "alpha": 0.7},
        arrowprops={"arrowstyle": "->", "color": "black"},
    )

    ax.set_xlabel("Bet Number", fontsize=12)
    ax.set_ylabel("Drawdown (%)", fontsize=12)
    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.grid(True, alpha=0.3)

    return finalize_figure(fig, output_path=output_path)


def plot_performance_heatmap(  # pylint: disable=too-many-locals
    backtest_df: pd.DataFrame,
    *,
    metric: str = "pnl_1",
    group_by: str = "player_name",
    agg_func: str = "mean",
    title: str | None = None,
    figsize: tuple[int, int] = (12, 8),
    output_path: Path | None = None,
) -> Figure:
    """
    Plot performance heatmap grouped by a categorical variable.

    Args:
        backtest_df: Backtest DataFrame
        metric: Column to aggregate (default 'pnl_1')
        group_by: Column to group by (e.g., 'player_name', 'opp_team_abbr')
        agg_func: Aggregation function ('mean', 'sum', 'count')
        title: Chart title
        figsize: Figure size
        output_path: Optional save path

    Returns:
        Matplotlib Figure
    """
    if metric not in backtest_df.columns:
        raise ValueError(f"Metric '{metric}' not found in backtest_df")
    if group_by not in backtest_df.columns:
        raise ValueError(f"Group_by column '{group_by}' not found in backtest_df")

    # Aggregate data
    agg_series = cast(pd.Series, backtest_df.groupby(group_by)[metric].agg(agg_func))
    agg_data = agg_series.sort_values(ascending=False)

    # Limit to top 30 for readability
    if len(agg_data) > 30:
        agg_data = agg_data.head(30)

    fig, ax = plt.subplots(figsize=figsize)

    # Create horizontal bar chart with color mapping
    values = agg_data.to_numpy(dtype=float, copy=False)
    colors = ["green" if val > 0 else "red" for val in values]
    ax.barh(range(len(agg_data)), values, color=colors, alpha=0.7)

    # Add value labels
    for i, (_, val) in enumerate(agg_data.items()):
        val_f = float(val)
        label = f"{val_f:.2f}"
        ax.text(val_f, i, label, va="center", ha="left" if val_f > 0 else "right", fontsize=9)

    ax.set_yticks(range(len(agg_data)))
    ax.set_yticklabels(agg_data.index, fontsize=10)
    ax.axvline(x=0, color="black", linestyle="-", linewidth=1.5)
    ax.set_xlabel(f"{metric.upper()} ({agg_func})", fontsize=12)

    if title is None:
        title = f"Performance by {group_by.replace('_', ' ').title()}"
    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.grid(axis="x", alpha=0.3)

    return finalize_figure(fig, output_path=output_path)


def plot_bet_sizing_distribution(
    backtest_df: pd.DataFrame,
    *,
    title: str = "Kelly Fraction Distribution",
    figsize: tuple[int, int] = (10, 6),
    output_path: Path | None = None,
) -> Figure:
    """
    Plot distribution of Kelly fractions (bet sizes).

    Args:
        backtest_df: Backtest DataFrame with 'kelly_fraction' column
        title: Chart title
        figsize: Figure size
        output_path: Optional save path

    Returns:
        Matplotlib Figure
    """
    if "kelly_fraction" not in backtest_df.columns:
        raise ValueError("backtest_df must contain 'kelly_fraction' column")

    fig, ax = plt.subplots(figsize=figsize)

    kelly = backtest_df["kelly_fraction"].to_numpy(dtype=float, copy=False)

    # Histogram
    ax.hist(kelly, bins=50, alpha=0.7, color="#2E86AB", edgecolor="black")

    # Add vertical lines for statistics
    mean_kelly = float(np.mean(kelly))
    median_kelly = float(np.median(kelly))

    ax.axvline(
        mean_kelly, color="red", linestyle="--", linewidth=2, label=f"Mean: {mean_kelly:.3f}"
    )
    ax.axvline(
        median_kelly,
        color="orange",
        linestyle="--",
        linewidth=2,
        label=f"Median: {median_kelly:.3f}",
    )

    ax.set_xlabel("Kelly Fraction", fontsize=12)
    ax.set_ylabel("Frequency", fontsize=12)
    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.legend()
    ax.grid(True, alpha=0.3)

    return finalize_figure(fig, output_path=output_path)
