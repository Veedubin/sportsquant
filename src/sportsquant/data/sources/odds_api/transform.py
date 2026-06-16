"""Odds API transform stub."""

import pandas as pd


def transform_props_response(responses: list, players: dict) -> pd.DataFrame:
    """Transform odds API response to DataFrame."""
    rows = []
    for resp in responses:
        for outcome in resp.get("outcomes", []):
            player_name = outcome.get("description", "Unknown")
            player_info = players.get(player_name)
            row = {
                "player_name": player_name,
                "player_id": player_info.player_id if player_info else None,
                "team_abbr": player_info.team_abbr if player_info else None,
                "opp_team_abbr": resp.get("opp_team_abbr"),
                "odds_over": outcome.get("odds_over"),
                "odds_under": outcome.get("odds_under"),
                "line": outcome.get("line"),
                "team_guess": outcome.get("team_guess"),
            }
            rows.append(row)
    return pd.DataFrame(rows)
