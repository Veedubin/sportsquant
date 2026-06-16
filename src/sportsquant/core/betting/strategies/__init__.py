"""
Betting strategies module.

Provides pluggable betting strategies using the strategy pattern.
"""

from sportsquant.core.betting.strategies.arbitrage import ArbitrageStrategy
from sportsquant.core.betting.strategies.base import (
    BetDecision,
    BettingOpportunity,
    BettingStrategy,
    make_bet_decision,
)
from sportsquant.core.betting.strategies.over_under import OverUnderStrategy
from sportsquant.core.betting.strategies.probability_threshold import (
    ProbabilityThresholdConfig,
    ProbabilityThresholdStrategy,
)
from sportsquant.core.betting.strategies.registry import StrategyRegistry
from sportsquant.core.betting.strategies.value_betting import ValueBettingStrategy

__all__ = [
    "BettingStrategy",
    "BetDecision",
    "BettingOpportunity",
    "make_bet_decision",
    "OverUnderStrategy",
    "ValueBettingStrategy",
    "ArbitrageStrategy",
    "ProbabilityThresholdConfig",
    "ProbabilityThresholdStrategy",
    "StrategyRegistry",
]
