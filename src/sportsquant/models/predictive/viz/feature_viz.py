"""
Feature analysis and correlation visualization.
"""

# pylint: disable=too-many-arguments,too-many-locals

from pathlib import Path
from typing import Literal

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.figure import Figure

from sportsquant.models.predictive.viz.plot_helpers import finalize_figure


def plot_feature_importance(
    feature_names: list[str],
    importance_scores: list[float],
    *,
    title: str = "Feature Importance",
    top_n: int = 20,
    figsize: tuple[int, int] = (10, 8),
    output_path: Path | None = None,
) -> Figure:
    """
    Plot feature importance from XGBoost model.

    Args:
        feature_names: List of feature names
        importance_scores: List of importance scores (same order as names)
        title: Chart title
        top_n: Number of top features to display
        figsize: Figure size
        output_path: Optional save path

    Returns:
        Matplotlib Figure
    """
    if len(feature_names) != len(importance_scores):
        raise ValueError("feature_names and importance_scores must have same length")

    # Create DataFrame and sort
    df = pd.DataFrame({"feature": feature_names, "importance": importance_scores})
    df = df.sort_values("importance", ascending=False).head(top_n)

    fig, ax = plt.subplots(figsize=figsize)

    # Horizontal bar chart
    colors = plt.colormaps["viridis"](np.linspace(0.3, 0.9, len(df)))
    importance_vals = df["importance"].to_numpy(dtype=float, copy=False)
    ax.barh(range(len(df)), importance_vals, color=colors, alpha=0.8)

    # Add value labels
    for i, (_, row) in enumerate(df.iterrows()):
        val = float(row["importance"])
        ax.text(
            val,
            i,
            f" {val:.3f}",
            va="center",
            ha="left",
            fontsize=9,
        )

    ax.set_yticks(range(len(df)))
    ax.set_yticklabels(df["feature"].values, fontsize=10)
    ax.set_xlabel("Importance Score", fontsize=12)
    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.grid(axis="x", alpha=0.3)

    return finalize_figure(fig, output_path=output_path)


def plot_predicted_vs_actual(
    y_true: list[float] | np.ndarray,
    y_pred: list[float] | np.ndarray,
    *,
    title: str = "Predicted vs Actual PRA",
    xlabel: str = "Actual",
    ylabel: str = "Predicted",
    figsize: tuple[int, int] = (10, 10),
    output_path: Path | None = None,
) -> Figure:
    """
    Plot predicted vs actual values scatter plot with perfect prediction line.

    Args:
        y_true: True values
        y_pred: Predicted values
        title: Chart title
        xlabel: X-axis label
        ylabel: Y-axis label
        figsize: Figure size
        output_path: Optional save path

    Returns:
        Matplotlib Figure
    """
    y_true_arr = np.array(y_true)
    y_pred_arr = np.array(y_pred)

    if len(y_true_arr) != len(y_pred_arr):
        raise ValueError("y_true and y_pred must have same length")

    fig, ax = plt.subplots(figsize=figsize)

    # Scatter plot with transparency
    ax.scatter(y_true_arr, y_pred_arr, alpha=0.5, s=30, color="#2E86AB", edgecolors="none")

    # Perfect prediction line (y=x)
    min_val = min(y_true_arr.min(), y_pred_arr.min())
    max_val = max(y_true_arr.max(), y_pred_arr.max())
    ax.plot([min_val, max_val], [min_val, max_val], "r--", linewidth=2, label="Perfect Prediction")

    # Calculate R²
    try:
        from sklearn.metrics import r2_score  # pyright: ignore[reportMissingImports] # pylint: disable=import-outside-toplevel
    except ModuleNotFoundError:

        def r2_score(y_true: np.ndarray, y_pred: np.ndarray) -> float:
            ss_res = float(np.sum((y_true - y_pred) ** 2))
            ss_tot = float(np.sum((y_true - np.mean(y_true)) ** 2))
            return 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0

    r2 = r2_score(y_true_arr, y_pred_arr)
    mae = np.mean(np.abs(y_true_arr - y_pred_arr))
    rmse = np.sqrt(np.mean((y_true_arr - y_pred_arr) ** 2))

    # Add metrics text box
    metrics_text = f"R² = {r2:.3f}\nMAE = {mae:.2f}\nRMSE = {rmse:.2f}"
    ax.text(
        0.05,
        0.95,
        metrics_text,
        transform=ax.transAxes,
        fontsize=11,
        verticalalignment="top",
        bbox={"boxstyle": "round", "facecolor": "wheat", "alpha": 0.8},
    )

    ax.set_xlabel(xlabel, fontsize=12)
    ax.set_ylabel(ylabel, fontsize=12)
    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.legend(loc="lower right")
    ax.grid(True, alpha=0.3)

    # Make axes equal
    ax.set_aspect("equal", adjustable="box")

    return finalize_figure(fig, output_path=output_path)


