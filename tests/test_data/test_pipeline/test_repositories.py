"""Tests for SQLite repositories (migrated from sports-bet)."""

import sqlite3
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pandas as pd
import pytest

from sportsquant.data.pipeline.sqlite_repositories import (
    SQLiteMarketRepository,
    SQLitePlayerRepository,
    SQLiteProjectionRepository,
    _connect,
)


class TestSQLiteProjectionRepository:
    """Tests for SQLiteProjectionRepository."""

    def test_health_check(self, tmp_db_path: Path) -> None:
        """Test health check returns True for valid database."""
        repo = SQLiteProjectionRepository(tmp_db_path)
        assert repo.health_check() is True

    def test_health_check_invalid_path(self, tmp_path: Path) -> None:
        """Test health check returns True even for "non-existent" database.

        Note: SQLite creates the file when connecting, so health_check
        returns True even for paths that didn't exist before.
        """
        non_existent = tmp_path / "non_existent.db"
        repo = SQLiteProjectionRepository(non_existent)
        assert repo.health_check() is True

    def test_get_projections_prizepicks(self, tmp_db_path: Path) -> None:
        """Test fetching PrizePicks projections."""
        # Insert test data
        conn = sqlite3.connect(str(tmp_db_path))
        conn.execute(
            "INSERT INTO projections VALUES (?, ?, ?, ?, ?)",
            ("pp_001", "Jayson Tatum", "pts", 28.5, "2026-04-19T19:00:00Z"),
        )
        conn.commit()
        conn.close()

        repo = SQLiteProjectionRepository(tmp_db_path)
        df = repo.get_projections(site="prizepicks")

        assert len(df) == 1
        assert df.iloc[0]["player_name"] == "Jayson Tatum"
        assert df.iloc[0]["stat_type"] == "pts"
        assert df["site"].iloc[0] == "prizepicks"

    def test_get_projections_filter_by_player(
        self, tmp_db_path: Path, sample_projections: list[dict[str, Any]]
    ) -> None:
        """Test filtering projections by player name."""
        # Insert test data
        conn = sqlite3.connect(str(tmp_db_path))
        for proj in sample_projections:
            conn.execute(
                "INSERT INTO projections VALUES (?, ?, ?, ?, ?)",
                (
                    proj["id"],
                    proj["player_name"],
                    proj["stat_type"],
                    proj["line_score"],
                    proj.get("start_time"),
                ),
            )
        conn.commit()
        conn.close()

        repo = SQLiteProjectionRepository(tmp_db_path)
        df = repo.get_projections(site="prizepicks", player_name="Tatum")

        assert len(df) == 1
        assert "Tatum" in df.iloc[0]["player_name"]

    def test_get_projection_by_id(self, tmp_db_path: Path) -> None:
        """Test fetching projection by ID."""
        conn = sqlite3.connect(str(tmp_db_path))
        conn.execute(
            "INSERT INTO projections VALUES (?, ?, ?, ?, ?)",
            ("pp_test_001", "Stephen Curry", "pts", 32.5, "2026-04-19T20:00:00Z"),
        )
        conn.commit()
        conn.close()

        repo = SQLiteProjectionRepository(tmp_db_path)
        result = repo.get_projection_by_id(site="prizepicks", projection_id="pp_test_001")

        assert result is not None
        assert result["player_name"] == "Stephen Curry"

    def test_get_players(self, tmp_db_path: Path, sample_projections: list[dict]) -> None:
        """Test fetching distinct player list."""
        conn = sqlite3.connect(str(tmp_db_path))
        for proj in sample_projections:
            conn.execute(
                "INSERT INTO projections VALUES (?, ?, ?, ?, ?)",
                (
                    proj["id"],
                    proj["player_name"],
                    proj["stat_type"],
                    proj["line_score"],
                    proj.get("start_time"),
                ),
            )
        conn.commit()
        conn.close()

        repo = SQLiteProjectionRepository(tmp_db_path)
        players = repo.get_players(site="prizepicks")

        assert len(players) == 3
        assert "Jayson Tatum" in players
        assert "Jaylen Brown" in players
        assert "Stephen Curry" in players


class TestSQLiteMarketRepository:
    """Tests for SQLiteMarketRepository."""

    def test_health_check(self, tmp_db_path: Path) -> None:
        """Test health check returns True for valid database."""
        repo = SQLiteMarketRepository(tmp_db_path)
        assert repo.health_check() is True

    def test_health_check_invalid_path(self, tmp_path: Path) -> None:
        """Test health check returns True even for "non-existent" database.

        Note: SQLite creates the file when connecting, so health_check
        returns True even for paths that didn't exist before.
        """
        non_existent = tmp_path / "non_existent.db"
        repo = SQLiteMarketRepository(non_existent)
        assert repo.health_check() is True


