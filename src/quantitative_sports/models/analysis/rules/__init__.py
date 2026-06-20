"""Rules for site-specific DFS evaluation.

Contains official rules, payouts, and scoring for:
- PrizePicks: More/Less pick'em, Power/Flex plays
- Underdog: Higher/Lower pick'em, Best Ball
- FanDuel: DFS lineups, Picks format
- NFL, NHL, PGA, MLB: Sport-specific rules

This module re-exports from:
- .fanduel: FanDuel rules
- .underdog: Underdog rules
- .nfl: NFL rules
- .nhl: NHL rules
- .pga: PGA rules
- .mlb: MLB rules
"""

# Import FanDuel rules
from .fanduel import (
    FANDUEL_NBA_WEIGHTS,
    FANDUEL_NFL_WEIGHTS,
    FANDUEL_NHL_WEIGHTS,
    calculate_fanduel_points,
    get_salary_cap,
    get_payout_multiplier,
    validate_lineup,
    calculate_picks_payout,
    validate_picks,
    PICKS_FORMAT,
    ENTRY_TYPES,
    SalaryCap,
    PositionLimits,
)

# Import Underdog rules
from .underdog import (
    PICKEM_PAYOUTS,
    FLEX_PAYOUTS,
    DEFAULT_PICKEM_RULES,
    PickemRules,
    calculate_payout,
    calculate_flex_payout,
    get_correlation,
    validate_pickem_entry,
    get_flex_allowed_misses,
    FLEX_ALLOWED_MISSES,
    BestBallRules,
    BESTBALL_BY_SPORT,
)

# Import NFL rules
from .nfl import (
    NFL_PASSING_STATS,
    NFL_RUSHING_STATS,
    NFL_RECEIVING_STATS,
    NFL_API_STAT_MAPPING,
    NFL_TIER_PAYOUT_MODIFIERS,
    DRAFTKINGS_NFL_WEIGHTS,
    NFL_DNP_THRESHOLD,
    get_nfl_stat_key,
    get_correlation_nfl,
    is_nfl_poisson_stat,
    calculate_nfl_fanduel_points,
)

# Import NHL rules
from .nhl import (
    NHL_SKATER_STATS,
    NHL_GOALIE_STATS,
    NHL_API_STAT_MAPPING,
    NHL_TIER_PAYOUT_MODIFIERS,
    DRAFTKINGS_NHL_WEIGHTS,
    NHL_DNP_THRESHOLD,
    get_nhl_stat_key,
    is_nhl_goalie_stat,
    get_correlation_nhl,
    is_nhl_poisson_stat,
    calculate_nhl_fanduel_points,
)

# Import PGA rules
from .pga import (
    PGA_STROKES_GAINED_STATS,
    PGA_TRADITIONAL_STATS,
    PGA_FINISH_STATS,
    PGA_API_STAT_MAPPING,
    PGA_TIER_PAYOUT_MODIFIERS,
    FANDUEL_PGA_WEIGHTS,
    DRAFTKINGS_PGA_WEIGHTS,
    PGA_DNP_THRESHOLD,
    get_pga_stat_key,
    is_pga_finish_prop,
    is_pga_strokes_gained_stat,
    get_correlation_pga,
    is_pga_poisson_stat,
    calculate_pga_fanduel_points,
)

# Import MLB rules
from .mlb import (
    MLB_HITTER_STATS,
    MLB_PITCHER_STATS,
    MLB_COMBO_STATS,
    MLB_API_STAT_MAPPING as MLB_API_STAT_MAPPING,
    MLB_TIER_PAYOUT_MODIFIERS,
    FANDUEL_MLB_WEIGHTS,
    DRAFTKINGS_MLB_WEIGHTS,
    MLB_DNP_THRESHOLD,
    get_mlb_stat_key,
    is_mlb_pitcher_stat,
    get_correlation_mlb,
    is_mlb_poisson_stat,
    calculate_mlb_fanduel_points,
    detect_player_type,
)

