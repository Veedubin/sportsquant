"""Underdog Fantasy rules, payouts, and configuration.

This module contains official Underdog Fantasy rules for accurate
evaluation of Higher/Lower props and Best Ball contests.
"""

from dataclasses import dataclass
from typing import Optional

# =============================================================================
# Higher/Lower Pick'em Rules
# =============================================================================

# Official payout structure for pick'em entries
# Based on Underdog's actual payout table
PICKEM_PAYOUT_8 = {
    (8, 8): 80.0,  # All 8 correct
    (8, 7): 8.0,  # 7 of 8
    (8, 6): 2.0,  # 6 of 8
}

PICKEM_PAYOUT_7 = {
    (7, 7): 50.0,
    (7, 6): 5.0,
    (7, 5): 1.5,
}

PICKEM_PAYOUT_6 = {
    (6, 6): 25.0,
    (6, 5): 4.0,
    (6, 4): 1.0,
}

PICKEM_PAYOUT_5 = {
    (5, 5): 12.0,
    (5, 4): 2.5,
    (5, 3): 0.5,
}

PICKEM_PAYOUT_4 = {
    (4, 4): 8.0,
    (4, 3): 2.0,
    (4, 2): 0.4,
}

PICKEM_PAYOUT_3 = {
    (3, 3): 5.0,
    (3, 2): 1.0,
}

PICKEM_PAYOUT_2 = {
    (2, 2): 3.0,
    (2, 1): 0.4,
}

# Combined payout structure dict
PICKEM_PAYOUTS = {
    2: PICKEM_PAYOUT_2,
    3: PICKEM_PAYOUT_3,
    4: PICKEM_PAYOUT_4,
    5: PICKEM_PAYOUT_5,
    6: PICKEM_PAYOUT_6,
    7: PICKEM_PAYOUT_7,
    8: PICKEM_PAYOUT_8,
}


# =============================================================================
# FLEX Play Rules
# =============================================================================

# FLEX allows 1-2 misses depending on pick count
FLEX_ALLOWED_MISSES = {
    2: 0,  # No misses
    3: 0,  # No misses
    4: 1,  # 1 miss allowed
    5: 1,  # 1 miss allowed
    6: 1,  # 1 miss allowed
    7: 2,  # 2 misses allowed
    8: 2,  # 2 misses allowed
}

# FLEX payout structure (from Underdog)
FLEX_PAYOUT_8 = {
    (8, 8): 40.0,  # All 8 correct
    (8, 7): 6.0,  # 1 miss
    (8, 6): 1.5,  # 2 misses
}

FLEX_PAYOUT_7 = {
    (7, 7): 25.0,
    (7, 6): 4.0,
    (7, 5): 1.0,
}

FLEX_PAYOUT_6 = {
    (6, 6): 15.0,
    (6, 5): 3.0,
    (6, 4): 0.8,
}

FLEX_PAYOUT_5 = {
    (5, 5): 8.0,
    (5, 4): 2.0,
    (5, 3): 0.5,
}

FLEX_PAYOUT_4 = {
    (4, 4): 5.0,
    (4, 3): 1.5,
    (4, 2): 0.4,
}

FLEX_PAYOUTS = {
    4: FLEX_PAYOUT_4,
    5: FLEX_PAYOUT_5,
    6: FLEX_PAYOUT_6,
    7: FLEX_PAYOUT_7,
    8: FLEX_PAYOUT_8,
}


# =============================================================================
# Best Ball Rules
# =============================================================================


@dataclass
class BestBallRules:
    """Rules for Underdog Best Ball contests."""

    # Roster size
    roster_size: int = 18  # NFL
    # Typical: 12 (NBA), 18 (NFL), 15 (MLB)

    # Draft rounds
    draft_rounds: int = 18  # NFL
    # Typically match roster size

    # Matchup weeks
    start_week: int = 1
    playoff_weeks: int = 4  # Weeks 15-18 typically

    # Scoring
    best_ball_scoring: str = "full"  # full, half, ppr

    # Warm roster
    warm_roster_size: Optional[int] = None  # None = no bench

    # DNP handling
    dnp_counts_zero: bool = True  # DNP players score 0


# Sport-specific Best Ball rules
BESTBALL_BY_SPORT = {
    "NFL": BestBallRules(roster_size=18, draft_rounds=18),
    "NBA": BestBallRules(roster_size=12, draft_rounds=12),
    "MLB": BestBallRules(roster_size=15, draft_rounds=15),
    "NHL": BestBallRules(roster_size=9, draft_rounds=9),
}


# =============================================================================
# DNP / Injury Handling
# =============================================================================

DNP_RULES = {
    # Higher/Lower pick'em
    "pickem": {
        "dnp_handling": "leg_voided",  # Leg voided, payout recalculated
        "live_game": "counts_if_play",  # Counts if player plays 1+ second
    },
    # Best Ball
    "bestball": {
        "dnp_handling": "scores_zero",  # DNP = 0 points
        "warm_roster": "not_allowed",  # No bench in most contests
    },
}


# =============================================================================
# Sportsbook Odds Integration
# =============================================================================

# Underdog includes sportsbook odds in their projections!
# This is a unique feature of Underdog

# Sportsbook odds are typically -110 to +150 range for standard props
# Used to validate fair line and calculate edge


# =============================================================================
# Pick'em Entry Rules
# =============================================================================