class TestSQLitePlayerRepository:
    """Tests for SQLitePlayerRepository."""

    def test_health_check(self, tmp_db_path: Path) -> None:
        """Test health check returns True for valid database."""
        repo = SQLitePlayerRepository(tmp_db_path)
        assert repo.health_check() is True

    def test_health_check_invalid_path(self, tmp_path: Path) -> None:
        """Test health check returns True even for "non-existent" database.

        Note: SQLite creates the file when connecting, so health_check
        returns True even for paths that didn't exist before.
        """
        non_existent = tmp_path / "non_existent.db"
        repo = SQLitePlayerRepository(non_existent)
        assert repo.health_check() is True

    def test_find_player_exact_match(self, tmp_db_path: Path) -> None:
        """Test finding player by exact name match."""
        conn = sqlite3.connect(str(tmp_db_path))
        conn.execute(
            """
            INSERT INTO player_mapping (id, canonical_name, pp_name, fd_name)
            VALUES (?, ?, ?, ?)
            """,
            (1, "Jayson Tatum", "Jayson Tatum", "Jayson Tatum"),
        )
        conn.commit()
        conn.close()

        repo = SQLitePlayerRepository(tmp_db_path)
        result = repo.find_player("Jayson Tatum")

        assert result is not None
        assert result["canonical_name"] == "Jayson Tatum"

    def test_find_player_not_found(self, tmp_db_path: Path) -> None:
        """Test finding non-existent player returns None."""
        repo = SQLitePlayerRepository(tmp_db_path)
        result = repo.find_player("Non Existent Player")
        assert result is None

    def test_get_player_aliases(self, tmp_db_path: Path) -> None:
        """Test getting all aliases for a player."""
        conn = sqlite3.connect(str(tmp_db_path))
        conn.execute(
            """
            INSERT INTO player_mapping (id, canonical_name, pp_name, fd_name, ud_name, dk_name)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (1, "Jayson Tatum", "Jayson Tatum", "Jayson Tatum", "Jayson Tatum", "Jayson Tatum"),
        )
        conn.commit()
        conn.close()

        repo = SQLitePlayerRepository(tmp_db_path)
        aliases = repo.get_player_aliases(player_id=1)

        assert len(aliases) > 0
        assert "Jayson Tatum" in aliases

    def test_map_name(self, tmp_db_path: Path) -> None:
        """Test mapping player name across sites."""
        conn = sqlite3.connect(str(tmp_db_path))
        conn.execute(
            """
            INSERT INTO player_mapping (id, canonical_name, pp_name, fd_name)
            VALUES (?, ?, ?, ?)
            """,
            (1, "Jayson Tatum", "Jayson Tatum", "J. Tatum"),
        )
        conn.commit()
        conn.close()

        repo = SQLitePlayerRepository(tmp_db_path)
        mapped = repo.map_name("Jayson Tatum", source_site="pp", target_site="fd")
        assert mapped == "J. Tatum"

    def test_get_stats(self, tmp_db_path: Path) -> None:
        """Test getting database statistics."""
        conn = sqlite3.connect(str(tmp_db_path))
        conn.execute(
            """
            INSERT INTO player_mapping (id, canonical_name, pp_name, fd_name, ud_name, dk_name)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (1, "Jayson Tatum", "Jayson Tatum", "Jayson Tatum", "Jayson Tatum", "Jayson Tatum"),
        )
        conn.execute(
            """
            INSERT INTO player_mapping (id, canonical_name, pp_name, fd_name)
            VALUES (?, ?, ?, ?)
            """,
            (2, "Jaylen Brown", "Jaylen Brown", "Jaylen Brown"),
        )
        conn.commit()
        conn.close()

        repo = SQLitePlayerRepository(tmp_db_path)
        stats = repo.get_stats()

        assert stats["total_players"] == 2
        assert stats["prizepicks_count"] == 2
        assert stats["fanduel_count"] == 2
        assert stats["underdog_count"] == 1
        assert stats["draftkings_count"] == 1


class TestConnectHelper:
    """Tests for _connect helper function."""

    def test_connect_creates_row_factory(self, tmp_path: Path) -> None:
        """Test that _connect sets row_factory."""
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE test (id INTEGER)")
        conn.execute("INSERT INTO test VALUES (1)")
        conn.commit()
        conn.close()

        conn = _connect(db_path)
        cursor = conn.execute("SELECT * FROM test")
        row = cursor.fetchone()
        # Should be accessible by column name
        assert row["id"] == 1
        conn.close()
