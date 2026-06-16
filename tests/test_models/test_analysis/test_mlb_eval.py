"""Tests for MLB evaluation module (migrated from sports-bet).

Tests cover:
- get_mlb_stat_key() normalization
- is_mlb_poisson_stat() for different stat types
- MLBDataProvider with mock gamelog data
- MLBStatisticalModel.compute_probability()
- Pitcher vs batter detection
- Fallback behavior (returns 0.52 when no data)
"""

import math
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from sportsquant.models.analysis.rules.mlb import (
    MLB_HITTER_STATS,
    MLB_PITCHER_STATS,
    MLB_COMBO_STATS,
    MLB_TIER_PAYOUT_MODIFIERS,
    FANDUEL_MLB_WEIGHTS,
    get_mlb_stat_key,
    is_mlb_poisson_stat,
    calculate_mlb_fanduel_points,
    detect_player_type,
    is_pitcher_stat,
    is_batter_stat,
)
from sportsquant.models.analysis.mlb_eval import (
    compute_mlb_stat_from_gamelog_row,
    MLBDataProvider,
    MLBStatisticalModel,
    MLBEvaluator,
    MLBPrizePicksEvaluator,
    MLBUnderdogEvaluator,
    MLBFanDuelEvaluator,
)


class TestGetMlbStatKey:
    """Tests for get_mlb_stat_key() function."""

    @pytest.mark.parametrize(
        "input_name,expected",
        [
            ("hits", "hits"),
            ("runs", "runs"),
            ("rbi", "rbi"),
            ("hr", "hr"),
            ("home_runs", "hr"),
            ("home runs", "hr"),
            ("HR", "hr"),
            ("HRs", "hr"),
            ("singles", "singles"),
            ("doubles", "doubles"),
            ("triples", "triples"),
            ("total_bases", "total_bases"),
            ("stolen_bases", "stolen_bases"),
            ("sb", "stolen_bases"),
            ("walks", "walks"),
            ("strikeouts", "strikeouts"),
            ("k", "strikeouts"),
            ("so", "strikeouts"),
            ("pitcher_strikeouts", "pitcher_strikeouts"),
            ("pitcher_outs", "pitcher_outs"),
            ("outs", "pitcher_outs"),
            ("earned_runs", "earned_runs"),
            ("er", "earned_runs"),
            ("innings_pitched", "innings_pitched"),
            ("ip", "innings_pitched"),
            ("hits_runs_rbi", "hits_runs_rbi"),
            ("runs_rbi", "runs_rbi"),
            ("hr_rbi", "hr_rbi"),
            ("hits_runs", "hits_runs"),
            ("batting_average", "batting_average"),
            ("ba", "batting_average"),
            ("whip", "whip"),
            ("era", "era"),
            ("", ""),
            ("unknown_stat", "unknown_stat"),
        ],
    )
    def test_stat_key_normalization(self, input_name, expected):
        """Test that various stat name formats are normalized correctly."""
        result = get_mlb_stat_key(input_name)
        assert result == expected

    def test_stat_key_without_spaces_underscores(self):
        """Test normalization removes spaces and underscores."""
        assert get_mlb_stat_key("home runs") == "hr"
        assert get_mlb_stat_key("home_runs") == "hr"
        assert get_mlb_stat_key("pitcher_strikeouts") == "pitcher_strikeouts"
        assert get_mlb_stat_key("total bases") == "total_bases"


class TestIsMlbPoissonStat:
    """Tests for is_mlb_poisson_stat() function."""

    @pytest.mark.parametrize(
        "stat,expected",
        [
            # Counting stats (Poisson)
            ("hits", True),
            ("runs", True),
            ("rbi", True),
            ("hr", True),
            ("singles", True),
            ("doubles", True),
            ("triples", True),
            ("total_bases", True),
            ("stolen_bases", True),
            ("walks", True),
            ("strikeouts", True),
            ("pitcher_strikeouts", True),
            ("pitcher_outs", True),
            ("earned_runs", True),
            ("walks_allowed", True),
            ("hits_allowed", True),
            ("hr_allowed", True),
            # Rate stats (NOT Poisson)
            ("batting_average", False),
            ("obp", False),
            ("slg", False),
            ("ops", False),
            ("whip", False),
            ("era", False),
            # Unknown
            ("unknown", False),
        ],
    )
    def test_poisson_stat_classification(self, stat, expected):
        """Test that counting stats are identified as Poisson."""
        assert is_mlb_poisson_stat(stat) == expected


