"""Fuzzy player name matching using rapidfuzz library.

Provides utilities for matching player names across different sportsbooks
where naming conventions may differ slightly.
"""

import re
import unicodedata
from typing import Optional, NamedTuple

from rapidfuzz import fuzz

# Known nickname mappings
NICKNAME_TO_CANONICAL: dict[str, str] = {
    "joker": "nikola jokic",
    "book": "devin booker",
    "booker": "devin booker",
    "spida": "donovan mitchell",
    "spida mitchell": "donovan mitchell",
    "the greek": "giannis antetokounmpo",
    "greek": "giannis antetokounmpo",
    "giannis": "giannis antetokounmpo",
    "bron": "lebron james",
    "lebron": "lebron james",
    "lj": "lebron james",
    "king james": "lebron james",
    "steph": "stephen curry",
    "steph curry": "stephen curry",
    "curry": "stephen curry",
    "klay": "klay thompson",
    "klay thompson": "klay thompson",
    "kd": "kevin durant",
    "durant": "kevin durant",
    "ad": "anthony davis",
    "a.d.": "anthony davis",
    "anthony": "anthony davis",
    "ja": "ja morant",
    "morant": "ja morant",
    "zp": "zion williamson",
    "zion": "zion williamson",
    "bb": "bradley beal",
    "beal": "bradley beal",
    "kj": "kj okonjo",
    "okonjo": "kj okonjo",
    "pg": "paul george",
    "paul george": "paul george",
    "luka": "luka doncic",
    "dončić": "luka doncic",
    "doncic": "luka doncic",
    "jk": "jayson tatum",
    "jt": "jayson tatum",
    "tatum": "jayson tatum",
    "scotty": "scottie barnes",
    "scottie": "scottie barnes",
    "barnes": "scottie barnes",
    "sw": "Scottie Barnes",
    "deuce": "deuce vaughn",
    "vaughn": "deuce vaughn",
    "pj": "pj tucker",
    "tucker": "pj tucker",
    "cp3": "chris paul",
    "chris paul": "chris paul",
    "bronny": "bronny james",
    # De'Anthony variations
    "deanthony": "deanthony melton",
    "de'anthony": "deanthony melton",
    "de anthony": "deanthony melton",
    # Tyreek vs Trayce (different players with similar names)
    "tyreke": "tyreke hill",
    "trayce": "trayce jackson-davis",
}


class MatchResult(NamedTuple):
    """Result of a fuzzy name match."""

    matched_name: str
    score: float
    is_nickname: bool


def normalize_for_matching(name: str) -> str:
    """Normalize name specifically for fuzzy matching.

    Args:
        name: Raw player name

    Returns:
        Normalized name string optimized for matching
    """
    if not name:
        return ""

    s = str(name).strip().lower()

    # Handle Unicode Accents
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")

    # Handle special apostrophes - remove them to combine names
    # e.g., "De'Anthony" -> "Deanthony"
    s = re.sub(r"['\u2019\u2018]", "", s)

    # Remove special characters except spaces and hyphens
    s = "".join(c if c.isalnum() or c in " -'" else "" for c in s)

    # Normalize whitespace
    s = " ".join(s.split())

    return s


def find_player(
    name: str,
    candidates: list[str],
    threshold: float = 80.0,
) -> Optional[MatchResult]:
    """Find best matching player name from a list of candidates.

    Uses rapidfuzz for fuzzy string matching. First checks for nickname
    matches, then falls back to fuzzy matching.

    Args:
        name: Name to match
        candidates: List of candidate names to match against
        threshold: Minimum similarity score (0-100) to consider a match

    Returns:
        MatchResult with matched name, score, and nickname flag,
        or None if no match above threshold

    Examples:
        >>> find_player("Nikola Jokic", ["Nikola Jokic", "Luka Doncic", "Giannis Antetokounmpo"])
        MatchResult(matched_name='Nikola Jokic', score=100.0, is_nickname=False)
    """
    if not name or not candidates:
        return None

    name_normalized = normalize_for_matching(name)

    # First check nickname mappings
    if name_normalized in NICKNAME_TO_CANONICAL:
        canonical = NICKNAME_TO_CANONICAL[name_normalized]
        # Look for canonical name in candidates
        for candidate in candidates:
            candidate_norm = normalize_for_matching(candidate)
            if canonical == candidate_norm:
                return MatchResult(candidate, 100.0, True)

    # Fuzzy match against all candidates
    # Use multiple rapidfuzz methods for better accuracy
    best_match = None
    best_score = 0.0

    for candidate in candidates:
        candidate_norm = normalize_for_matching(candidate)

        # Try different fuzzy matching strategies
        # 1. Token set ratio (good for word reordering)
        score1 = fuzz.token_set_ratio(name_normalized, candidate_norm)

        # 2. Partial ratio (good for partial matches)
        score2 = fuzz.partial_ratio(name_normalized, candidate_norm)

        # 3. Simple ratio (exact character similarity)
        score3 = fuzz.ratio(name_normalized, candidate_norm)

        # Take the maximum of all strategies
        score = max(score1, score2, score3)

        if score > best_score:
            best_score = score
            best_match = candidate

    if best_score >= threshold:
        return MatchResult(best_match, best_score, False)

    return None


