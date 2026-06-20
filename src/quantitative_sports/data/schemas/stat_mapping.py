"""Bidirectional stat type mapping across all sportsbook sites.

Canonical keys are the standard format used internally:
- player_points, player_rebounds, player_assists, player_threes
- player_pra (points+rebounds+assists), player_pr, player_pa, player_ra
- player_steals, player_blocks, player_sb (steals+blocks)
- player_turnovers, player_fantasy_score
- player_double_double, player_triple_double

Each site has its own key format that maps to/from canonical keys.
"""

from typing import Optional

# Canonical stat keys used internally
CANONICAL_KEYS = [
    "player_points",
    "player_rebounds",
    "player_assists",
    "player_threes",
    "player_pra",
    "player_pr",
    "player_pa",
    "player_ra",
    "player_steals",
    "player_blocks",
    "player_sb",
    "player_turnovers",
    "player_fantasy_score",
    "player_double_double",
    "player_triple_double",
    # Period-specific props
    "player_period1_points",
    "player_period1_rebounds",
    "player_period1_assists",
    "player_period1_pra",
    "player_period1_threes",
    "player_firsthalf_points",
    "player_firsthalf_threes",
    "player_firsthalf_pra",
    "player_first5min_points",
    "player_first5min_pra",
    # Additional stats
    "player_minutes",
    "player_off_rebounds",
    "player_def_rebounds",
    "player_field_goals",
    "player_fg_pct",
    "player_free_throws",
    "player_ft_pct",
    "player_three_pt_attempts",
    "player_personal_fouls",
    "player_first_fg_attempt",
    "player_first_three_attempt",
    "player_first_to_10",
    # Game-level props
    "game_high_scorer",
    "team_high_scorer",
]

# PrizePicks stat type to canonical mapping
PRIZEPICKS_KEYS: dict[str, str] = {
    "Points": "player_points",
    "Rebounds": "player_rebounds",
    "Assists": "player_assists",
    "Threes": "player_threes",
    "Pts + Rebs + Asts": "player_pra",
    "Pts + Rebs": "player_pr",
    "Pts + Asts": "player_pa",
    "Rebs + Asts": "player_ra",
    "Steals": "player_steals",
    "Blocks": "player_blocks",
    "Stls + Blks": "player_sb",
    "Turnovers": "player_turnovers",
    "Fantasy Score": "player_fantasy_score",
    "Double Double": "player_double_double",
    "Triple Double": "player_triple_double",
    # Period props
    "Q1 Points": "player_period1_points",
    "Q1 Rebounds": "player_period1_rebounds",
    "Q1 Assists": "player_period1_assists",
    "Q1 Pts + Rebs + Asts": "player_period1_pra",
    "Q1 Threes": "player_period1_threes",
    "First Half Pts": "player_firsthalf_points",
    "First Half Pts + Rebs + Asts": "player_firsthalf_pra",
}

# Reverse mapping for PrizePicks (canonical -> PP)
_PRIZEPICKS_REVERSE: dict[str, str] = {v: k for k, v in PRIZEPICKS_KEYS.items()}

# FanDuel stat key to canonical mapping
# FanDuel uses player_points, player_rebounds, etc. (same as canonical)
FANDUEL_KEYS: dict[str, str] = {
    "player_points": "player_points",
    "player_rebounds": "player_rebounds",
    "player_assists": "player_assists",
    "player_threes": "player_threes",
    "player_pra": "player_pra",
    "player_pr": "player_pr",
    "player_pa": "player_pa",
    "player_ra": "player_ra",
    "player_steals": "player_steals",
    "player_blocks": "player_blocks",
    "player_sb": "player_sb",
    "player_turnovers": "player_turnovers",
    "player_fantasy_score": "player_fantasy_score",
    "player_double_double": "player_double_double",
    "player_triple_double": "player_triple_double",
    # Period props
    "player_period1_points": "player_period1_points",
    "player_period1_rebounds": "player_period1_rebounds",
    "player_period1_assists": "player_period1_assists",
    "player_period1_pra": "player_period1_pra",
    "player_firsthalf_points": "player_firsthalf_points",
    "player_firsthalf_pra": "player_firsthalf_pra",
}

# FanDuel reverse mapping
_FANDUEL_REVERSE: dict[str, str] = {v: k for k, v in FANDUEL_KEYS.items()}

# Underdog stat type to canonical mapping
# Underdog uses snake_case with underscores and combined stats
UNDERDOG_KEYS: dict[str, str] = {
    # Standard stats
    "points": "player_points",
    "rebounds": "player_rebounds",
    "assists": "player_assists",
    "three_pointers_made": "player_threes",
    "three_pointers": "player_threes",
    "three_pointersMade": "player_threes",
    "three_points_made": "player_threes",
    # Combined stats
    "points_rebounds_assists": "player_pra",
    "points_rebounds": "player_pr",
    "points_assists": "player_pa",
    "rebounds_assists": "player_ra",
    # Shortened combos
    "pts_rebs_asts": "player_pra",
    "pts_rebs": "player_pr",
    "pts_asts": "player_pa",
    "rebs_asts": "player_ra",
    "pra": "player_pra",
    "pr": "player_pr",
    "pa": "player_pa",
    "ra": "player_ra",
    # Other stats
    "steals": "player_steals",
    "blocks": "player_blocks",
    "steals_blocks": "player_sb",
    "blks_stls": "player_sb",
    "sb": "player_sb",
    "turnovers": "player_turnovers",
    "fantasy_points": "player_fantasy_score",
    "fantasy_score": "player_fantasy_score",
    # Period-specific
    "period_1_points": "player_period1_points",
    "period_1_rebounds": "player_period1_rebounds",
    "period_1_assists": "player_period1_assists",
    "period_1_pts_rebs_asts": "player_period1_pra",
    "period_1_three_points_made": "player_period1_threes",
    "period_1_2_points": "player_firsthalf_points",
    "period_1_2_pts_rebs_asts": "player_firsthalf_pra",
    "period_1_first_5_min_pts": "player_first5min_points",
    "period_1_first_5_min_pra": "player_first5min_pra",
    # Additional
    "ts": "player_threes",
    "fgm": "player_field_goals",
    "fgp": "player_fg_pct",
    "ftm": "player_free_throws",
    "ftp": "player_ft_pct",
    "3pa": "player_three_pt_attempts",
    "tpm": "player_threes",
    "double_double": "player_double_double",
    "double_doubles": "player_double_double",
    "triple_double": "player_triple_double",
    "triple_doubles": "player_triple_double",
}

