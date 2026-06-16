"""Backtest module for sportsquant."""

from sportsquant.core.backtest.engine import (
    PraBacktestConfig,
    backtest_pra_lines,
)
from sportsquant.core.backtest.parallel import (
    BacktestConfig,
    backtest_summary,
    backtest_v2,
)
from sportsquant.core.backtest.regime import (
    FoldResult,
    RegimeAwareBacktest,
    RegimeAwareResults,
    RegimeBacktestResults,
    RegimeDetector,
    RegimePeriod,
    SensitivityAnalyzer,
    SensitivityConfig,
    SensitivityReport,
    SensitivityResult,
    WalkForwardBacktest,
    WalkForwardConfig,
    WalkForwardResults,
    record_backtest_metrics,
)

__all__ = [
    "BacktestConfig",
    "FoldResult",
    "PraBacktestConfig",
    "RegimeAwareBacktest",
    "RegimeAwareResults",
    "RegimeBacktestResults",
    "RegimeDetector",
    "RegimePeriod",
    "SensitivityAnalyzer",
    "SensitivityConfig",
    "SensitivityReport",
    "SensitivityResult",
    "WalkForwardBacktest",
    "WalkForwardConfig",
    "WalkForwardResults",
    "backtest_pra_lines",
    "backtest_summary",
    "backtest_v2",
    "record_backtest_metrics",
]
