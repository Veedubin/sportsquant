"""Tests for odds API game lines parser (NFL)."""

from __future__ import annotations

import pandas as pd

from quantitative_sports.data.sources.odds_api.game_lines import (
    _COLUMNS,
    parse_game_lines_to_raw,
    parse_outrights_to_futures,
)


def _sample_event() -> dict:
    return {
        "id": "abc123",
        "sport_key": "americanfootball_nfl",
        "commence_time": "2026-09-07T20:20:00Z",
        "home_team": "Kansas City Chiefs",
        "away_team": "Baltimore Ravens",
        "bookmakers": [
            {
                "key": "draftkings",
                "title": "DraftKings",
                "last_update": "2026-09-07T18:00:00Z",
                "markets": [
                    {
                        "key": "h2h",
                        "outcomes": [
                            {"name": "Kansas City Chiefs", "price": -150},
                            {"name": "Baltimore Ravens", "price": 130},
                        ],
                    },
                    {
                        "key": "spreads",
                        "outcomes": [
                            {"name": "Kansas City Chiefs", "point": -3.5, "price": -110},
                            {"name": "Baltimore Ravens", "point": 3.5, "price": -110},
                        ],
                    },
                    {
                        "key": "totals",
                        "outcomes": [
                            {"name": "Over", "point": 47.5, "price": -110},
                            {"name": "Under", "point": 47.5, "price": -110},
                        ],
                    },
                ],
            },
            {
                "key": "fanduel",
                "title": "FanDuel",
                "last_update": "2026-09-07T18:01:00Z",
                "markets": [
                    {
                        "key": "h2h",
                        "outcomes": [
                            {"name": "Kansas City Chiefs", "price": -145},
                            {"name": "Baltimore Ravens", "price": 125},
                        ],
                    },
                    {
                        "key": "spreads",
                        "outcomes": [
                            {"name": "Kansas City Chiefs", "point": -3, "price": -115},
                            {"name": "Baltimore Ravens", "point": 3, "price": -105},
                        ],
                    },
                ],
            },
        ],
    }


def test_parse_game_lines_returns_canonical_schema_on_empty() -> None:
    df = parse_game_lines_to_raw([])
    assert df.empty
    assert list(df.columns) == _COLUMNS


def test_parse_game_lines_flattens_two_books() -> None:
    df = parse_game_lines_to_raw([_sample_event()])
    assert len(df) == 2
    assert set(df["source_id"]) == {"DraftKings", "FanDuel"}
    assert set(df.columns) == set(_COLUMNS)


def test_parse_game_lines_fills_moneyline_spread_and_total() -> None:
    df = parse_game_lines_to_raw([_sample_event()])
    dk = df[df["source_id"] == "DraftKings"].iloc[0]
    assert dk["ml_home"] == -150
    assert dk["ml_away"] == 130
    assert dk["spread_home"] == -3.5
    assert dk["spread_home_price"] == -110
    assert dk["spread_away_price"] == -110
    assert dk["total"] == 47.5
    assert dk["total_over_price"] == -110
    assert dk["total_under_price"] == -110


def test_parse_game_lines_handles_book_without_totals() -> None:
    df = parse_game_lines_to_raw([_sample_event()])
    fd = df[df["source_id"] == "FanDuel"].iloc[0]
    assert pd.isna(fd["total"])
    assert pd.isna(fd["total_over_price"])
    assert pd.isna(fd["total_under_price"])


def test_parse_game_lines_skips_malformed_events() -> None:
    bad = {"id": "x"}  # missing home_team / away_team
    df = parse_game_lines_to_raw([bad, _sample_event()])
    assert len(df) == 2  # only the valid event produced rows


def test_parse_outrights_to_futures_empty() -> None:
    df = parse_outrights_to_futures([], futures_market="super_bowl_winner")
    assert df.empty
    expected_cols = {
        "event_id",
        "commence_time",
        "futures_market",
        "outcome_name",
        "odds_american",
        "observed_at",
        "source_id",
    }
    assert set(df.columns) == expected_cols


def test_parse_outrights_to_futures_extracts_outcomes() -> None:
    event = {
        "id": "fut1",
        "commence_time": "2026-09-01T00:00:00Z",
        "home_team": None,
        "away_team": None,
        "bookmakers": [
            {
                "title": "DraftKings",
                "last_update": "2026-09-01T00:00:00Z",
                "markets": [
                    {
                        "key": "outrights",
                        "outcomes": [
                            {"name": "Kansas City Chiefs", "price": 600},
                            {"name": "Buffalo Bills", "price": 750},
                        ],
                    },
                    {
                        "key": "h2h",
                        "outcomes": [],  # should be ignored
                    },
                ],
            }
        ],
    }
    df = parse_outrights_to_futures([event], futures_market="super_bowl_winner")
    assert len(df) == 2
    assert set(df["outcome_name"]) == {"Kansas City Chiefs", "Buffalo Bills"}
    assert (df["futures_market"] == "super_bowl_winner").all()
