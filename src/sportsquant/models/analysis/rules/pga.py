"""PGA-specific evaluation rules and payouts.

This module contains official PGA rules for DFS evaluation including:
- Strokes gained, birdies, eagles
- Top finish, cut make/miss
- FanDuel PGA scoring weights
- PrizePicks PGA payout rules
"""

import re

# Strokes gained stats ( ShotLink data)
PGA_STROKES_GAINED_STATS = {
    "strokes_gained_total",
    "sg_total",
    "strokes_gained_tee_to_green",
    "sg_tee_to_green",
    "strokes_gained_off_the_tee",
    "sg_off_the_tee",
    "strokes_gained_around_the_green",
    "sg_around_the_green",
    "strokes_gained_putting",
    "sg_putting",
    "strokes_gained_apr",
    "sg_apr",  # Approach
    "strokes_gained_arg",
    "sg_arg",  # Around the green
}

# Traditional stats
PGA_TRADITIONAL_STATS = {
    "birdies",
    "bogeys",
    "pars",
    "doubles",
    "triples",
    " eagles",
    "albatross",
    "holes_in_one",
    "birdie_or_better",
    "bogey_or_worse",
    "pars_or_better",
    "gir",
    "greens_in_regulation",
    "fairways_hit",
    "fairways_bunkers",
    "sand_saves",
    "sand_save_percentage",
    "total_putts",
    "putts_per_round",
    "longest_drive",
    "driving_distance",
    "driving_distance",
    "drive_distance",
    "driving_accuracy",
    "fairways_hit_percentage",
}

# Finish-based props
PGA_FINISH_STATS = {
    "top_5",
    "top_10",
    "top_20",
    "top_25",
    "top_30",
    "top_40",
    "make_cut",
    "cut_made",
    "miss_cut",
    "cut_line",
    "winner",
    "first_round_leader",
    "tournament_matchups",
    "group_winner",
    "stage_of_competition",
}

# DFS/Tournament props
PGA_DFS_STATS = {
    "fantasy_points",
    "draftkings_fantasy",
    "fanduel_fantasy",
    "strokes",
    "total_strokes",
    "score_to_par",
}

# =============================================================================
# FanDuel PGA Scoring Weights
# =============================================================================

# FanDuel uses a "Stroke +" system where each stroke is negative points
# but bonuses are given for birdies/eagles/better finish
FANDUEL_PGA_WEIGHTS = {
    # Standard (negative for strokes)
    "Strokes": -1.0,
    "Score to Par": 3.0,  # Bonus points for under par
    # Finish bonuses
    "Top 5": 10.0,
    "Top 10": 6.0,
    "Top 20": 3.0,
    "Made Cut": 1.5,
    "Missed Cut": 0.0,
    # Birdie-or-better bonus
    "Birdie or Better": 1.5,
    "Eagle or Better": 5.0,
    # Greens in Regulation
    "Greens in Regulation": 1.0,
    # Sand Save
    "Sand Save": 1.0,
}

# DraftKings PGA weights (for reference)
DRAFTKINGS_PGA_WEIGHTS = {
    # DraftKings uses a flat point system
    "Strokes": -0.9,
    "Birdie or Better": 2.0,
    "Eagle or Better": 8.0,
    "Albatross": 20.0,
    "Hole in One": 10.0,
    "Top 5": 10.0,
    "Top 10": 5.0,
    "Top 20": 3.0,
    "Made Cut": 2.0,
    "Missed Cut": -2.0,
    "Bogey or Worse": -1.0,
}

# =============================================================================
# PrizePicks PGA Tiers
# =============================================================================

PGA_TIER_PAYOUT_MODIFIERS = {
    "Standard": 1.0,
    "Major": 1.2,  # Higher payouts for majors
    "Fade": 1.1,  # Fade picks have boosted payouts
}

# =============================================================================
# Correlation Factors for PGA Props
# =============================================================================

# PGA has lower correlations since strokes are independent events
# But finishing position props can have correlations

PGA_SAME_PLAYER_CORRELATION = {
    ("birdies", "eagles"): 0.40,
    ("birdies", "pars"): 0.20,
    ("birdies", "bogeys"): -0.15,
    ("strokes_gained_putting", "birdies"): 0.25,
    ("strokes_gained_tee_to_green", "birdies"): 0.35,
    # Default
    "default": 0.10,
}

PGA_SAME_TOURNAMENT_CORRELATION = 0.05
PGA_DIFFERENT_TOURNAMENT_CORRELATION = 0.0

# =============================================================================
# Tournament/Injury Handling
# =============================================================================

# Golfers who WD (withdraw) typically void the leg
PGA_DNP_THRESHOLD = "Start of tournament"
PGA_WD_HANDLING = "leg_voided"

# =============================================================================
# Data Provider Settings
# =============================================================================

