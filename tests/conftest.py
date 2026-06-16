"""Pytest fixtures for sportsquant tests."""

import sqlite3
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Sample Projections
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_projections() -> list[dict[str, Any]]:
    """Sample PrizePicks projection dicts."""
    return [
        {
            "id": "pp_001",
            "player_name": "Jayson Tatum",
            "team_name": "Boston Celtics",
            "team_abbreviation": "BOS",
            "stat_type": "pts",
            "stat_display_name": "Points",
            "line_score": 28.5,
            "league_id": "8",
            "league_name": "NBA",
            "status": "active",
            "start_time": "2026-04-19T19:00:00Z",
            "description": "Jayson Tatum Points",
            "tier": "standard",
            "is_live": False,
        },
        {
            "id": "pp_002",
            "player_name": "Jaylen Brown",
            "team_name": "Boston Celtics",
            "team_abbreviation": "BOS",
            "stat_type": "reb",
            "stat_display_name": "Rebounds",
            "line_score": 6.5,
            "league_id": "8",
            "league_name": "NBA",
            "status": "active",
            "start_time": "2026-04-19T19:00:00Z",
            "description": "Jaylen Brown Rebounds",
            "tier": "standard",
            "is_live": False,
        },
        {
            "id": "pp_003",
            "player_name": "Stephen Curry",
            "team_name": "Golden State Warriors",
            "team_abbreviation": "GSW",
            "stat_type": "pts",
            "stat_display_name": "Points",
            "line_score": 32.5,
            "league_id": "8",
            "league_name": "NBA",
            "status": "active",
            "start_time": "2026-04-19T20:00:00Z",
            "description": "Stephen Curry Points",
            "tier": "demon",
            "is_live": False,
        },
    ]


# ---------------------------------------------------------------------------
# Sample Market Data
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_market_data() -> pd.DataFrame:
    """Sample per_book_df DataFrame with market odds."""
    return pd.DataFrame(
        [
            {
                "event_id": "evt_001",
                "market_key": "player_points",
                "player_name_norm": "jayson tatum",
                "book": "fanduel",
                "line": 28.5,
                "odds_american": -110,
                "p_over_devig": 0.52,
            },
            {
                "event_id": "evt_001",
                "market_key": "player_points",
                "player_name_norm": "jayson tatum",
                "book": "draftkings",
                "line": 28.5,
                "odds_american": -105,
                "p_over_devig": 0.51,
            },
            {
                "event_id": "evt_002",
                "market_key": "player_rebounds",
                "player_name_norm": "jaylen brown",
                "book": "fanduel",
                "line": 6.5,
                "odds_american": -115,
                "p_over_devig": 0.48,
            },
            {
                "event_id": "evt_002",
                "market_key": "player_rebounds",
                "player_name_norm": "jaylen brown",
                "book": "draftkings",
                "line": 6.5,
                "odds_american": -120,
                "p_over_devig": 0.47,
            },
        ]
    )


# ---------------------------------------------------------------------------
# Sample Player Game Logs
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_player_logs_dict() -> list[dict[str, Any]]:
    """Sample game logs in dict format."""
    return [
        {"points": 28},
        {"points": 35},
        {"points": 22},
        {"points": 31},
        {"points": 29},
        {"points": 33},
        {"points": 27},
        {"points": 30},
        {"points": 25},
        {"points": 32},
    ]


@pytest.fixture
def sample_player_logs_int() -> list[int]:
    """Sample game logs as plain integers."""
    return [28, 35, 22, 31, 29, 33, 27, 30, 25, 32]


@pytest.fixture
def sample_player_logs_mixed() -> list[Any]:
    """Mixed valid/invalid game log formats."""
    return [
        {"points": 28},
        35,
        {"points": 22},
        "invalid",
        {"rebounds": 8},
        None,
        {"points": 31},
        29,
        {},
        {"points": 33},
    ]


# ---------------------------------------------------------------------------
# Temporary Database
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> Path:
    """Temporary SQLite database path."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE projections (id TEXT, player_name TEXT, stat_type TEXT, line_score REAL, start_time TEXT)"
    )
    conn.execute(
        "CREATE TABLE markets (id INTEGER, event_id TEXT, market_key TEXT, runner_name TEXT, line REAL)"
    )
    conn.execute(
        "CREATE TABLE player_mapping (id INTEGER, canonical_name TEXT, pp_name TEXT, fd_name TEXT, ud_name TEXT, dk_name TEXT)"
    )
    conn.commit()
    conn.close()
    return db_path


# ---------------------------------------------------------------------------
# Mock Storage
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_dk_storage() -> MagicMock:
    """Mock DraftKings storage."""
    mock = MagicMock()
    mock.to_market_dataframe.return_value = pd.DataFrame(
        [
            {
                "event_id": "evt_001",
                "market_key": "player_points",
                "player_name_norm": "stephen curry",
                "line": 10.5,
                "book": "draftkings",
                "p_over_devig": 0.52,
            }
        ]
    )
    return mock


@pytest.fixture
def mock_fd_storage() -> MagicMock:
    """Mock FanDuel storage."""
    mock = MagicMock()
    mock.to_market_dataframe.return_value = pd.DataFrame(
        [
            {
                "event_id": "evt_002",
                "market_key": "player_points",
                "player_name_norm": "stephen curry",
                "line": 10.0,
                "odds_american": 120,
            }
        ]
    )
    return mock


# ---------------------------------------------------------------------------
# Sports-Platform Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_player_stats():
    """Sample player stats data for testing."""
    return {
        "headers": ["PLAYER_ID", "PLAYER_NAME", "TEAM_ID", "PTS", "REB", "AST"],
        "rowSet": [
            [2544, "LeBron James", 1610612747, 25.5, 7.0, 8.0],
            [2546, "Anthony Davis", 1610612747, 24.0, 10.5, 3.0],
        ],
    }


@pytest.fixture
def sample_game_results():
    """Sample game results data for testing."""
    return {
        "headers": [
            "GAME_ID",
            "GAME_DATE",
            "HOME_TEAM_ID",
            "AWAY_TEAM_ID",
            "HOME_SCORE",
            "AWAY_SCORE",
        ],
        "rowSet": [
            ["0022400001", "2024-10-22", 1610612747, 1610612744, 110, 105],
            ["0022400002", "2024-10-23", 1610612744, 1610612739, 98, 102],
        ],
    }


@pytest.fixture
def sample_schedule_updates():
    """Sample schedule data for testing."""
    return {
        "games": [
            {
                "GAME_ID": "0022400003",
                "GAME_DATE": "2024-10-25",
                "HOME_TEAM": "Lakers",
                "AWAY_TEAM": "Warriors",
                "STATUS": "Scheduled",
            },
            {
                "GAME_ID": "0022400004",
                "GAME_DATE": "2024-10-26",
                "HOME_TEAM": "Celtics",
                "AWAY_TEAM": "Heat",
                "STATUS": "Scheduled",
            },
        ]
    }
