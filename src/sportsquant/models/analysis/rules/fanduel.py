"""FanDuel DFS rules, scoring, and payout structure.

This module contains official FanDuel DFS rules for accurate
evaluation of FanDuel picks and lineups.
"""

from dataclasses import dataclass

# =============================================================================
# NBA Scoring Rules
# =============================================================================

NBA_SCoring = {
    # Standard stats
    "DK Points": 1.0,
    "DraftKings Points": 1.0,
    "FanDuel Points": 1.0,
    # Main stats
    "Points": 1.0,
    "Rebounds": 1.2,
    "Assists": 1.5,
    "Blocked Shots": 3.0,
    "Steals": 3.0,
    "Turnovers": -1.0,
    # Double-Double Bonus
    "Double-Double": 3.0,
    "Triple-Double": 6.0,
    # Shooting bonuses
    "Field Goals Made": 0.0,  # No bonus in FanDuel
    "Three Pointers Made": 0.0,
    "Free Throws Made": 0.0,
    # Other
    "Minutes": 0.0,
    "Fantasy Score": 1.0,
}


# FanDuel NBA point multipliers
FANDUEL_NBA_WEIGHTS = {
    "PTS": 1.0,
    "REB": 1.2,
    "AST": 1.5,
    "BLK": 3.0,
    "STL": 3.0,
    "TOV": -1.0,
    "DD": 3.0,  # Double-Double bonus
    "TD": 6.0,  # Triple-Double bonus
}


# =============================================================================
# NFL Scoring Rules
# =============================================================================

FANDUEL_NFL_WEIGHTS = {
    # Passing
    "Passing Yards": 0.04,
    "Passing TDs": 4.0,
    "Interceptions": -1.0,
    "Sacks Taken": 0.0,
    # Rushing
    "Rushing Yards": 0.1,
    "Rushing TDs": 6.0,
    # Receiving
    "Receiving Yards": 0.1,
    "Receiving TDs": 6.0,
    "Receptions": 0.5,
    # Other
    "Fumbles Lost": -2.0,
    "2-PT Conversions": 2.0,
}


# =============================================================================
# MLB Scoring Rules
# =============================================================================

FANDUEL_MLB_WEIGHTS = {
    # Pitching
    "Pitching Outs": 2.5,  # 3 outs per IP
    "Strikeouts": 2.0,
    "Win": 4.0,
    "Earned Runs": -1.0,
    "Hits Allowed": -0.5,
    "Walks Allowed": -0.5,
    "Innings Pitched": 2.0,
    # Hitting
    "Singles": 3.0,
    "Doubles": 6.0,
    "Triples": 9.0,
    "Home Runs": 12.0,
    "Runs Batted In": 3.5,
    "Runs Scored": 3.2,
    "Walks": 3.0,
    "Stolen Bases": 5.0,
    # Catchers
    "Passed Balls": -0.5,
}


# =============================================================================
# NHL Scoring Rules
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
    # Goalies
    "Goalie Wins": 6.0,
    "Goalie Saves": 0.5,
    "Goalie Shutouts": 4.0,
    "Goals Against": -1.0,
}


# =============================================================================
# Salary Cap & Entry Rules
# =============================================================================


@dataclass
class SalaryCap:
    """FanDuel salary cap configuration."""

    NBA: int = 60000
    NFL: int = 60000
    MLB: int = 35000
    NHL: int = 55000
    NBA_Showdown: int = 50000


@dataclass
class PositionLimits:
    """FanDuel position limits per sport."""

    NBA: dict = None

    def __post_init__(self):
        self.NBA = {
            "PG": 1,
            "SG": 1,
            "SF": 1,
            "PF": 1,
            "C": 1,
            "G": 1,  # PG or SG
            "F": 1,  # SF or PF
            "UTIL": 2,  # Any position
        }


# Default salary cap
DEFAULT_SALARY_CAP = SalaryCap()
DEFAULT_POSITION_LIMITS = PositionLimits()


# =============================================================================
# Entry Types
# =============================================================================

ENTRY_TYPES = {
    "head_to_head": {
        "description": "1v1 against single opponent",
        "max_entries": 1,
        "payout": "Top 50% win 1.9x (approx)",
    },
    "50_50": {
        "description": "Top 50% cash",
        "max_entries": 150,
        "payout": "Top 50% win 1.8x",
    },
    "double_up": {
        "description": "Top 50% double your money",
        "max_entries": 150,
        "payout": "Top 50% win 2.0x",
    },
    "tournament": {
        "description": "GPP - top heavy payouts",
        "max_entries": 150,
        "payout": "1st place 10-30% of pool",
    },
    "multiplier": {
        "description": "Top 20% multiply your money",
        "max_entries": 150,
        "payout": "Top 20% win 2x-10x",
    },
    "showdown": {
        "description": "Single game DFS",
        "max_entries": 150,
        "payout": "Varies by contest",
    },
}


# =============================================================================
# Payout Structures
# =============================================================================

# 50/50 / Double Up - top 50% cash
PAYOUT_50_50 = {
    "winners": 0.5,  # Top 50%
    "payout": 2.0,  # 2x entry fee
}

# Tournament typical payout (%)
TOURNAMENT_PAYOUT_STRUCTURE = [
    (1, 0.20),  # 1st: 20%
    (2, 0.10),  # 2nd: 10%
    (3, 0.08),  # 3rd: 8%
    (4, 0.06),  # 4th: 6%
    (5, 0.05),  # 5th: 5%
    (6, 0.04),  # 6th: 4%
    (7, 0.03),  # 7th: 3%
    (8, 0.03),  # 8th: 3%
    (9, 0.02),  # 9th: 2%
    (10, 0.02),  # 10th: 2%
    # Remaining top 20% typically get 1.5-2x
]


