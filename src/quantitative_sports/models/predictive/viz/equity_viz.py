"""
Equity curve and drawdown visualization.

Provides charts for tracking cumulative P&L, equity curves, and drawdown analysis.
"""

# pylint: disable=too-many-arguments

from pathlib import Path
from typing import Sequence

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.figure import Figure

from quantitative_sports.models.predictive.viz.plot_helpers import finalize_figure


def plot_cumulative_pnl(
    cumulative_pnl: Sequence[float],
    *,
    title: str = "Cumulative P&L",
    xlabel: str = "Bet Number",
    ylabel: str = "Cumulative P&L ($)",
    figsize: tuple[int, int] = (12, 6),
    output_path: Path | None = None,
) -> Figure:
    """
    Plot cumulative P&L over time.

    Args:
        cumulative_pnl: Sequence of cumulative P&L values
        title: Chart title
        xlabel: X-axis label
        ylabel: Y-axis label
        figsize: Figure size (width, height)
        output_path: Optional path to save the figure

    Returns:
        Matplotlib Figure object
    """
    fig, ax = plt.subplots(figsize=figsize)

    cum_pnl = np.array(cumulative_pnl, dtype=float)
    bet_numbers = np.arange(1, len(cum_pnl) + 1)

    # Plot cumulative P&L
    ax.plot(bet_numbers, cum_pnl, linewidth=2, color="#2E86AB", label="Cumulative P&L")

    # Add zero line
    ax.axhline(y=0, color="black", linestyle="--", linewidth=1, alpha=0.5)

    # Fill area above/below zero
    ax.fill_between(
        bet_numbers,
        cum_pnl,
        0,
        where=(cum_pnl >= 0).tolist(),
        alpha=0.3,
        color="green",
        label="Profit",
    )
    ax.fill_between(
        bet_numbers,
        cum_pnl,
        0,
        where=(cum_pnl < 0).tolist(),
        alpha=0.3,
        color="red",
        label="Loss",
    )

    # Formatting
    ax.set_xlabel(xlabel, fontsize=12)
    ax.set_ylabel(ylabel, fontsize=12)
    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.legend(loc="best")
    ax.grid(True, alpha=0.3)

    # Add stats annotation
    final_pnl = cum_pnl[-1] if len(cum_pnl) > 0 else 0
    peak_pnl = np.max(cum_pnl) if len(cum_pnl) > 0 else 0
    trough_pnl = np.min(cum_pnl) if len(cum_pnl) > 0 else 0

    stats_text = f"Final: ${final_pnl:.2f}\nPeak: ${peak_pnl:.2f}\nTrough: ${trough_pnl:.2f}"
    ax.text(
        0.02,
        0.98,
        stats_text,
        transform=ax.transAxes,
        fontsize=10,
        verticalalignment="top",
        bbox={"boxstyle": "round", "facecolor": "wheat", "alpha": 0.5},
    )

    return finalize_figure(fig, output_path=output_path)


def plot_drawdown_periods(
    cumulative_pnl: Sequence[float],
    *,
    title: str = "Drawdown Over Time",
    xlabel: str = "Bet Number",
    ylabel: str = "Drawdown ($)",
    figsize: tuple[int, int] = (12, 6),
    output_path: Path | None = None,
) -> Figure:
    """
    Plot underwater (drawdown) chart showing distance from peak equity.

    Args:
        cumulative_pnl: Sequence of cumulative P&L values
        title: Chart title
        xlabel: X-axis label
        ylabel: Y-axis label
        figsize: Figure size
        output_path: Optional path to save the figure

    Returns:
        Matplotlib Figure object
    """
    fig, ax = plt.subplots(figsize=figsize)

    cum_pnl = np.array(cumulative_pnl, dtype=float)
    bet_numbers = np.arange(1, len(cum_pnl) + 1)

    # Calculate running maximum
    running_max = np.maximum.accumulate(cum_pnl)

    # Calculate drawdown
    drawdown = running_max - cum_pnl

    # Plot drawdown
    ax.fill_between(
        bet_numbers,
        drawdown,
        0,
        alpha=0.5,
        color="red",
        label="Drawdown",
    )
    ax.plot(bet_numbers, drawdown, linewidth=2, color="darkred")

    # Add zero line
    ax.axhline(y=0, color="black", linestyle="-", linewidth=1)

    # Highlight max drawdown
    if len(drawdown) > 0:
        max_dd_idx = int(np.argmax(drawdown))
        max_dd = drawdown[max_dd_idx]
        ax.scatter(
            [max_dd_idx + 1],
            [max_dd],
            color="darkred",
            s=100,
            zorder=5,
            label=f"Max DD: ${max_dd:.2f}",
        )

    # Formatting
    ax.set_xlabel(xlabel, fontsize=12)
    ax.set_ylabel(ylabel, fontsize=12)
    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.legend(loc="best")
    ax.grid(True, alpha=0.3)
    ax.invert_yaxis()  # Drawdown is typically shown as negative going down

    return finalize_figure(fig, output_path=output_path)


def create_equity_dashboard(
    backtest_df: pd.DataFrame,
    *,
    output_dir: Path | None = None,
) -> tuple[Figure, Figure]:
    """
    Create a complete equity analysis dashboard with multiple charts.

    Args:
        backtest_df: DataFrame with backtest results including 'cumulative_pnl' column
        output_dir: Optional directory to save figures

    Returns:
        Tuple of (equity_curve_fig, drawdown_fig)
    """
    if "cumulative_pnl" not in backtest_df.columns:
        raise ValueError("backtest_df must contain 'cumulative_pnl' column")

    cum_pnl = backtest_df["cumulative_pnl"].to_numpy(dtype=float, copy=False)

    # Create equity curve
    equity_fig = plot_cumulative_pnl(
        cum_pnl.tolist(),
        output_path=output_dir / "equity_curve.png" if output_dir else None,
    )

    # Create drawdown chart
    drawdown_fig = plot_drawdown_periods(
        cum_pnl.tolist(),
        output_path=output_dir / "drawdown.png" if output_dir else None,
    )

    return equity_fig, drawdown_fig
