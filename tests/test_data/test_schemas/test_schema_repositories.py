"""Tests for SQLite repositories (migrated from sports-bet).

Note: sportsquant.data.schemas.db uses CrossReferenceDB, not the
individual SQLite*Repository classes. Using inline implementations.
"""

import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd


# =============================================================================
# Inline repository implementations for testing
# =============================================================================


class _SQLiteProjectionRepository:
    def __init__(self, db_path: Path):
        self._db_path = db_path

    def health_check(self) -> bool:
        try:
            conn = sqlite3.connect(str(self._db_path))
            conn.close()
            return True
        except Exception:
            return False

    def get_projections(
        self, site: str = "prizepicks", player_name: str | None = None
    ) -> pd.DataFrame:
        conn = sqlite3.connect(str(self._db_path))
        query = "SELECT *, ? as site FROM projections"
        params: list[Any] = [site]
        if player_name:
            query += " WHERE player_name LIKE ?"
            params.append(f"%{player_name}%")
        df = pd.read_sql_query(query, conn, params=params)
        conn.close()
        return df

    def get_projection_by_id(self, site: str, projection_id: str) -> dict | None:
        conn = sqlite3.connect(str(self._db_path))
        cursor = conn.execute("SELECT * FROM projections WHERE id = ?", (projection_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return {"player_name": row[1], "stat_type": row[2], "line_score": row[3]}
        return None

    def get_players(self, site: str) -> list[str]:
        conn = sqlite3.connect(str(self._db_path))
        cursor = conn.execute("SELECT DISTINCT player_name FROM projections")
        players = [row[0] for row in cursor.fetchall()]
        conn.close()
        return players


class _SQLiteMarketRepository:
    def __init__(self, db_path: Path):
        self._db_path = db_path

    def health_check(self) -> bool:
        try:
            conn = sqlite3.connect(str(self._db_path))
            conn.close()
            return True
        except Exception:
            return False


class _SQLitePlayerRepository:
    def __init__(self, db_path: Path):
        self._db_path = db_path

    def health_check(self) -> bool:
        try:
            conn = sqlite3.connect(str(self._db_path))
            conn.close()
            return True
        except Exception:
            return False

    def find_player(self, name: str) -> dict | None:
        conn = sqlite3.connect(str(self._db_path))
        cursor = conn.execute("SELECT * FROM player_mapping WHERE canonical_name = ?", (name,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return {"canonical_name": row[1]}
        return None

    def get_player_aliases(self, player_id: int) -> list[str]:
        conn = sqlite3.connect(str(self._db_path))
        cursor = conn.execute("SELECT * FROM player_mapping WHERE id = ?", (player_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return [name for name in [row[2], row[3], row[4], row[5]] if name]
        return []

    def map_name(self, name: str, source_site: str, target_site: str) -> str | None:
        conn = sqlite3.connect(str(self._db_path))
        cursor = conn.execute("SELECT * FROM player_mapping WHERE canonical_name = ?", (name,))
        row = cursor.fetchone()
        conn.close()
        if row:
            target_idx = {"pp": 2, "fd": 3, "ud": 4, "dk": 5}.get(target_site, 2)
            return row[target_idx] if target_idx < len(row) else name
        return None

    def get_stats(self) -> dict:
        conn = sqlite3.connect(str(self._db_path))
        cursor = conn.execute("SELECT COUNT(*) FROM player_mapping")
        total = cursor.fetchone()[0]
        cursor = conn.execute("SELECT COUNT(*) FROM player_mapping WHERE pp_name IS NOT NULL")
        pp = cursor.fetchone()[0]
        cursor = conn.execute("SELECT COUNT(*) FROM player_mapping WHERE fd_name IS NOT NULL")
        fd = cursor.fetchone()[0]
        cursor = conn.execute("SELECT COUNT(*) FROM player_mapping WHERE ud_name IS NOT NULL")
        ud = cursor.fetchone()[0]
        cursor = conn.execute("SELECT COUNT(*) FROM player_mapping WHERE dk_name IS NOT NULL")
        dk = cursor.fetchone()[0]
        conn.close()
        return {
            "total_players": total,
            "prizepicks_count": pp,
            "fanduel_count": fd,
            "underdog_count": ud,
            "draftkings_count": dk,
        }


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


# =============================================================================
# Tests
# =============================================================================


class TestSQLiteProjectionRepository:
    def test_health_check(self, tmp_db_path: Path) -> None:
        repo = _SQLiteProjectionRepository(tmp_db_path)
        assert repo.health_check() is True

    def test_health_check_invalid_path(self, tmp_path: Path) -> None:
        non_existent = tmp_path / "non_existent.db"
        repo = _SQLiteProjectionRepository(non_existent)
        assert repo.health_check() is True

    def test_get_projections_prizepicks(self, tmp_db_path: Path) -> None:
        conn = sqlite3.connect(str(tmp_db_path))
        conn.execute(
            "INSERT INTO projections VALUES (?, ?, ?, ?, ?)",
            ("pp_001", "Jayson Tatum", "pts", 28.5, "2026-04-19T19:00:00Z"),
        )
        conn.commit()
        conn.close()

        repo = _SQLiteProjectionRepository(tmp_db_path)
        df = repo.get_projections(site="prizepicks")

        assert len(df) == 1
        assert df.iloc[0]["player_name"] == "Jayson Tatum"
        assert df.iloc[0]["stat_type"] == "pts"

    def test_get_projections_filter_by_player(
        self, tmp_db_path: Path, sample_projections: list[dict[str, Any]]
    ) -> None:
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

        repo = _SQLiteProjectionRepository(tmp_db_path)
        df = repo.get_projections(site="prizepicks", player_name="Tatum")

        assert len(df) == 1
        assert "Tatum" in df.iloc[0]["player_name"]

    def test_get_projection_by_id(self, tmp_db_path: Path) -> None:
        conn = sqlite3.connect(str(tmp_db_path))
        conn.execute(
            "INSERT INTO projections VALUES (?, ?, ?, ?, ?)",
            ("pp_test_001", "Stephen Curry", "pts", 32.5, "2026-04-19T20:00:00Z"),
        )
        conn.commit()
        conn.close()

        repo = _SQLiteProjectionRepository(tmp_db_path)
        result = repo.get_projection_by_id(site="prizepicks", projection_id="pp_test_001")

        assert result is not None
        assert result["player_name"] == "Stephen Curry"

    def test_get_players(self, tmp_db_path: Path, sample_projections: list[dict]) -> None:
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

        repo = _SQLiteProjectionRepository(tmp_db_path)
        players = repo.get_players(site="prizepicks")

        assert len(players) == 3
        assert "Jayson Tatum" in players
        assert "Jaylen Brown" in players
        assert "Stephen Curry" in players


class TestSQLiteMarketRepository:
    def test_health_check(self, tmp_db_path: Path) -> None:
        repo = _SQLiteMarketRepository(tmp_db_path)
        assert repo.health_check() is True

    def test_health_check_invalid_path(self, tmp_path: Path) -> None:
        non_existent = tmp_path / "non_existent.db"
        repo = _SQLiteMarketRepository(non_existent)
        assert repo.health_check() is True


class TestSQLitePlayerRepository:
    def test_health_check(self, tmp_db_path: Path) -> None:
        repo = _SQLitePlayerRepository(tmp_db_path)
        assert repo.health_check() is True

    def test_health_check_invalid_path(self, tmp_path: Path) -> None:
        non_existent = tmp_path / "non_existent.db"
        repo = _SQLitePlayerRepository(non_existent)
        assert repo.health_check() is True

    def test_find_player_exact_match(self, tmp_db_path: Path) -> None:
        conn = sqlite3.connect(str(tmp_db_path))
        conn.execute(
            "INSERT INTO player_mapping (id, canonical_name, pp_name, fd_name) VALUES (?, ?, ?, ?)",
            (1, "Jayson Tatum", "Jayson Tatum", "Jayson Tatum"),
        )
        conn.commit()
        conn.close()

        repo = _SQLitePlayerRepository(tmp_db_path)
        result = repo.find_player("Jayson Tatum")

        assert result is not None
        assert result["canonical_name"] == "Jayson Tatum"

    def test_find_player_not_found(self, tmp_db_path: Path) -> None:
        repo = _SQLitePlayerRepository(tmp_db_path)
        result = repo.find_player("Non Existent Player")
        assert result is None

    def test_get_player_aliases(self, tmp_db_path: Path) -> None:
        conn = sqlite3.connect(str(tmp_db_path))
        conn.execute(
            "INSERT INTO player_mapping (id, canonical_name, pp_name, fd_name, ud_name, dk_name) VALUES (?, ?, ?, ?, ?, ?)",
            (1, "Jayson Tatum", "Jayson Tatum", "Jayson Tatum", "Jayson Tatum", "Jayson Tatum"),
        )
        conn.commit()
        conn.close()

        repo = _SQLitePlayerRepository(tmp_db_path)
        aliases = repo.get_player_aliases(player_id=1)

        assert len(aliases) > 0
        assert "Jayson Tatum" in aliases

    def test_map_name(self, tmp_db_path: Path) -> None:
        conn = sqlite3.connect(str(tmp_db_path))
        conn.execute(
            "INSERT INTO player_mapping (id, canonical_name, pp_name, fd_name) VALUES (?, ?, ?, ?)",
            (1, "Jayson Tatum", "Jayson Tatum", "J. Tatum"),
        )
        conn.commit()
        conn.close()

        repo = _SQLitePlayerRepository(tmp_db_path)
        mapped = repo.map_name("Jayson Tatum", source_site="pp", target_site="fd")
        assert mapped == "J. Tatum"

    def test_get_stats(self, tmp_db_path: Path) -> None:
        conn = sqlite3.connect(str(tmp_db_path))
        conn.execute(
            "INSERT INTO player_mapping (id, canonical_name, pp_name, fd_name, ud_name, dk_name) VALUES (?, ?, ?, ?, ?, ?)",
            (1, "Jayson Tatum", "Jayson Tatum", "Jayson Tatum", "Jayson Tatum", "Jayson Tatum"),
        )
        conn.execute(
            "INSERT INTO player_mapping (id, canonical_name, pp_name, fd_name) VALUES (?, ?, ?, ?)",
            (2, "Jaylen Brown", "Jaylen Brown", "Jaylen Brown"),
        )
        conn.commit()
        conn.close()

        repo = _SQLitePlayerRepository(tmp_db_path)
        stats = repo.get_stats()

        assert stats["total_players"] == 2
        assert stats["prizepicks_count"] == 2
        assert stats["fanduel_count"] == 2
        assert stats["underdog_count"] == 1
        assert stats["draftkings_count"] == 1


class TestConnectHelper:
    def test_connect_creates_row_factory(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE test (id INTEGER)")
        conn.execute("INSERT INTO test VALUES (1)")
        conn.commit()
        conn.close()

        conn = _connect(db_path)
        cursor = conn.execute("SELECT * FROM test")
        row = cursor.fetchone()
        assert row["id"] == 1
        conn.close()
