"""
Betting strategies module.

Provides pluggable betting strategies using the strategy pattern.
"""

from quantitative_sports.core.betting.strategies.arbitrage import ArbitrageStrategy
from quantitative_sports.core.betting.strategies.base import (
    BetDecision,
    BettingOpportunity,
    BettingStrategy,
    make_bet_decision,
)
from quantitative_sports.core.betting.strategies.over_under import OverUnderStrategy
from quantitative_sports.core.betting.strategies.probability_threshold import (
    ProbabilityThresholdConfig,
    ProbabilityThresholdStrategy,
)
from quantitative_sports.core.betting.strategies.registry import StrategyRegistry
from quantitative_sports.core.betting.strategies.value_betting import ValueBettingStrategy

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