# Underdog reverse mapping
_UNDERDOG_REVERSE: dict[str, str] = {v: k for k, v in UNDERDOG_KEYS.items()}

# DraftKings stat key to canonical mapping
# DraftKings uses subCategoryId for categorization, but market names are similar
DRAFTKINGS_KEYS: dict[str, str] = {
    # Direct mappings (market names)
    "player_points": "player_points",
    "player_rebounds": "player_rebounds",
    "player_assists": "player_assists",
    "player_threes": "player_threes",
    "player_pra": "player_pra",
    "player_pr": "player_pr",
    "player_pa": "player_pa",
    "player_ra": "player_ra",
    "player_steals": "player_steals",
    "player_blocks": "player_blocks",
    "player_sb": "player_sb",
    "player_turnovers": "player_turnovers",
    "player_fantasy_score": "player_fantasy_score",
    "player_double_double": "player_double_double",
    "player_triple_double": "player_triple_double",
    # subCategoryId mappings (numeric IDs used in API)
    "12488": "player_points",
    "12492": "player_rebounds",
    "12495": "player_assists",
    "12497": "player_threes",
    "13781": "player_sb",
    "13759": "player_triple_double",
    "13762": "player_double_double",
}

# DraftKings reverse mapping
_DRAFTKINGS_REVERSE: dict[str, str] = {v: k for k, v in DRAFTKINGS_KEYS.items() if not k.isdigit()}

# Site name constants
SITES = ["prizepicks", "fanduel", "underdog", "draftkings"]

# Site key mappings lookup
SITE_KEY_MAPPINGS: dict[str, dict[str, str]] = {
    "prizepicks": PRIZEPICKS_KEYS,
    "fanduel": FANDUEL_KEYS,
    "underdog": UNDERDOG_KEYS,
    "draftkings": DRAFTKINGS_KEYS,
}

# Reverse mappings lookup
SITE_REVERSE_MAPPINGS: dict[str, dict[str, str]] = {
    "prizepicks": _PRIZEPICKS_REVERSE,
    "fanduel": _FANDUEL_REVERSE,
    "underdog": _UNDERDOG_REVERSE,
    "draftkings": _DRAFTKINGS_REVERSE,
}


def to_canonical(site_key: str, site: str) -> Optional[str]:
    """Convert a site-specific stat key to canonical key.

    Args:
        site_key: The stat key used by the site (e.g., "Points", "player_points")
        site: The site name (prizepicks, fanduel, underdog, draftkings)

    Returns:
        Canonical key (e.g., "player_points") or None if not mapped

    Examples:
        >>> to_canonical("Points", "prizepicks")
        'player_points'
        >>> to_canonical("pts_rebs_asts", "underdog")
        'player_pra'
        >>> to_canonical("12488", "draftkings")
        'player_points'
    """
    if site not in SITE_KEY_MAPPINGS:
        return None

    mapping = SITE_KEY_MAPPINGS[site]

    # Direct lookup
    if site_key in mapping:
        return mapping[site_key]

    # Case-insensitive lookup for PrizePicks
    if site == "prizepicks":
        site_key_lower = site_key.lower()
        for k, v in mapping.items():
            if k.lower() == site_key_lower:
                return v

    return None


def from_canonical(canonical_key: str, site: str) -> Optional[str]:
    """Convert a canonical key to site-specific stat key.

    Args:
        canonical_key: The canonical stat key (e.g., "player_points")
        site: The site name (prizepicks, fanduel, underdog, draftkings)

    Returns:
        Site-specific key or None if not mapped

    Examples:
        >>> from_canonical("player_points", "prizepicks")
        'Points'
        >>> from_canonical("player_pra", "underdog")
        'pts_rebs_asts'
        >>> from_canonical("player_points", "fanduel")
        'player_points'
    """
    if site not in SITE_REVERSE_MAPPINGS:
        return None

    reverse_mapping = SITE_REVERSE_MAPPINGS[site]
    return reverse_mapping.get(canonical_key)


def get_all_site_keys(canonical_key: str) -> dict[str, Optional[str]]:
    """Get all site-specific keys for a canonical key.

    Args:
        canonical_key: The canonical stat key (e.g., "player_points")

    Returns:
        Dict mapping site name to site-specific key (None if not available)

    Examples:
        >>> get_all_site_keys("player_points")
        {'prizepicks': 'Points', 'fanduel': 'player_points', 'underdog': 'points', 'draftkings': 'player_points'}
    """
    result = {}
    for site in SITES:
        result[site] = from_canonical(canonical_key, site)
    return result


def is_canonical(key: str) -> bool:
    """Check if a key is a canonical stat key.

    Args:
        key: The stat key to check

    Returns:
        True if the key is a canonical stat key
    """
    return key in CANONICAL_KEYS


def get_canonical_stats() -> list[str]:
    """Get list of all canonical stat keys.

    Returns:
        List of canonical stat keys
    """
    return CANONICAL_KEYS.copy()
