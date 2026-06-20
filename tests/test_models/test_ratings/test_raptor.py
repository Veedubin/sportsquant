"""Tests for RAPTOR composite calculation (new)."""

import pytest
import pandas as pd
import numpy as np

from quantitative_sports.models.ratings.raptor_composite import RaptorCompositeFeatures


class TestRaptorCompositeCalculation:
    """Tests for RAPTOR composite calculation."""

    def setup_method(self):
        self.composite = RaptorCompositeFeatures()

    def _make_test_df(self, n=3):
        """Create a minimal test DataFrame."""
        return pd.DataFrame(
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

    def test_compute_raptor_total_returns_float(self):
        """Test RAPTOR total returns float values."""
        df = self._make_test_df()
        result = self.composite.compute_raptor_total(df)
        assert len(result) == 3
        assert all(isinstance(x, (float, np.floating)) for x in result)

    def test_compute_raptor_total_ordering(self):
        """Test RAPTOR total ordering matches expected skill ordering."""
        # Player 3 has best stats (pts=35, ast=10, reb=12)
        # Player 1 is middle (pts=30, ast=8, reb=10)
        # Player 2 is worst (pts=25, ast=5, reb=8)
        df = self._make_test_df()
        result = self.composite.compute_raptor_total(df)
        # Player 3 (index 2) should have highest RAPTOR
        assert result[2] >= result[0]
        assert result[2] >= result[1]

    def test_compute_raptor_percentile_bounds(self):
        """Test RAPTOR percentiles are between 0 and 100."""
        df = self._make_test_df()
        result = self.composite.compute_raptor_percentile(df)
        assert all(0 <= p <= 100 for p in result["raptor_total_percentile"])

    def test_compute_raptor_percentile_columns(self):
        """Test RAPTOR percentile has expected columns."""
        df = self._make_test_df()
        result = self.composite.compute_raptor_percentile(df)
        assert "raptor_total" in result.columns
        assert "raptor_total_percentile" in result.columns

    def test_normalize_raptor_for_market_pts(self):
        """Test RAPTOR normalization for points market."""
        df = self._make_test_df()
        result = self.composite.normalize_raptor_for_market(df, "pts")
        assert "market_raptor" in result.columns
        assert len(result) == 3

    def test_normalize_raptor_for_market_reb(self):
        """Test RAPTOR normalization for rebounds market."""
        df = self._make_test_df()
        result = self.composite.normalize_raptor_for_market(df, "reb")
        assert "market_raptor" in result.columns

    def test_normalize_raptor_for_market_ast(self):
        """Test RAPTOR normalization for assists market."""
        df = self._make_test_df()
        result = self.composite.normalize_raptor_for_market(df, "ast")
        assert "market_raptor" in result.columns

    def test_normalize_raptor_for_market_pra(self):
        """Test RAPTOR normalization for PRA market."""
        df = self._make_test_df()
        result = self.composite.normalize_raptor_for_market(df, "pra")
        assert "market_raptor" in result.columns

    def test_single_player(self):
        """Test RAPTOR with single player."""
        df = pd.DataFrame(
            {
                "fga": [20],
                "fta": [10],
                "pts": [30],
                "fgm": [8],
                "fg3m": [4],
                "ftm": [6],
                "fg3a": [10],
                "fg2m": [4],
                "fg2a": [10],
                "min": [30],
                "ast": [8],
                "to": [3],
                "reb": [10],
                "orb": [3],
                "drb": [7],
                "opp_drb": [40],
                "team_reb": [35],
                "blk": [2],
                "stl": [3],
                "deflections": [5],
                "contested_2pt": [8],
                "contested_3pt": [4],
                "opp_fg_pct": [0.45],
                "opp_fg3_pct": [0.35],
                "height": [200],
                "weight": [95],
                "age": [26],
                "draft_year": [2018],
                "draft_round": [1],
                "draft_pick": [15],
                "years_experience": [4],
            }
        )
        result = self.composite.compute_raptor_total(df)
        assert len(result) == 1
        assert isinstance(result[0], (float, np.floating))

    def test_empty_dataframe(self):
        """Test RAPTOR with empty DataFrame."""
        df = pd.DataFrame()
        with pytest.raises((ValueError, KeyError)):
            self.composite.compute_raptor_total(df)
