"""Game-level feature engineering for spreads, totals, and moneyline.

Aggregates player-level projections to team-level features for game outcome prediction.
Phase 5: Game-Level Betting Models
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional, cast

import numpy as np
import pandas as pd
from pandas import DataFrame, Series

from quantitative_sports.data.sources.curated.io import CuratedPaths, resolve_snapshot_id
from quantitative_sports.util.nba_logging import get_logger

logger = get_logger(__name__)


def _read_parquet_df(path: Path) -> DataFrame:
    """Typed wrapper around pandas.read_parquet."""
    return cast(DataFrame, cast(Any, pd).read_parquet(path))


def _coerce_numeric(df: DataFrame, col: str) -> Series:
    """Coerce column to numeric, filling errors with NaN."""
    if col not in df.columns:
        return pd.Series(np.nan, index=df.index, dtype="float64")
    return cast(Series, cast(Any, pd).to_numeric(df[col], errors="coerce"))


def aggregate_player_projections_to_team(
    player_features: DataFrame,
    *,
    date_col: str = "game_date",
    team_col: str = "team_abbr",
    minutes_col: str = "min_last_10_mean",
    min_minutes_threshold: float = 5.0,
) -> DataFrame:
    """Aggregate player-level features to team-level for a given game date.

    Args:
        player_features: PRA features DataFrame with player-level stats
        date_col: Column name for game date
        team_col: Column name for team abbreviation
        minutes_col: Column name for projected minutes
        min_minutes_threshold: Minimum minutes to include player

    Returns:
        DataFrame with team-level aggregated features per game date
    """
    # Filter to players with meaningful minutes
    df = player_features.copy()
    df[minutes_col] = _coerce_numeric(df, minutes_col)
    df = df[df[minutes_col] >= min_minutes_threshold].copy()

    if df.empty:
        return DataFrame()

    # Aggregate to team-date level
    gb = cast(Any, df).groupby([date_col, team_col], dropna=False)

    agg_dict: dict[str, Any] = {
        minutes_col: "sum",
        "pra_last_10_mean": "sum",
        "y_points": "sum",
        "ppm_last_10_mean": "mean",
        "rpm_last_10_mean": "mean",
        "apm_last_10_mean": "mean",
        "rest_days": "mean",
        "is_back_to_back": "max",
        "games_last_7_days": "max",
    }

    # Filter to columns that exist
    agg_dict_filtered = {k: v for k, v in agg_dict.items() if k in df.columns}

    team_agg = cast(DataFrame, gb.agg(agg_dict_filtered).reset_index())

    # Calculate PRA to points conversion ratio per team-date
    # This uses historical data to convert projected PRA to expected points
    if "pra_last_10_mean" in team_agg.columns and "y_points" in team_agg.columns:
        pra_total = team_agg["pra_last_10_mean"]
        points_total = team_agg["y_points"]
        # Use mean ratio, but handle edge cases
        pra_to_points_ratio = (
            (points_total / pra_total.replace(0, 1))
            .replace([float("inf"), float("-inf")], float("nan"))
            .fillna(0.5)
        )
        team_agg["pra_to_points_ratio"] = pra_to_points_ratio.clip(0.3, 0.7)
    else:
        team_agg["pra_to_points_ratio"] = 0.5  # Default fallback

    # Rename aggregated columns
    rename_map = {
        minutes_col: "team_proj_minutes",
        "pra_last_10_mean": "team_proj_pra",
        "y_points": "team_hist_points",
        "ppm_last_10_mean": "team_avg_ppm",
        "rpm_last_10_mean": "team_avg_rpm",
        "apm_last_10_mean": "team_avg_apm",
        "rest_days": "team_avg_rest_days",
        "is_back_to_back": "team_is_back_to_back",
        "games_last_7_days": "team_games_last_7_days",
    }
    team_agg = team_agg.rename(
        columns={k: v for k, v in rename_map.items() if k in team_agg.columns}
    )

    # Calculate projected points from PRA using the conversion ratio
    team_agg["team_proj_points"] = team_agg["team_proj_pra"] * team_agg["pra_to_points_ratio"]

    return team_agg


def build_game_matchup_features(
    player_features: DataFrame,
    *,
    date_col: str = "game_date",
    team_col: str = "team_abbr",
    opp_col: str = "opp_team_abbr",
    is_home_col: str = "is_home",
) -> DataFrame:
    """Build game-level matchup features from player features.

    Each row represents one game (team vs opponent on a date).

    Args:
        player_features: PRA features DataFrame
        date_col: Game date column
        team_col: Team abbreviation column
        opp_col: Opponent team abbreviation column
        is_home_col: Home indicator column

    Returns:
        DataFrame with one row per game, containing both team and opponent projections
    """
    # Aggregate players to team level
    team_agg = aggregate_player_projections_to_team(
        player_features,
        date_col=date_col,
        team_col=team_col,
    )

    if team_agg.empty:
        return DataFrame()

    # Extract home indicator per team-date
    home_indicators = (
        player_features[[date_col, team_col, is_home_col]]
        .drop_duplicates()
        .groupby([date_col, team_col], dropna=False)[is_home_col]
        .first()
        .reset_index()
    )

    team_agg = team_agg.merge(home_indicators, on=[date_col, team_col], how="left")

    # Extract opponent per team-date
    opponents = (
        player_features[[date_col, team_col, opp_col]]
        .drop_duplicates()
        .groupby([date_col, team_col], dropna=False)[opp_col]
        .first()
        .reset_index()
    )

    team_agg = team_agg.merge(opponents, on=[date_col, team_col], how="left")

    # Build matchups: join team with opponent on same date
    # Home team perspective
    home_games = team_agg[team_agg[is_home_col] == 1].copy()
    away_games = team_agg[team_agg[is_home_col] == 0].copy()

    # Merge home and away on date + matchup
    matchups = home_games.merge(
        away_games,
        left_on=[date_col, opp_col],
        right_on=[date_col, team_col],
        how="inner",
        suffixes=("_home", "_away"),
    )

    # Clean up column names
    matchups = matchups.rename(
        columns={
            f"{team_col}_home": "home_team",
            f"{team_col}_away": "away_team",
            date_col: "game_date",
        }
    )

    # Calculate differential features
    if "team_proj_points_home" in matchups.columns and "team_proj_points_away" in matchups.columns:
        matchups["proj_point_differential"] = (
            matchups["team_proj_points_home"] - matchups["team_proj_points_away"]
        )
        matchups["proj_total_points"] = (
            matchups["team_proj_points_home"] + matchups["team_proj_points_away"]
        )
    elif "team_proj_pra_home" in matchups.columns and "team_proj_pra_away" in matchups.columns:
        matchups["proj_point_differential"] = (
            matchups["team_proj_pra_home"] - matchups["team_proj_pra_away"]
        )
        matchups["proj_total_points"] = (
            matchups["team_proj_pra_home"] + matchups["team_proj_pra_away"]
        )

    # Rest advantage
    if (
        "team_avg_rest_days_home" in matchups.columns
        and "team_avg_rest_days_away" in matchups.columns
    ):
        matchups["rest_advantage_home"] = (
            matchups["team_avg_rest_days_home"] - matchups["team_avg_rest_days_away"]
        )

    return matchups


def build_game_features_from_snapshot(
    cache_root: Path,
    *,
    league: str = "nba",
    season: str,
    snapshot_id: Optional[str] = None,
) -> DataFrame:
    """Build game-level features from a season snapshot's PRA features.

    Args:
        cache_root: Cache root directory
        league: League name
        season: Season string (e.g., "2025-26")
        snapshot_id: Optional snapshot ID (defaults to current)

    Returns:
        DataFrame with game-level matchup features
    """
    sid = resolve_snapshot_id(cache_root, league=league, season=season, snapshot_id=snapshot_id)
    if sid is None:
        logger.warning("no snapshot found for season %s", season)
        return DataFrame()

    paths = CuratedPaths(cache_root=cache_root, league=league, season=season, snapshot_id=sid)
    pra_features_path = paths.features_dir() / f"pra_features_{season}.parquet"

    if not pra_features_path.exists():
        logger.warning("PRA features not found: %s", pra_features_path)
        return DataFrame()

    player_features = _read_parquet_df(pra_features_path)

    game_features = build_game_matchup_features(player_features)

    # Write to snapshot
    game_features_path = paths.features_dir() / f"game_features_{season}.parquet"
    game_features_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        cast(Any, game_features).to_parquet(game_features_path, index=False)
        logger.info("wrote game features: %s (rows=%s)", game_features_path, len(game_features))
    except (OSError, ValueError, ImportError):
        logger.exception("failed writing game features: %s", game_features_path)

    return game_features