# =====================================================================
# PrizePicks Rules (from analysis/rules.py)
# These are included directly to avoid circular imports with the
# analysis package (since rules/ is a subpackage of analysis/).
# =====================================================================

from dataclasses import dataclass
from typing import Optional

# Official standard payouts (from PrizePicks rules page)
STANDARD_PAYOUT_POWER = {
    (2, 2): 3.0,
    (3, 3): 6.0,
    (4, 4): 10.0,
    (5, 5): 20.0,
    (6, 6): 25.0,
}

STANDARD_PAYOUT_FLEX = {
    (3, 3): 3.0,
    (3, 2): 1.0,
    (4, 4): 6.0,
    (4, 3): 1.5,
    (5, 5): 10.0,
    (5, 4): 2.0,
    (5, 3): 0.4,
    (6, 6): 12.5,
    (6, 5): 2.0,
    (6, 4): 0.4,
}

# Tier-specific modifiers (approximate - these vary)
TIER_PAYOUT_MODIFIERS = {
    "Standard": 1.0,
    "Goblin": 0.85,
    "Demon": 1.5,
}

# Scoring points for group competition
TIER_SCORING_POINTS = {
    "Demon": 1.05,
    "Standard": 1.0,
    "Goblin": 0.95,
    "Discounted": 0.95,
    "Stack": 0.95,
}

# Over-only tiers
OVER_ONLY_TIERS = {"Goblin", "Demon"}


@dataclass
class LineupRules:
    """Rules for a PrizePicks lineup."""

    min_teams: int = 2
    max_same_player: int = 1
    max_per_game: Optional[int] = None
    dnp_reverts: bool = True
    reboot_eligible: bool = True
    payout_power: dict = None
    payout_flex: dict = None

    def __post_init__(self):
        if self.payout_power is None:
            self.payout_power = STANDARD_PAYOUT_POWER.copy()
        if self.payout_flex is None:
            self.payout_flex = STANDARD_PAYOUT_FLEX.copy()


# DNP/Reboot reversion rules
DNP_REVERSION_POWER = {
    6: 5,
    5: 4,
    4: 3,
    3: 2,
    2: None,
}

DNP_REVERSION_FLEX = {
    6: 5,
    5: 4,
    4: 3,
    3: 2,
}

# NBA Fantasy Score calculation
NBA_FANTASY_SCORE_WEIGHTS = {
    "PTS": 1.0,
    "REB": 1.2,
    "AST": 1.5,
    "BLK": 3.0,
    "STL": 3.0,
    "TOV": -1.0,
}


def calculate_nba_fantasy_score(stats: dict) -> float:
    """Calculate NBA Fantasy Score from stat dict."""
    return sum(stats.get(k, 0) * v for k, v in NBA_FANTASY_SCORE_WEIGHTS.items())


def calculate_effective_payout(
    n_legs: int,
    n_hits: int,
    format_type: str,
    tier: str = "Standard",
    payout_power: Optional[dict] = None,
    payout_flex: Optional[dict] = None,
) -> float:
    """Calculate effective payout with tier modifiers."""
    payout_power = payout_power or STANDARD_PAYOUT_POWER
    payout_flex = payout_flex or STANDARD_PAYOUT_FLEX

    if format_type.lower() == "power":
        base_payout = payout_power.get((n_legs, n_hits), 0.0)
    else:
        base_payout = payout_flex.get((n_legs, n_hits), 0.0)

    modifier = TIER_PAYOUT_MODIFIERS.get(tier, 1.0)
    return base_payout * modifier


def validate_same_team_restriction(legs: list, league: str = "NBA") -> bool:
    """Validate minimum team requirement (at least 2 teams in slip)."""
    teams = set()
    for leg in legs:
        if leg.team:
            teams.add(leg.team)
    return len(teams) >= 2


