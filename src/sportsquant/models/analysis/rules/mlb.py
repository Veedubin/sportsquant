"""MLB-specific evaluation rules and payouts.

This module contains official MLB rules for DFS evaluation including:
- Batting and pitching stats
- FanDuel MLB scoring weights
- PrizePicks MLB payout rules
- Underdog MLB rules
"""


# =============================================================================
# MLB Market Types (stat names used across sites)
# =============================================================================

# Primary MLB batting props
MLB_BATTING_STATS = {
    "hits",
    "runs",
    "rbi",
    "hr",
    "singles",
    "doubles",
    "triples",
    "total_bases",
    "stolen_bases",
    "walks",
    "strikeouts",
    "batting_average",
    "obp",
    "slg",
    "ops",
}

# Alias for rules/__init__.py compatibility
MLB_HITTER_STATS = MLB_BATTING_STATS

# Primary MLB pitching props
MLB_PITCHING_STATS = {
    "pitcher_strikeouts",
    "pitcher_outs",
    "earned_runs",
    "innings_pitched",
    "whip",
    "era",
    "walks_allowed",
    "hits_allowed",
    "hr_allowed",
}

# Alias for rules/__init__.py compatibility
MLB_PITCHER_STATS = MLB_PITCHING_STATS

# Combined stats
MLB_COMBINED_STATS = {
    "hits_runs_rbi",
    "runs_rbi",
    "hr_rbi",
    "hits_runs",
    "singles_plus_doubles",
    "total_bases_plus_runs",
}

# Alias for rules/__init__.py compatibility
MLB_COMBO_STATS = MLB_COMBINED_STATS

# =============================================================================
# FanDuel MLB Scoring Weights
# =============================================================================

FANDUEL_MLB_WEIGHTS = {
    # Batting
    "Singles": 3.0,
    "Doubles": 6.0,
    "Triples": 9.0,
    "Home Runs": 12.0,
    "Runs Scored": 3.2,
    "Runs Batted In": 3.5,
    "Walks": 3.0,
    "Hit by Pitch": 3.0,
    "Stolen Bases": 6.0,
    # Pitching
    "Strikeouts": 3.0,
    "Innings Pitched": 3.0,
    "Win": 6.0,
    "Earned Runs Allowed": -2.0,
    "Walks Allowed": -1.0,
    "Hits Allowed": -1.0,
    "Home Runs Allowed": -2.0,
}

# DraftKings MLB weights (for reference)
DRAFTKINGS_MLB_WEIGHTS = {
    "Singles": 3.0,
    "Doubles": 6.0,
    "Triples": 9.0,
    "Home Runs": 12.0,
    "Runs Scored": 3.2,
    "Runs Batted In": 3.5,
    "Walks": 3.0,
    "Hit by Pitch": 3.0,
    "Stolen Bases": 6.0,
    "Win": 10.0,
    "Strikeouts": 2.0,
    "Quality Start": 4.0,
}

# =============================================================================
# PrizePicks MLB Tiers
# =============================================================================

MLB_TIER_PAYOUT_MODIFIERS = {
    "Standard": 1.0,
    "Flash": 1.2,  # Short window props
    "Elite": 1.15,  # Higher profile props
}

# =============================================================================
# Underdog MLB Rules
# =============================================================================

UNDERDOG_MLB_BESTBALL = {
    "roster_size": 15,
    "draft_rounds": 15,
    "start_date": "opening_day",
    "scoring": "full",
}

# =============================================================================
# Correlation Factors for MLB Props
# =============================================================================

# Same player correlations
MLB_SAME_PLAYER_CORRELATION = {
    ("hits", "runs"): 0.40,
    ("hits", "rbi"): 0.45,
    ("runs", "rbi"): 0.40,
    ("hr", "rbi"): 0.35,
    ("hr", "runs"): 0.30,
    ("singles", "runs"): 0.35,
    ("doubles", "hits"): 0.25,
    ("strikeouts", "innings_pitched"): 0.60,  # Pitcher correlation
    ("walks", "strikeouts"): 0.10,
    "default": 0.20,
}

MLB_SAME_GAME_CORRELATION = 0.05
MLB_DIFFERENT_GAME_CORRELATION = 0.02

# =============================================================================
# DNP/Injury Handling
# =============================================================================

MLB_DNP_THRESHOLD = "1 plate appearance"  # Must have at least 1 PA for batting
MLB_PITCHER_DNP_THRESHOLD = "1 batter faced"

# =============================================================================
# MLB API Stat Mappings
# =============================================================================

