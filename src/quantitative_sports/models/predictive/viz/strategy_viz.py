"""
Strategy comparison and multi-strategy visualization.
"""

# pylint: disable=too-many-arguments,too-many-locals

from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.figure import Figure

from quantitative_sports.models.predictive.viz.plot_helpers import finalize_figure


def plot_strategy_comparison(
    strategies_metrics: dict[str, dict[str, Any]],
    *,
    metrics_to_plot: list[str] | None = None,
    title: str = "Strategy Performance Comparison",
    figsize: tuple[int, int] = (14, 8),
    output_path: Path | None = None,
) -> Figure:
    """
    Plot side-by-side comparison of multiple strategies.

    Args:
        strategies_metrics: Dict mapping strategy names to their metrics dicts
        metrics_to_plot: List of metric keys to include (None = use defaults)
        title: Chart title
        figsize: Figure size
        output_path: Optional save path

    Returns:
        Matplotlib Figure
    """
    if not strategies_metrics:
        raise ValueError("strategies_metrics cannot be empty")

    # Default metrics to compare
    if metrics_to_plot is None:
        metrics_to_plot = [
            "total_pnl",
            "win_rate",
            "sharpe_ratio",
            "sortino_ratio",
            "max_drawdown",
            "profit_factor",
        ]

    # Build comparison DataFrame
    comparison_data = []
    for strategy_name, metrics in strategies_metrics.items():
        row: dict[str, float | str] = {"strategy": strategy_name}
        for metric in metrics_to_plot:
            if metric in metrics:
                row[metric] = metrics[metric]
            else:
                row[metric] = 0.0
        comparison_data.append(row)

    df = pd.DataFrame(comparison_data)

    # Create subplots for each metric
    n_metrics = len(metrics_to_plot)
    n_cols = 3
    n_rows = (n_metrics + n_cols - 1) // n_cols

    fig, axes = plt.subplots(n_rows, n_cols, figsize=figsize)
    axes = axes.flatten() if n_metrics > 1 else [axes]

    for idx, metric in enumerate(metrics_to_plot):
        ax = axes[idx]

        # Bar chart for each metric
        strategies = df["strategy"].values
        values = df[metric].values

        colors = plt.colormaps["viridis"](np.linspace(0, 1, len(strategies)))
        bars = ax.bar(range(len(strategies)), values, color=colors, alpha=0.8)

        # Add value labels on bars
        for bar_item, val in zip(bars, values):
            height = bar_item.get_height()
            ax.text(
                bar_item.get_x() + bar_item.get_width() / 2.0,
                height,
                f"{val:.2f}",
                ha="center",
                va="bottom" if val >= 0 else "top",
                fontsize=9,
            )

        ax.set_xticks(range(len(strategies)))
        ax.set_xticklabels(strategies, rotation=45, ha="right", fontsize=9)
        ax.set_title(metric.replace("_", " ").title(), fontsize=11, fontweight="bold")
        ax.grid(axis="y", alpha=0.3)
        ax.axhline(y=0, color="black", linestyle="-", linewidth=0.8)

    # Hide extra subplots
    for idx in range(n_metrics, len(axes)):
        axes[idx].set_visible(False)

    fig.suptitle(title, fontsize=16, fontweight="bold", y=1.00)
    return finalize_figure(fig, output_path=output_path)


def plot_return_distributions(
    strategies_returns: dict[str, list[float]],
    *,
    title: str = "Return Distributions by Strategy",
    figsize: tuple[int, int] = (12, 6),
    output_path: Path | None = None,
) -> Figure:
    """
    Plot return distributions for multiple strategies using violin or box plots.

    Args:
        strategies_returns: Dict mapping strategy names to lists of per-bet returns
        title: Chart title
        figsize: Figure size
        output_path: Optional save path

    Returns:
        Matplotlib Figure
    """
    if not strategies_returns:
        raise ValueError("strategies_returns cannot be empty")

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=figsize)

    # Prepare data for seaborn
    data_for_plot = []
    for strategy, returns in strategies_returns.items():
        for ret in returns:
            data_for_plot.append({"strategy": strategy, "return": ret})

    df = pd.DataFrame(data_for_plot)

    # Violin plot
    sns.violinplot(data=df, x="strategy", y="return", ax=ax1, palette="Set2")
    ax1.axhline(y=0, color="black", linestyle="--", linewidth=1)
    ax1.set_title("Violin Plot", fontsize=12, fontweight="bold")
    ax1.set_xlabel("Strategy", fontsize=11)
    ax1.set_ylabel("Per-Bet Return ($)", fontsize=11)
    ax1.tick_params(axis="x", rotation=45)
    ax1.grid(axis="y", alpha=0.3)

    # Box plot
    sns.boxplot(data=df, x="strategy", y="return", ax=ax2, palette="Set3")
    ax2.axhline(y=0, color="black", linestyle="--", linewidth=1)
    ax2.set_title("Box Plot", fontsize=12, fontweight="bold")
    ax2.set_xlabel("Strategy", fontsize=11)
    ax2.set_ylabel("Per-Bet Return ($)", fontsize=11)
    ax2.tick_params(axis="x", rotation=45)
    ax2.grid(axis="y", alpha=0.3)

    fig.suptitle(title, fontsize=14, fontweight="bold")
    return finalize_figure(fig, output_path=output_path)


