"""NHL-specific evaluation rules and payouts.

This module contains official NHL rules for DFS evaluation including:
- Goals, assists, points for skaters
- Saves, shutouts for goalies
- FanDuel NHL scoring weights
- PrizePicks NHL payout rules
"""


# =============================================================================
# NHL Market Types (stat names used across sites)
# =============================================================================

# Skater stats
NHL_SKATER_STATS = {
    "goals",
    "assists",
    "points",
    "shots_on_goal",
    "shots",
    "power_play_points",
    "pp_points",
    "shorthanded_points",
    "sh_points",
    "blocked_shots",
    "blocks",
    "hits",
    "takeaways",
    "giveaways",
    "faceoff_wins",
    "faceoffs",
    "plus_minus",
    "plusmin",
    "penalty_minutes",
    "pim",
    "toi",
    "time_on_ice",
}

# Goalie stats
NHL_GOALIE_STATS = {
    "saves",
    "save",
    "shots_against",
    "goals_against",
    "ga",
    "save_percentage",
    "sv_pct",
    "save_pct",
    "shutouts",
    "shutout",
    "wins",
    "win",
    "losses",
    "loss",
    "goals_against_average",
    "gaa",
}

# Combined stats
NHL_COMBO_STATS = {
    "points_assists",
    "goals_assists",
    "shots_on_goal",
    "sog",
}

# Fantasy scoring stats
NHL_FANTASY_STATS = {
    "fantasy_points",
    "draftkings_fantasy",
    "fanduel_fantasy",
}

# =============================================================================
# FanDuel NHL Scoring Weights
# =============================================================================

FANDUEL_NHL_WEIGHTS = {
    # Skater
    "Goals": 12.0,
    "Assists": 6.0,
    "Shots on Goal": 1.0,
    "Power Play Points": 3.0,
    "Shorthanded Points": 5.0,
    "Blocked Shots": 0.8,
    "Hits": 0.5,
    "Takeaways": 0.5,
    "Faceoff Wins": 0.5,
    # Goalie
    "Goalie Wins": 6.0,
    "Goalie Saves": 0.5,
    "Goalie Shutouts": 4.0,
    "Goals Against": -1.0,
    # Others
    "Plus/Minus": 1.0,
    "Penalty Minutes": 0.4,
}

# DraftKings NHL weights (for reference)
DRAFTKINGS_NHL_WEIGHTS = {
    "Goals": 3.0,
    "Assists": 2.0,
    "Shots on Goal": 0.5,
    "Power Play Points": 1.0,
    "Shorthanded Points": 1.0,
    "Blocked Shots": 0.5,
    "Hits": 0.5,
    "Takeaways": 0.2,
    "Faceoff Wins": 0.1,
    # Goalie
    "Goalie Win": 5.0,
    "Goalie Save": 0.7,
    "Goalie Shutout": 4.0,
    "Goals Against": -1.0,
}

# =============================================================================
# PrizePicks NHL Tiers
# =============================================================================

NHL_TIER_PAYOUT_MODIFIERS = {
    "Standard": 1.0,
    "Clutch": 1.1,  # Game-winning goals etc
    "Ice Time": 1.05,  # Minutes-based props
}

# =============================================================================
# Correlation Factors for NHL Props
# =============================================================================

# Same player correlations
NHL_SAME_PLAYER_CORRELATION = {
    ("goals", "assists"): 0.35,
    ("goals", "points"): 0.45,
    ("assists", "points"): 0.70,
    ("shots_on_goal", "goals"): 0.15,
    ("shots_on_goal", "points"): 0.30,
    ("power_play_points", "goals"): 0.20,
    ("power_play_points", "assists"): 0.25,
    # Goalie correlations
    ("saves", "wins"): 0.40,
    ("saves", "shutouts"): 0.25,
    ("shutouts", "wins"): 0.20,
    # Default
    "default": 0.20,
}

NHL_SAME_GAME_CORRELATION = 0.06
NHL_DIFFERENT_GAME_CORRELATION = 0.02

# =============================================================================
# DNP/Injury Handling
# =============================================================================

NHL_DNP_THRESHOLD = "1 shift"  # Must play at least 1 shift

# =============================================================================
# Data Provider Settings
# =============================================================================

