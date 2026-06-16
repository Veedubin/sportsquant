"""Tests for odds API transform (migrated from sports-analytics)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from sportsquant.data.sources.odds_api.schema import PLAYER_PROP_REQUIRED_COLUMNS
from sportsquant.data.sources.odds_api.transform import transform_props_response
from sportsquant.data.sources.odds_api.types import PlayerInfo


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "odds_api_response.json"


def test_transform_props_response_pairs_outcomes_and_required_columns() -> None:
    responses = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    players = {
        "lebron_james": PlayerInfo(player_id=23, player_name="LeBron James", team_abbr="LAL")
    }

    df = transform_props_response(responses, players)

    assert not df.empty
    missing = set(PLAYER_PROP_REQUIRED_COLUMNS) - set(df.columns)
    assert not missing

    james_row = df[df["player_name"] == "LeBron James"].iloc[0]
    assert james_row["odds_over"] == -110
    assert james_row["odds_under"] == -105
    assert james_row["player_id"] == 23
    assert james_row["team_abbr"] == "LAL"
    assert james_row["opp_team_abbr"] == "BOS"


def test_transform_marks_unmatched_players_as_unknown() -> None:
    responses = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    players: dict[str, PlayerInfo] = {}

    df = transform_props_response(responses, players)

    rookie_row = df[df["player_name"] == "Unknown Rookie"].iloc[0]
    assert pd.isna(rookie_row["player_id"])
    assert pd.isna(rookie_row["team_abbr"])
    assert pd.isna(rookie_row["opp_team_abbr"])
    assert bool(rookie_row.get("team_guess"))
