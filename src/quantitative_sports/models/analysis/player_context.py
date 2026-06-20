"""Player Context Provider - Unified enrichment data for player props.

Combines matchup history, rest days, defense ratings, recent form, and venue splits
into a single context object for each prop.
"""

import sqlite3
from datetime import datetime
from pathlib import Path

# Import all enrichment modules
from quantitative_sports.models.analysis.matchup_history import get_matchup_avg, clear_matchup_cache
from quantitative_sports.models.analysis.rest_days import (
    get_rest_days,
    get_rest_impact,
    get_rest_description,
    clear_rest_cache,
)
from quantitative_sports.models.analysis.defense_ratings import (
    get_defense_rank,
    get_player_position,
    clear_defense_cache,
)
from quantitative_sports.models.analysis.recent_form import get_last_5_games, clear_recent_form_cache
from quantitative_sports.models.analysis.venue_splits import get_home_away_split, clear_venue_splits_cache

# Cache DB path
CACHE_DIR = Path("./data/analysis")
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CONTEXT_DB = CACHE_DIR / "player_context.db"


def _get_context_db() -> sqlite3.Connection:
    """Get or create context database connection."""
    conn = sqlite3.connect(CONTEXT_DB, check_same_thread=False)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS prop_context (
            prop_id TEXT,
            site TEXT,
            context TEXT,
            last_updated TEXT,
            PRIMARY KEY (prop_id, site)
        )
    """)
    conn.commit()
    return conn


def _normalize_stat_type(stat_type: str) -> str:
    """Normalize stat type across different site formats."""
    st = (stat_type or "").strip()

    # PrizePicks normalizations
    pp_normalize = {
        "PTS": "Points",
        "REB": "Rebounds",
        "AST": "Assists",
        "3P_MADE": "3-PT Made",
        "STL": "Steals",
        "BLK": "Blocks",
        "TOV": "Turnovers",
        "PTS_REB_AST": "Pts+Rebs+Asts",
        "PTS_REB": "Pts+Rebs",
        "PTS_AST": "Pts+Asts",
        "REB_AST": "Rebs+Asts",
    }
    if st in pp_normalize:
        return pp_normalize[st]

    # Generic normalizations
    generic = {
        "pts": "Points",
        "reb": "Rebounds",
        "ast": "Assists",
        "3pm": "3-PT Made",
        "stl": "Steals",
        "blk": "Blocks",
        "tov": "Turnovers",
    }
    lower = st.lower()
    if lower in generic:
        return generic[lower]

    return st


def get_player_context(
    player_name: str,
    opponent_team: str,
    stat_type: str,
    player_team: str,
    prop_id: str = "",
    site: str = "",
) -> dict:
    """Get comprehensive context for a player prop.

    Args:
        player_name: Player's name
        opponent_team: Opponent team abbreviation
        stat_type: Stat type (will be normalized)
        player_team: Player's team abbreviation
        prop_id: Prop ID for caching
        site: Site name for caching

    Returns:
        Context dictionary with all enrichment data
    """
    stat_type = _normalize_stat_type(stat_type)

    # Check cache first
    if prop_id and site:
        conn = _get_context_db()
        cursor = conn.execute(
            """SELECT context, last_updated FROM prop_context
               WHERE prop_id = ? AND site = ?""",
            (prop_id, site),
        )
        row = cursor.fetchone()
        conn.close()

        if row:
            from datetime import timedelta

            last_updated = datetime.fromisoformat(row[1])
            if datetime.now() - last_updated < timedelta(hours=1):
                import json

                try:
                    return json.loads(row[0])
                except Exception:
                    pass

    context = {
        "player_name": player_name,
        "player_team": player_team,
        "stat_type": stat_type,
        "matchup_avg": None,
        "matchup_games": 0,
        "rest_days": None,
        "rest_description": None,
        "rest_impact": None,
        "defense_rank": None,
        "defense_note": None,
        "last_5": [],
        "trend": None,
        "trend_avg": None,
        "home_avg": None,
        "away_avg": None,
        "venue_advantage": None,
    }

    # 1. Matchup History
    try:
        matchup = get_matchup_avg(player_name, opponent_team, stat_type)
        if matchup:
            context["matchup_avg"] = matchup.get("avg_value")
            context["matchup_games"] = matchup.get("games_count", 0)
    except Exception as e:
        print(f"Context error (matchup): {e}")

    # 2. Rest Days
    try:
        rest = get_rest_days(player_name, player_team)
        if rest:
            context["rest_days"] = rest.get("rest_days")
            context["rest_description"] = get_rest_description(context["rest_days"])
            context["rest_impact"] = get_rest_impact(stat_type, context["rest_days"])
    except Exception as e:
        print(f"Context error (rest): {e}")

    # 3. Defense Ratings
    try:
        position = get_player_position(player_name)
        defense = get_defense_rank(opponent_team, position, stat_type)
        if defense:
            context["defense_rank"] = defense.get("rank")
            context["defense_note"] = defense.get("note")
    except Exception as e:
        print(f"Context error (defense): {e}")

    # 4. Recent Form
    try:
        recent = get_last_5_games(player_name, stat_type)
        if recent:
            context["last_5"] = recent.get("last_5", [])
            context["trend"] = recent.get("trend")
            context["trend_avg"] = recent.get("avg_last_5")
    except Exception as e:
        print(f"Context error (recent): {e}")

    # 5. Venue Splits
    try:
        splits = get_home_away_split(player_name, stat_type)
        if splits:
            context["home_avg"] = splits.get("home_avg")
            context["away_avg"] = splits.get("away_avg")
    except Exception as e:
        print(f"Context error (venue): {e}")

    # Cache result
    if prop_id and site:
        import json

        conn = _get_context_db()
        conn.execute(
            """INSERT OR REPLACE INTO prop_context (prop_id, site, context, last_updated)
               VALUES (?, ?, ?, ?)""",
            (prop_id, site, json.dumps(context), datetime.now().isoformat()),
        )
        conn.commit()
        conn.close()

    return context


def get_context_summary(context: dict) -> str:
    """Get a one-line summary of the context for display."""
    parts = []

    if context.get("matchup_avg"):
        parts.append(f"vs {context['matchup_avg']}")

    if context.get("rest_description"):
        parts.append(context["rest_description"])

    if context.get("defense_note"):
        parts.append(f"Def #{context['defense_rank']}")

    if context.get("trend"):
        trend_emoji = (
            "📈" if context["trend"] == "up" else "📉" if context["trend"] == "down" else "➡️"
        )
        parts.append(f"{trend_emoji} {context['trend']}")

    return " | ".join(parts) if parts else ""


def clear_all_context_cache():
    """Clear all cached context data."""
    clear_matchup_cache()
    clear_rest_cache()
    clear_defense_cache()
    clear_recent_form_cache()
    clear_venue_splits_cache()

    conn = _get_context_db()
    conn.execute("DELETE FROM prop_context")
    conn.commit()
    conn.close()


def get_context_for_prop(prop: dict) -> dict:
    """Extract context data from a prop dict and get enrichment.

    Args:
        prop: A formatted prop dictionary from the dashboard

    Returns:
        Enrichment context dictionary
    """
    # Extract needed fields from prop
    player_name = prop.get("player_name", "")
    player_team = prop.get("player_team", "")
    stat_type = prop.get("stat_type", "")
    prop_id = prop.get("id", "")
    site = prop.get("site", "")

    # Parse opponent from matchup (format: "Team vs OPP" or "Team @ OPP")
    matchup = prop.get("matchup", "")
    opponent_team = ""
    if matchup:
        if " vs " in matchup:
            opponent_team = matchup.split(" vs ")[-1].strip()
        elif " @ " in matchup:
            opponent_team = matchup.split(" @ ")[-1].strip()

    # If no opponent in matchup, try to get from game info
    if not opponent_team and player_team:
        # This would need game schedule lookup - for now, use placeholder
        opponent_team = "UNK"

    if not player_name or not stat_type:
        return {}

    return get_player_context(
        player_name=player_name,
        opponent_team=opponent_team,
        stat_type=stat_type,
        player_team=player_team,
        prop_id=prop_id,
        site=site,
    )