# NHL stat mappings for different APIs
NHL_API_STAT_MAPPING = {
    # Standard
    "goals": "goals",
    "assists": "assists",
    "points": "points",
    "shots": "shots_on_goal",
    "shots_on_goal": "shots_on_goal",
    "sog": "shots_on_goal",
    "power_play_points": "power_play_points",
    "pp_points": "power_play_points",
    "sh_points": "shorthanded_points",
    "shorthanded_points": "shorthanded_points",
    "blocked_shots": "blocked_shots",
    "blocks": "blocked_shots",
    "hits": "hits",
    "takeaways": "takeaways",
    "giveaways": "giveaways",
    "faceoff_wins": "faceoff_wins",
    "faceoffs": "faceoff_wins",
    "plus_minus": "plus_minus",
    "plusmin": "plus_minus",
    "pim": "penalty_minutes",
    "penalty_minutes": "penalty_minutes",
    # Goalie
    "saves": "saves",
    "shots_against": "shots_against",
    "goals_against": "goals_against",
    "save_percentage": "save_percentage",
    "sv_pct": "save_percentage",
    "shutouts": "shutouts",
    "wins": "wins",
    "losses": "losses",
    "goals_against_average": "goals_against_average",
    "gaa": "goals_against_average",
    # Common variations
    "goalie_saves": "saves",
    "goalie_wins": "wins",
    "goalie_shutouts": "shutouts",
}

# =============================================================================
# Utility Functions
# =============================================================================


def get_nhl_stat_key(stat_name: str) -> str:
    """Normalize NHL stat name to standard key.

    Args:
        stat_name: Raw stat name from API/scraper

    Returns:
        Standardized stat key
    """
    if not stat_name:
        return ""

    s = stat_name.lower().strip()

    # Check direct mapping
    if s in NHL_API_STAT_MAPPING:
        return NHL_API_STAT_MAPPING[s]

    # Try without spaces/underscores
    s_normalized = s.replace("_", "").replace(" ", "")
    for key, value in NHL_API_STAT_MAPPING.items():
        if key.replace("_", "").replace(" ", "") == s_normalized:
            return value

    return s


def is_nhl_goalie_stat(stat_type: str) -> bool:
    """Check if stat type is for goalies.

    Args:
        stat_type: The stat type

    Returns:
        True if goalie stat
    """
    goalie_stats = {
        "saves",
        "save",
        "shots_against",
        "goals_against",
        "save_percentage",
        "sv_pct",
        "shutouts",
        "shutout",
        "wins",
        "win",
        "losses",
        "goals_against_average",
        "gaa",
    }
    return stat_type.lower().replace(" ", "_") in goalie_stats


def get_correlation_nhl(
    stat1: str,
    stat2: str,
    same_player: bool = False,
    same_game: bool = True,
) -> float:
    """Get correlation factor between two NHL props.

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
        if key in NHL_SAME_PLAYER_CORRELATION:
            return NHL_SAME_PLAYER_CORRELATION[key]
        # Check reverse
        key_reverse = (stat2.lower(), stat1.lower())
        if key_reverse in NHL_SAME_PLAYER_CORRELATION:
            return NHL_SAME_PLAYER_CORRELATION[key_reverse]
        return NHL_SAME_PLAYER_CORRELATION["default"]

    if same_game:
        return NHL_SAME_GAME_CORRELATION

    return NHL_DIFFERENT_GAME_CORRELATION


def is_nhl_poisson_stat(stat_type: str) -> bool:
    """Check if NHL stat should use Poisson distribution.

    Args:
        stat_type: The stat type

    Returns:
        True if should use Poisson
    """
    # Goals, saves, and points tend to follow Poisson
    poisson_stats = {
        "goals",
        "points",
        "assists",
        "saves",
        "power_play_points",
        "shorthanded_points",
        "blocked_shots",
        "hits",
        "takeaways",
    }
    return stat_type.lower().replace(" ", "_") in poisson_stats


def calculate_nhl_fanduel_points(stats: dict, is_goalie: bool = False) -> float:
    """Calculate FanDuel NHL fantasy points from stats.

    Args:
        stats: Dict with stat names and values
        is_goalie: Whether player is a goalie

    Returns:
        FanDuel fantasy points
    """
    points = 0.0
    for stat, value in stats.items():
        stat_upper = stat.upper()
        weight = FANDUEL_NHL_WEIGHTS.get(stat_upper, 0.0)
        points += value * weight
    return points
