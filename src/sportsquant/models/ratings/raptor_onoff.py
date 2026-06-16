"""
RAPTOR On-Off Component Features

Implements the on-court vs off-court performance differential component
from FiveThirtyEight's RAPTOR methodology.

Key components:
1. Team performance differentials when player is on vs off court
2. Lineup-adjusted on-off calculations
3. Reliability metrics for on-off estimates
4. Positional adjustments for on-off

Data Sources:
- Player stats: TimescaleDB (player_stats table)
- Game data: Kafka topic 'sports-analytics-player-stats'
- Schedule: Kafka topic 'sports-schedules'
- Caching: Apache Ignite for player indices and opponent strength

Usage:
    >>> from sportsquant.models.ratings.raptor_onoff import RaptorOnOffFeatures
    >>> features = RaptorOnOffFeatures()
    >>> onoff = features.compute_all_onoff_features(player_df)
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from pandas import DataFrame, Series


@dataclass(frozen=True)
class RaptorOnOffConfig:
    """Configuration for RAPTOR on-off features."""

    min_possessions_for_onoff: int = 100
    min_games_for_reliability: int = 10
    lookback_games: int = 20
    lineup_impact_window: int = 5


def _safe_divide(numerator: Series, denominator: float | Series, fill_value: float = 0.0) -> Series:
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
    shifted = series.shift(1)
    if shifted is None or not isinstance(shifted, Series):
        return Series(0.0, index=series.index)
    rolled = shifted.rolling(window=window, min_periods=1).mean()
    if rolled is None or not isinstance(rolled, Series):
        return Series(0.0, index=series.index)
    return rolled


class RaptorOnOffFeatures:
    """Compute RAPTOR-style on-off features.

    All feature calculation logic is preserved from the original implementation.
    Data sources have been adapted to use TimescaleDB and Kafka instead of Redis.
    """

    def __init__(self, config: RaptorOnOffConfig = RaptorOnOffConfig()):
        self.config = config

    def compute_onoff_differentials(self, df: DataFrame) -> DataFrame:
        """Compute basic on-off differentials from game-by-game data."""
        features = DataFrame(index=df.index)

        if "on_court" not in df.columns or "off_court" not in df.columns:
            return self._compute_synthetic_onoff(df, features)

        team_pts_on = _coerce_numeric(df, "team_pts_on")
        team_pts_off = _coerce_numeric(df, "team_pts_off")
        opp_pts_on = _coerce_numeric(df, "opp_pts_on")
        opp_pts_off = _coerce_numeric(df, "opp_pts_off")

        features["net_rating_on"] = team_pts_on - opp_pts_on
        features["net_rating_off"] = team_pts_off - opp_pts_off
        features["raw_onoff_net"] = features["net_rating_on"] - features["net_rating_off"]

        team_pts_on = _coerce_numeric(df, "team_pts_on")
        team_pts_off = _coerce_numeric(df, "team_pts_off")
        features["off_rating_on"] = team_pts_on
        features["off_rating_off"] = team_pts_off
        features["raw_onoff_off"] = team_pts_on - team_pts_off

        opp_pts_on = _coerce_numeric(df, "opp_pts_on")
        opp_pts_off = _coerce_numeric(df, "opp_pts_off")
        features["def_rating_on"] = opp_pts_on
        features["def_rating_off"] = opp_pts_off
        features["raw_onoff_def"] = opp_pts_off - opp_pts_on

        return features

    def _compute_synthetic_onoff(self, df: DataFrame, features: DataFrame) -> DataFrame:
        """Compute synthetic on-off when actual lineup data unavailable."""
        team_pts = _coerce_numeric(df, "team_pts")
        opp_pts = _coerce_numeric(df, "opp_pts")
        mins = _coerce_numeric(df, "min")
        plus_minus = _coerce_numeric(df, "plus_minus")

        team_orb = _coerce_numeric(df, "team_orb")
        team_trb = _coerce_numeric(df, "team_trb")
        team_ast = _coerce_numeric(df, "team_ast")

        team_orb_pct = _safe_divide(team_orb, team_trb)
        ast_rate = _safe_divide(team_ast, team_pts)

        features["net_rating_on"] = _safe_divide(plus_minus, mins) * 100 + 5
        features["net_rating_off"] = 0.0
        features["raw_onoff_net"] = features["net_rating_on"]

        features["off_rating_on"] = _safe_divide(team_pts, mins) * 12 + ast_rate * 20
        features["off_rating_off"] = _safe_divide(team_pts, mins) * 12
        features["raw_onoff_off"] = features["off_rating_on"] - features["off_rating_off"]

        features["def_rating_on"] = _safe_divide(opp_pts, mins) * 12 - team_orb_pct * 3
        features["def_rating_off"] = _safe_divide(opp_pts, mins) * 12
        features["raw_onoff_def"] = features["def_rating_off"] - features["def_rating_on"]

        return features

    def compute_lineup_adjusted_onoff(self, df: DataFrame) -> DataFrame:
        """Compute lineup-adjusted on-off (removing teammate effects)."""
        features = DataFrame(index=df.index)

        raw_onoff = self.compute_onoff_differentials(df)
        features["raw_onoff_net"] = raw_onoff["raw_onoff_net"]
        features["raw_onoff_off"] = raw_onoff["raw_onoff_off"]
        features["raw_onoff_def"] = raw_onoff["raw_onoff_def"]

        team_on_court = _coerce_numeric(df, "teammates_on_court")
        team_off_court = _coerce_numeric(df, "teammates_off_court")

        lineup_quality_on = _safe_divide(team_on_court, _coerce_numeric(df, "teammate_count_on"))
        lineup_quality_off = _safe_divide(team_off_court, _coerce_numeric(df, "teammate_count_off"))

        features["lineup_quality_on"] = lineup_quality_on
        features["lineup_quality_off"] = lineup_quality_off

        features["adj_onoff_net"] = (
            features["raw_onoff_net"] + (lineup_quality_off - lineup_quality_on) * 0.3
        )

        features["adj_onoff_off"] = (
            features["raw_onoff_off"] + (lineup_quality_off - lineup_quality_on) * 0.2
        )

        features["adj_onoff_def"] = (
            features["raw_onoff_def"] + (lineup_quality_on - lineup_quality_off) * 0.2
        )

        return features

    def compute_onoff_reliability(self, df: DataFrame) -> DataFrame:
        """Compute reliability metrics for on-off estimates."""
        features = DataFrame(index=df.index)

        possessions_on = _coerce_numeric(df, "poss_on_court")
        possessions_off = _coerce_numeric(df, "poss_off_court")
        total_poss = possessions_on + possessions_off

        features["possessions_on"] = possessions_on
        features["possessions_off"] = possessions_off
        features["total_possessions"] = total_poss

        features["on_court_pct"] = _safe_divide(possessions_on, total_poss)

        features["poss_reliability"] = _safe_divide(
            possessions_on, self.config.min_possessions_for_onoff
        ).clip(0, 1)

        raw_onoff = self.compute_onoff_differentials(df)
        raw_onoff_std = raw_onoff["raw_onoff_net"].std()
        on_court_std = raw_onoff["raw_onoff_net"][possessions_on > 0].std()
        off_court_std = raw_onoff["raw_onoff_net"][possessions_off > 0].std()

        if on_court_std > 0 and off_court_std > 0:
            features["onoff_signal_noise"] = (
                raw_onoff_std / (on_court_std + off_court_std) * np.sqrt(2)
            )
        else:
            features["onoff_signal_noise"] = 0.5

        features["onoff_reliability"] = (
            features["poss_reliability"] * features["onoff_signal_noise"]
        ).clip(0, 1)

        games_played = _coerce_numeric(df, "games_played")
        features["games_played"] = games_played
        features["games_reliability"] = _safe_divide(
            games_played, self.config.min_games_for_reliability
        ).clip(0, 1)

        features["combined_reliability"] = (
            features["onoff_reliability"] * 0.6 + features["games_reliability"] * 0.4
        )

        return features

    def compute_positional_onoff(self, df: DataFrame) -> DataFrame:
        """Compute position-specific on-off adjustments."""
        features = DataFrame(index=df.index)

        raw_onoff = self.compute_onoff_differentials(df)
        pos_raw = df.get("position")
        pos_series: Series = (
            pos_raw if isinstance(pos_raw, Series) else Series("unknown", index=df.index)
        )

        pos_adjustments = {
            "PG": {"off": 0.5, "def": -0.3},
            "SG": {"off": 0.3, "def": 0.0},
            "SF": {"off": 0.0, "def": 0.2},
            "PF": {"off": -0.2, "def": 0.5},
            "C": {"off": -0.5, "def": 0.8},
        }

        features["pos_adj_onoff_off"] = raw_onoff["raw_onoff_off"] + pos_series.map(
            lambda x: pos_adjustments.get(x, {"off": 0, "def": 0})["off"]
        )
        features["pos_adj_onoff_def"] = raw_onoff["raw_onoff_def"] + pos_series.map(
            lambda x: pos_adjustments.get(x, {"off": 0, "def": 0})["def"]
        )

        return features

    def compute_all_onoff_features(self, df: DataFrame) -> DataFrame:
        """Compute all RAPTOR on-off features."""
        features = DataFrame(index=df.index)

        onoff = self.compute_onoff_differentials(df)
        lineup_adj = self.compute_lineup_adjusted_onoff(df)
        reliability = self.compute_onoff_reliability(df)
        pos_adj = self.compute_positional_onoff(df)

        for feat_df in [onoff, lineup_adj, reliability, pos_adj]:
            for col in feat_df.columns:
                features[col] = feat_df[col]

        features["raptor_onoff_raw"] = features["raw_onoff_net"]
        features["raptor_onoff_adj"] = features["adj_onoff_net"]
        features["raptor_onoff_pos_adj"] = (
            features["pos_adj_onoff_off"] + features["pos_adj_onoff_def"]
        )

        reliability_weight = features["combined_reliability"]
        features["raptor_onoff_weighted"] = (
            features["raptor_onoff_adj"] * reliability_weight
            + features["raptor_onoff_raw"] * (1 - reliability_weight) * 0.5
        )

        return features


def _coerce_numeric(df: DataFrame, col: str) -> Series:
    """Safely coerce column to numeric."""
    if col not in df.columns:
        return Series(0.0, index=df.index)
    result = pd.to_numeric(df[col], errors="coerce")
    if result is None or not isinstance(result, Series):
        return Series(0.0, index=df.index)
    filled = result.fillna(0)
    if filled is None or not isinstance(filled, Series):
        return Series(0.0, index=df.index)
    return filled
