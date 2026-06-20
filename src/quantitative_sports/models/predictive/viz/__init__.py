"""Visualization module for betting strategy analysis and backtesting.

Provides comprehensive charting and visualization capabilities including:
- Equity curves and drawdown charts
- Strategy comparison visualizations
- Performance heatmaps
- Feature importance and correlation analysis
"""

from quantitative_sports.models.predictive.viz.backtest_viz import (
    plot_equity_curve,
    plot_performance_heatmap,
    plot_underwater_chart,
    plot_bet_sizing_distribution,
)

from quantitative_sports.models.predictive.viz.equity_viz import (
    plot_cumulative_pnl,
    plot_drawdown_periods,
    create_equity_dashboard,
)

from quantitative_sports.models.predictive.viz.feature_viz import (
    plot_feature_importance,
    plot_predicted_vs_actual,
    plot_correlation_matrix,
    plot_residuals,
)

from quantitative_sports.models.predictive.viz.strategy_viz import (
    plot_return_distributions,
    plot_risk_return_scatter,
    plot_strategy_comparison,
    plot_cumulative_comparison,
)

from quantitative_sports.models.predictive.viz.plot_helpers import finalize_figure

__all__ = [
    # backtest_viz
    "plot_equity_curve",
    "plot_underwater_chart",
    "plot_performance_heatmap",
    "plot_bet_sizing_distribution",
    # equity_viz
    "plot_cumulative_pnl",
    "plot_drawdown_periods",
    "create_equity_dashboard",
    # feature_viz
    "plot_feature_importance",
    "plot_predicted_vs_actual",
    "plot_correlation_matrix",
    "plot_residuals",
    # strategy_viz
    "plot_return_distributions",
    "plot_risk_return_scatter",
    "plot_strategy_comparison",
    "plot_cumulative_comparison",
    # plot_helpers
    "finalize_figure",
]
