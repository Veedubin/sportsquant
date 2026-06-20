"""DFS +EV Analysis Engine for PrizePicks, FanDuel, and Underdog.

This package provides site-specific analysis components for finding positive
expected value plays across multiple daily fantasy sports platforms.

Components:
- engine: Base evaluation engine with EV calculation and confidence scoring
- market_matcher: Matches prop lines to market odds with interpolation
- statistical_model: Builds player performance models from historical data
- ev_calculator: Core EV calculation using logit blending
- slip_optimizer: Monte Carlo optimization for constructing optimal slips
- pipeline: Orchestrates the full analysis pipeline
- prizepicks_eval: PrizePicks-specific evaluation (More/Less, Power/Flex)
- underdog_eval: Underdog-specific evaluation (Higher/Lower, includes sportsbook odds)
- fanduel_eval: FanDuel-specific evaluation (DFS lineups, Picks format)
- rules: Site-specific rules, payouts, and scoring configurations
"""

from quantitative_sports.models.analysis.engine import BaseEvaluator, EvaluationResult
from quantitative_sports.models.analysis.market_matcher import MarketMatcher, InterpolationMethod
from quantitative_sports.models.analysis.statistical_model import StatisticalModel, NBADataProvider
from quantitative_sports.models.analysis.ev_calculator import EVCalculator
from quantitative_sports.models.analysis.slip_optimizer import SlipOptimizer, Leg
from quantitative_sports.models.analysis.pipeline import AnalysisPipeline, AnalysisConfig

# Sport-specific evaluators
from quantitative_sports.models.analysis.evaluators.nfl_eval import (
    NFLEvaluator,
    NFLPrizePicksEvaluator,
    NFLUnderdogEvaluator,
    NFLFanDuelEvaluator,
)
from quantitative_sports.models.analysis.evaluators.nhl_eval import (
    NHLEvaluator,
    NHLPrizePicksEvaluator,
    NHLUnderdogEvaluator,
    NHLFanDuelEvaluator,
)
from quantitative_sports.models.analysis.evaluators.pga_eval import (
    PGAEvaluator,
    PGAPrizePicksEvaluator,
    PGAUnderdogEvaluator,
    PGAFanDuelEvaluator,
)
from quantitative_sports.models.analysis.evaluators.mlb_eval import (
    MLBEvaluator,
    MLBPrizePicksEvaluator,
    MLBUnderdogEvaluator,
    MLBFanDuelEvaluator,
)

# Site-specific evaluators
from quantitative_sports.models.analysis.evaluators.prizepicks_eval import (
    PrizePicksEvaluator,
    PrizePicksLeg,
    PrizePicksSlip,
)
from quantitative_sports.models.analysis.evaluators.underdog_eval import (
    UnderdogEvaluator,
    UnderdogLeg,
    UnderdogEntry,
)
from quantitative_sports.models.analysis.evaluators.fanduel_eval import (
    FanDuelEvaluator,
    FanDuelPlayer,
    FanDuelLineup,
    FanDuelPick,
)

__all__ = [
    # Base engine
    "BaseEvaluator",
    "EvaluationResult",
    # Core components
    "MarketMatcher",
    "InterpolationMethod",
    "StatisticalModel",
    "NBADataProvider",
    "EVCalculator",
    "SlipOptimizer",
    "Leg",
    "AnalysisPipeline",
    "AnalysisConfig",
    # NFL evaluators
    "NFLEvaluator",
    "NFLPrizePicksEvaluator",
    "NFLUnderdogEvaluator",
    "NFLFanDuelEvaluator",
    # NHL evaluators
    "NHLEvaluator",
    "NHLPrizePicksEvaluator",
    "NHLUnderdogEvaluator",
    "NHLFanDuelEvaluator",
    # PGA evaluators
    "PGAEvaluator",
    "PGAPrizePicksEvaluator",
    "PGAUnderdogEvaluator",
    "PGAFanDuelEvaluator",
    # MLB evaluators
    "MLBEvaluator",
    "MLBPrizePicksEvaluator",
    "MLBUnderdogEvaluator",
    "MLBFanDuelEvaluator",
    # PrizePicks evaluator
    "PrizePicksEvaluator",
    "PrizePicksLeg",
    "PrizePicksSlip",
    # Underdog evaluator
    "UnderdogEvaluator",
    "UnderdogLeg",
    "UnderdogEntry",
    # FanDuel evaluator
    "FanDuelEvaluator",
    "FanDuelPlayer",
    "FanDuelLineup",
    "FanDuelPick",
]
