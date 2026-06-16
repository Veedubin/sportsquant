"""Rest Days Analysis - Days since last game and impact on performance.

Shows if player is on back-to-back, 2 days rest, 3+ days rest and
calculates the percentage impact on performance.
"""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


# Cache DB path
CACHE_DIR = Path("./data/analysis")
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CONTEXT_DB = CACHE_DIR / "player_context.db"


def _get_context_db() -> sqlite3.Connection:
    """Get or create context database connection."""
    conn = sqlite3.connect(CONTEXT_DB, check_same_thread=False)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS rest_days (
            player_name TEXT,
            team TEXT,
            stat_type TEXT,
            rest_days INTEGER,
            last_game_date TEXT,
            last_updated TEXT,
            PRIMARY KEY (player_name, team, stat_type)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS rest_impact (
            stat_type TEXT PRIMARY KEY,
            back_to_back REAL,
            two_days REAL,
            three_plus_days REAL
        )
    """)
    conn.commit()
    return conn


def _init_nba_api():
    """Lazy initialization of nba_api."""
    from nba_api.stats.static import players as nba_players
    from nba_api.stats.endpoints import playergamelog
    from nba_api.stats.endpoints import teamgamelog
    from nba_api.stats.endpoints import teamdetails

    return nba_players, playergamelog, teamgamelog, teamdetails


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


# Default rest impact percentages (based on NBA research)
# Back-to-back games typically see 2-5% decrease in production
DEFAULT_REST_IMPACTS = {
    "Points": {"back_to_back": -3.0, "two_days": 0.0, "three_plus_days": 2.0},
    "Rebounds": {"back_to_back": -4.0, "two_days": -1.0, "three_plus_days": 1.5},
    "Assists": {"back_to_back": -2.5, "two_days": 0.0, "three_plus_days": 1.0},
    "3-PT Made": {"back_to_back": -5.0, "two_days": -1.0, "three_plus_days": 2.0},
    "3PT Made": {"back_to_back": -5.0, "two_days": -1.0, "three_plus_days": 2.0},
    "Steals": {"back_to_back": -3.0, "two_days": 0.0, "three_plus_days": 1.0},
    "Blocks": {"back_to_back": -4.0, "two_days": -1.0, "three_plus_days": 1.5},
    "Turnovers": {"back_to_back": 5.0, "two_days": 2.0, "three_plus_days": 0.0},
}


def get_rest_impact(stat_type: str, rest_days: int) -> str:
    """Get the percentage impact based on rest days.

    Args:
        stat_type: The stat type
        rest_days: Number of days since last game

    Returns:
        Formatted string like "+5%" or "-3%"
    """
    impacts = DEFAULT_REST_IMPACTS.get(stat_type, DEFAULT_REST_IMPACTS["Points"])

    if rest_days == 1:
        impact = impacts["back_to_back"]
    elif rest_days == 2:
        impact = impacts["two_days"]
    else:
        impact = impacts["three_plus_days"]

    sign = "+" if impact >= 0 else ""
    return f"{sign}{impact:.0f}%"


def get_rest_days(player_name: str, team: str) -> Optional[dict]:
    """Get days since last game for a player.

    Args:
        player_name: Player's name
        team: Team abbreviation

    Returns:
        Dict with rest_days, last_game_date or None if not found
    """
    # Check cache first (valid for 12 hours)
    conn = _get_context_db()
    cursor = conn.execute(
        """SELECT rest_days, last_game_date, last_updated FROM rest_days
           WHERE player_name = ? AND team = ?""",
        (normalize_name(player_name), team.upper()),
    )
    row = cursor.fetchone()
    conn.close()

    if row:
        last_updated = datetime.fromisoformat(row[2])
        if datetime.now() - last_updated < timedelta(hours=12):
            return {"rest_days": row[0], "last_game_date": row[1]}

    # Fetch fresh data
    try:
        nba_players, playergamelog, _, _ = _init_nba_api()

        # Find player ID
        matches = nba_players.find_players_by_full_name(player_name)
        if not matches:
            n = normalize_name(player_name)
            all_players = nba_players.get_players()
            matches = [p for p in all_players if n == normalize_name(p["full_name"])]

        if not matches:
            return None

        player_id = int(matches[0]["id"])

        # Get gamelog
        gl = playergamelog.PlayerGameLog(player_id=player_id, timeout=10).get_data_frames()[0]

        if len(gl) == 0:
            return None

        # Parse game date from first row (most recent)
        most_recent = gl.iloc[0]
        game_date_str = most_recent.get("DATE", "")

        try:
            last_game_date = datetime.strptime(game_date_str, "%m/%d/%Y")
        except Exception:
            try:
                last_game_date = datetime.strptime(game_date_str, "%Y-%m-%d")
            except Exception:
                return None

        # Calculate rest days
        today = datetime.now()
        days_since = (today - last_game_date).days

        # If game was today or yesterday, rest_days = 0 or 1
        # Otherwise it's the days since that game
        rest_days = min(max(0, days_since), 7)  # Cap at 7 days

        # Cache result
        conn = _get_context_db()
        conn.execute(
            """INSERT OR REPLACE INTO rest_days 
               (player_name, team, stat_type, rest_days, last_game_date, last_updated)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                normalize_name(player_name),
                team.upper(),
                "general",
                rest_days,
                last_game_date.date().isoformat(),
                datetime.now().isoformat(),
            ),
        )
        conn.commit()
        conn.close()

        return {"rest_days": rest_days, "last_game_date": last_game_date.date().isoformat()}

    except Exception as e:
        print(f"Error fetching rest days for {player_name}: {e}")
        return None


def get_rest_description(rest_days: int) -> str:
    """Get human-readable rest description."""
    if rest_days == 0:
        return "Today"
    elif rest_days == 1:
        return "Back-to-back"
    elif rest_days == 2:
        return "2 days rest"
    else:
        return f"{rest_days}+ days rest"


def clear_rest_cache():
    """Clear all cached rest day data."""
    conn = _get_context_db()
    conn.execute("DELETE FROM rest_days")
    conn.commit()
    conn.close()
