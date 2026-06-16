"""SQLite repositories stub."""

import sqlite3
from pathlib import Path
from typing import Optional

import pandas as pd


def _connect(db_path: Path) -> sqlite3.Connection:
    """Connect to SQLite database with row factory."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


class SQLiteProjectionRepository:
    """SQLite projection repository stub."""

    def __init__(self, db_path: Path):
        self.db_path = db_path

    def health_check(self) -> bool:
        try:
            conn = _connect(self.db_path)
            conn.execute("SELECT 1")
            conn.close()
            return True
        except Exception:
            return False

    def get_projections(
        self, site: str = "prizepicks", player_name: Optional[str] = None
    ) -> pd.DataFrame:
        conn = _connect(self.db_path)
        query = "SELECT *, ? AS site FROM projections"
        params: list = [site]
        if player_name:
            query += " WHERE player_name LIKE ?"
            params.append(f"%{player_name}%")
        df = pd.read_sql_query(query, conn, params=params)
        conn.close()
        return df

    def get_projection_by_id(self, site: str, projection_id: str) -> Optional[dict]:
        conn = _connect(self.db_path)
        cursor = conn.execute("SELECT * FROM projections WHERE id = ?", (projection_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def get_players(self, site: str = "prizepicks") -> list:
        conn = _connect(self.db_path)
        cursor = conn.execute("SELECT DISTINCT player_name FROM projections")
        rows = cursor.fetchall()
        conn.close()
        return [row["player_name"] for row in rows]


class SQLiteMarketRepository:
    """SQLite market repository stub."""

    def __init__(self, db_path: Path):
        self.db_path = db_path

    def health_check(self) -> bool:
        try:
            conn = _connect(self.db_path)
            conn.execute("SELECT 1")
            conn.close()
            return True
        except Exception:
            return False


class SQLitePlayerRepository:
    """SQLite player repository stub."""

    def __init__(self, db_path: Path):
        self.db_path = db_path

    def health_check(self) -> bool:
        try:
            conn = _connect(self.db_path)
            conn.execute("SELECT 1")
            conn.close()
            return True
        except Exception:
            return False

    def find_player(self, name: str) -> Optional[dict]:
        conn = _connect(self.db_path)
        cursor = conn.execute("SELECT * FROM player_mapping WHERE canonical_name = ?", (name,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def get_player_aliases(self, player_id: int) -> list:
        conn = _connect(self.db_path)
        cursor = conn.execute("SELECT * FROM player_mapping WHERE id = ?", (player_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            row = dict(row)
            return [v for k, v in row.items() if k.endswith("_name") and v]
        return []

    def map_name(self, name: str, source_site: str, target_site: str) -> Optional[str]:
        conn = _connect(self.db_path)
        cursor = conn.execute(
            f"SELECT {target_site}_name FROM player_mapping WHERE {source_site}_name = ?",
            (name,),
        )
        row = cursor.fetchone()
        conn.close()
        return row[target_site + "_name"] if row else None

    def get_stats(self) -> dict:
        conn = _connect(self.db_path)
        cursor = conn.execute("SELECT * FROM player_mapping")
        rows = cursor.fetchall()
        conn.close()
        total = len(rows)
        pp = sum(1 for r in rows if r["pp_name"])
        fd = sum(1 for r in rows if r["fd_name"])
        ud = sum(1 for r in rows if r["ud_name"])
        dk = sum(1 for r in rows if r["dk_name"])
        return {
            "total_players": total,
            "prizepicks_count": pp,
            "fanduel_count": fd,
            "underdog_count": ud,
            "draftkings_count": dk,
        }
