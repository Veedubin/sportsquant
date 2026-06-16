"""Betting metrics and performance analysis utilities.

This package provides comprehensive tools for analyzing betting performance,
including:
- Performance metrics (Sharpe, Sortino, max drawdown, streaks)
- Statistical significance testing and confidence intervals
- Market analysis (line movements, steam moves, multi-book correlations)
- Multi-market arbitrage and line shopping
- Odds conversion and implied probability calculations
- Ignite-based odds caching with TTL and credit tracking
"""

from .betting_metrics import (
    CoreMetrics,
    RiskAdjustedMetrics,
    DrawdownMetrics,
    StreakMetrics,
    DistributionMetrics,
    ReturnMetrics,
    PerformanceMetrics,
    calculate_sharpe_ratio,
    calculate_sortino_ratio,
    calculate_max_drawdown,
    calculate_profit_factor,
    calculate_streaks,
    calculate_performance_metrics,
    ranked_probability_score,
    multi_class_rps,
    compute_rps_by_market,
)
from .statistics import (
    BetRecord,
    HypothesisResult,
    SignificanceTester,
    ConfidenceIntervalCalculator,
)
from .market_analysis import MarketAnalyzer, MarketAnalysisConfig
from .multi_market import (
    MultiMarketConfig,
    MultiMarketBettor,
    EuropeanBookConfig,
    EuropeanBookIntegrator,
    BestLine,
    ArbitrageResult,
    PotentialBet,
    Allocation,
    ComparisonResult,
    EuropeanOdds,
)
from .odds_metrics import Odds
from .implied_odds import ImpliedOddsCalculator
from .ignite_odds_cache import (
    IgniteOddsCacheConfig,
    IgniteOddsCache,
    CreditBudgetMonitor,
    create_ignite_odds_cache,
    create_credit_monitor,
)

__all__ = [
    # Performance metrics
    "CoreMetrics",
    "RiskAdjustedMetrics",
    "DrawdownMetrics",
    "StreakMetrics",
    "DistributionMetrics",
    "ReturnMetrics",
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
    # Statistics
    "BetRecord",
    "HypothesisResult",
    "SignificanceTester",
    "ConfidenceIntervalCalculator",
    # Market analysis
    "MarketAnalyzer",
    "MarketAnalysisConfig",
    # Multi-market
    "MultiMarketConfig",
    "MultiMarketBettor",
    "EuropeanBookConfig",
    "EuropeanBookIntegrator",
    "BestLine",
    "ArbitrageResult",
    "PotentialBet",
    "Allocation",
    "ComparisonResult",
    "EuropeanOdds",
    # Odds
    "Odds",
    # Implied odds
    "ImpliedOddsCalculator",
    # Ignite cache
    "IgniteOddsCacheConfig",
    "IgniteOddsCache",
    "CreditBudgetMonitor",
    "create_ignite_odds_cache",
    "create_credit_monitor",
]
