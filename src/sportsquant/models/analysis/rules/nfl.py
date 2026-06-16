"""NFL-specific evaluation rules and payouts.

This module contains official NFL rules for DFS evaluation including:
- Passing, rushing, receiving stats
- FanDuel NFL scoring weights
- PrizePicks NFL payout rules
- Underdog NFL Best Ball rules
"""


# =============================================================================
# NFL Market Types (stat names used across sites)
# =============================================================================

# Primary NFL props
NFL_PASSING_STATS = {
    "passing_yards",
    "passing_tds",
    "interceptions",
    "passing_completions",
    "passing_attempts",
    "passingcompletion",
    "passing yards",
}

NFL_RUSHING_STATS = {
    "rushing_yards",
    "rushing_tds",
    "rushing_attempts",
    "rushing yards",
    "rush yards",
}

NFL_RECEIVING_STATS = {
    "receiving_yards",
    "receiving_tds",
    "receptions",
    "receiving_receptions",
    "targets",
    "receiving yards",
    "rec yards",
}

NFL_DEFENSIVE_STATS = {
    "sacks",
    "tackles",
    "interceptions",
    "passes_defended",
    "forced_fumbles",
    "fumble_recoveries",
    "safeties",
}

# Fantasy scoring stats
NFL_FANTASY_STATS = {
    "fantasy_points",
    "draftkings_fantasy",
    "fanduel_fantasy",
}

# =============================================================================
# FanDuel NFL Scoring Weights
# =============================================================================

FANDUEL_NFL_WEIGHTS = {
    # Passing
    "Passing Yards": 0.04,
    "Passing TDs": 4.0,
    "Interceptions": -1.0,
    "Passing Completions": 0.0,
    "Passing Attempts": 0.0,
    "Sacks Taken": 0.0,
    # Rushing
    "Rushing Yards": 0.1,
    "Rushing TDs": 6.0,
    "Rushing Attempts": 0.0,
    # Receiving
    "Receiving Yards": 0.1,
    "Receiving TDs": 6.0,
    "Receptions": 0.5,
    "Receiving Targets": 0.0,
    # Turnovers/Other
    "Fumbles Lost": -2.0,
    "2-PT Conversions": 2.0,
    "Kickoff Return TDs": 6.0,
    "Punt Return TDs": 6.0,
    "Fumble Recovery TD": 6.0,
}

# DraftKings NFL weights (for reference)
DRAFTKINGS_NFL_WEIGHTS = {
    "Passing Yards": 0.04,
    "Passing TDs": 4.0,
    "Interceptions": -1.0,
    "Rushing Yards": 0.1,
    "Rushing TDs": 6.0,
    "Receiving Yards": 0.1,
    "Receiving TDs": 6.0,
    "Receptions": 0.5,
    "Fumbles Lost": -2.0,
    "2-PT Conversions": 2.0,
}

# =============================================================================
# PrizePicks NFL Tiers
# =============================================================================

# NFL typically has Standard and some alternate tiers
NFL_TIER_PAYOUT_MODIFIERS = {
    "Standard": 1.0,
    "Bootleg": 1.1,  # Higher payouts for certain props
    "Red Zone": 1.15,  # TD-focused props
}

# =============================================================================
# Underdog NFL Best Ball Rules
# =============================================================================

UNDERDOG_NFL_BESTBALL = {
    "roster_size": 18,
    "draft_rounds": 18,
    "start_week": 1,
    "playoff_weeks": 4,  # Weeks 15-18
    "scoring": "full",  # Standard PPR-ish
}

# =============================================================================
# Correlation Factors for NFL Props
# =============================================================================

# Same player correlations (passing + rushing + receiving for QBs)
NFL_SAME_PLAYER_CORRELATION = {
    ("passing_yards", "passing_tds"): 0.45,
    ("passing_yards", "rushing_yards"): 0.15,
    ("passing_tds", "rushing_tds"): 0.10,
    # WR/RB receiving correlations
    ("receptions", "receiving_yards"): 0.75,
    ("receptions", "receiving_tds"): 0.25,
    ("receiving_yards", "receiving_tds"): 0.30,
    # RB rushing/receiving
    ("rushing_yards", "receptions"): 0.10,
    ("rushing_yards", "receiving_yards"): 0.10,
    # Default
    "default": 0.15,
}

