"""
SportsQuant Betting Core

Core betting module providing odds conversion, bet decision logic,
Kelly criterion calculations, model selection, validation, performance
metrics, and Ignite-based state management.
"""

from sportsquant.core.betting.engine import (
    BetDecision,
    decide_over_under,
    expected_value,
    kelly_fraction,
    record_bet_placed,
    record_bet_settled,
    record_edge_calculation,
    record_kelly_recommendation,
)
from sportsquant.core.betting.kelly import (
    AdaptiveKellyContext,
    BankrollManager,
    BankrollManagerConfig,
    EdgeCalculator,
    EdgeCalculatorConfig,
    ExposureLimits,
    KellyCalculator,
    KellyCalculatorConfig,
    KellyFloat,
)
from sportsquant.core.betting.metrics import (
    PerformanceMetrics,
    calculate_max_drawdown,
    calculate_performance_metrics,
    calculate_profit_factor,
    calculate_sharpe_ratio,
    calculate_sortino_ratio,
    calculate_streaks,
    compute_rps_by_market,
    multi_class_rps,
    ranked_probability_score,
)
from sportsquant.core.betting.odds import Odds
from sportsquant.core.betting.selection import (
    ComparisonResult,
    ComplexityAnalyzer,
    ComplexityAnalyzerConfig,
    ModelRecommendation,
    ModelSelector,
    ModelSelectorConfig,
    ReasoningParams,
)
from sportsquant.core.betting.validation import (
    CLVConfig,
    CLVTrend,
    CalibrationConfig,
    MetricsDashboardConfig,
    MetricsPriority,
    ModelValidator,
    ProbabilityCalibrator,
    WalkForwardConfig,
    WalkForwardValidator,
    WeightedCLVConfig,
    compute_edge_durability_score,
    get_edge_health_summary,
)

# Ignite client exports
from sportsquant.core.betting.ignite_client import (
    BankrollState,
    IgniteBankrollManager,
    IgniteCache,
    IgniteConfig,
    IgnitePortfolioManager,
    IgnitePositionManager,
    PortfolioState,
    Position,
)

__all__ = [
    # engine
    "BetDecision",
    "expected_value",
    "kelly_fraction",
    "decide_over_under",
    "record_bet_placed",
    "record_bet_settled",
    "record_edge_calculation",
    "record_kelly_recommendation",
    # kelly
    "KellyFloat",
    "KellyCalculatorConfig",
    "KellyCalculator",
    "AdaptiveKellyContext",
    "ExposureLimits",
    "BankrollManagerConfig",
    "BankrollManager",
    "EdgeCalculatorConfig",
    "EdgeCalculator",
    # odds
    "Odds",
    # selection
    "ModelSelectorConfig",
    "ModelSelector",
    "ComplexityAnalyzerConfig",
    "ComplexityAnalyzer",
    "ComparisonResult",
    "ModelRecommendation",
    "ReasoningParams",
    # validation
    "WalkForwardConfig",
    "CalibrationConfig",
    "CLVConfig",
    "WeightedCLVConfig",
    "WalkForwardValidator",
    "ProbabilityCalibrator",
    "CLVTracker",
    "ModelValidator",
    "MetricsPriority",
    "MetricsDashboardConfig",
    "CLVTrend",
    "compute_edge_durability_score",
    "get_edge_health_summary",
    # metrics
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
    # ignite_client
    "IgniteConfig",
    "IgniteCache",
    "BankrollState",
    "Position",
    "PortfolioState",
    "IgniteBankrollManager",
    "IgnitePositionManager",
    "IgnitePortfolioManager",
]