MLB_API_STAT_MAPPING = {
    # Batting variations
    "hits": "hits",
    "runs": "runs",
    "rbi": "rbi",
    "hr": "hr",
    "home_runs": "hr",
    "home runs": "hr",
    "hrs": "hr",
    "homeruns": "hr",
    "singles": "singles",
    "doubles": "doubles",
    "triples": "triples",
    "total_bases": "total_bases",
    "stolen_bases": "stolen_bases",
    "sb": "stolen_bases",
    "walks": "walks",
    "strikeouts": "strikeouts",
    "k": "strikeouts",
    "so": "strikeouts",
    "batting_average": "batting_average",
    "ba": "batting_average",
    "obp": "obp",
    "slg": "slg",
    "ops": "ops",
    # Pitching variations
    "pitcher_strikeouts": "pitcher_strikeouts",
    "pitcher_outs": "pitcher_outs",
    "outs": "pitcher_outs",
    "earned_runs": "earned_runs",
    "er": "earned_runs",
    "innings_pitched": "innings_pitched",
    "ip": "innings_pitched",
    "whip": "whip",
    "era": "era",
    "walks_allowed": "walks_allowed",
    "hits_allowed": "hits_allowed",
    "hr_allowed": "hr_allowed",
    # Combined
    "hits_runs_rbi": "hits_runs_rbi",
    "runs_rbi": "runs_rbi",
    "hr_rbi": "hr_rbi",
    "hits_runs": "hits_runs",
}

# Stats that follow Poisson distribution (counting stats)
MLB_POISSON_STATS = {
    "hits",
    "runs",
    "rbi",
    "hr",
    "singles",
    "doubles",
    "triples",
    "total_bases",
    "stolen_bases",
    "walks",
    "strikeouts",
    "pitcher_strikeouts",
    "pitcher_outs",
    "earned_runs",
    "walks_allowed",
    "hits_allowed",
    "hr_allowed",
}

# Stats that are rate-based (NOT Poisson)
MLB_RATE_STATS = {
    "batting_average",
    "obp",
    "slg",
    "ops",
    "whip",
    "era",
}


# =============================================================================
# Utility Functions
# =============================================================================


def get_mlb_stat_key(stat_name: str) -> str:
    """Normalize MLB stat name to standard key.

    Args:
        stat_name: Raw stat name from API/scraper

    Returns:
        Standardized stat key
    """
    if not stat_name:
        return ""

    s = stat_name.lower().strip()

    # Check direct mapping
    if s in MLB_API_STAT_MAPPING:
        return MLB_API_STAT_MAPPING[s]

    # Try without spaces/underscores
    s_normalized = s.replace("_", "").replace(" ", "")
    for key, value in MLB_API_STAT_MAPPING.items():
        if key.replace("_", "").replace(" ", "") == s_normalized:
            return value

    return s


def is_mlb_poisson_stat(stat_key: str) -> bool:
    """Whether stat follows Poisson distribution (counting stats).

    Args:
        stat_key: The normalized stat key

    Returns:
        True for counting stats (K's, HRs, walks, hits, etc.)
        False for rate stats (batting average, ERA, etc.)
    """
    return stat_key in MLB_POISSON_STATS


def get_correlation_mlb(
    stat1: str,
    stat2: str,
    same_player: bool = False,
    same_game: bool = True,
) -> float:
    """Get correlation factor between two MLB props.

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
        if key in MLB_SAME_PLAYER_CORRELATION:
            return MLB_SAME_PLAYER_CORRELATION[key]
        # Check reverse
        key_reverse = (stat2.lower(), stat1.lower())
        if key_reverse in MLB_SAME_PLAYER_CORRELATION:
            return MLB_SAME_PLAYER_CORRELATION[key_reverse]
        return MLB_SAME_PLAYER_CORRELATION["default"]

    if same_game:
        return MLB_SAME_GAME_CORRELATION

    return MLB_DIFFERENT_GAME_CORRELATION


def calculate_mlb_fanduel_points(stats: dict) -> float:
    """Calculate FanDuel MLB fantasy points from stats.

    Args:
        stats: Dict with stat names and values

    Returns:
        FanDuel fantasy points
    """
    points = 0.0
    for stat, value in stats.items():
        # Use title case for lookup (FANDUEL_MLB_WEIGHTS uses "Home Runs" format)
        stat_title = stat.title()
        weight = FANDUEL_MLB_WEIGHTS.get(stat_title, 0.0)
        points += value * weight
    return points


def is_pitcher_stat(stat_key: str) -> bool:
    """Check if stat is a pitcher stat.

    Args:
        stat_key: The normalized stat key

    Returns:
        True if pitcher stat
    """
    return stat_key in MLB_PITCHING_STATS


# Alias for rules/__init__.py compatibility
is_mlb_pitcher_stat = is_pitcher_stat


def is_batter_stat(stat_key: str) -> bool:
    """Check if stat is a batter stat.

    Args:
        stat_key: The normalized stat key

    Returns:
        True if batter stat
    """
    return stat_key in MLB_BATTING_STATS


def detect_player_type(stat_type: str, player_name: str = "") -> str:
    """Detect if player is a pitcher or batter based on stat type.

    Args:
        stat_type: The stat type being evaluated
        player_name: Player name (optional, for additional context)

    Returns:
        "pitcher" or "batter"
    """
    stat_key = get_mlb_stat_key(stat_type)
    if stat_key in MLB_PITCHING_STATS:
        return "pitcher"
    return "batter"