class TestComputeMlbStatFromGamelogRow:
    """Tests for compute_mlb_stat_from_gamelog_row() function."""

    def test_hits(self):
        """Test computing hits from gamelog row."""
        row = pd.Series({"H": 2.0, "R": 1.0, "RBI": 0.0})
        assert compute_mlb_stat_from_gamelog_row("hits", row) == 2.0

    def test_runs(self):
        """Test computing runs from gamelog row."""
        row = pd.Series({"H": 2.0, "R": 3.0, "RBI": 1.0})
        assert compute_mlb_stat_from_gamelog_row("runs", row) == 3.0

    def test_rbi(self):
        """Test computing RBI from gamelog row."""
        row = pd.Series({"H": 2.0, "R": 1.0, "RBI": 4.0})
        assert compute_mlb_stat_from_gamelog_row("rbi", row) == 4.0

    def test_hr(self):
        """Test computing HR from gamelog row."""
        row = pd.Series({"HR": 2.0, "2B": 1.0, "3B": 0.0, "1B": 1.0})
        assert compute_mlb_stat_from_gamelog_row("hr", row) == 2.0

    def test_singles_calculated(self):
        """Test singles is calculated as Hits - Doubles - Triples - HR."""
        # Row: 3 hits total, 1 double, 0 triples, 1 HR = 1 single
        row = pd.Series({"H": 3.0, "2B": 1.0, "3B": 0.0, "HR": 1.0})
        result = compute_mlb_stat_from_gamelog_row("singles", row)
        assert result == 1.0

    def test_total_bases_direct(self):
        """Test total_bases from row when directly available."""
        row = pd.Series({"TB": 8.0})
        assert compute_mlb_stat_from_gamelog_row("total_bases", row) == 8.0

    def test_total_bases_calculated(self):
        """Test total_bases calculated when not directly available."""
        # singles=1, doubles=2, triples=1, hr=1 => 1*1 + 2*2 + 1*3 + 1*4 = 12
        row = pd.Series({"H": 4.0, "2B": 2.0, "3B": 1.0, "HR": 1.0, "1B": 0.0})
        # singles = 4 - 2 - 1 - 1 = 0
        # total_bases = 0*1 + 2*2 + 1*3 + 1*4 = 11
        result = compute_mlb_stat_from_gamelog_row("total_bases", row)
        assert result == 11.0

    def test_pitcher_strikeouts(self):
        """Test pitcher strikeouts from gamelog row."""
        row = pd.Series({"K": 7.0, "SO": 7.0})
        assert compute_mlb_stat_from_gamelog_row("pitcher_strikeouts", row) == 7.0

    def test_pitcher_outs_direct(self):
        """Test pitcher_outs from row when directly available."""
        row = pd.Series({"OUT": 18.0})
        assert compute_mlb_stat_from_gamelog_row("pitcher_outs", row) == 18.0

    def test_pitcher_outs_from_ip(self):
        """Test pitcher_outs calculated from IP."""
        row = pd.Series({"IP": 6.0})  # 6 innings = 18 outs
        result = compute_mlb_stat_from_gamelog_row("pitcher_outs", row)
        assert result == 18.0

    def test_earned_runs(self):
        """Test earned runs from gamelog row."""
        row = pd.Series({"ER": 3.0})
        assert compute_mlb_stat_from_gamelog_row("earned_runs", row) == 3.0

    def test_combined_hits_runs_rbi(self):
        """Test combined hits+runs+RBI stat."""
        row = pd.Series({"H": 2.0, "R": 3.0, "RBI": 1.0})
        result = compute_mlb_stat_from_gamelog_row("hits_runs_rbi", row)
        assert result == 6.0

    def test_combined_runs_rbi(self):
        """Test combined runs+RBI stat."""
        row = pd.Series({"R": 3.0, "RBI": 2.0})
        result = compute_mlb_stat_from_gamelog_row("runs_rbi", row)
        assert result == 5.0

    def test_combined_hr_rbi(self):
        """Test combined HR+RBI stat."""
        row = pd.Series({"HR": 2.0, "RBI": 3.0})
        result = compute_mlb_stat_from_gamelog_row("hr_rbi", row)
        assert result == 5.0

    def test_unknown_stat_returns_nan(self):
        """Test that unknown stat returns NaN."""
        row = pd.Series({"H": 2.0})
        result = compute_mlb_stat_from_gamelog_row("unknown_stat", row)
        assert math.isnan(result)

    def test_missing_data_returns_nan(self):
        """Test that missing data returns NaN."""
        row = pd.Series({})
        result = compute_mlb_stat_from_gamelog_row("hits", row)
        assert math.isnan(result)


