"""Recent Form Analysis - Last 5 games and trend calculation.

Shows last 5 games for the stat and calculates trend direction.
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
        CREATE TABLE IF NOT EXISTS recent_form (
            player_name TEXT,
            stat_type TEXT,
            last_5 TEXT,
            trend TEXT,
            avg_last_5 REAL,
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


def get_trend(last_5_list: list[float]) -> str:
    """Calculate trend direction from last 5 values.

    Uses linear regression slope to determine trend.

    Args:
        last_5_list: List of last 5 stat values (most recent last)

    Returns:
        "up", "down", or "flat"
    """
    if len(last_5_list) < 3:
        return "flat"

    vals = np.array(last_5_list, dtype=float)

    # Simple linear regression
    x = np.arange(len(vals))
    x_mean = np.mean(x)
    y_mean = np.mean(vals)

    numerator = np.sum((x - x_mean) * (vals - y_mean))
    denominator = np.sum((x - x_mean) ** 2)

    if denominator == 0:
        return "flat"

    slope = numerator / denominator

    # Normalize slope by mean to make it scale-independent
    if y_mean == 0:
        return "flat"

    normalized_slope = slope / y_mean

    # Threshold for determining trend
    if normalized_slope > 0.05:
        return "up"
    elif normalized_slope < -0.05:
        return "down"
    else:
        return "flat"


def get_last_5_games(player_name: str, stat_type: str) -> Optional[dict]:
    """Get player's last 5 games for a stat.

    Args:
        player_name: Player's name
        stat_type: Stat type (e.g., "Points", "Rebounds")

    Returns:
        Dict with last_5 list, trend, avg_last_5
    """
    # Check cache (valid for 6 hours)
    conn = _get_context_db()
    cursor = conn.execute(
        """SELECT last_5, trend, avg_last_5, last_updated FROM recent_form
           WHERE player_name = ? AND stat_type = ?""",
        (normalize_name(player_name), stat_type),
    )
    row = cursor.fetchone()
    conn.close()

    if row:
        last_updated = datetime.fromisoformat(row[3])
        if datetime.now() - last_updated < timedelta(hours=6):
            last_5 = [float(x) for x in row[0].split(",")]
            return {"last_5": last_5, "trend": row[1], "avg_last_5": row[2]}

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

        # Get gamelog - last 10 games to ensure we get 5 valid
        gl = (
            playergamelog.PlayerGameLog(player_id=player_id, timeout=10)
            .get_data_frames()[0]
            .head(10)
        )

        if len(gl) == 0:
            return None

        # Extract stat values
        vals = []
        for _, game_row in gl.iterrows():
            mins = _parse_minutes(game_row.get("MIN"))
            if mins >= 6:  # Minimum valid minutes
                stat_val = get_stat_value(stat_type, game_row)
                if not np.isnan(stat_val):
                    vals.append(stat_val)

        last_5 = vals[:5] if len(vals) >= 5 else vals
        trend = get_trend(last_5)
        avg_last_5 = round(float(np.mean(last_5)), 1) if last_5 else None

        # Cache result
        conn = _get_context_db()
        conn.execute(
            """INSERT OR REPLACE INTO recent_form 
               (player_name, stat_type, last_5, trend, avg_last_5, last_updated)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                normalize_name(player_name),
                stat_type,
                ",".join(str(v) for v in last_5),
                trend,
                avg_last_5,
                datetime.now().isoformat(),
            ),
        )
        conn.commit()
        conn.close()

        return {"last_5": [round(v, 1) for v in last_5], "trend": trend, "avg_last_5": avg_last_5}

    except Exception as e:
        print(f"Error fetching recent form for {player_name}/{stat_type}: {e}")
        return None


def get_trend_emoji(trend: str) -> str:
    """Get emoji representation of trend."""
    if trend == "up":
        return "📈"
    elif trend == "down":
        return "📉"
    else:
        return "➡️"


def get_trend_description(trend: str, avg_last_5: float) -> str:
    """Get human-readable trend description."""
    if trend == "up":
        return f"Trending up (avg {avg_last_5:.1f})"
    elif trend == "down":
        return f"Trending down (avg {avg_last_5:.1f})"
    else:
        return f"Stable (avg {avg_last_5:.1f})"


def clear_recent_form_cache():
    """Clear all cached recent form data."""
    conn = _get_context_db()
    conn.execute("DELETE FROM recent_form")
    conn.commit()
    conn.close()
