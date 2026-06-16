"""Venue Splits Analysis - Home vs Away performance.

Shows player's home and away averages for a stat type.
"""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np

# Cache DB path
CACHE_DIR = Path("./data/analysis")
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CONTEXT_DB = CACHE_DIR / "player_context.db"


def _get_context_db() -> sqlite3.Connection:
    """Get or create context database connection."""
    conn = sqlite3.connect(CONTEXT_DB, check_same_thread=False)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS venue_splits (
            player_name TEXT,
            stat_type TEXT,
            home_avg REAL,
            home_games INTEGER,
            away_avg REAL,
            away_games INTEGER,
            last_updated TEXT,
            PRIMARY KEY (player_name, stat_type)
        )
    """)
    conn.commit()
    return conn


def _init_nba_api():
    """Lazy initialization of nba_api."""
    from nba_api.stats.static import players as nba_players
    from nba_api.stats.endpoints import playergamelog

    return nba_players, playergamelog


def normalize_name(s: str) -> str:
    """Normalize player name for matching."""
    import re

    s = (s or "").strip().lower().replace("'", "'")
    s = re.sub(r"[^a-z0-9\s'-]", " ", s)
    s = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b.?", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _parse_minutes(min_str) -> float:
    """Parse minutes string to float."""
    if min_str is None:
        return float("nan")
    if isinstance(min_str, (int, float)):
        return float(min_str)
    s = str(min_str).strip()
    if ":" in s:
        try:
            a, b = s.split(":", 1)
            return float(a) + float(b) / 60.0
        except Exception:
            return float("nan")
    try:
        return float(s)
    except Exception:
        return float("nan")


def get_stat_value(stat_type: str, row) -> float:
    """Extract stat value from gamelog row."""
    pts = float(row.get("PTS", 0) or 0)
    reb = float(row.get("REB", 0) or 0)
    ast = float(row.get("AST", 0) or 0)
    stl = float(row.get("STL", 0) or 0)
    blk = float(row.get("BLK", 0) or 0)
    tov = float(row.get("TOV", 0) or 0)
    fg3m = float(row.get("FG3M", 0) or 0)

    st = (stat_type or "").strip()
    if st == "Points":
        return pts
    if st == "Rebounds":
        return reb
    if st == "Assists":
        return ast
    if st in ("3-PT Made", "3PT Made", "3 Pointers Made", "3PM"):
        return fg3m
    if st == "Turnovers":
        return tov
    if st == "Blocks":
        return blk
    if st == "Steals":
        return stl
    if st in ("Blocks + Steals", "Blocks+Steals"):
        return blk + stl
    if st in ("Pts+Rebs+Asts", "PRA"):
        return pts + reb + ast
    if st in ("Pts+Rebs", "PR"):
        return pts + reb
    if st in ("Pts+Asts", "PA"):
        return pts + ast
    if st in ("Rebs+Asts", "RA"):
        return reb + ast
    return float("nan")


def is_home_game(matchup: str) -> bool:
    """Determine if game was home from matchup string."""
    if not matchup or not isinstance(matchup, str):
        return False
    # Home games show as "Team vs OPP" (vs means home)
    return " vs " in matchup


def get_home_away_split(player_name: str, stat_type: str) -> Optional[dict]:
    """Get player's home vs away splits for a stat.

    Args:
        player_name: Player's name
        stat_type: Stat type

    Returns:
        Dict with home_avg, home_games, away_avg, away_games
    """
    # Check cache (valid for 24 hours)
    conn = _get_context_db()
    cursor = conn.execute(
        """SELECT home_avg, home_games, away_avg, away_games, last_updated 
           FROM venue_splits WHERE player_name = ? AND stat_type = ?""",
        (normalize_name(player_name), stat_type),
    )
    row = cursor.fetchone()
    conn.close()

    if row:
        last_updated = datetime.fromisoformat(row[4])
        if datetime.now() - last_updated < timedelta(hours=24):
            return {
                "home_avg": row[0],
                "home_games": row[1],
                "away_avg": row[2],
                "away_games": row[3],
            }

    # Fetch fresh data
    try:
        nba_players, playergamelog = _init_nba_api()

        # Find player ID
        matches = nba_players.find_players_by_full_name(player_name)
        if not matches:
            n = normalize_name(player_name)
            all_players = nba_players.get_players()
            matches = [p for p in all_players if n == normalize_name(p["full_name"])]
            if not matches:
                matches = [p for p in all_players if n in normalize_name(p["full_name"])]

        if not matches:
            return None

        player_id = int(matches[0]["id"])

        # Get gamelog - need 15+ games for meaningful splits
        gl = (
            playergamelog.PlayerGameLog(player_id=player_id, timeout=10)
            .get_data_frames()[0]
            .head(25)
        )

        if len(gl) == 0:
            return None

        home_vals = []
        away_vals = []

        for _, game_row in gl.iterrows():
            mins = _parse_minutes(game_row.get("MIN"))
            if mins >= 6:  # Minimum valid minutes
                stat_val = get_stat_value(stat_type, game_row)
                if not np.isnan(stat_val):
                    matchup = game_row.get("MATCHUP", "")
                    if is_home_game(matchup):
                        home_vals.append(stat_val)
                    else:
                        away_vals.append(stat_val)

        home_avg = round(float(np.mean(home_vals)), 1) if home_vals else None
        home_games = len(home_vals)
        away_avg = round(float(np.mean(away_vals)), 1) if away_vals else None
        away_games = len(away_vals)

        # Cache result
        conn = _get_context_db()
        conn.execute(
            """INSERT OR REPLACE INTO venue_splits 
               (player_name, stat_type, home_avg, home_games, away_avg, away_games, last_updated)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                normalize_name(player_name),
                stat_type,
                home_avg,
                home_games,
                away_avg,
                away_games,
                datetime.now().isoformat(),
            ),
        )
        conn.commit()
        conn.close()

        return {
            "home_avg": home_avg,
            "home_games": home_games,
            "away_avg": away_avg,
            "away_games": away_games,
        }

    except Exception as e:
        print(f"Error fetching venue splits for {player_name}/{stat_type}: {e}")
        return None


def get_venue_advantage(home_avg: Optional[float], away_avg: Optional[float]) -> Optional[str]:
    """Calculate venue advantage as percentage difference.

    Returns:
        String like "+15%" for home advantage or "-10%" for away advantage
    """
    if home_avg is None or away_avg is None or away_avg == 0:
        return None

    diff = ((home_avg - away_avg) / away_avg) * 100

    sign = "+" if diff >= 0 else ""
    return f"{sign}{diff:.0f}%"


def get_split_description(
    home_avg: Optional[float], home_games: int, away_avg: Optional[float], away_games: int
) -> str:
    """Get human-readable split description."""
    if home_avg is None and away_avg is None:
        return "No split data"

    parts = []
    if home_avg is not None:
        parts.append(f"Home: {home_avg:.1f} ({home_games}g)")
    if away_avg is not None:
        parts.append(f"Away: {away_avg:.1f} ({away_games}g)")

    return " | ".join(parts)


def clear_venue_splits_cache():
    """Clear all cached venue splits data."""
    conn = _get_context_db()
    conn.execute("DELETE FROM venue_splits")
    conn.commit()
    conn.close()
