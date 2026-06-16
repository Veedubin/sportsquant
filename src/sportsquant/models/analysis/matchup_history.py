"""Matchup History Analysis - Player averages vs specific opponents.

Uses nba_api to get head-to-head stats for each player vs current opponent.
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
        CREATE TABLE IF NOT EXISTS matchup_history (
            player_name TEXT,
            opponent_team TEXT,
            stat_type TEXT,
            avg_value REAL,
            games_count INTEGER,
            last_updated TEXT,
            PRIMARY KEY (player_name, opponent_team, stat_type)
        )
    """)
    conn.commit()
    return conn


def _init_nba_api():
    """Lazy initialization of nba_api."""
    from nba_api.stats.static import players as nba_players
    from nba_api.stats.static import teams as nba_teams
    from nba_api.stats.endpoints import playergamelog
    from nba_api.stats.endpoints import teamgamelog

    return nba_players, nba_teams, playergamelog, teamgamelog


def normalize_name(s: str) -> str:
    """Normalize player name for matching."""
    import re

    s = (s or "").strip().lower().replace("'", "'")
    s = re.sub(r"[^a-z0-9\s'-]", " ", s)
    s = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b.?", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+", " ", s).strip()
    return s


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


def get_matchup_avg(player_name: str, opponent_team: str, stat_type: str) -> Optional[dict]:
    """Get player's average vs specific opponent.

    Args:
        player_name: Player's name
        opponent_team: Opponent team abbreviation (e.g., "BOS")
        stat_type: Stat type (e.g., "Points", "Rebounds")

    Returns:
        Dict with avg_value, games_count or None if not found
    """
    # Check cache first
    conn = _get_context_db()
    cursor = conn.execute(
        """SELECT avg_value, games_count, last_updated FROM matchup_history
           WHERE player_name = ? AND opponent_team = ? AND stat_type = ?""",
        (normalize_name(player_name), opponent_team.upper(), stat_type),
    )
    row = cursor.fetchone()
    conn.close()

    if row:
        last_updated = datetime.fromisoformat(row[2])
        # Cache valid for 24 hours
        if datetime.now() - last_updated < timedelta(hours=24):
            return {"avg_value": row[0], "games_count": row[1]}

    # Fetch fresh data from NBA API
    try:
        nba_players, nba_teams, playergamelog, _ = _init_nba_api()

        # Find player ID
        matches = nba_players.find_players_by_full_name(player_name)
        if not matches:
            # Try partial match
            n = normalize_name(player_name)
            all_players = nba_players.get_players()
            matches = [p for p in all_players if n == normalize_name(p["full_name"])]
            if not matches:
                matches = [p for p in all_players if n in normalize_name(p["full_name"])]

        if not matches:
            return None

        player_id = int(matches[0]["id"])

        # Get player's gamelog
        gl = playergamelog.PlayerGameLog(player_id=player_id, timeout=10).get_data_frames()[0]

        # Get opponent team ID
        all_teams = nba_teams.get_teams()
        opp_team = next((t for t in all_teams if t["abbreviation"] == opponent_team.upper()), None)
        if not opp_team:
            return None

        int(opp_team["id"])

        # Filter games vs opponent
        opp_games = gl[gl["MATCHUP"].str.contains(opponent_team.upper(), na=False)]

        if len(opp_games) == 0:
            return {"avg_value": None, "games_count": 0}

        # Calculate average
        vals = []
        for _, game_row in opp_games.iterrows():
            mins = _parse_minutes(game_row.get("MIN"))
            if mins >= 6:  # Minimum valid minutes
                stat_val = get_stat_value(stat_type, game_row)
                if not np.isnan(stat_val):
                    vals.append(stat_val)

        if len(vals) == 0:
            return {"avg_value": None, "games_count": 0}

        avg_value = float(np.mean(vals))
        games_count = len(vals)

        # Cache result
        conn = _get_context_db()
        conn.execute(
            """INSERT OR REPLACE INTO matchup_history 
               (player_name, opponent_team, stat_type, avg_value, games_count, last_updated)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                normalize_name(player_name),
                opponent_team.upper(),
                stat_type,
                avg_value,
                games_count,
                datetime.now().isoformat(),
            ),
        )
        conn.commit()
        conn.close()

        return {"avg_value": round(avg_value, 1), "games_count": games_count}

    except Exception as e:
        print(f"Error fetching matchup data for {player_name} vs {opponent_team}: {e}")
        return None


def clear_matchup_cache():
    """Clear all cached matchup data."""
    conn = _get_context_db()
    conn.execute("DELETE FROM matchup_history")
    conn.commit()
    conn.close()