NFL_SAME_GAME_CORRELATION = 0.08
NFL_DIFFERENT_GAME_CORRELATION = 0.02

# =============================================================================
# DNP/Injury Handling
# =============================================================================

NFL_DNP_THRESHOLD = "1 snap"  # Must play at least 1 snap

# =============================================================================
# Data Provider Settings
# =============================================================================

# NFL stat mappings for different APIs
NFL_API_STAT_MAPPING = {
    # ESPN/Fangraphs style
    "pass_yards": "passing_yards",
    "pass_tds": "passing_tds",
    "pass_int": "interceptions",
    "rush_yards": "rushing_yards",
    "rush_tds": "rushing_tds",
    "rec_yards": "receiving_yards",
    "rec_tds": "receiving_tds",
    "receptions": "receptions",
    "targets": "targets",
    # Common variations
    "passing yards": "passing_yards",
    "rushing yards": "rushing_yards",
    "receiving yards": "receiving_yards",
    "passing touchdowns": "passing_tds",
    "rushing touchdowns": "rushing_tds",
    "receiving touchdowns": "receiving_tds",
}

# =============================================================================
# Utility Functions
# =============================================================================


def get_nfl_stat_key(stat_name: str) -> str:
    """Normalize NFL stat name to standard key.

    Args:
        stat_name: Raw stat name from API/scraper

    Returns:
        Standardized stat key
    """
    if not stat_name:
        return ""

    s = stat_name.lower().strip()

    # Check direct mapping
    if s in NFL_API_STAT_MAPPING:
        return NFL_API_STAT_MAPPING[s]

    # Try without spaces/underscores
    s_normalized = s.replace("_", "").replace(" ", "")
    for key, value in NFL_API_STAT_MAPPING.items():
        if key.replace("_", "").replace(" ", "") == s_normalized:
            return value

    return s


def get_correlation_nfl(
    stat1: str,
    stat2: str,
    same_player: bool = False,
    same_game: bool = True,
) -> float:
    """Get correlation factor between two NFL props.

    Args:
        stat1: First stat type
        stat2: Second stat type
        same_player: Whether same player
        same_game: Whether same game

    Returns:
        Correlation coefficient
    """
    if same_player:
        key = (stat1.lower(), stat2.lower())
        if key in NFL_SAME_PLAYER_CORRELATION:
            return NFL_SAME_PLAYER_CORRELATION[key]
        # Check reverse
        key_reverse = (stat2.lower(), stat1.lower())
        if key_reverse in NFL_SAME_PLAYER_CORRELATION:
            return NFL_SAME_PLAYER_CORRELATION[key_reverse]
        return NFL_SAME_PLAYER_CORRELATION["default"]

    if same_game:
        return NFL_SAME_GAME_CORRELATION

    return NFL_DIFFERENT_GAME_CORRELATION


def is_nfl_poisson_stat(stat_type: str) -> bool:
    """Check if NFL stat should use Poisson distribution.

    Args:
        stat_type: The stat type

    Returns:
        True if should use Poisson
    """
    poisson_stats = {
        "passing_tds",
        "rushing_tds",
        "receiving_tds",
        "interceptions",
        "sacks",
        "tackles",
        "forced_fumbles",
    }
    return stat_type.lower().replace(" ", "_") in poisson_stats


def calculate_nfl_fanduel_points(stats: dict) -> float:
    """Calculate FanDuel NFL fantasy points from stats.

    Args:
        stats: Dict with stat names and values

    Returns:
        FanDuel fantasy points
    """
    points = 0.0
    for stat, value in stats.items():
        stat_upper = stat.upper()
        weight = FANDUEL_NFL_WEIGHTS.get(stat_upper, 0.0)
        points += value * weight
    return points
