"""DraftKings utility functions stub."""

from typing import Optional


def normalize_odds_string(odds: Optional[str]) -> Optional[str]:
    """Normalize odds string (handle Unicode minus)."""
    if odds is None:
        return None
    if not odds:
        return ""
    return odds.replace("\u2212", "-")


def american_to_prob(odds) -> float:
    """Convert American odds to implied probability."""
    if odds is None:
        return 0.0
    if isinstance(odds, str):
        if not odds or odds == "invalid":
            return 0.0
        odds = odds.replace("\u2212", "-")
        try:
            odds = float(odds)
        except (ValueError, TypeError):
            return 0.0
    odds = float(odds)
    if odds < 0:
        return abs(odds) / (abs(odds) + 100)
    else:
        return 100 / (odds + 100)


def american_to_decimal(odds) -> float:
    """Convert American odds to decimal odds."""
    if odds is None:
        return 0.0
    odds = float(odds)
    if odds < 0:
        return 1 + 100 / abs(odds)
    else:
        return 1 + odds / 100


def prob_to_american(prob: float) -> float:
    """Convert probability to American odds."""
    if prob >= 1.0:
        return float("inf")
    if prob <= 0.0:
        return float("-inf")
    if prob > 0.5:
        return -100 * prob / (1 - prob)
    else:
        return 100 * (1 - prob) / prob


def remove_vig_two_way(p_over: float, p_under: float) -> float:
    """Remove vig from two-way market."""
    total = p_over + p_under
    if total <= 0:
        return float("nan")
    return p_over / total


def map_subcategory_id_to_market_key(subcategory_id) -> Optional[str]:
    """Map DraftKings subcategory ID to market key."""
    mapping = {
        12488: "player_points",
        12492: "player_rebounds",
        12495: "player_assists",
        12497: "player_threes",
    }
    try:
        return mapping.get(int(subcategory_id))
    except (ValueError, TypeError):
        return None


def map_market_name_to_key(market_name: Optional[str]) -> Optional[str]:
    """Map market name to market key."""
    if market_name is None:
        return None
    name = market_name.lower()
    if "points" in name and "o/u" in name:
        return "player_points"
    if "rebounds" in name and "o/u" in name:
        return "player_rebounds"
    if "assists" in name and "o/u" in name:
        return "player_assists"
    if "three" in name and "o/u" in name:
        return "player_threes"
    if "steals" in name and "blocks" in name:
        return "player_sb"
    if "triple double" in name:
        return "player_triple_double"
    if "double double" in name:
        return "player_double_double"
    return None


def normalize_player_name(name: Optional[str]) -> Optional[str]:
    """Normalize player name."""
    if name is None:
        return None
    name = name.strip()
    if not name:
        return None
    import re

    name = name.lower().replace("'", "")
    name = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b\.?", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\s+", " ", name).strip()
    return name