# =============================================================================
# Picks Format Rules
# =============================================================================

PICKS_FORMAT = {
    "NBA": {
        "max_picks": 5,
        "games_required": 2,  # Must pick from at least 2 games
        "same_team_restriction": True,
        "payout_structure": {
            # Win % based on correct picks
            5: {5: 10.0, 4: 2.0},  # 5 picks: 5/5 = 10x, 4/5 = 2x
            4: {4: 5.0, 3: 1.0},
            3: {3: 3.0, 2: 0.5},
        },
    },
    "NFL": {
        "max_picks": 5,
        "games_required": 2,
        "same_team_restriction": True,
        "payout_structure": {
            5: {5: 10.0, 4: 2.0},
            4: {4: 5.0, 3: 1.0},
            3: {3: 3.0, 2: 0.5},
        },
    },
}


# =============================================================================
# Tie Handling
# =============================================================================

TIE_RULES = {
    "standard": "Ties push (stake returned)",
    "no_ties": "Ties lose (common in Showdown)",
}


# =============================================================================
# Utility Functions
# =============================================================================


def calculate_fanduel_points(stats: dict, sport: str = "NBA") -> float:
    """Calculate FanDuel fantasy points from stats.

    Args:
        stats: Dict with stat names and values
        sport: Sport ("NBA", "NFL", "MLB", "NHL")

    Returns:
        FanDuel fantasy points
    """
    weights = {
        "NBA": FANDUEL_NBA_WEIGHTS,
        "NFL": FANDUEL_NFL_WEIGHTS,
        "MLB": FANDUEL_MLB_WEIGHTS,
        "NHL": FANDUEL_NHL_WEIGHTS,
    }.get(sport, FANDUEL_NBA_WEIGHTS)

    points = 0.0
    for stat, value in stats.items():
        # Find matching weight
        stat_upper = stat.upper()
        weight = 0.0
        for key, w in weights.items():
            if key.upper() == stat_upper:
                weight = w
                break
        points += value * weight

    return points


def get_salary_cap(sport: str, contest_type: str = "standard") -> int:
    """Get salary cap for sport.

    Args:
        sport: Sport abbreviation
        contest_type: Type of contest

    Returns:
        Salary cap
    """
    caps = {
        "NBA": 60000,
        "NFL": 60000,
        "MLB": 35000,
        "NHL": 55000,
    }
    return caps.get(sport, 60000)


def get_payout_multiplier(entry_type: str, n_entries: int = 1) -> float:
    """Get payout multiplier for entry type.

    Args:
        entry_type: Type of entry
        n_entries: Number of entries

    Returns:
        Payout multiplier
    """
    payouts = {
        "head_to_head": 1.9,
        "50_50": 1.8,
        "double_up": 2.0,
        "tournament": 0.0,  # Highly variable
        "multiplier": 2.0,
    }
    return payouts.get(entry_type, 1.8)


def validate_lineup(
    players: list,
    sport: str,
    salary_cap: int,
    salary_by_player: dict,
) -> tuple[bool, str]:
    """Validate a FanDuel lineup.

    Args:
        players: List of player dicts with 'position' and 'salary'
        sport: Sport
        salary_cap: Salary cap limit
        salary_by_player: Dict mapping player name to salary

    Returns:
        (is_valid, error_message)
    """
    if not players:
        return False, "Empty lineup"

    # Check salary cap
    total_salary = sum(salary_by_player.get(p.get("name", ""), p.get("salary", 0)) for p in players)
    if total_salary > salary_cap:
        return False, f"Over salary cap: {total_salary} > {salary_cap}"

    # Check positions
    position_counts = {}
    for p in players:
        pos = p.get("position", "")
        position_counts[pos] = position_counts.get(pos, 0) + 1

    # Basic validation - would need sport-specific rules
    for pos, count in position_counts.items():
        if count > 1 and pos not in ("G", "F", "UTIL"):
            return False, f"Too many of position {pos}"

    return True, ""


# =============================================================================
# Picks Format Helpers
# =============================================================================


def calculate_picks_payout(n_picks: int, n_correct: int, sport: str = "NBA") -> float:
    """Calculate payout for FanDuel Picks format.

    Args:
        n_picks: Number of picks made
        n_correct: Number of correct picks
        sport: Sport

    Returns:
        Payout multiplier (0 if lost)
    """
    structure = PICKS_FORMAT.get(sport, PICKS_FORMAT["NBA"])["payout_structure"]
    payout_table = structure.get(n_picks, {})
    return payout_table.get(n_correct, 0.0)


def validate_picks(picks: list, sport: str = "NBA") -> tuple[bool, str]:
    """Validate FanDuel Picks selection.

    Args:
        picks: List of pick dicts
        sport: Sport

    Returns:
        (is_valid, error_message)
    """
    if not picks:
        return False, "No picks"

    n_picks = len(picks)
    structure = PICKS_FORMAT.get(sport, PICKS_FORMAT["NBA"])

    if n_picks > structure["max_picks"]:
        return False, f"Too many picks: {n_picks} > {structure['max_picks']}"

    # Check games
    teams = set()
    for pick in picks:
        team = pick.get("team", "")
        if team:
            teams.add(team)

    if structure["same_team_restriction"] and len(teams) < structure["games_required"]:
        return False, f"Must pick from at least {structure['games_required']} games"

    return True, ""
