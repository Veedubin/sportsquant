"""
RAPTOR Composite Score

Combines the three RAPTOR components into a final score:
1. Box Score Component (individual statistics)
2. On-Off Component (team impact when on court)
3. Priors Component (age, height, draft, etc.)

Provides offensive/defensive breakdowns and final RAPTOR rating.

Data Sources:
- Player stats: TimescaleDB (player_stats table)
- Game data: Kafka topic 'sports-analytics-player-stats'
- Schedule: Kafka topic 'sports-schedules'
- Caching: Apache Ignite for player indices and computed features

Usage:
    >>> from quantitative_sports.models.ratings.raptor_composite import RaptorCompositeFeatures
    >>> from quantitative_sports.models.ratings.raptor_box import RaptorBoxConfig
    >>> from quantitative_sports.models.ratings.raptor_onoff import RaptorOnOffConfig
    >>> from quantitative_sports.models.ratings.raptor_priors import RaptorPriorsConfig
    >>> composite = RaptorCompositeFeatures()
    >>> raptor = composite.compute_all_raptor_features(player_df)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd
from pandas import DataFrame, Series

from quantitative_sports.models.ratings.raptor_box import RaptorBoxConfig, RaptorBoxFeatures
from quantitative_sports.models.ratings.raptor_onoff import RaptorOnOffConfig, RaptorOnOffFeatures
from quantitative_sports.models.ratings.raptor_priors import RaptorPriorsConfig, RaptorPriorsFeatures


@dataclass(frozen=True)
class RaptorCompositeConfig:  # pylint: disable=too-many-instance-attributes
    """Configuration for RAPTOR composite score."""

    box_weight: float = 0.45
    onoff_weight: float = 0.35
    priors_weight: float = 0.20

    box_offense_weight: float = 0.55
    box_defense_weight: float = 0.45

    onoff_offense_weight: float = 0.60
    onoff_defense_weight: float = 0.40

    min_games_for_raptor: int = 5
    raptor_mean: float = 0.0
    raptor_std: float = 2.0


class RaptorCompositeFeatures:
    """Compute final RAPTOR composite score.

    All feature calculation logic is preserved from the original implementation.
    Data sources have been adapted to use TimescaleDB and Kafka instead of Redis.
    """

    def __init__(
        self,
        box_config: Optional[RaptorBoxConfig] = None,
        onoff_config: Optional[RaptorOnOffConfig] = None,
        priors_config: Optional[RaptorPriorsConfig] = None,
        composite_config: Optional[RaptorCompositeConfig] = None,
    ):
        self.box_config = box_config or RaptorBoxConfig()
        self.onoff_config = onoff_config or RaptorOnOffConfig()
        self.priors_config = priors_config or RaptorPriorsConfig()
        self.composite_config = composite_config or RaptorCompositeConfig()

        self.box_features = RaptorBoxFeatures(self.box_config)
        self.onoff_features = RaptorOnOffFeatures(self.onoff_config)
        self.priors_features = RaptorPriorsFeatures(self.priors_config)

    def compute_raptor_components(self, df: DataFrame) -> DataFrame:
        """Compute all three RAPTOR components."""
        box = self.box_features.compute_all_box_features(df)
        onoff = self.onoff_features.compute_all_onoff_features(df)
        priors = self.priors_features.compute_all_priors(df)

        features = pd.concat([box, onoff, priors], axis=1)

        return features

    def compute_offensive_raptor(self, df: DataFrame) -> Series:
        """Compute offensive RAPTOR component."""
        box = self.box_features.compute_all_box_features(df)
        onoff = self.onoff_features.compute_all_onoff_features(df)
        priors = self.priors_features.compute_all_priors(df)

        box_off = self.composite_config.box_weight * self.composite_config.box_offense_weight
        onoff_off = self.composite_config.onoff_weight * self.composite_config.onoff_offense_weight
        priors_off = self.composite_config.priors_weight * 0.5

        offensive_raptor = (
            box_off * box["raptor_box_offense"].fillna(0)
            + onoff_off * onoff["raptor_onoff_weighted"].fillna(0)
            + priors_off * priors["raptor_positive_priors"].fillna(0)
        )

        return offensive_raptor

    def compute_defensive_raptor(self, df: DataFrame) -> Series:
        """Compute defensive RAPTOR component."""
        box = self.box_features.compute_all_box_features(df)
        onoff = self.onoff_features.compute_all_onoff_features(df)
        priors = self.priors_features.compute_all_priors(df)

        box_def = self.composite_config.box_weight * self.composite_config.box_defense_weight
        onoff_def = self.composite_config.onoff_weight * self.composite_config.onoff_defense_weight
        priors_def = self.composite_config.priors_weight * 0.5

        defensive_raptor = (
            box_def * box["raptor_box_defense"].fillna(0)
            + onoff_def * onoff["raptor_onoff_weighted"].fillna(0)
            + priors_def * priors["raptor_negative_priors"].fillna(0)
        )

        return defensive_raptor

    def compute_raptor_total(self, df: DataFrame) -> Series:
        """Compute total RAPTOR rating."""
        if df.empty:
            raise ValueError("DataFrame is empty — cannot compute RAPTOR total")
        offensive = self.compute_offensive_raptor(df)
        defensive = self.compute_defensive_raptor(df)

        total_raptor = offensive + defensive

        return total_raptor

    def compute_raptor_percentile(self, df: DataFrame) -> DataFrame:
        """Compute RAPTOR as percentile ranks."""
        features = DataFrame(index=df.index)

        total = self.compute_raptor_total(df)
        off = self.compute_offensive_raptor(df)
        def_val = self.compute_defensive_raptor(df)

        features["raptor_total"] = total
        features["raptor_offensive"] = off
        features["raptor_defensive"] = def_val

        features["raptor_total_percentile"] = total.rank(pct=True) * 100
        features["raptor_offensive_percentile"] = off.rank(pct=True) * 100
        features["raptor_defensive_percentile"] = def_val.rank(pct=True) * 100

        return features

    def compute_raptor_momentum(self, df: DataFrame) -> DataFrame:
        """Compute RAPTOR momentum (recent vs season averages)."""
        features = DataFrame(index=df.index)

        total_raptor = self.compute_raptor_total(df)
        recent_raptor = total_raptor.tail(10).mean()
        season_raptor = total_raptor.mean()

        features["raptor_momentum"] = recent_raptor - season_raptor

        box = self.box_features.compute_all_box_features(df)
        recent_box = box["raptor_box_total"].tail(10).mean()
        season_box = box["raptor_box_total"].mean()
        features["box_momentum"] = recent_box - season_box

        onoff = self.onoff_features.compute_all_onoff_features(df)
        recent_onoff = onoff["raptor_onoff_weighted"].tail(10).mean()
        season_onoff = onoff["raptor_onoff_weighted"].mean()
        features["onoff_momentum"] = recent_onoff - season_onoff

        features["raptor_trending_up"] = (features["raptor_momentum"] > 0.5).astype(float)
        features["raptor_trending_down"] = (features["raptor_momentum"] < -0.5).astype(float)

        return features

    def compute_all_raptor_features(self, df: DataFrame) -> DataFrame:
        """Compute all RAPTOR features for a player/game."""
        box = self.box_features.compute_all_box_features(df)
        onoff = self.onoff_features.compute_all_onoff_features(df)
        priors = self.priors_features.compute_all_priors(df)
        momentum = self.compute_raptor_momentum(df)

        features = pd.concat([box, onoff, priors, momentum], axis=1)

        raptor = self.compute_raptor_percentile(df)
        features["raptor_total"] = raptor["raptor_total"]
        features["raptor_offensive"] = raptor["raptor_offensive"]
        features["raptor_defensive"] = raptor["raptor_defensive"]
        features["raptor_total_percentile"] = raptor["raptor_total_percentile"]
        features["raptor_offensive_percentile"] = raptor["raptor_offensive_percentile"]
        features["raptor_defensive_percentile"] = raptor["raptor_defensive_percentile"]

        features["raptor_star_rating"] = (
            (features["raptor_total_percentile"] >= 95).astype(float)
            + (features["raptor_total_percentile"] >= 90).astype(float)
            + (features["raptor_total_percentile"] >= 75).astype(float)
        )

        features["raptor_role_classification"] = np.where(
            features["raptor_total_percentile"] >= 80,
            "star",
            np.where(
                features["raptor_total_percentile"] >= 60,
                "starter",
                np.where(
                    features["raptor_total_percentile"] >= 40,
                    "rotation",
                    np.where(
                        features["raptor_total_percentile"] >= 20,
                        "reserve",
                        "bench",
                    ),
                ),
            ),
        )

        return features

    def normalize_raptor_for_market(
        self,
        df: DataFrame,
        market: str = "pts",
    ) -> DataFrame:
        """Normalize RAPTOR for specific prop market.

        Different markets weight RAPTOR components differently.

        Data Sources:
        - Player stats: TimescaleDB (player_stats table)
        - Game data: Kafka topic 'sports-analytics-player-stats'
        """
        features = self.compute_all_raptor_features(df)

        if market == "pts":
            features["market_raptor"] = (
                features["raptor_offensive"] * 0.7 + features["raptor_defensive"] * 0.3
            )
            features["raptor_scoring_weight"] = 1.0
            features["raptor_playmaking_weight"] = 0.3
            features["raptor_rebounding_weight"] = 0.1
        elif market == "reb":
            features["market_raptor"] = (
                features["raptor_offensive"] * 0.2 + features["raptor_defensive"] * 0.8
            )
            features["raptor_scoring_weight"] = 0.1
            features["raptor_playmaking_weight"] = 0.1
            features["raptor_rebounding_weight"] = 1.0
        elif market == "ast":
            features["market_raptor"] = (
                features["raptor_offensive"] * 0.8 + features["raptor_defensive"] * 0.2
            )
            features["raptor_scoring_weight"] = 0.2
            features["raptor_playmaking_weight"] = 1.0
            features["raptor_rebounding_weight"] = 0.1
        elif market == "pra":
            features["market_raptor"] = features["raptor_total"]
            features["raptor_scoring_weight"] = 0.5
            features["raptor_playmaking_weight"] = 0.3
            features["raptor_rebounding_weight"] = 0.2
        else:
            features["market_raptor"] = features["raptor_total"]
            features["raptor_scoring_weight"] = 0.4
            features["raptor_playmaking_weight"] = 0.3
            features["raptor_rebounding_weight"] = 0.3

        return features
