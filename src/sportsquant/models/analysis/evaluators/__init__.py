"""Site-specific DFS evaluators.

This package contains evaluator modules for each DFS platform and sport:
- prizepicks_eval: PrizePicks evaluation (More/Less, Power/Flex)
- underdog_eval: Underdog evaluation (Higher/Lower, includes sportsbook odds)
- draftkings_eval: DraftKings evaluation (Over/Under lines)
- fanduel_eval: FanDuel evaluation (DFS lineups, Picks format)
- nfl_eval: NFL-specific statistical model and evaluation
- mlb_eval: MLB-specific statistical model and evaluation
- nhl_eval: NHL-specific statistical model and evaluation
- pga_eval: PGA-specific statistical model and evaluation
"""

from sportsquant.models.analysis.evaluators.prizepicks_eval import (
    PrizePicksEvaluator,
    PrizePicksLeg,
    PrizePicksSlip,
)
from sportsquant.models.analysis.evaluators.underdog_eval import (
    UnderdogEvaluator,
    UnderdogLeg,
    UnderdogEntry,
)
from sportsquant.models.analysis.evaluators.draftkings_eval import DraftKingsEvaluator
from sportsquant.models.analysis.evaluators.fanduel_eval import (
    FanDuelEvaluator,
    FanDuelPlayer,
    FanDuelLineup,
    FanDuelPick,
)

# Sport-specific evaluators
from sportsquant.models.analysis.evaluators.nfl_eval import (
    NFLEvaluator,
    NFLPrizePicksEvaluator,
    NFLUnderdogEvaluator,
    NFLFanDuelEvaluator,
)
from sportsquant.models.analysis.evaluators.nhl_eval import (
    NHLEvaluator,
    NHLPrizePicksEvaluator,
    NHLUnderdogEvaluator,
    NHLFanDuelEvaluator,
)
from sportsquant.models.analysis.evaluators.pga_eval import (
    PGAEvaluator,
    PGAPrizePicksEvaluator,
    PGAUnderdogEvaluator,
    PGAFanDuelEvaluator,
)
from sportsquant.models.analysis.evaluators.mlb_eval import (
    MLBEvaluator,
    MLBPrizePicksEvaluator,
    MLBUnderdogEvaluator,
    MLBFanDuelEvaluator,
)

__all__ = [
    # PrizePicks
    "PrizePicksEvaluator",
    "PrizePicksLeg",
    "PrizePicksSlip",
    # Underdog
    "UnderdogEvaluator",
    "UnderdogLeg",
    "UnderdogEntry",
    # DraftKings
    "DraftKingsEvaluator",
    # FanDuel
    "FanDuelEvaluator",
    "FanDuelPlayer",
    "FanDuelLineup",
    "FanDuelPick",
    # NFL
    "NFLEvaluator",
    "NFLPrizePicksEvaluator",
    "NFLUnderdogEvaluator",
    "NFLFanDuelEvaluator",
    # NHL
    "NHLEvaluator",
    "NHLPrizePicksEvaluator",
    "NHLUnderdogEvaluator",
    "NHLFanDuelEvaluator",
    # PGA
    "PGAEvaluator",
    "PGAPrizePicksEvaluator",
    "PGAUnderdogEvaluator",
    "PGAFanDuelEvaluator",
    # MLB
    "MLBEvaluator",
    "MLBPrizePicksEvaluator",
    "MLBUnderdogEvaluator",
    "MLBFanDuelEvaluator",
]
