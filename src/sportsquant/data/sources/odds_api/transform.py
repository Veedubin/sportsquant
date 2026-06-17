"""Odds API transform — converts raw API responses to normalized DataFrames.

Handles prop betting responses from The Odds API, pairing Over/Under
outcomes into single rows and resolving player identity via a lookup
dictionary.
"""

from __future__ import annotations

import re
from typing import Any

import numpy as np
import pandas as pd

from sportsquant.data.sources.odds_api.types import PlayerInfo


def _normalize_player_key(name: str) -> str:
    """Normalize a player name to a lowercase underscore key for lookup."""
    return re.sub(r"[^a-z0-9]", "_", name.lower()).strip("_")


def transform_props_response(
    responses: list[dict[str, Any]], players: dict[str, PlayerInfo]
) -> pd.DataFrame:
    """Transform odds API prop responses to a normalized DataFrame.

    Each response dict represents a prop market and may contain outcomes
    structured either as:

    1. **Bookmaker format** — ``bookmakers → markets → outcomes`` with
       Over/Under pairs identified by ``name``.
    2. **Flat format** — top-level ``outcomes`` list with Over/Under pairs.

    Outcomes are grouped by player description and paired into a single
    row with ``odds_over`` and ``odds_under`` columns.

    The ``players`` dict maps normalised keys (e.g. ``"lebron_james"``)
    to :class:`PlayerInfo`. When a match is found the canonical
    ``player_name`` from ``PlayerInfo`` replaces the raw description.
    Unmatched players retain their description and get ``NaN`` for
    ``player_id``, ``team_abbr``, and ``opp_team_abbr``.

    Parameters
    ----------
    responses:
        List of raw odds API response dicts.
    players:
        Mapping of normalised player keys to :class:`PlayerInfo`.

    Returns
    -------
    DataFrame with ``PLAYER_PROP_REQUIRED_COLUMNS`` plus ``team_guess``.
    """
    rows: list[dict[str, Any]] = []

    for resp in responses:
        opp_team_abbr = resp.get("opp_team_abbr")

        # Collect outcomes from bookmakers/markets structure
        all_outcomes: list[dict[str, Any]] = []
        for bookmaker in resp.get("bookmakers", []):
            for market in bookmaker.get("markets", []):
                for outcome in market.get("outcomes", []):
                    all_outcomes.append(outcome)

        # Fallback to top-level outcomes
        if not all_outcomes:
            all_outcomes = resp.get("outcomes", [])

        # Group outcomes by player (description) then pair Over/Under
        player_outcomes: dict[str, dict[str, dict[str, Any]]] = {}
        for outcome in all_outcomes:
            raw_name = outcome.get("description", "Unknown")
            side = outcome.get("name", "")
            if raw_name not in player_outcomes:
                player_outcomes[raw_name] = {}
            player_outcomes[raw_name][side] = outcome

        for raw_name, sides in player_outcomes.items():
            over = sides.get("Over", {})
            under = sides.get("Under", {})
            # Use whichever side has data for shared fields
            primary = over or under
            line = primary.get("point")
            team_guess = primary.get("team_guess")

            # Resolve player via normalised key
            key = _normalize_player_key(raw_name)
            player_info: PlayerInfo | None = players.get(key)

            # Use canonical name when available, raw description otherwise
            player_name = player_info.player_name if player_info else raw_name

            row: dict[str, Any] = {
                "player_name": player_name,
                "player_id": player_info.player_id if player_info else np.nan,
                "team_abbr": player_info.team_abbr if player_info else np.nan,
                # For matched players we know the opponent; for unmatched we don't.
                "opp_team_abbr": opp_team_abbr if player_info else np.nan,
                "odds_over": over.get("price"),
                "odds_under": under.get("price"),
                "line": line,
                "team_guess": team_guess,
            }
            rows.append(row)

    return pd.DataFrame(rows)