@dataclass
class PickemRules:
    """Rules for Underdog Higher/Lower pick'em."""

    # Pick limits
    min_picks: int = 2
    max_picks: int = 8

    # Same-game restrictions
    same_game_limit: Optional[int] = None  # None = no limit, but risk is higher

    # Player limits
    max_per_player: int = 1  # Can't pick same player twice

    # DNP handling
    dnp_voids_leg: bool = True
    dnp_recalculates_payout: bool = True

    # Ties
    tie_handling: str = "push"  # "push" or "loss"

    # Payout structure
    use_flex: bool = False  # FLEX allows misses

    def get_payout(self, n_picks: int, n_hits: int) -> float:
        """Get payout for n picks with n hits.

        Args:
            n_picks: Total picks
            n_hits: Correct picks

        Returns:
            Payout multiplier (0 if lost)
        """
        if self.use_flex:
            payouts = FLEX_PAYOUTS.get(n_picks, {})
        else:
            payouts = PICKEM_PAYOUTS.get(n_picks, {})

        return payouts.get((n_picks, n_hits), 0.0)

    def is_valid_pick_count(self, n_picks: int) -> bool:
        """Check if pick count is valid."""
        return self.min_picks <= n_picks <= self.max_picks


# Default rules
DEFAULT_PICKEM_RULES = PickemRules()


# =============================================================================
# Correlation Factors
# =============================================================================

# Correlation between props (for multi-pick entries)
# Used in EV calculations for correlated legs

CORRELATION_SAME_PLAYER = {
    # Same player, different stat
    ("PTS", "REB"): 0.12,
    ("PTS", "AST"): 0.18,
    ("PTS", "3PM"): 0.20,
    ("PRA", "PTS"): 0.35,
    ("PRA", "REB"): 0.30,
    ("PRA", "AST"): 0.32,
    # Default
    "default": 0.22,
}

CORRELATION_SAME_GAME = 0.06
CORRELATION_DIFFERENT_GAME = 0.02


# =============================================================================
# Utility Functions
# =============================================================================


def get_payout_table(n_picks: int, flex: bool = False) -> dict:
    """Get payout table for pick count.

    Args:
        n_picks: Number of picks
        flex: Whether using FLEX format

    Returns:
        Dict mapping (n_picks, n_hits) to payout multiplier
    """
    if flex:
        return FLEX_PAYOUTS.get(n_picks, {})
    return PICKEM_PAYOUTS.get(n_picks, {})


def calculate_payout(n_picks: int, n_hits: int, flex: bool = False) -> float:
    """Calculate payout for entry.

    Args:
        n_picks: Number of picks
        n_hits: Number of hits
        flex: Whether using FLEX format

    Returns:
        Payout multiplier
    """
    table = get_payout_table(n_picks, flex)
    return table.get((n_picks, n_hits), 0.0)


def get_flex_allowed_misses(n_picks: int) -> int:
    """Get number of misses allowed in FLEX for n picks.

    Args:
        n_picks: Number of picks

    Returns:
        Number of misses allowed
    """
    return FLEX_ALLOWED_MISSES.get(n_picks, 0)


def is_flex_win(n_picks: int, n_hits: int, flex: bool = True) -> bool:
    """Check if entry is a winner (FLEX allows misses).

    Args:
        n_picks: Number of picks
        n_hits: Number of hits
        flex: Whether using FLEX format

    Returns:
        True if winning entry
    """
    if not flex:
        return n_hits == n_picks

    allowed_misses = get_flex_allowed_misses(n_picks)
    return (n_picks - n_hits) <= allowed_misses


def calculate_flex_payout(n_picks: int, n_hits: int) -> float:
    """Calculate FLEX payout.

    Args:
        n_picks: Number of picks
        n_hits: Number of hits

    Returns:
        Payout multiplier
    """
    if n_picks < 4:
        # FLEX starts at 4 picks
        return 0.0

    allowed_misses = get_flex_allowed_misses(n_picks)
    misses = n_picks - n_hits

    if misses > allowed_misses:
        return 0.0

    return calculate_payout(n_picks, n_hits, flex=True)


def get_correlation(
    stat1: str,
    stat2: str,
    same_player: bool = False,
    same_game: bool = True,
) -> float:
    """Get correlation factor between two props.

    Args:
        stat1: First stat type
        stat2: Second stat type
        same_player: Whether same player
        same_game: Whether same game

    Returns:
        Correlation coefficient
    """
    if same_player:
        key = (stat1.upper(), stat2.upper())
        return CORRELATION_SAME_PLAYER.get(key, CORRELATION_SAME_PLAYER["default"])

    if same_game:
        return CORRELATION_SAME_GAME

    return CORRELATION_DIFFERENT_GAME


def validate_pickem_entry(
    picks: list,
    rules: Optional[PickemRules] = None,
) -> tuple[bool, str]:
    """Validate pick'em entry.

    Args:
        picks: List of pick dicts with player, team, stat, line, side
        rules: PickemRules instance

    Returns:
        (is_valid, error_message)
    """
    rules = rules or DEFAULT_PICKEM_RULES

    n_picks = len(picks)

    if not rules.is_valid_pick_count(n_picks):
        return False, f"Invalid pick count: {n_picks}"

    # Check same player
    players = [p.get("player", "") for p in picks]
    if len(players) != len(set(players)):
        return False, "Duplicate player picks"

    return True, ""