class TestCalculateMlbFanDuelPoints:
    """Tests for calculate_mlb_fanduel_points() function."""

    def test_batter_stats(self):
        """Test FanDuel points calculation for batting stats."""
        stats = {
            "Singles": 2.0,
            "Doubles": 1.0,
            "Home Runs": 1.0,
            "Runs Scored": 2.0,
            "Runs Batted In": 3.0,
            "Walks": 1.0,
        }
        points = calculate_mlb_fanduel_points(stats)
        # 2*3 + 1*6 + 1*12 + 2*3.2 + 3*3.5 + 1*3 = 6+6+12+6.4+10.5+3 = 43.9
        assert abs(points - 43.9) < 0.01

    def test_pitcher_stats(self):
        """Test FanDuel points calculation for pitching stats."""
        stats = {
            "Strikeouts": 7.0,
            "Innings Pitched": 6.0,
            "Earned Runs Allowed": 2.0,
        }
        points = calculate_mlb_fanduel_points(stats)
        # 7*3 + 6*3 + 2*(-2) = 21 + 18 - 4 = 35
        assert points == 35.0

    def test_empty_stats(self):
        """Test with empty stats dict."""
        points = calculate_mlb_fanduel_points({})
        assert points == 0.0


class TestDetectPlayerType:
    """Tests for detect_player_type() function."""

    @pytest.mark.parametrize(
        "stat_type,expected",
        [
            ("hits", "batter"),
            ("runs", "batter"),
            ("rbi", "batter"),
            ("hr", "batter"),
            ("pitcher_strikeouts", "pitcher"),
            ("pitcher_outs", "pitcher"),
            ("earned_runs", "pitcher"),
            ("innings_pitched", "pitcher"),
        ],
    )
    def test_player_type_detection(self, stat_type, expected):
        """Test that player type is correctly detected from stat."""
        assert detect_player_type(stat_type) == expected


class TestMlbDataProvider:
    """Tests for MLBDataProvider class."""

    def test_initialization(self):
        """Test MLBDataProvider initializes correctly."""
        provider = MLBDataProvider()
        assert provider.n_lookback == 25
        assert provider._gamelog_cache == {}

    def test_parse_minutes_returns_one(self):
        """Test that parse_minutes returns 1.0 for MLB."""
        provider = MLBDataProvider()
        assert provider.parse_minutes("") == 1.0
        assert provider.parse_minutes(None) == 1.0
        assert provider.parse_minutes("anything") == 1.0

    def test_is_poisson_stat(self):
        """Test is_poisson_stat delegates correctly."""
        provider = MLBDataProvider()
        assert provider.is_poisson_stat("hr") is True
        assert provider.is_poisson_stat("batting_average") is False

    def test_compute_stat(self):
        """Test compute_stat calls compute_mlb_stat_from_gamelog_row."""
        provider = MLBDataProvider()
        row = pd.Series({"H": 2.0, "R": 1.0})
        assert provider.compute_stat("hits", row) == 2.0

    def test_get_player_id_with_mock(self):
        """Test get_player_id with mocked API call."""
        provider = MLBDataProvider()

        with patch("urllib.request.urlopen"):
            # Mock would need more setup; this tests the fallback path
            result = provider.get_player_id("NonExistent Player")
            assert result is None


class TestMlbStatisticalModel:
    """Tests for MLBStatisticalModel class."""

    def test_initialization(self):
        """Test MLBStatisticalModel initializes with correct defaults."""
        model = MLBStatisticalModel()
        assert model.min_games == 8
        assert model.base_blend == 0.30

    def test_initialization_with_custom_provider(self):
        """Test MLBStatisticalModel with custom data provider."""
        provider = MLBDataProvider(n_lookback=10)
        model = MLBStatisticalModel(data_provider=provider, base_blend=0.5)
        assert model.min_games == 8
        assert model.base_blend == 0.5
        assert model.provider.n_lookback == 10

    def test_compute_probability_fallback(self):
        """Test compute_probability returns 0.52 when no data."""
        model = MLBStatisticalModel()
        # Should return 0.52 as fallback when no player data
        result = model.compute_probability("Unknown Player", "hits", 2.0)
        assert result == 0.52