def plot_correlation_matrix(
    features_df: pd.DataFrame,
    *,
    title: str = "Feature Correlation Matrix",
    method: Literal["pearson", "spearman", "kendall"] = "pearson",
    figsize: tuple[int, int] = (12, 10),
    output_path: Path | None = None,
) -> Figure:
    """
    Plot correlation heatmap for features.

    Args:
        features_df: DataFrame with feature columns
        title: Chart title
        method: Correlation method ('pearson', 'spearman', 'kendall')
        figsize: Figure size
        output_path: Optional save path

    Returns:
        Matplotlib Figure
    """
    # Calculate correlation matrix
    corr_matrix = features_df.corr(method=method)

    fig, ax = plt.subplots(figsize=figsize)

    # Heatmap
    sns.heatmap(
        corr_matrix,
        annot=False,
        fmt=".2f",
        cmap="coolwarm",
        center=0,
        square=True,
        linewidths=1,
        cbar_kws={"shrink": 0.8},
        ax=ax,
        vmin=-1,
        vmax=1,
    )

    ax.set_title(title, fontsize=14, fontweight="bold", pad=20)

    return finalize_figure(fig, output_path=output_path)


def plot_residuals(
    y_true: list[float] | np.ndarray,
    y_pred: list[float] | np.ndarray,
    *,
    title: str = "Residual Plot",
    figsize: tuple[int, int] = (12, 6),
    output_path: Path | None = None,
) -> Figure:
    """
    Plot residuals to diagnose model fit.

    Args:
        y_true: True values
        y_pred: Predicted values
        title: Chart title
        figsize: Figure size
        output_path: Optional save path

    Returns:
        Matplotlib Figure
    """
    y_true_arr = np.array(y_true)
    y_pred_arr = np.array(y_pred)
    residuals = y_true_arr - y_pred_arr

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=figsize)

    # Residual vs predicted scatter
    ax1.scatter(y_pred_arr, residuals, alpha=0.5, s=30, color="#2E86AB", edgecolors="none")
    ax1.axhline(y=0, color="red", linestyle="--", linewidth=2)
    ax1.set_xlabel("Predicted Values", fontsize=11)
    ax1.set_ylabel("Residuals", fontsize=11)
    ax1.set_title("Residuals vs Predicted", fontsize=12, fontweight="bold")
    ax1.grid(True, alpha=0.3)

    # Residual histogram
    ax2.hist(residuals, bins=50, alpha=0.7, color="#2E86AB", edgecolor="black")
    ax2.axvline(x=0, color="red", linestyle="--", linewidth=2)
    ax2.set_xlabel("Residual Value", fontsize=11)
    ax2.set_ylabel("Frequency", fontsize=11)
    ax2.set_title("Residual Distribution", fontsize=12, fontweight="bold")
    ax2.grid(True, alpha=0.3)

    # Add residual statistics
    mean_res = np.mean(residuals)
    std_res = np.std(residuals)
    stats_text = f"Mean: {mean_res:.3f}\nStd: {std_res:.3f}"
    ax2.text(
        0.70,
        0.95,
        stats_text,
        transform=ax2.transAxes,
        fontsize=10,
        verticalalignment="top",
        bbox={"boxstyle": "round", "facecolor": "wheat", "alpha": 0.7},
    )

    fig.suptitle(title, fontsize=14, fontweight="bold")
    return finalize_figure(fig, output_path=output_path)
