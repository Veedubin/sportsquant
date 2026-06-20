"""Tests for middling detection."""

from __future__ import annotations

import pandas as pd

from quantitative_sports.core.betting.strategies.middling import (
    detect_middles,
    detect_spread_middles,
    detect_total_middles,
)


def test_detect_spread_middles_empty_input() -> None:
    df = pd.DataFrame()
    out = detect_spread_middles(df)
    assert out.empty
    assert "market" in out.columns
    assert "middle_points" in out.columns


def test_detect_spread_middles_finds_wide_gap() -> None:
    df = pd.DataFrame(
        [
            {"game_id": "G1", "spread_home": -3.5, "source_id": "BookA"},
            {"game_id": "G1", "spread_home": -7.0, "source_id": "BookB"},
        ]
    )
    out = detect_spread_middles(df, min_middle_points=1.0)
    assert len(out) == 1
    row = out.iloc[0]
    assert row["market"] == "spread"
    assert row["low_line"] == -7.0  # away best (home favored most)
    assert row["low_book"] == "BookB"
    assert row["high_line"] == -3.5
    assert row["high_book"] == "BookA"
    assert row["middle_points"] == 3.5


def test_detect_spread_middles_below_threshold() -> None:
    df = pd.DataFrame(
        [
            {"game_id": "G1", "spread_home": -3.5, "source_id": "BookA"},
            {"game_id": "G1", "spread_home": -4.0, "source_id": "BookB"},
        ]
    )
    out = detect_spread_middles(df, min_middle_points=1.0)
    assert out.empty


def test_detect_total_middles_finds_wide_gap() -> None:
    df = pd.DataFrame(
        [
            {"game_id": "G1", "total": 41.5, "source_id": "BookA"},
            {"game_id": "G1", "total": 48.0, "source_id": "BookB"},
        ]
    )
    out = detect_total_middles(df, min_middle_points=1.0)
    assert len(out) == 1
    row = out.iloc[0]
    assert row["market"] == "total"
    assert row["low_line"] == 41.5
    assert row["high_line"] == 48.0
    assert row["middle_points"] == 6.5


def test_detect_middles_combines_spread_and_total() -> None:
    df = pd.DataFrame(
        [
            {"game_id": "G1", "spread_home": -3.5, "total": None, "source_id": "BookA"},
            {"game_id": "G1", "spread_home": -7.0, "total": None, "source_id": "BookB"},
            {"game_id": "G1", "spread_home": None, "total": 41.5, "source_id": "BookA"},
            {"game_id": "G1", "spread_home": None, "total": 48.0, "source_id": "BookB"},
        ]
    )
    out = detect_middles(df, min_middle_points=1.0)
    assert len(out) == 2
    assert set(out["market"]) == {"spread", "total"}


def test_detect_middles_returns_empty_schema_when_nothing() -> None:
    df = pd.DataFrame(
        [
            {"game_id": "G1", "spread_home": -3.5, "total": 47.0, "source_id": "Only"},
        ]
    )
    out = detect_middles(df, min_middle_points=1.0)
    assert out.empty
    assert "market" in out.columns


def test_detect_spread_middles_drops_null_lines() -> None:
    df = pd.DataFrame(
        [
            {"game_id": "G1", "spread_home": -3.5, "source_id": "BookA"},
            {"game_id": "G1", "spread_home": None, "source_id": "BookB"},
        ]
    )
    out = detect_spread_middles(df, min_middle_points=1.0)
    assert out.empty  # only one book with a real line → no middle
