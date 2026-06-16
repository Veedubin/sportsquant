"""NFL data source module.

Provides unified access to NFL data sources:
- nflfastR (play-by-play and player stats)
- ESPN NFL injuries
- Pinnacle NFL odds
- The Odds API NFL odds

All sources support caching to disk and return normalized DataFrames.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd


# ──────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────


@dataclass
class NFLDataConfig:
    """Configuration for NFL data fetching."""

    cache_dir: Path = Path("./cache/nfl")
    current_season: int = 2024
    nflfastr_base_url: str = (
        "https://github.com/nflverse/nflverse-data/releases/download/player_stats"
    )
    espn_injury_url: str = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/injuries"
    pinnacle_sport_id: str = "football_nfl"
    odds_api_sport_key: str = "americanfootball_nfl"


# ──────────────────────────────────────────────
# nflfastR Data Fetcher
# ──────────────────────────────────────────────


class NFLfastRSource:
    """Fetches player stats from nflverse GitHub releases.

    Data URL pattern:
        {base_url}/player_stats_{season}.csv.gz

    Columns include:
        player_id, player_display_name, position, team,
        season, week, passing_yards, passing_tds, interceptions,
        rushing_yards, rushing_tds, receiving_yards, receptions,
        receiving_tds, targets, completions, attempts, carries,
        fantasy_points, fantasy_points_ppr
    """

    def __init__(self, config: NFLDataConfig):
        self.config = config
        self._season_cache: dict[int, pd.DataFrame] = {}
        config.cache_dir.mkdir(parents=True, exist_ok=True)

    def get_season(self, season: int) -> Optional[pd.DataFrame]:
        """Fetch player stats for an entire NFL season."""
        if season in self._season_cache:
            return self._season_cache[season]

        cache_path = self.config.cache_dir / f"nflfastr_{season}.csv.gz"

        # Check disk cache
        if cache_path.exists():
            try:
                df = pd.read_csv(cache_path, compression="gzip")
                if df is not None and not df.empty:
                    self._season_cache[season] = df
                    return df
            except Exception:
                cache_path.unlink(missing_ok=True)

        # Download from GitHub
        url = f"{self.config.nflfastr_base_url}/player_stats_{season}.csv.gz"
        try:
            df = pd.read_csv(url, compression="gzip")
            if df is not None and not df.empty:
                df.to_csv(cache_path, compression="gzip", index=False)
                self._season_cache[season] = df
                return df
        except Exception as e:
            print(f"nflfastR download failed for {season}: {e}")

        return None

    def get_player_gamelog(
        self, player_id: str, seasons: Optional[list[int]] = None, n_games: int = 10
    ) -> pd.DataFrame:
        """Get recent game log for a specific player."""
        if seasons is None:
            seasons = [self.config.current_season, self.config.current_season - 1]

        frames = []
        for season in seasons:
            df = self.get_season(season)
            if df is not None and "player_id" in df.columns:
                player_games = df[df["player_id"] == player_id]
                if not player_games.empty:
                    frames.append(player_games)

        if not frames:
            return pd.DataFrame()

        combined = pd.concat(frames, ignore_index=True)
        combined = combined.sort_values(["season", "week"], ascending=[False, False])
        return combined.head(n_games)

    def search_player(self, name: str) -> Optional[str]:
        """Search for player ID by name."""
        last_name = name.split()[-1] if name else ""
        if not last_name:
            return None

        for season in [self.config.current_season, self.config.current_season - 1]:
            df = self.get_season(season)
            if df is not None and "player_display_name" in df.columns:
                matches = df[
                    df["player_display_name"].str.contains(last_name, case=False, na=False)
                ]
                if not matches.empty:
                    player_id = matches.iloc[0].get("player_id")
                    if pd.notna(player_id):
                        return player_id
        return None


# ──────────────────────────────────────────────
# ESPN NFL Injuries
# ──────────────────────────────────────────────


class ESPNInjurySource:
    """Fetches NFL injury reports from ESPN public API.

    Endpoint: https://site.api.espn.com/apis/site/v2/sports/football/nfl/injuries

    Returns:
        DataFrame with columns: team, player_name, position, status,
        injury_type, practice_status, game_status
    """

    def __init__(self, config: NFLDataConfig):
        self.config = config

    def fetch(self) -> pd.DataFrame:
        """Fetch current NFL injury report."""
        url = self.config.espn_injury_url
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})

        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                data = json.loads(response.read().decode())
        except Exception as e:
            print(f"ESPN injury fetch failed: {e}")
            return pd.DataFrame()

        records = []
        for team_entry in data.get("injuries", []):
            team = team_entry.get("team", {}).get("displayName", "Unknown")
            for injury in team_entry.get("injuries", []):
                records.append(
                    {
                        "team": team,
                        "player_name": injury.get("athlete", {}).get("displayName", ""),
                        "position": injury.get("athlete", {})
                        .get("position", {})
                        .get("abbreviation", ""),
                        "status": injury.get("status", ""),
                        "injury_type": injury.get("type", {}).get("name", ""),
                        "practice_status": injury.get("practiceStatus", ""),
                        "game_status": injury.get("gameStatus", ""),
                    }
                )

        return pd.DataFrame(records)


# ──────────────────────────────────────────────
# Pinnacle NFL Odds
# ──────────────────────────────────────────────


class PinnacleNFLOddsSource:
    """Fetches NFL odds from Pinnacle (sharp book).

    Pinnacle is the market-maker — their odds represent the
    sharpest lines available. Used for:
    - Fair value estimation (remove vig from Pinnacle lines)
    - Market efficiency analysis
    - Cross-book arbitrage detection

    Note: Requires Pinnacle API access. The current pinnacle/
    module is a stub. This class provides the interface.
    """

    def __init__(self, config: NFLDataConfig):
        self.config = config

    def fetch_games(self, week: Optional[int] = None) -> pd.DataFrame:
        """Fetch NFL game odds from Pinnacle.

        Returns DataFrame with: game_id, home_team, away_team,
        commence_time, ml_home, ml_away, spread_home, spread_home_price,
        spread_away_price, total, total_over_price, total_under_price
        """
        # STUB — requires Pinnacle API implementation
        return pd.DataFrame()

    def fetch_props(self, game_id: str) -> pd.DataFrame:
        """Fetch player props for a specific game."""
        return pd.DataFrame()


# ──────────────────────────────────────────────
# Unified NFL Data Pipeline
# ──────────────────────────────────────────────


class NFLDataPipeline:
    """Unified NFL data access layer.

    Combines all NFL data sources with caching and normalization.
    This is the primary interface for notebooks, CLI, and MCP tools.
    """

    def __init__(self, config: Optional[NFLDataConfig] = None):
        self.config = config or NFLDataConfig()
        self.nflfastr = NFLfastRSource(self.config)
        self.injuries = ESPNInjurySource(self.config)
        self.pinnacle = PinnacleNFLOddsSource(self.config)

    def get_player_stats(
        self, player_name: str, stat_types: list[str], n_games: int = 10
    ) -> pd.DataFrame:
        """Get recent game stats for a player."""
        player_id = self.nflfastr.search_player(player_name)
        if player_id is None:
            return pd.DataFrame()
        return self.nflfastr.get_player_gamelog(player_id, n_games=n_games)

    def get_injury_report(self) -> pd.DataFrame:
        """Get current NFL injury report."""
        return self.injuries.fetch()

    def get_odds(self, week: Optional[int] = None) -> pd.DataFrame:
        """Get NFL game odds."""
        return self.pinnacle.fetch_games(week=week)

    def get_all_data(self, week: Optional[int] = None) -> dict[str, pd.DataFrame]:
        """Fetch all available NFL data for a given week."""
        return {
            "injuries": self.get_injury_report(),
            "odds": self.get_odds(week=week),
            "fetched_at": datetime.utcnow().isoformat(),
        }