class TestMlbEvaluator:
    """Tests for MLBEvaluator class."""

    def test_initialization(self):
        """Test MLBEvaluator initializes correctly."""
        evaluator = MLBEvaluator()
        assert evaluator.model_weight == 0.30
        assert evaluator.min_confidence == 45.0
        assert evaluator.min_edge == 0.03
        assert evaluator.base_kelly == 0.25

    def test_is_pitcher_heuristic(self):
        """Test _is_pitcher heuristic detection."""
        evaluator = MLBEvaluator()
        # Names with "pitcher" should be detected
        assert evaluator._is_pitcher("Shohei Ohtani") is False  # Not a pitcher in name
        assert evaluator._is_pitcher("Pitcher Player") is True
        assert evaluator._is_pitcher("Justin Verlander") is False

    def test_detect_player_type_from_stat(self):
        """Test _detect_player_type_from_stat method."""
        evaluator = MLBEvaluator()
        assert evaluator._detect_player_type_from_stat("hr") == "batter"
        assert evaluator._detect_player_type_from_stat("pitcher_strikeouts") == "pitcher"
        assert evaluator._detect_player_type_from_stat("runs") == "batter"

    def test_evaluate_projection_basic(self):
        """Test evaluate_projection returns EvaluationResult."""
        evaluator = MLBEvaluator()

        # Create a mock projection
        mock_proj = MagicMock()
        mock_proj.player_name = "Shohei Ohtani"
        mock_proj.stat_display_name = "hits"
        mock_proj.line_score = 1.5
        mock_proj.tier = "Standard"

        result = evaluator.evaluate_projection(mock_proj)

        assert result.player_name == "Shohei Ohtani"
        assert result.stat_type == "hits"
        assert result.line == 1.5
        assert result.site == "prizepicks"  # default site
        assert 0.0 <= result.model_prob <= 1.0
        assert result.recommended_side in ("More", "Less")

    def test_evaluate_projection_with_over_term(self):
        """Test evaluate_projection with PrizePicks More/Less terms."""
        evaluator = MLBEvaluator()

        mock_proj = MagicMock()
        mock_proj.player_name = "Test Player"
        mock_proj.stat_display_name = "runs"
        mock_proj.line_score = 0.5
        mock_proj.tier = "Standard"

        result = evaluator.evaluate_projection(mock_proj, site="PrizePicks")

        assert result.site == "prizepicks"
        assert result.recommended_side in ("More", "Less")

    def test_evaluate_projection_with_underdog(self):
        """Test evaluate_projection with Underdog Higher/Lower terms."""
        evaluator = MLBEvaluator()

        mock_proj = MagicMock()
        mock_proj.player_name = "Test Player"
        mock_proj.stat_display_name = "HR"
        mock_proj.line_score = 0.5
        mock_proj.tier = "Standard"

        result = evaluator.evaluate_projection(mock_proj, site="Underdog")

        assert result.site == "underdog"
        assert result.recommended_side in ("Higher", "Lower")

    def test_rank_projections(self):
        """Test rank_projections sorts by EV."""
        evaluator = MLBEvaluator()

        mock_proj1 = MagicMock()
        mock_proj1.player_name = "Player 1"
        mock_proj1.stat_display_name = "hits"
        mock_proj1.line_score = 1.0
        mock_proj1.tier = "Standard"

        mock_proj2 = MagicMock()
        mock_proj2.player_name = "Player 2"
        mock_proj2.stat_display_name = "runs"
        mock_proj2.line_score = 0.5
        mock_proj2.tier = "Standard"

        results = evaluator.rank_projections([mock_proj1, mock_proj2])

        assert len(results) == 2
        # Results should be sorted by EV descending
        if len(results) == 2:
            assert results[0].ev >= results[1].ev

    def test_get_best_single_picks_filter(self):
        """Test get_best_single_picks filters by EV and confidence."""
        evaluator = MLBEvaluator()

        mock_proj = MagicMock()
        mock_proj.player_name = "Test Player"
        mock_proj.stat_display_name = "HR"
        mock_proj.line_score = 0.5
        mock_proj.tier = "Standard"

        # With default thresholds, most props won't pass
        results = evaluator.get_best_single_picks(
            [mock_proj],
            min_ev=0.10,  # High EV threshold
            min_confidence=80.0,  # High confidence threshold
        )

        # Results may be empty if model_prob is too low
        assert isinstance(results, list)