# PGA stat mappings for different APIs
PGA_API_STAT_MAPPING = {
    # Strokes gained
    "strokes_gained_total": "strokes_gained_total",
    "sg_total": "strokes_gained_total",
    "strokes gained: total": "strokes_gained_total",
    "strokes_gained_tee_to_green": "strokes_gained_tee_to_green",
    "sg_tee_to_green": "strokes_gained_tee_to_green",
    "strokes_gained_off_the_tee": "strokes_gained_off_the_tee",
    "sg_off_the_tee": "strokes_gained_off_the_tee",
    "strokes_gained_around_the_green": "strokes_gained_around_the_green",
    "sg_arg": "strokes_gained_around_the_green",
    "strokes_gained_putting": "strokes_gained_putting",
    "sg_putting": "strokes_gained_putting",
    # Traditional
    "birdies": "birdies",
    "bogeys": "bogeys",
    "pars": "pars",
    "doubles": "doubles",
    "eagles": "eagles",
    "albatross": "albatross",
    "holes_in_one": "holes_in_one",
    "greens_in_regulation": "gir",
    "gir": "gir",
    "fairways_hit": "fairways_hit",
    "driving_distance": "driving_distance",
    "drive_distance": "driving_distance",
    "total_putts": "total_putts",
    "putts_per_round": "putts_per_round",
    # Finish
    "top_5": "top_5",
    "top_10": "top_10",
    "top_20": "top_20",
    "cut_made": "cut_made",
    "make_cut": "cut_made",
    "missed_cut": "miss_cut",
    "winner": "winner",
}

# =============================================================================
# Utility Functions
# =============================================================================


def get_pga_stat_key(stat_name: str) -> str:
    """Normalize PGA stat name to standard key.

    Args:
        stat_name: Raw stat name from API/scraper

    Returns:
        Standardized stat key
    """
    if not stat_name:
        return ""

    s = stat_name.lower().strip()

    # Check direct mapping
    if s in PGA_API_STAT_MAPPING:
        return PGA_API_STAT_MAPPING[s]

    # Try without spaces/underscores/hyphens
    s_normalized = re.sub(r"[\s_\-]", "", s)
    for key, value in PGA_API_STAT_MAPPING.items():
        if re.sub(r"[\s_\-]", "", key) == s_normalized:
            return value

    return s


def is_pga_finish_prop(stat_type: str) -> bool:
    """Check if stat type is a finish-based prop.

    Args:
        stat_type: The stat type

    Returns:
        True if finish-based prop
    """
    finish_stats = {
        "top_5",
        "top_10",
        "top_20",
        "top_25",
        "top_30",
        "top_40",
        "make_cut",
        "cut_made",
        "miss_cut",
        "cut_line",
        "winner",
        "first_round_leader",
        "tournament_matchups",
    }
    normalized = stat_type.lower().replace(" ", "_").replace("-", "_")
    return normalized in finish_stats or stat_type.lower() in finish_stats


def is_pga_strokes_gained_stat(stat_type: str) -> bool:
    """Check if stat type is strokes gained.

    Args:
        stat_type: The stat type

    Returns:
        True if strokes gained stat
    """
    sg_stats = {
        "strokes_gained_total",
        "sg_total",
        "strokes_gained_tee_to_green",
        "sg_tee_to_green",
        "strokes_gained_off_the_tee",
        "sg_off_the_tee",
        "strokes_gained_around_the_green",
        "sg_arg",
        "strokes_gained_putting",
        "sg_putting",
        "strokes_gained_apr",
        "sg_apr",
    }
    normalized = stat_type.lower().replace(" ", "_").replace("-", "_")
    return normalized in sg_stats


def get_correlation_pga(
    stat1: str,
    stat2: str,
    same_player: bool = False,
    same_tournament: bool = True,
) -> float:
    """Get correlation factor between two PGA props.

    Args:
        stat1: First stat type
        stat2: Second stat type
        same_player: Whether same player
        same_tournament: Whether same tournament

    Returns:
        Correlation coefficient
    """
    if same_player:
        key = (stat1.lower(), stat2.lower())
        if key in PGA_SAME_PLAYER_CORRELATION:
            return PGA_SAME_PLAYER_CORRELATION[key]
        # Check reverse
        key_reverse = (stat2.lower(), stat1.lower())
        if key_reverse in PGA_SAME_PLAYER_CORRELATION:
            return PGA_SAME_PLAYER_CORRELATION[key_reverse]
        return PGA_SAME_PLAYER_CORRELATION["default"]

    if same_tournament:
        return PGA_SAME_TOURNAMENT_CORRELATION

    return PGA_DIFFERENT_TOURNAMENT_CORRELATION


def is_pga_poisson_stat(stat_type: str) -> bool:
    """Check if PGA stat should use Poisson distribution.

    Birdies, pars, bogeys tend to follow Poisson-like distributions.

    Args:
        stat_type: The stat type

    Returns:
        True if should use Poisson
    """
    poisson_stats = {
        "birdies",
        "bogeys",
        "pars",
        "doubles",
        "eagles",
        "holes_in_one",
        "sand_saves",
    }
    normalized = stat_type.lower().replace(" ", "_").replace("-", "_")
    return normalized in poisson_stats


def calculate_pga_fanduel_points(stats: dict) -> float:
    """Calculate FanDuel PGA fantasy points from stats.

    Args:
        stats: Dict with stat names and values

    Returns:
        FanDuel fantasy points
    """
    points = 0.0
    for stat, value in stats.items():
        stat_upper = stat.upper()
        weight = FANDUEL_PGA_WEIGHTS.get(stat_upper, 0.0)
        points += value * weight
    return points