def plot_risk_return_scatter(
    strategies_metrics: dict[str, dict[str, Any]],
    *,
    risk_metric: str = "max_drawdown",
    return_metric: str = "total_pnl",
    size_metric: str = "total_bets",
    title: str = "Risk vs Return by Strategy",
    figsize: tuple[int, int] = (10, 7),
    output_path: Path | None = None,
) -> Figure:
    """
    Plot risk-return scatter plot for strategy comparison.

    Args:
        strategies_metrics: Dict mapping strategy names to metrics
        risk_metric: Metric to use for x-axis (risk)
        return_metric: Metric to use for y-axis (return)
        size_metric: Metric to use for bubble size
        title: Chart title
        figsize: Figure size
        output_path: Optional save path

    Returns:
        Matplotlib Figure
    """
    if not strategies_metrics:
        raise ValueError("strategies_metrics cannot be empty")

    fig, ax = plt.subplots(figsize=figsize)

    # Extract data
    strategies = []
    risks = []
    returns = []
    sizes = []

    for strategy, metrics in strategies_metrics.items():
        strategies.append(strategy)
        risks.append(metrics.get(risk_metric, 0.0))
        returns.append(metrics.get(return_metric, 0.0))
        sizes.append(metrics.get(size_metric, 100))

    # Normalize sizes for bubble chart
    size_scale = 100
    if max(sizes) > 0:
        normalized_sizes = [size_scale * (s / max(sizes)) for s in sizes]
    else:
        normalized_sizes = [size_scale] * len(sizes)

    # Scatter plot
    colors = plt.colormaps["tab10"](np.linspace(0, 1, len(strategies)))
    for i, (strat, risk, ret, size) in enumerate(zip(strategies, risks, returns, normalized_sizes)):
        ax.scatter(
            risk, ret, s=size * 3, alpha=0.6, color=colors[i], edgecolors="black", linewidth=1.5
        )
        ax.annotate(
            strat,
            xy=(risk, ret),
            xytext=(5, 5),
            textcoords="offset points",
            fontsize=10,
            fontweight="bold",
        )

    # Add quadrant lines
    if len(risks) > 0 and len(returns) > 0:
        median_risk = np.median(risks)
        median_return = np.median(returns)
        ax.axvline(median_risk, color="gray", linestyle="--", alpha=0.5, linewidth=1)
        ax.axhline(median_return, color="gray", linestyle="--", alpha=0.5, linewidth=1)

    ax.set_xlabel(risk_metric.replace("_", " ").title(), fontsize=12)
    ax.set_ylabel(return_metric.replace("_", " ").title(), fontsize=12)
    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.grid(True, alpha=0.3)

    # Add legend for bubble size
    if size_metric:
        size_label = f"Bubble size = {size_metric.replace('_', ' ').title()}"
        ax.text(
            0.02,
            0.98,
            size_label,
            transform=ax.transAxes,
            fontsize=10,
            verticalalignment="top",
            bbox={"boxstyle": "round", "facecolor": "lightblue", "alpha": 0.5},
        )

    return finalize_figure(fig, output_path=output_path)


def plot_cumulative_comparison(
    strategies_cumulative: dict[str, list[float]],
    *,
    title: str = "Cumulative P&L Comparison",
    xlabel: str = "Bet Number",
    ylabel: str = "Cumulative P&L ($)",
    figsize: tuple[int, int] = (14, 7),
    output_path: Path | None = None,
) -> Figure:
    """
    Plot cumulative P&L curves for multiple strategies on the same chart.

    Args:
        strategies_cumulative: Dict mapping strategy names to cumulative P&L lists
        title: Chart title
        xlabel: X-axis label
        ylabel: Y-axis label
        figsize: Figure size
        output_path: Optional save path

    Returns:
        Matplotlib Figure
    """
    if not strategies_cumulative:
        raise ValueError("strategies_cumulative cannot be empty")

    fig, ax = plt.subplots(figsize=figsize)

    colors = plt.colormaps["tab10"](np.linspace(0, 1, len(strategies_cumulative)))

    for i, (strategy, cum_pnl) in enumerate(strategies_cumulative.items()):
        bet_numbers = np.arange(1, len(cum_pnl) + 1)
        ax.plot(bet_numbers, cum_pnl, linewidth=2, label=strategy, color=colors[i])

    ax.axhline(y=0, color="black", linestyle="--", linewidth=1, alpha=0.5)
    ax.set_xlabel(xlabel, fontsize=12)
    ax.set_ylabel(ylabel, fontsize=12)
    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.legend(loc="best", fontsize=11)
    ax.grid(True, alpha=0.3)

    return finalize_figure(fig, output_path=output_path)