class TestMlbPerSiteEvaluators:
    """Tests for per-site MLB evaluator subclasses."""

    def test_prizepicks_evaluator(self):
        """Test MLBPrizePicksEvaluator."""
        evaluator = MLBPrizePicksEvaluator()
        assert evaluator.site == "PrizePicks"

        mock_proj = MagicMock()
        mock_proj.player_name = "Test"
        mock_proj.stat_display_name = "hits"
        mock_proj.line_score = 1.0
        mock_proj.tier = "Standard"

        result = evaluator.evaluate_projection(mock_proj)
        assert result.site == "prizepicks"

    def test_underdog_evaluator(self):
        """Test MLBUnderdogEvaluator."""
        evaluator = MLBUnderdogEvaluator()
        assert evaluator.site == "Underdog"

        mock_proj = MagicMock()
        mock_proj.player_name = "Test"
        mock_proj.stat_display_name = "runs"
        mock_proj.line_score = 0.5
        mock_proj.tier = "Standard"

        result = evaluator.evaluate_projection(mock_proj)
        assert result.site == "underdog"

    def test_fanduel_evaluator(self):
        """Test MLBFanDuelEvaluator."""
        evaluator = MLBFanDuelEvaluator()
        assert evaluator.site == "FanDuel"

        mock_proj = MagicMock()
        mock_proj.player_name = "Test"
        mock_proj.stat_display_name = "HR"
        mock_proj.line_score = 0.5
        mock_proj.tier = "Standard"

        result = evaluator.evaluate_projection(mock_proj)
        assert result.site == "fanduel"

    def test_underdog_with_sportsbook_odds(self):
        """Test MLBUnderdogEvaluator with sportsbook odds conversion."""
        evaluator = MLBUnderdogEvaluator()

        mock_proj = MagicMock()
        mock_proj.player_name = "Test"
        mock_proj.stat_display_name = "hits"
        mock_proj.line_score = 1.5
        mock_proj.tier = "Standard"

        sportsbook_odds = {"higher": -110, "lower": -120}

        result = evaluator.evaluate_projection(mock_proj, sportsbook_odds=sportsbook_odds)

        assert result.site == "underdog"


class TestMlbRulesExports:
    """Tests that MLB rules module exports correctly."""

    def test_mlb_hitter_stats_exists(self):
        """Test MLB_HITTER_STATS is exported."""
        assert MLB_HITTER_STATS is not None
        assert "hits" in MLB_HITTER_STATS

    def test_mlb_pitcher_stats_exists(self):
        """Test MLB_PITCHER_STATS is exported."""
        assert MLB_PITCHER_STATS is not None
        assert "pitcher_strikeouts" in MLB_PITCHER_STATS

    def test_mlb_combo_stats_exists(self):
        """Test MLB_COMBO_STATS is exported."""
        assert MLB_COMBO_STATS is not None
        assert "hits_runs_rbi" in MLB_COMBO_STATS

    def test_mlb_tier_payout_modifiers(self):
        """Test MLB_TIER_PAYOUT_MODIFIERS structure."""
        assert "Standard" in MLB_TIER_PAYOUT_MODIFIERS
        assert MLB_TIER_PAYOUT_MODIFIERS["Standard"] == 1.0

    def test_fanduel_mlb_weights(self):
        """Test FANDUEL_MLB_WEIGHTS structure."""
        assert "Singles" in FANDUEL_MLB_WEIGHTS
        assert FANDUEL_MLB_WEIGHTS["Singles"] == 3.0
        assert "Home Runs" in FANDUEL_MLB_WEIGHTS
        assert FANDUEL_MLB_WEIGHTS["Home Runs"] == 12.0

    def test_is_pitcher_stat_function(self):
        """Test is_pitcher_stat function."""
        assert is_pitcher_stat("pitcher_strikeouts") is True
        assert is_pitcher_stat("hits") is False

    def test_is_batter_stat_function(self):
        """Test is_batter_stat function."""
        assert is_batter_stat("hits") is True
        assert is_batter_stat("pitcher_strikeouts") is False