def build_player_index(
    players: list[str],
    min_score: float = 70.0,
) -> dict[str, list[tuple[str, float]]]:
    """Build a lookup index for player names with fuzzy matches.

    Creates a dictionary mapping normalized names to lists of
    (original_name, score) tuples.

    Args:
        players: List of player names
        min_score: Minimum score to include in index

    Returns:
        Dict mapping normalized name -> [(player_name, score), ...]
    """
    index: dict[str, list[tuple[str, float]]] = {}

    for player in players:
        if not player:
            continue

        normalized = normalize_for_matching(player)

        # Add exact match
        if normalized not in index:
            index[normalized] = []
        index[normalized].append((player, 100.0))

        # Add to similar names' lists
        for existing_norm in list(index.keys()):
            score = fuzz.ratio(normalized, existing_norm)
            if score >= min_score:
                if normalized not in index:
                    index[normalized] = []
                index[normalized].append((player, score))

    return index


def find_player_indexed(
    name: str,
    index: dict[str, list[tuple[str, float]]],
    threshold: float = 80.0,
) -> Optional[MatchResult]:
    """Find a player in the pre-built index.

    Args:
        name: Name to match
        index: Pre-built player index from build_player_index
        threshold: Minimum similarity score

    Returns:
        MatchResult or None
    """
    if not name or not index:
        return None

    name_normalized = normalize_for_matching(name)

    # Direct lookup
    if name_normalized in index:
        best = max(index[name_normalized], key=lambda x: x[1])
        if best[1] >= threshold:
            return MatchResult(best[0], best[1], False)

    # Check nickname
    if name_normalized in NICKNAME_TO_CANONICAL:
        canonical = NICKNAME_TO_CANONICAL[name_normalized]
        if canonical in index:
            best = max(index[canonical], key=lambda x: x[1])
            if best[1] >= threshold:
                return MatchResult(best[0], best[1], True)

    # Fuzzy search in index
    best_match = None
    best_score = 0.0

    for norm_key, matches in index.items():
        score = fuzz.ratio(name_normalized, norm_key)
        if score > best_score:
            best_score = score
            best_match = matches[0][0]  # Get the original name

    if best_score >= threshold:
        return MatchResult(best_match, best_score, False)

    return None


def add_nickname_mapping(nickname: str, canonical: str) -> None:
    """Add a custom nickname mapping.

    Args:
        nickname: The nickname (e.g., "joker")
        canonical: The canonical player name (e.g., "nikola jokic")
    """
    NICKNAME_TO_CANONICAL[normalize_for_matching(nickname)] = normalize_for_matching(canonical)


def suggest_similar_names(
    name: str, candidates: list[str], limit: int = 5
) -> list[tuple[str, float]]:
    """Get list of similar names with scores.

    Args:
        name: Name to match
        candidates: List of candidate names
        limit: Maximum number of results

    Returns:
        List of (name, score) tuples sorted by score descending
    """
    if not name or not candidates:
        return []

    name_normalized = normalize_for_matching(name)

    results = []
    for candidate in candidates:
        candidate_norm = normalize_for_matching(candidate)
        score = max(
            fuzz.token_set_ratio(name_normalized, candidate_norm),
            fuzz.partial_ratio(name_normalized, candidate_norm),
            fuzz.ratio(name_normalized, candidate_norm),
        )
        results.append((candidate, score))

    results.sort(key=lambda x: x[1], reverse=True)
    return results[:limit]
