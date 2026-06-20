"""Build InsightFeed from lines.csv and parquet data.

Constructs the canonical Discord Top Insights feed from betting lines
and optional historical performance data from player_games.parquet.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, cast

import pandas as pd

from quantitative_sports.notifications.models import (
    BookPrice,
    Confidence,
    Event,
    HeroCard,
    Insight,
    InsightFeed,
    Pick,
    Presentation,
    Team,
)

logger = logging.getLogger(__name__)


TEAM_INFO: dict[str, dict[str, str]] = {
    "ATL": {"name": "Atlanta Hawks", "short_name": "Atlanta", "abbr": "ATL"},
    "BOS": {"name": "Boston Celtics", "short_name": "Boston", "abbr": "BOS"},
    "BKN": {"name": "Brooklyn Nets", "short_name": "Brooklyn", "abbr": "BKN"},
    "CHA": {"name": "Charlotte Hornets", "short_name": "Charlotte", "abbr": "CHA"},
    "CHI": {"name": "Chicago Bulls", "short_name": "Chicago", "abbr": "CHI"},
    "CLE": {"name": "Cleveland Cavaliers", "short_name": "Cleveland", "abbr": "CLE"},
    "DAL": {"name": "Dallas Mavericks", "short_name": "Dallas", "abbr": "DAL"},
    "DEN": {"name": "Denver Nuggets", "short_name": "Denver", "abbr": "DEN"},
    "DET": {"name": "Detroit Pistons", "short_name": "Detroit", "abbr": "DET"},
    "GSW": {
        "name": "Golden State Warriors",
        "short_name": "Golden State",
        "abbr": "GSW",
    },
    "HOU": {"name": "Houston Rockets", "short_name": "Houston", "abbr": "HOU"},
    "IND": {"name": "Indiana Pacers", "short_name": "Indiana", "abbr": "IND"},
    "LAC": {"name": "Los Angeles Clippers", "short_name": "LA Clippers", "abbr": "LAC"},
    "LAL": {"name": "Los Angeles Lakers", "short_name": "LA Lakers", "abbr": "LAL"},
    "MEM": {"name": "Memphis Grizzlies", "short_name": "Memphis", "abbr": "MEM"},
    "MIA": {"name": "Miami Heat", "short_name": "Miami", "abbr": "MIA"},
    "MIL": {"name": "Milwaukee Bucks", "short_name": "Milwaukee", "abbr": "MIL"},
    "MIN": {"name": "Minnesota Timberwolves", "short_name": "Minnesota", "abbr": "MIN"},
    "NOP": {"name": "New Orleans Pelicans", "short_name": "New Orleans", "abbr": "NOP"},
    "NYK": {"name": "New York Knicks", "short_name": "New York", "abbr": "NYK"},
    "OKC": {
        "name": "Oklahoma City Thunder",
        "short_name": "Oklahoma City",
        "abbr": "OKC",
    },
    "ORL": {"name": "Orlando Magic", "short_name": "Orlando", "abbr": "ORL"},
    "PHI": {"name": "Philadelphia 76ers", "short_name": "Philadelphia", "abbr": "PHI"},
    "PHX": {"name": "Phoenix Suns", "short_name": "Phoenix", "abbr": "PHX"},
    "POR": {"name": "Portland Trail Blazers", "short_name": "Portland", "abbr": "POR"},
    "SAC": {"name": "Sacramento Kings", "short_name": "Sacramento", "abbr": "SAC"},
    "SAS": {"name": "San Antonio Spurs", "short_name": "San Antonio", "abbr": "SAS"},
    "TOR": {"name": "Toronto Raptors", "short_name": "Toronto", "abbr": "TOR"},
    "UTA": {"name": "Utah Jazz", "short_name": "Utah", "abbr": "UTA"},
    "WAS": {"name": "Washington Wizards", "short_name": "Washington", "abbr": "WAS"},
}

BOOK_EMOJI_MAP: dict[str, str] = {
    "DraftKings": ":chart_with_upwards_trend:",
    "FanDuel": ":star:",
    "BetMGM": ":moneybag:",
    "Caesars": ":crown:",
    "BetRivers": ":river:",
    "PointsBet": ":point_up:",
    "ESPNBet": ":tv:",
    "Underdog": ":dog:",
    "PrizePicks": ":trophy:",
}


def _american_to_decimal(american_odds: int) -> float:
    """Convert American odds to decimal odds."""
    if american_odds >= 0:
        return 1 + (american_odds / 100)
    return 1 + (100 / abs(american_odds))


def _parse_event_id(event_id: str) -> tuple[str, str, str]:
    """Parse event_id to extract home_abbr, away_abbr, and date.

    Expected format: nba:YYYY-MM-DD:AWAY@HOME
    Example: nba:2026-01-10:LAL@BOS -> away=LAL, home=BOS
    """
    parts = event_id.split(":")
    if len(parts) != 3:
        raise ValueError(f"Invalid event_id format: {event_id}")

    date_part = parts[1]
    matchup = parts[2]

    if "@" not in matchup:
        raise ValueError(f"Invalid matchup format in event_id: {event_id}")

    away, home = matchup.split("@")
    return away.strip().upper(), home.strip().upper(), date_part


def _get_team(abbr: str) -> Team:
    """Get Team object from abbreviation."""
    info = TEAM_INFO.get(abbr, {"name": abbr, "short_name": abbr, "abbr": abbr})
    return Team(
        team_id=abbr,
        name=info["name"],
        short_name=info["short_name"],
        abbr=info["abbr"],
    )


def _load_parquet_stats(parquet_path: Path | None, player_id: int) -> dict[str, Any] | None:
    """Load player stats from parquet file if available.

    Args:
        parquet_path: Path to player_games.parquet
        player_id: NBA player ID to look up

    Returns:
        Dict with stats or None if not available
    """
    if parquet_path is None or not parquet_path.exists():
        return None

    try:
        df = pd.read_parquet(parquet_path)
        if df.empty:
            return None

        player_col = "player_id" if "player_id" in df.columns else "PLAYER_ID"
        player_df = df[df[player_col] == player_id]

        if player_df.empty:
            return None

        row = player_df.iloc[-1]

        return {
            "last_game_pts": float(row.get("PTS", 0)),
            "last_game_min": float(row.get("MIN", 0)),
            "avg_pts_10": float(row.get("LAG_PTS_10_AVG", 0)),
            "games_played": int(row.get("GAMES_PLAYED", 0)),
        }
    except Exception as e:
        logger.warning("Failed to load parquet stats for player %d: %s", player_id, e)
        return None


def _build_confidence(
    stats: dict[str, Any] | None, line: float, side: Literal["over", "under"]
) -> Confidence:
    """Build Confidence object from stats and line info."""
    if stats is None:
        return Confidence(
            model="hit_rate_v1",
            score_0_to_1=0.5,
            sample_size=0,
            hit_count=0,
        )

    avg_pts = stats.get("avg_pts_10", 0)
    games = stats.get("games_played", 0)

    if games < 3:
        return Confidence(
            model="hit_rate_v1",
            score_0_to_1=0.5,
            sample_size=games,
            hit_count=0,
        )

    if side == "over":
        hit_rate = sum(1 for _ in range(games) if avg_pts > line) / games
    else:
        hit_rate = sum(1 for _ in range(games) if avg_pts < line) / games

    hit_count = int(hit_rate * games)

    return Confidence(
        model="hit_rate_v1",
        score_0_to_1=min(max(hit_rate, 0.0), 1.0),
        sample_size=games,
        hit_count=hit_count,
    )


def _build_statement(
    player_name: str,
    stat_name: str,
    side: str,
    line: float,
    confidence: Confidence,
) -> str:
    """Generate insight statement text."""
    side_word = "exceed" if side == "over" else "fall short of"
    conf_pct = int(confidence.score_0_to_1 * 100)

    if confidence.sample_size > 0:
        return (
            f"{player_name} has {conf_pct}% hit rate "
            f"({confidence.hit_count}/{confidence.sample_size}) "
            f"trying to {side_word} {line:g} {stat_name}."
        )

    return f"{player_name} line set at {line:g} {stat_name}. Model confidence: {conf_pct}%."


def _build_pick(
    player_id: int,
    player_name: str,
    market_type: str,
    market_name: str,
    line: float,
    side: Literal["over", "under", "home", "away", "yes", "no"],
) -> Pick:
    """Build Pick object from line data."""
    market_key = f"{market_type}_line"
    return Pick(
        market_key=market_key,
        market_label=market_name,
        subject_type="player",
        subject_name=player_name,
        side=side,
        line=line,
    )


def _build_pricing(
    book_name: str,
    odds_over: int,
    odds_under: int,
    side: str,
) -> dict[str, Any]:
    """Build pricing dict with best_book and all_books."""
    selected_odds = odds_over if side == "over" else odds_under
    selected_decimal = _american_to_decimal(selected_odds)

    book_emoji = BOOK_EMOJI_MAP.get(book_name, "")

    best_book = BookPrice(
        book_key=book_name.lower().replace(" ", "_"),
        book_name=book_name,
        book_emoji=book_emoji,
        american_odds=selected_odds,
        decimal_odds=selected_decimal,
    ).to_dict()

    return {
        "best_book": best_book,
        "all_books": [best_book],
    }


@dataclass(frozen=True)
class BuildFeedConfig:
    """Configuration for building an insight feed."""

    lines_csv: Path
    parquet_path: Path | None = None
    league: str = "NBA"
    presentation: Presentation | None = None


def build_insight_feed(config: BuildFeedConfig) -> InsightFeed:
    """Build an InsightFeed from lines.csv and optional parquet data.

    Args:
        config: BuildFeedConfig with paths and settings

    Returns:
        InsightFeed ready for Discord webhook rendering
    """
    logger.info("Building insight feed from %s", config.lines_csv)

    if not config.lines_csv.exists():
        raise FileNotFoundError(f"Lines CSV not found: {config.lines_csv}")

    lines_df = pd.read_csv(config.lines_csv)
    if lines_df.empty:
        raise ValueError("Lines CSV is empty")

    logger.info("Loaded %d lines from CSV", len(lines_df))

    event_id = lines_df["event_id"].iloc[0]
    away_abbr, home_abbr, date_str = _parse_event_id(event_id)

    away_team = _get_team(away_abbr)
    home_team = _get_team(home_abbr)

    start_time_utc = f"{date_str}T00:00:00Z"
    display_time_local = date_str

    hero_title = f"{away_team.abbr} @ {home_team.abbr}"
    hero_card = HeroCard(
        title=hero_title,
        subtitle="Trending Insights",
        background_theme="teal_plum_gradient",
    )

    event = Event(
        event_id=event_id,
        start_time_utc=start_time_utc,
        display_time_local=display_time_local,
        away_team=away_team,
        home_team=home_team,
        hero_card=hero_card,
    )

    insights: list[Insight] = []
    seen_insights: set[str] = set()

    player_ids = lines_df["player_id"].tolist()
    player_names = lines_df["player_name"].tolist()
    game_dates = lines_df["game_date"].tolist()
    lines = lines_df["line"].tolist()

    sportsbooks = (
        lines_df["sportsbook"].tolist()
        if "sportsbook" in lines_df.columns
        else ["DraftKings"] * len(lines_df)
    )
    source_urls = (
        lines_df["source_url"].tolist()
        if "source_url" in lines_df.columns
        else [""] * len(lines_df)
    )
    market_types = (
        lines_df["market_type"].tolist()
        if "market_type" in lines_df.columns
        else ["points"] * len(lines_df)
    )
    market_names = (
        lines_df["market_name"].tolist()
        if "market_name" in lines_df.columns
        else ["Points"] * len(lines_df)
    )
    odds_overs = (
        lines_df["odds_over"].tolist()
        if "odds_over" in lines_df.columns
        else [-110] * len(lines_df)
    )
    odds_unders = (
        lines_df["odds_under"].tolist()
        if "odds_under" in lines_df.columns
        else [-110] * len(lines_df)
    )

    for idx in range(len(lines_df)):
        player_id_val = player_ids[idx]
        player_id = int(player_id_val) if pd.notna(player_id_val) else 0
        if player_id == 0:
            logger.warning("Skipping row %d with missing player_id", idx)
            continue

        player_name = str(player_names[idx]) if pd.notna(player_names[idx]) else "Unknown"
        game_date = str(game_dates[idx]) if pd.notna(game_dates[idx]) else ""
        line_val = lines[idx]
        line = float(line_val) if pd.notna(line_val) else 0.0
        odds_over_val = odds_overs[idx]
        odds_over = int(odds_over_val) if pd.notna(odds_over_val) else -110
        odds_under_val = odds_unders[idx]
        odds_under = int(odds_under_val) if pd.notna(odds_under_val) else -110
        book_name = str(sportsbooks[idx]) if pd.notna(sportsbooks[idx]) else "DraftKings"
        source_url = str(source_urls[idx]) if pd.notna(source_urls[idx]) else ""
        market_type_val = market_types[idx]
        market_type = str(market_type_val).lower() if pd.notna(market_type_val) else "points"
        market_name_val = market_names[idx]
        market_name = str(market_name_val) if pd.notna(market_name_val) else market_type.title()

        side_str = "over" if odds_over < odds_under else "under"
        side = cast(Literal["over", "under"], side_str)

        insight_id = f"nba:{game_date}:{event_id}:player:{player_id}:{market_type}:{side}:{line:g}"

        if insight_id in seen_insights:
            logger.debug("Skipping duplicate insight: %s", insight_id)
            continue
        seen_insights.add(insight_id)

        stats = _load_parquet_stats(config.parquet_path, player_id)

        pick = _build_pick(player_id, player_name, market_type, market_name, line, side)

        confidence = _build_confidence(stats, line, side)

        statement = _build_statement(player_name, market_name, side, line, confidence)

        pricing = _build_pricing(book_name, odds_over, odds_under, side)

        insight = Insight(
            insight_id=insight_id,
            rank=idx + 1,
            category="player_prop_trend",
            statement=statement,
            pick=pick,
            pricing=pricing,
            confidence=confidence,
            deeplink_add_to_betslip_url=source_url,
        )

        insights.append(insight)

    logger.info("Built %d insights for feed", len(insights))

    presentation = config.presentation or Presentation(
        brand_name="Quant-Sports",
        accent_color_decimal=4886754,
        hero_description="Top insights for matchup",
        footer_text="Trending Insights",
    )

    return InsightFeed(
        schema_version="1.0",
        generated_at=datetime.utcnow().isoformat() + "Z",
        league=config.league,
        event=event,
        insights=insights,
        presentation=presentation,
    )
