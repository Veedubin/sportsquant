"""
RAPTOR Predictive Priors

Implements the prior-based adjustments from FiveThirtyEight's RAPTOR methodology.
These priors capture contextual factors that influence expected performance
beyond what raw statistics show.

Key priors:
1. Age curve (performance peaks at 27-28, declines after)
2. Height adjustments (spacing value in modern NBA)
3. Draft position priors (lottery vs late round vs undrafted)
4. Contract year motivation
5. All-NBA team indicators
6. Injury history adjustments
7. Rest days and schedule adjustments

Data Sources:
- Player info: TimescaleDB (player_info table)
- Game data: Kafka topic 'sports-analytics-player-stats'
- Schedule: Kafka topic 'sports-schedules'
- Caching: Apache Ignite for player indices

Usage:
    >>> from quantitative_sports.models.ratings.raptor_priors import RaptorPriorsFeatures
    >>> features = RaptorPriorsFeatures()
    >>> priors = features.compute_all_priors(player_df)
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from pandas import DataFrame, Series


@dataclass(frozen=True)
class RaptorPriorsConfig:  # pylint: disable=too-many-instance-attributes
    """Configuration for RAPTOR predictive priors."""

    age_curve_peak: int = 27
    age_curve_peak_impact: float = 1.05
    age_curve_decline_rate: float = 0.015
    height_inches_weight: float = 0.3
    draft_lottery_bonus: float = 1.5
    draft_late_round_bonus: float = 0.5
    undrafted_bonus: float = -1.0
    contract_year_bonus: float = 2.0
    all_nba_bonus: float = 3.0
    injury_return_factor: float = 0.85
    b2b_adjustment: float = -1.0
    rest_day_bonus: float = 0.5


def _safe_divide(numerator: Series, denominator: Series, fill_value: float = 0.0) -> Series:
    """Safely divide two series, avoiding division by zero."""
    denom_arr = np.asarray(denominator, dtype=float)
    numer_arr = np.asarray(numerator, dtype=float)
    out_arr = np.full_like(numer_arr, np.nan, dtype=float)
    nonzero = ~np.isclose(denom_arr, 0.0, atol=1e-12)
    np.divide(numer_arr, denom_arr, out=out_arr, where=nonzero)
    out_arr = np.where(np.isfinite(out_arr), out_arr, fill_value)
    return Series(out_arr, index=numerator.index)


def _coerce_numeric(df: DataFrame, col: str) -> Series:
    """Safely coerce column to numeric."""
    if col not in df.columns:
        return Series(0.0, index=df.index)
    return pd.to_numeric(df[col], errors="coerce").fillna(0)


class RaptorPriorsFeatures:
    """Compute RAPTOR predictive prior features.

    All feature calculation logic is preserved from the original implementation.
    Data sources have been adapted to use TimescaleDB and Kafka instead of Redis.
    """

    def __init__(self, config: RaptorPriorsConfig = RaptorPriorsConfig()):
        self.config = config

    def compute_age_prior(self, df: DataFrame) -> DataFrame:  # type: ignore[override]
        """Compute age-based performance priors.

        RAPTOR assumes players peak around age 27-28.
        - Ages 25-30: near peak performance
        - Ages 20-24: still developing
        - Ages 31+: gradual decline
        """
        features = DataFrame(index=df.index)

        age = _coerce_numeric(df, "age")

        age_diff_from_peak = age - self.config.age_curve_peak

        features["age_years"] = age
        features["age_diff_from_peak"] = age_diff_from_peak

        age_effect = np.where(
            age_diff_from_peak <= 0,
            self.config.age_curve_peak_impact + age_diff_from_peak * 0.02,
            self.config.age_curve_peak_impact
            - age_diff_from_peak * self.config.age_curve_decline_rate,
        )
        features["age_prior"] = age_effect

        age_squared = age_diff_from_peak**2
        features["age_squared"] = age_squared

        features["prime_years"] = ((age >= 25) & (age <= 30)).astype(float)
        features["young_player"] = ((age >= 19) & (age < 25)).astype(float)
        features["veteran_player"] = ((age > 30) & (age < 35)).astype(float)
        features["aged_player"] = (age >= 35).astype(float)

        return features

    def compute_height_prior(self, df: DataFrame) -> DataFrame:  # type: ignore[override]
        """Compute height-based priors for spacing value.

        Modern NBA values shooting and spacing.
        - Point guards often have most spacing value
        - Centers have interior value
        - Forwards need versatility
        """
        features = DataFrame(index=df.index)

        height_cm = _coerce_numeric(df, "height_cm")
        position_raw = df.get("position", pd.Series("unknown", index=df.index))
        if position_raw is None:
            position = pd.Series("unknown", index=df.index)
        else:
            position = position_raw.fillna("unknown")

        height_inches = height_cm / 2.54
        features["height_inches"] = height_inches
        features["height_cm"] = height_cm

        pos_height_adjustments = {
            "PG": 0.3,
            "SG": 0.2,
            "SF": 0.0,
            "PF": -0.2,
            "C": -0.4,
        }

        base_height_value = height_inches - 78
        features["base_height_value"] = base_height_value

        features["height_spacing_value"] = base_height_value + position.map(
            lambda x: pos_height_adjustments.get(x, 0)
        )

        position_multipliers = {
            "PG": 1.2,
            "SG": 1.1,
            "SF": 1.0,
            "PF": 0.9,
            "C": 0.7,
        }
        features["position_height_interaction"] = height_inches * position.map(
            lambda x: position_multipliers.get(x, 1.0)
        )

        features["tall_guard"] = ((position == "PG") & (height_inches > 76)).astype(float)
        features["short_big"] = ((position == "C") & (height_inches < 82)).astype(float)

        return features

    def compute_draft_prior(self, df: DataFrame) -> DataFrame:  # type: ignore[override]
        """Compute draft position priors.

        Draft position captures pre-NBA talent evaluation:
        - Lottery picks: high expected value
        - Late first/second round: solid role players
        - Undrafted: must prove themselves
        """
        features = DataFrame(index=df.index)

        draft_pick = _coerce_numeric(df, "draft_pick")
        draft_round = _coerce_numeric(df, "draft_round")
        years_pro = _coerce_numeric(df, "years_pro")

        features["draft_pick"] = draft_pick
        features["draft_round"] = draft_round
        features["years_pro"] = years_pro

        features["lottery_pick"] = (draft_pick <= 14).astype(float)
        features["top_5_pick"] = (draft_pick <= 5).astype(float)

        draft_value = np.where(
            draft_round == 0,
            0,
            np.where(
                draft_pick <= 14,
                self.config.draft_lottery_bonus * (15 - draft_pick) / 14,
                np.where(
                    draft_round <= 2,
                    self.config.draft_late_round_bonus,
                    np.where(draft_pick > 60, self.config.undrafted_bonus, 0),
                ),
            ),
        )
        features["draft_value_prior"] = draft_value

        features["draft_pick_years_pro_interaction"] = draft_value * np.clip(years_pro, 0.5, 5)

        features["late_round_success"] = (
            (draft_round > 2) & (years_pro >= 3) & (draft_pick > 30)
        ).astype(float)

        return features

    def compute_contract_year_prior(self, df: DataFrame) -> DataFrame:  # type: ignore[override]
        """Compute contract year motivation priors.

        Players often perform better in contract years.
        """
        features = DataFrame(index=df.index)

        years_on_current_team = _coerce_numeric(df, "years_on_current_team")
        contract_years_remaining = _coerce_numeric(df, "contract_years_remaining")
        is_contract_year = _coerce_numeric(df, "is_contract_year")
        max_contract_year = _coerce_numeric(df, "max_contract_year")

        features["years_on_team"] = years_on_current_team
        features["contract_years_left"] = contract_years_remaining
        features["is_contract_year"] = is_contract_year
        features["max_contract_year"] = max_contract_year

        contract_motivation = np.where(
            is_contract_year == 1,
            self.config.contract_year_bonus,
            np.where(
                contract_years_remaining == 1,
                self.config.contract_year_bonus * 0.7,
                np.where(
                    contract_years_remaining == 2,
                    self.config.contract_year_bonus * 0.3,
                    0,
                ),
            ),
        )
        features["contract_year_prior"] = contract_motivation

        features["up_for_extension"] = (
            (contract_years_remaining == 1) & (is_contract_year == 0)
        ).astype(float)

        return features

    def compute_all_star_prior(self, df: DataFrame) -> DataFrame:  # type: ignore[override]
        """Compute All-Star/All-NBA prior adjustments."""
        features = DataFrame(index=df.index)

        all_nba_teams = _coerce_numeric(df, "all_nba_teams")
        all_star_games = _coerce_numeric(df, "all_star_games")
        all_nba_first = _coerce_numeric(df, "all_nba_first")
        all_nba_second = _coerce_numeric(df, "all_nba_second")
        all_nba_third = _coerce_numeric(df, "all_nba_third")

        features["all_nba_teams"] = all_nba_teams
        features["all_star_games"] = all_star_games
        features["all_nba_first"] = all_nba_first
        features["all_nba_second"] = all_nba_second
        features["all_nba_third"] = all_nba_third

        all_nba_value = (
            all_nba_first * self.config.all_nba_bonus
            + all_nba_second * self.config.all_nba_bonus * 0.6
            + all_nba_third * self.config.all_nba_bonus * 0.3
        )
        features["all_nba_prior"] = all_nba_value

        features["all_star_prior"] = all_star_games * 0.15

        features["superstar_indicator"] = (all_nba_teams >= 3).astype(float)
        features["elite_player"] = (all_nba_teams >= 1).astype(float)

        return features

    def compute_injury_prior(self, df: DataFrame) -> DataFrame:  # type: ignore[override]
        """Compute injury history and return priors."""
        features = DataFrame(index=df.index)

        games_missed_prev_season = _coerce_numeric(df, "games_missed_prev_season")
        days_since_injury = _coerce_numeric(df, "days_since_injury")
        injury_severity = _coerce_numeric(df, "injury_severity")
        games_played_this_season = _coerce_numeric(df, "games_played_this_season")

        features["games_missed_prev"] = games_missed_prev_season
        features["days_since_injury"] = days_since_injury
        features["injury_severity"] = injury_severity
        features["games_played_this_season"] = games_played_this_season

        injury_recovery = np.where(
            days_since_injury <= 30,
            self.config.injury_return_factor
            + (30 - days_since_injury) / 30 * (1 - self.config.injury_return_factor),
            np.where(
                days_since_injury <= 90,
                1.0 - (days_since_injury - 90) / 180 * (1 - self.config.injury_return_factor),
                1.0,
            ),
        )
        features["injury_recovery_factor"] = injury_recovery

        features["injury_impact"] = injury_severity * (1 - injury_recovery) * -0.5

        features["durability_bonus"] = (games_missed_prev_season == 0).astype(float)
        features["injury_concern"] = (
            (games_missed_prev_season >= 20) & (days_since_injury < 90)
        ).astype(float)

        return features

    def compute_schedule_prior(self, df: DataFrame) -> DataFrame:  # type: ignore[override]
        """Compute schedule-based priors (rest, travel, back-to-back)."""
        features = DataFrame(index=df.index)

        days_rest = _coerce_numeric(df, "days_rest")
        games_in_last_7 = _coerce_numeric(df, "games_in_last_7")
        travel_distance = _coerce_numeric(df, "travel_distance_miles")
        is_b2b = _coerce_numeric(df, "is_b2b")
        b2b_game_number = _coerce_numeric(df, "b2b_game_number")

        features["days_rest"] = days_rest
        features["games_in_last_7"] = games_in_last_7
        features["travel_miles"] = travel_distance
        features["is_b2b"] = is_b2b
        features["b2b_number"] = b2b_game_number

        rest_effect = np.where(
            days_rest == 0,
            self.config.b2b_adjustment,
            np.where(
                days_rest == 1,
                self.config.b2b_adjustment * 0.5,
                np.where(
                    days_rest >= 3,
                    self.config.rest_day_bonus,
                    self.config.rest_day_bonus * 0.5,
                ),
            ),
        )
        features["rest_prior"] = rest_effect

        features["schedule_impact"] = rest_effect - travel_distance / 3000 - games_in_last_7 * 0.1

        features["fresh_legs"] = (days_rest >= 2).astype(float)
        features["heavy_legs"] = (games_in_last_7 >= 4).astype(float)

        return features

    def compute_all_priors(self, df: DataFrame) -> DataFrame:  # type: ignore[override]
        """Compute all RAPTOR prior features."""
        features = DataFrame(index=df.index)

        age = self.compute_age_prior(df)
        height = self.compute_height_prior(df)
        draft = self.compute_draft_prior(df)
        contract = self.compute_contract_year_prior(df)
        allstar = self.compute_all_star_prior(df)
        injury = self.compute_injury_prior(df)
        schedule = self.compute_schedule_prior(df)

        for feat_df in [age, height, draft, contract, allstar, injury, schedule]:
            for col in feat_df.columns:
                features[col] = feat_df[col]

        age_prior = (
            features.get("age_prior")
            if "age_prior" in features
            else pd.Series([1.0], index=features.index)
        )
        draft_prior = (
            features.get("draft_value_prior")
            if "draft_value_prior" in features
            else pd.Series([0], index=features.index)
        )
        contract_prior = (
            features.get("contract_year_prior")
            if "contract_year_prior" in features
            else pd.Series([0], index=features.index)
        )
        all_nba_prior = (
            features.get("all_nba_prior")
            if "all_nba_prior" in features
            else pd.Series([0], index=features.index)
        )
        injury_recov = (
            features.get("injury_recovery_factor")
            if "injury_recovery_factor" in features
            else pd.Series([1.0], index=features.index)
        )
        rest_prior = (
            features.get("rest_prior")
            if "rest_prior" in features
            else pd.Series([0], index=features.index)
        )
        injury_impact = (
            features.get("injury_impact")
            if "injury_impact" in features
            else pd.Series([0], index=features.index)
        )
        schedule_impact = (
            features.get("schedule_impact")
            if "schedule_impact" in features
            else pd.Series([0], index=features.index)
        )

        features["raptor_prior_total"] = (
            age_prior * 0.5
            + draft_prior * 0.3
            + contract_prior * 0.2
            + all_nba_prior * 0.5
            + injury_recov
            - 1.0
            + rest_prior * 0.1
        )

        features["raptor_positive_priors"] = (
            (age_prior - 1.0).clip(0) * 5
            + draft_prior.clip(0) * 0.5
            + contract_prior.clip(0) * 0.5
            + all_nba_prior.clip(0) * 0.3
        )

        features["raptor_negative_priors"] = (
            (1.0 - age_prior).clip(0) * 5
            + injury_impact.clip(None, 0) * -1
            + schedule_impact.clip(None, 0) * -0.5
        )

        return features
