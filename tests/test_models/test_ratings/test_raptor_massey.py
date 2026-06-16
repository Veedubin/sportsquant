"""Tests for RAPTOR box features and Massey ratings (migrated from Sports-Platform)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from sportsquant.models.ratings.raptor_box import (
    RaptorBoxConfig,
    RaptorBoxFeatures,
    _safe_divide,
    _rolling_mean_lagged,
)
from sportsquant.models.ratings.raptor_composite import RaptorCompositeFeatures
from sportsquant.models.ratings.massey_ratings import MasseyRatings


class TestSafeDivide:
    """Tests for _safe_divide helper function."""

    def test_normal_division(self):
        numerator = pd.Series([10, 20, 30])
        denominator = pd.Series([2, 4, 5])
        result = _safe_divide(numerator, denominator)
        expected = pd.Series([5.0, 5.0, 6.0])
        np.testing.assert_allclose(np.asarray(result), np.asarray(expected))

    def test_divide_by_zero(self):
        numerator = pd.Series([10, 20, 30])
        denominator = pd.Series([2, 0, 5])
        result = _safe_divide(numerator, denominator, fill_value=0.0)
        expected = pd.Series([5.0, 0.0, 6.0])
        np.testing.assert_allclose(np.asarray(result), np.asarray(expected))

    def test_all_zeros(self):
        numerator = pd.Series([0, 0, 0])
        denominator = pd.Series([0, 0, 0])
        result = _safe_divide(numerator, denominator, fill_value=1.0)
        assert all(v == pytest.approx(1.0) for v in result.values)


class TestRollingMeanLagged:
    """Tests for _rolling_mean_lagged helper function."""

    def test_basic_rolling_mean(self):
        series = pd.Series([1, 2, 3, 4, 5])
        result = _rolling_mean_lagged(series, 3)
        assert pd.isna(result.iloc[0])
        np.testing.assert_allclose(float(result.iloc[1]), 1.0)
        np.testing.assert_allclose(float(result.iloc[2]), 1.5)
        np.testing.assert_allclose(float(result.iloc[3]), 2.0)
        np.testing.assert_allclose(float(result.iloc[4]), 3.0)

    def test_short_series(self):
        series = pd.Series([10, 20])
        result = _rolling_mean_lagged(series, 5)
        assert pd.isna(result.iloc[0]) or result.iloc[0] == pytest.approx(10.0)


class TestRaptorBoxFeatures:
    """Tests for RaptorBoxFeatures class."""

    def test_scoring_features(self):
        config = RaptorBoxConfig()
        features = RaptorBoxFeatures(config)

        df = pd.DataFrame(
            {
                "fga": [20, 15, 25],
                "fta": [10, 8, 12],
                "pts": [30, 25, 35],
                "fgm": [8, 6, 10],
                "fg3m": [4, 3, 5],
                "ftm": [6, 5, 8],
                "fg3a": [10, 8, 12],
                "fg2m": [4, 3, 5],
                "fg2a": [10, 7, 13],
                "min": [30, 28, 32],
            }
        )

        result = features.compute_scoring_features(df)

        assert "ts_pct" in result.columns
        assert "efg_pct" in result.columns
        assert "pts_per_36" in result.columns
        assert 0.6 < float(result["ts_pct"].iloc[0]) < 0.7

    def test_playmaking_features(self):
        config = RaptorBoxConfig()
        features = RaptorBoxFeatures(config)

        df = pd.DataFrame(
            {
                "ast": [8, 5, 10],
                "min": [30, 28, 32],
                "fga": [20, 15, 25],
                "fta": [10, 8, 12],
                "to": [3, 2, 4],
            }
        )

        result = features.compute_playmaking_features(df)

        assert "ast_per_36" in result.columns
        assert "ast_to_usage" in result.columns
        expected_ast = 8 / 30 * 36
        np.testing.assert_allclose(float(result["ast_per_36"].iloc[0]), expected_ast)

    def test_rebounding_features(self):
        config = RaptorBoxConfig()
        features = RaptorBoxFeatures(config)

        df = pd.DataFrame(
            {
                "reb": [10, 8, 12],
                "orb": [3, 2, 4],
                "drb": [7, 6, 8],
                "min": [30, 28, 32],
                "opp_drb": [40, 38, 42],
                "team_reb": [35, 33, 37],
            }
        )

        result = features.compute_rebounding_features(df)

        assert "reb_per_36" in result.columns
        assert "orb_pct" in result.columns

    def test_defensive_features(self):
        config = RaptorBoxConfig()
        features = RaptorBoxFeatures(config)

        df = pd.DataFrame(
            {
                "blk": [2, 1, 3],
                "stl": [3, 2, 4],
                "min": [30, 28, 32],
                "deflections": [5, 4, 6],
                "contested_2pt": [8, 6, 10],
                "contested_3pt": [4, 3, 5],
                "opp_fg_pct": [0.45, 0.42, 0.48],
                "opp_fg3_pct": [0.35, 0.33, 0.37],
            }
        )

        result = features.compute_defensive_features(df)

        assert "blk_per_36" in result.columns
        assert "stl_per_36" in result.columns
        assert "def_activity" in result.columns

    def test_compute_all_box_features(self):
        config = RaptorBoxConfig()
        features = RaptorBoxFeatures(config)

        df = pd.DataFrame(
            {
                "fga": [20, 15, 25],
                "fta": [10, 8, 12],
                "pts": [30, 25, 35],
                "fgm": [8, 6, 10],
                "fg3m": [4, 3, 5],
                "ftm": [6, 5, 8],
                "fg3a": [10, 8, 12],
                "fg2m": [4, 3, 5],
                "fg2a": [10, 7, 13],
                "min": [30, 28, 32],
                "ast": [8, 5, 10],
                "to": [3, 2, 4],
                "reb": [10, 8, 12],
                "orb": [3, 2, 4],
                "drb": [7, 6, 8],
                "opp_drb": [40, 38, 42],
                "team_reb": [35, 33, 37],
                "blk": [2, 1, 3],
                "stl": [3, 2, 4],
                "deflections": [5, 4, 6],
                "contested_2pt": [8, 6, 10],
                "contested_3pt": [4, 3, 5],
                "opp_fg_pct": [0.45, 0.42, 0.48],
                "opp_fg3_pct": [0.35, 0.33, 0.37],
            }
        )

        result = features.compute_all_box_features(df)

        assert "raptor_box_offense" in result.columns
        assert "raptor_box_defense" in result.columns
        assert "raptor_box_total" in result.columns


class TestRaptorCompositeFeatures:
    """Tests for RaptorCompositeFeatures class."""

    def test_compute_raptor_total(self):
        composite = RaptorCompositeFeatures()

        df = pd.DataFrame(
            {
                "fga": [20, 15, 25],
                "fta": [10, 8, 12],
                "pts": [30, 25, 35],
                "fgm": [8, 6, 10],
                "fg3m": [4, 3, 5],
                "ftm": [6, 5, 8],
                "fg3a": [10, 8, 12],
                "fg2m": [4, 3, 5],
                "fg2a": [10, 7, 13],
                "min": [30, 28, 32],
                "ast": [8, 5, 10],
                "to": [3, 2, 4],
                "reb": [10, 8, 12],
                "orb": [3, 2, 4],
                "drb": [7, 6, 8],
                "opp_drb": [40, 38, 42],
                "team_reb": [35, 33, 37],
                "blk": [2, 1, 3],
                "stl": [3, 2, 4],
                "deflections": [5, 4, 6],
                "contested_2pt": [8, 6, 10],
                "contested_3pt": [4, 3, 5],
                "opp_fg_pct": [0.45, 0.42, 0.48],
                "opp_fg3_pct": [0.35, 0.33, 0.37],
                "height": [200, 195, 205],
                "weight": [95, 90, 100],
                "age": [26, 24, 28],
                "draft_year": [2018, 2019, 2020],
                "draft_round": [1, 2, 1],
                "draft_pick": [15, 30, 10],
                "years_experience": [4, 3, 5],
            }
        )

        result = composite.compute_raptor_total(df)

        assert len(result) == 3
        assert all(isinstance(x, (float, np.floating)) for x in result)

    def test_compute_raptor_percentile(self):
        composite = RaptorCompositeFeatures()

        df = pd.DataFrame(
            {
                "fga": [20, 15, 25],
                "fta": [10, 8, 12],
                "pts": [30, 25, 35],
                "fgm": [8, 6, 10],
                "fg3m": [4, 3, 5],
                "ftm": [6, 5, 8],
                "fg3a": [10, 8, 12],
                "fg2m": [4, 3, 5],
                "fg2a": [10, 7, 13],
                "min": [30, 28, 32],
                "ast": [8, 5, 10],
                "to": [3, 2, 4],
                "reb": [10, 8, 12],
                "orb": [3, 2, 4],
                "drb": [7, 6, 8],
                "opp_drb": [40, 38, 42],
                "team_reb": [35, 33, 37],
                "blk": [2, 1, 3],
                "stl": [3, 2, 4],
                "deflections": [5, 4, 6],
                "contested_2pt": [8, 6, 10],
                "contested_3pt": [4, 3, 5],
                "opp_fg_pct": [0.45, 0.42, 0.48],
                "opp_fg3_pct": [0.35, 0.33, 0.37],
                "height": [200, 195, 205],
                "weight": [95, 90, 100],
                "age": [26, 24, 28],
                "draft_year": [2018, 2019, 2020],
                "draft_round": [1, 2, 1],
                "draft_pick": [15, 30, 10],
                "years_experience": [4, 3, 5],
            }
        )

        result = composite.compute_raptor_percentile(df)

        assert "raptor_total" in result.columns
        assert "raptor_total_percentile" in result.columns
        assert all(0 <= p <= 100 for p in result["raptor_total_percentile"])

    def test_normalize_raptor_for_market(self):
        composite = RaptorCompositeFeatures()

        df = pd.DataFrame(
            {
                "fga": [20, 15, 25],
                "fta": [10, 8, 12],
                "pts": [30, 25, 35],
                "fgm": [8, 6, 10],
                "fg3m": [4, 3, 5],
                "ftm": [6, 5, 8],
                "fg3a": [10, 8, 12],
                "fg2m": [4, 3, 5],
                "fg2a": [10, 7, 13],
                "min": [30, 28, 32],
                "ast": [8, 5, 10],
                "to": [3, 2, 4],
                "reb": [10, 8, 12],
                "orb": [3, 2, 4],
                "drb": [7, 6, 8],
                "opp_drb": [40, 38, 42],
                "team_reb": [35, 33, 37],
                "blk": [2, 1, 3],
                "stl": [3, 2, 4],
                "deflections": [5, 4, 6],
                "contested_2pt": [8, 6, 10],
                "contested_3pt": [4, 3, 5],
                "opp_fg_pct": [0.45, 0.42, 0.48],
                "opp_fg3_pct": [0.35, 0.33, 0.37],
                "height": [200, 195, 205],
                "weight": [95, 90, 100],
                "age": [26, 24, 28],
                "draft_year": [2018, 2019, 2020],
                "draft_round": [1, 2, 1],
                "draft_pick": [15, 30, 10],
                "years_experience": [4, 3, 5],
            }
        )

        for market in ["pts", "reb", "ast", "pra"]:
            result = composite.normalize_raptor_for_market(df, market)
            assert "market_raptor" in result.columns


class TestMasseyRatings:
    """Tests for MasseyRatings class."""

    def test_compute_ratings_basic(self):
        ratings = MasseyRatings(home_advantage=3.0)

        games = pd.DataFrame(
            {
                "HOME_TEAM": ["LAL", "BOS", "LAL", "BOS", "CHI"],
                "AWAY_TEAM": ["BOS", "LAL", "CHI", "CHI", "LAL"],
                "HOME_SCORE": [110, 105, 100, 95, 108],
                "AWAY_SCORE": [105, 108, 98, 92, 102],
            }
        )

        result = ratings.compute_ratings(games)

        assert not result.empty
        assert "overall_rating" in result.columns

    def test_compute_ratings_empty_games(self):
        ratings = MasseyRatings(home_advantage=3.0)

        games = pd.DataFrame(
            {
                "HOME_TEAM": pd.Series(dtype="str"),
                "AWAY_TEAM": pd.Series(dtype="str"),
                "HOME_SCORE": pd.Series(dtype="int"),
                "AWAY_TEAM_score": pd.Series(dtype="int"),
            }
        )

        with pytest.raises(ValueError, match="Games DataFrame cannot be empty"):
            ratings.compute_ratings(games)

    def test_compute_ratings_missing_columns(self):
        ratings = MasseyRatings(home_advantage=3.0)

        games = pd.DataFrame(
            {
                "HOME_TEAM": ["LAL", "BOS"],
                "AWAY_TEAM": ["BOS", "LAL"],
            }
        )

        with pytest.raises(ValueError, match="Missing required columns"):
            ratings.compute_ratings(games)

    def test_decompose_rating(self):
        ratings = MasseyRatings(home_advantage=3.0)

        off, deff = ratings.decompose_rating(2.0)
        assert off > deff

        off, deff = ratings.decompose_rating(-2.0)
        assert isinstance(off, float)
        assert isinstance(deff, float)

    def test_home_away_split(self):
        ratings = MasseyRatings(home_advantage=3.0)

        home_adj = ratings.home_away_split(5.0, is_home=True)
        away_adj = ratings.home_away_split(5.0, is_home=False)

        assert home_adj > away_adj
        expected_home_adj = 5.0 + 1.5
        assert home_adj == pytest.approx(expected_home_adj)

    def test_schedule_strength(self):
        ratings = MasseyRatings(home_advantage=3.0)

        games = pd.DataFrame(
            {
                "HOME_TEAM": ["LAL", "BOS", "LAL"],
                "AWAY_TEAM": ["BOS", "LAL", "BOS"],
                "HOME_SCORE": [110, 105, 100],
                "AWAY_SCORE": [105, 108, 98],
            }
        )

        ratings_df = ratings.compute_ratings(games)
        strength = ratings.schedule_strength(games, "LAL", ratings_df)

        assert isinstance(strength, float)

    def test_rest_day_adjustment(self):
        ratings = MasseyRatings(home_advantage=3.0)

        adj0 = ratings.rest_day_adjustment(0, 5.0)
        assert adj0 == pytest.approx(5.0)

        adj2 = ratings.rest_day_adjustment(2, 5.0)
        expected_adj2 = 5.0 + 2 * 0.15
        assert adj2 == pytest.approx(expected_adj2)

        adj5 = ratings.rest_day_adjustment(5, 5.0)
        expected_adj5 = 5.0 + 4 * 0.15
        assert adj5 == pytest.approx(expected_adj5)

    def test_back_to_back_adjustment(self):
        ratings = MasseyRatings(home_advantage=3.0)

        adj_normal = ratings.back_to_back_adjustment(False, False, 5.0)
        assert adj_normal == pytest.approx(5.0)

        adj_first = ratings.back_to_back_adjustment(True, False, 5.0)
        expected_adj_first = 5.0 - 0.5 * 0.3
        assert adj_first == pytest.approx(expected_adj_first)

        adj_second = ratings.back_to_back_adjustment(True, True, 5.0)
        assert adj_second == pytest.approx(5.0 - 0.5)

    def test_conference_adjustment(self):
        ratings = MasseyRatings(home_advantage=3.0)

        ratings_df = pd.DataFrame(
            {"overall_rating": [1.0, -1.0, 2.0, -2.0]},
            index=pd.Index(["LAL", "BOS", "CHI", "NYK"]),
        )

        conference_teams = {
            "LAL": "West",
            "BOS": "East",
            "CHI": "East",
            "NYK": "East",
        }

        adjusted = ratings.conference_adjustment(ratings_df, conference_teams)
        assert "overall_rating" in adjusted.columns
