"""Sportsbook player-prop line schema definitions.

Canonical columns for NBA player prop lines (O/U markets).

The first 11 align with SPORTSBOOK_DATA_SPEC.md. Additional columns are allowed
(and preserved) for debugging and provenance.
"""

from __future__ import annotations

from typing import Final

PLAYER_PROP_COLUMNS: Final[tuple[str, ...]] = (
    "player_id",
    "player_name",
    "game_date",
    "game_id",
    "team_abbr",
    "opp_team_abbr",
    "line",
    "odds_over",
    "odds_under",
    "sportsbook",
    "timestamp",
    # Optional / provenance
    "market_type",
    "market_name",
    "source_url",
    "event_id",
)

PLAYER_PROP_REQUIRED_COLUMNS: Final[frozenset[str]] = frozenset(
    {
        "player_id",
        "player_name",
        "game_date",
        "team_abbr",
        "opp_team_abbr",
        "line",
        "odds_over",
        "odds_under",
        "sportsbook",
        "timestamp",
    }
)