__all__ = [
    # FanDuel
    "FANDUEL_NBA_WEIGHTS",
    "FANDUEL_NFL_WEIGHTS",
    "FANDUEL_MLB_WEIGHTS",
    "FANDUEL_NHL_WEIGHTS",
    "calculate_fanduel_points",
    "get_salary_cap",
    "get_payout_multiplier",
    "validate_lineup",
    "calculate_picks_payout",
    "validate_picks",
    "PICKS_FORMAT",
    "ENTRY_TYPES",
    "SalaryCap",
    "PositionLimits",
    # Underdog
    "PICKEM_PAYOUTS",
    "FLEX_PAYOUTS",
    "DEFAULT_PICKEM_RULES",
    "PickemRules",
    "calculate_payout",
    "calculate_flex_payout",
    "get_correlation",
    "validate_pickem_entry",
    "get_flex_allowed_misses",
    "FLEX_ALLOWED_MISSES",
    "BestBallRules",
    "BESTBALL_BY_SPORT",
    # PrizePicks
    "STANDARD_PAYOUT_POWER",
    "STANDARD_PAYOUT_FLEX",
    "TIER_PAYOUT_MODIFIERS",
    "TIER_SCORING_POINTS",
    "OVER_ONLY_TIERS",
    "DNP_REVERSION_POWER",
    "DNP_REVERSION_FLEX",
    "LineupRules",
    "calculate_effective_payout",
    "validate_same_team_restriction",
    "NBA_FANTASY_SCORE_WEIGHTS",
    "calculate_nba_fantasy_score",
    # NFL
    "NFL_PASSING_STATS",
    "NFL_RUSHING_STATS",
    "NFL_RECEIVING_STATS",
    "NFL_API_STAT_MAPPING",
    "NFL_TIER_PAYOUT_MODIFIERS",
    "FANDUEL_NFL_WEIGHTS",
    "DRAFTKINGS_NFL_WEIGHTS",
    "NFL_DNP_THRESHOLD",
    "get_nfl_stat_key",
    "get_correlation_nfl",
    "is_nfl_poisson_stat",
    "calculate_nfl_fanduel_points",
    # NHL
    "NHL_SKATER_STATS",
    "NHL_GOALIE_STATS",
    "NHL_API_STAT_MAPPING",
    "NHL_TIER_PAYOUT_MODIFIERS",
    "FANDUEL_NHL_WEIGHTS",
    "DRAFTKINGS_NHL_WEIGHTS",
    "NHL_DNP_THRESHOLD",
    "get_nhl_stat_key",
    "is_nhl_goalie_stat",
    "get_correlation_nhl",
    "is_nhl_poisson_stat",
    "calculate_nhl_fanduel_points",
    # PGA
    "PGA_STROKES_GAINED_STATS",
    "PGA_TRADITIONAL_STATS",
    "PGA_FINISH_STATS",
    "PGA_API_STAT_MAPPING",
    "PGA_TIER_PAYOUT_MODIFIERS",
    "FANDUEL_PGA_WEIGHTS",
    "DRAFTKINGS_PGA_WEIGHTS",
    "PGA_DNP_THRESHOLD",
    "get_pga_stat_key",
    "is_pga_finish_prop",
    "is_pga_strokes_gained_stat",
    "get_correlation_pga",
    "is_pga_poisson_stat",
    "calculate_pga_fanduel_points",
    # MLB
    "MLB_HITTER_STATS",
    "MLB_PITCHER_STATS",
    "MLB_COMBO_STATS",
    "MLB_API_STAT_MAPPING",
    "MLB_TIER_PAYOUT_MODIFIERS",
    "FANDUEL_MLB_WEIGHTS",
    "DRAFTKINGS_MLB_WEIGHTS",
    "MLB_DNP_THRESHOLD",
    "get_mlb_stat_key",
    "is_mlb_pitcher_stat",
    "get_correlation_mlb",
    "is_mlb_poisson_stat",
    "calculate_mlb_fanduel_points",
    "detect_player_type",
]
