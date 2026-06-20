"""
RAPTOR Box Score Component Features

Implements RAPTOR-style features from FiveThirtyEight methodology:
https://fivethirtyeight.com/features/how-our-raptor-metric-works/

Key components:
1. Scoring efficiency features
2. Playmaking features
3. Rebounding impact
4. Defensive indicators
5. Shot creation metrics
6. Pace/space indicators

Data Sources:
- Player stats: TimescaleDB (player_stats table)
- Game data: Kafka topic 'sports-analytics-player-stats'
- Schedule: Kafka topic 'sports-schedules'
- Caching: Apache Ignite for player indices and computed features

Usage:
    >>> from quantitative_sports.models.ratings.raptor_box import RaptorBoxFeatures
    >>> features = RaptorBoxFeatures()
    >>> box_features = features.compute_all_box_features(player_df)
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from pandas import DataFrame, Series


@dataclass(frozen=True)
class RaptorBoxConfig:
    """Configuration for RAPTOR box features."""

    scoring_weight: float = 0.30
    playmaking_weight: float = 0.20
    rebounding_weight: float = 0.15
    defensive_weight: float = 0.20
    spacing_weight: float = 0.15
    rolling_games: int = 10
    min_games_for_stats: int = 5


def _safe_divide(numerator: Series, denominator: Series, fill_value: float = 0.0) -> Series:
    """Safely divide two series, avoiding division by zero."""
    denom_arr = np.asarray(denominator, dtype=float)
    numer_arr = np.asarray(numerator, dtype=float)
    out_arr = np.full_like(numer_arr, np.nan, dtype=float)
    nonzero = ~np.isclose(denom_arr, 0.0, atol=1e-12)
    np.divide(numer_arr, denom_arr, out=out_arr, where=nonzero)
    out_arr = np.where(np.isfinite(out_arr), out_arr, fill_value)
    return Series(out_arr, index=numerator.index)


def _rolling_mean_lagged(series: Series, window: int) -> Series:
    """Compute rolling mean with 1-game lag to prevent leakage."""
    return Series(series.shift(1).rolling(window=window, min_periods=1).mean(), index=series.index)


def _rolling_std_lagged(series: Series, window: int) -> Series:
    """Compute rolling std with 1-game lag."""
    return Series(series.shift(1).rolling(window=window, min_periods=2).std(), index=series.index)


class RaptorBoxFeatures:
    """Compute RAPTOR-style box score features.

    All feature calculation logic is preserved from the original implementation.
    Data sources have been adapted to use TimescaleDB and Kafka instead of Redis.
    """

    def __init__(self, config: RaptorBoxConfig = RaptorBoxConfig()):
        self.config = config

    def compute_scoring_features(self, df: DataFrame) -> DataFrame:  # type: ignore[override]
        """Scoring efficiency features (RAPTOR values shot creation)."""
        # pylint: disable=R0914
        features = DataFrame(index=df.index)

        fga = _coerce_numeric(df, "fga")
        fta = _coerce_numeric(df, "fta")
        pts = _coerce_numeric(df, "pts")

        features["ts_pct"] = _safe_divide(pts, 2 * fga + 0.44 * fta)
        features["ts_pct"] = features["ts_pct"].clip(0, 2.0)

        fgm = _coerce_numeric(df, "fgm")
        fg3m = _coerce_numeric(df, "fg3m")

        features["efg_pct"] = _safe_divide(fgm + 0.5 * fg3m, fga)
        features["efg_pct"] = features["efg_pct"].clip(0, 2.0)

        features["pts_per_shot"] = _safe_divide(pts, fga)

        ftm = _coerce_numeric(df, "ftm")
        features["ft_rate"] = _safe_divide(ftm, fga)

        fg3a = _coerce_numeric(df, "fg3a")
        features["fg3_pct"] = _safe_divide(fg3m, fg3a)
        features["fg3_rate"] = _safe_divide(fg3a, fga)

        features["three_point_attempt_rate"] = _safe_divide(fg3a, fga)

        mins = _coerce_numeric(df, "min")
        features["pts_per_36"] = _safe_divide(pts, mins) * 36
        features["shot_volume"] = _safe_divide(fga, mins) * 36

        features["pts_std_last10"] = _rolling_std_lagged(pts, 10)

        pts_ma5 = _rolling_mean_lagged(pts, 5)
        pts_ma10 = _rolling_mean_lagged(pts, 10)
        features["pts_trend"] = pts_ma5 - pts_ma10

        features["usage_rate"] = _safe_divide(fga + fta, mins)

        fg2m = _coerce_numeric(df, "fg2m")
        fg2a = _coerce_numeric(df, "fg2a")
        features["rim_fg_pct"] = _safe_divide(fg2m, fg2a)

        if "fg2a" in df.columns:
            mid_range_a = fg2a - fg3a
            mid_range_m = fg2m - fg3m
            features["mid_range_pct"] = _safe_divide(mid_range_m, mid_range_a)
            features["mid_range_rate"] = _safe_divide(mid_range_a, fga)

        features["ft_pct"] = _safe_divide(ftm, fta)

        features["and1_per_36"] = _safe_divide(_coerce_numeric(df, "and1_fg"), mins) * 36

        features["opp_fg_pct_allowed"] = _coerce_numeric(df, "opp_fg_pct")

        return features

    def compute_playmaking_features(self, df: DataFrame) -> DataFrame:  # type: ignore[override]
        """Playmaking and ball-handling features."""
        # pylint: disable=R0914
        features = DataFrame(index=df.index)

        ast = _coerce_numeric(df, "ast")
        mins = _coerce_numeric(df, "min")

        features["ast_per_36"] = _safe_divide(ast, mins) * 36

        features["potential_ast_proxy"] = ast * 1.5
        features["ast_pct_possible"] = _safe_divide(
            ast, Series(features["potential_ast_proxy"], index=df.index)
        )

        fga = _coerce_numeric(df, "fga")
        fta = _coerce_numeric(df, "fta")
        to = _coerce_numeric(df, "to")

        usage_denom = Series(fga + 0.44 * fta + ast + to, index=df.index)
        features["ast_to_usage"] = _safe_divide(ast, usage_denom)

        features["secondary_ast_proxy"] = ast * 0.3

        features["passes_per_36"] = _safe_divide(ast * 3, mins) * 36

        features["touches_per_36"] = _safe_divide(_coerce_numeric(df, "touches"), mins) * 36

        features["poss_time_per_36"] = _safe_divide(_coerce_numeric(df, "touch_time"), mins) * 36

        features["dribbles_per_touch"] = _safe_divide(
            _coerce_numeric(df, "dribbles"), _coerce_numeric(df, "touches")
        )

        features["pullup_pts_per_36"] = _safe_divide(_coerce_numeric(df, "pullup_pts"), mins) * 36

        features["catch_shoot_pts_per_36"] = (
            _safe_divide(_coerce_numeric(df, "cand_s_pts"), mins) * 36
        )

        features["ast_to_ratio"] = _safe_divide(ast, to)

        ast_ma5 = _rolling_mean_lagged(ast, 5)
        ast_ma10 = _rolling_mean_lagged(ast, 10)
        features["ast_trend"] = ast_ma5 - ast_ma10

        return features

    def compute_rebounding_features(self, df: DataFrame) -> DataFrame:  # type: ignore[override]
        """Rebounding impact features."""
        features = DataFrame(index=df.index)

        reb = _coerce_numeric(df, "reb")
        mins = _coerce_numeric(df, "min")

        features["reb_per_36"] = _safe_divide(reb, mins) * 36

        orb = _coerce_numeric(df, "orb")
        features["orb_per_36"] = _safe_divide(orb, mins) * 36

        opp_drb = _coerce_numeric(df, "opp_drb")
        features["orb_pct"] = _safe_divide(orb, orb + opp_drb)

        drb = _coerce_numeric(df, "drb")
        features["drb_per_36"] = _safe_divide(drb, mins) * 36

        team_reb = _coerce_numeric(df, "team_reb")
        features["reb_pct"] = _safe_divide(reb, reb + team_reb)

        available_reb = orb + opp_drb
        features["reb_opp_rate"] = _safe_divide(reb, available_reb)

        features["second_chance_pts_per_36"] = (
            _safe_divide(_coerce_numeric(df, "second_chance_pts"), mins) * 36
        )

        features["tip_in_pts_per_36"] = _safe_divide(_coerce_numeric(df, "tip_in_pts"), mins) * 36

        features["reb_std_last10"] = _rolling_std_lagged(reb, 10)

        features["contested_reb_per_36"] = (
            _safe_divide(_coerce_numeric(df, "contested_reb"), mins) * 36
        )

        uncontested_reb = _coerce_numeric(df, "uncontested_reb")
        features["uncontested_reb_rate"] = _safe_divide(uncontested_reb, reb)

        return features

    def compute_defensive_features(self, df: DataFrame) -> DataFrame:  # type: ignore[override]
        """Defensive impact features."""
        features = DataFrame(index=df.index)

        mins = _coerce_numeric(df, "min")

        blk = _coerce_numeric(df, "blk")
        features["blk_per_36"] = _safe_divide(blk, mins) * 36

        stl = _coerce_numeric(df, "stl")
        features["stl_per_36"] = _safe_divide(stl, mins) * 36

        features["blk_stl_per_36"] = _safe_divide(blk + stl, mins) * 36

        features["deflections_per_36"] = _safe_divide(_coerce_numeric(df, "deflections"), mins) * 36

        contested_2pt = _coerce_numeric(df, "contested_2pt")
        contested_3pt = _coerce_numeric(df, "contested_3pt")

        features["contested_2pt_per_36"] = _safe_divide(contested_2pt, mins) * 36
        features["contested_3pt_per_36"] = _safe_divide(contested_3pt, mins) * 36
        features["total_contested_per_36"] = _safe_divide(contested_2pt + contested_3pt, mins) * 36

        features["def_ws_per_36"] = _safe_divide(_coerce_numeric(df, "def_ws"), mins) * 36

        opp_fg_pct = _coerce_numeric(df, "opp_fg_pct")
        features["opp_fg_pct_dfg"] = opp_fg_pct

        opp_fg3_pct = _coerce_numeric(df, "opp_fg3_pct")
        features["opp_fg3_pct_dfg"] = opp_fg3_pct

        features["charges_drawn_per_36"] = _safe_divide(_coerce_numeric(df, "charges"), mins) * 36

        features["box_outs_per_36"] = _safe_divide(_coerce_numeric(df, "box_outs"), mins) * 36

        features["loose_balls_per_36"] = _safe_divide(_coerce_numeric(df, "loose_balls"), mins) * 36

        pf = _coerce_numeric(df, "pf")
        features["fouls_per_36"] = _safe_divide(pf, mins) * 36

        features["def_activity"] = (
            features["blk_per_36"] + features["stl_per_36"] + features["deflections_per_36"] * 0.5
        )

        return features

    def compute_pacing_spacing_features(self, df: DataFrame) -> DataFrame:  # type: ignore[override]
        """Pace and floor spacing features (RAPTOR heavily values these)."""
        # pylint: disable=too-many-locals
        features = DataFrame(index=df.index)

        mins = _coerce_numeric(df, "min")

        features["speed_avg"] = _coerce_numeric(df, "speed")
        features["distance_per_36"] = _safe_divide(_coerce_numeric(df, "dist"), mins) * 36

        features["paint_touches_per_36"] = (
            _safe_divide(_coerce_numeric(df, "touches_paint"), mins) * 36
        )
        features["perimeter_touches_per_36"] = (
            _safe_divide(_coerce_numeric(df, "touches_perimeter"), mins) * 36
        )

        features["paint_to_perimeter_ratio"] = _safe_divide(
            Series(features["paint_touches_per_36"], index=df.index),
            Series(features["perimeter_touches_per_36"], index=df.index),
        )

        cand_s_3pm = _coerce_numeric(df, "cand_s_3pm")
        cand_s_3pa = _coerce_numeric(df, "cand_s_3pa")
        fga = _coerce_numeric(df, "fga")

        features["c_and_s_3p_pct"] = _safe_divide(cand_s_3pm, cand_s_3pa)
        features["c_and_s_3p_per_36"] = _safe_divide(cand_s_3pm, mins) * 36
        features["c_and_s_3p_rate"] = _safe_divide(cand_s_3pa, fga)

        pullup_3pm = _coerce_numeric(df, "pullup_3pm")
        features["pullup_3p_per_36"] = _safe_divide(pullup_3pm, mins) * 36
        features["pullup_3p_rate"] = _safe_divide(pullup_3pm, fga)

        time_as_pg = _coerce_numeric(df, "time_as_pg")
        time_off_ball = _coerce_numeric(df, "time_off_ball")

        features["ball_handler_time_pct"] = _safe_divide(time_as_pg, mins)
        features["off_ball_time_pct"] = _safe_divide(time_off_ball, mins)

        features["shot_creation_rate"] = _safe_divide(
            Series(features["pullup_3p_per_36"], index=df.index),
            Series(features["c_and_s_3p_per_36"], index=df.index),
        )

        transition_pts = _coerce_numeric(df, "transition_pts")
        half_court_pts = _coerce_numeric(df, "half_court_pts")

        features["transition_pts_per_36"] = _safe_divide(transition_pts, mins) * 36
        features["half_court_pts_per_36"] = _safe_divide(half_court_pts, mins) * 36
        features["transition_rate"] = _safe_divide(transition_pts, transition_pts + half_court_pts)

        avg_dist = _coerce_numeric(df, "avg_dist")
        features["avg_shot_distance"] = avg_dist

        pct_at_rim = _coerce_numeric(df, "pct_shots_at_rim")
        features["pct_shots_at_rim"] = pct_at_rim

        pct_from_3 = _coerce_numeric(df, "pct_shots_3pt")
        features["pct_shots_3pt"] = pct_from_3

        dist_ma5 = _rolling_mean_lagged(avg_dist, 5)
        dist_ma10 = _rolling_mean_lagged(avg_dist, 10)
        features["shot_distance_trend"] = dist_ma5 - dist_ma10

        return features

    def compute_all_box_features(self, df: DataFrame) -> DataFrame:  # type: ignore[override]
        """Compute all RAPTOR box score features."""
        features = DataFrame(index=df.index)

        scoring = self.compute_scoring_features(df)
        playmaking = self.compute_playmaking_features(df)
        rebounding = self.compute_rebounding_features(df)
        defensive = self.compute_defensive_features(df)
        pacing = self.compute_pacing_spacing_features(df)

        for feat_df in [scoring, playmaking, rebounding, defensive, pacing]:
            for col in feat_df.columns:
                features[col] = feat_df[col]

        features["raptor_box_offense"] = (
            self.config.scoring_weight
            * (
                scoring["ts_pct"].fillna(0.5) * 0.4
                + scoring["pts_per_36"].fillna(20) / 30 * 0.3
                + scoring["efg_pct"].fillna(0.5) * 0.3
            )
            + self.config.playmaking_weight
            * (
                playmaking["ast_per_36"].fillna(5) / 10 * 0.5
                + playmaking["ast_to_usage"].fillna(0.2) * 0.5
            )
            + self.config.spacing_weight
            * (
                pacing["c_and_s_3p_per_36"].fillna(2) / 4 * 0.5
                + pacing["pullup_3p_per_36"].fillna(1) / 3 * 0.5
            )
        )

        features["raptor_box_defense"] = self.config.defensive_weight * (
            defensive["blk_per_36"].fillna(1) / 3 * 0.4
            + defensive["stl_per_36"].fillna(1) / 3 * 0.4
            + defensive["def_activity"].fillna(3) / 6 * 0.2
        ) + self.config.rebounding_weight * (
            rebounding["orb_per_36"].fillna(1) / 3 * 0.3
            + rebounding["drb_per_36"].fillna(3) / 6 * 0.3
            + rebounding["reb_per_36"].fillna(6) / 10 * 0.4
        )

        features["raptor_box_total"] = (
            features["raptor_box_offense"] + features["raptor_box_defense"]
        )

        for col in ["raptor_box_offense", "raptor_box_defense", "raptor_box_total"]:
            mean_val = features[col].mean()
            std_val = features[col].std()
            if std_val > 0:
                features[col] = (features[col] - mean_val) / std_val * 2 + mean_val

        return features


def _coerce_numeric(df: DataFrame, col: str) -> Series:
    """Safely coerce column to numeric."""
    if col not in df.columns:
        return Series(0.0, index=df.index)
    col_series = df[col]
    numeric_vals = pd.to_numeric(col_series, errors="coerce")  # type: ignore[assignment]
    result = Series(numeric_vals, index=df.index)  # type: ignore[arg-type]
    result = result.fillna(0)  # type: ignore[assignment]
    return result
