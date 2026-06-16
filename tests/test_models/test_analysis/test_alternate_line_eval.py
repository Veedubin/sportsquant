"""Tests for alternate line evaluation (migrated from sports-bet)."""

import pytest

from sportsquant.models.analysis.alternate_line_eval import (
    AlternateLineEvaluator,
    AlternateLineResult,
    american_to_decimal,
    american_to_prob,
    clamp,
    quick_evaluate,
)


class TestClamp:
    """Tests for clamp helper function."""

    def test_within_bounds(self) -> None:
        assert clamp(5.0, 0.0, 10.0) == 5.0

    def test_below_lo(self) -> None:
        assert clamp(-5.0, 0.0, 10.0) == 0.0

    def test_above_hi(self) -> None:
        assert clamp(15.0, 0.0, 10.0) == 10.0


class TestAmericanToDecimal:
    """Tests for american_to_decimal function."""

    def test_negative_odds(self) -> None:
        assert round(american_to_decimal(-110), 4) == 1.9091

    def test_positive_odds(self) -> None:
        assert round(american_to_decimal(150), 4) == 2.5

    def test_plus_100(self) -> None:
        assert american_to_decimal(100) == 2.0


class TestAmericanToProb:
    """Tests for american_to_prob function."""

    def test_negative_odds(self) -> None:
        prob = american_to_prob(-110)
        assert round(prob, 4) == 0.5238

    def test_positive_odds(self) -> None:
        prob = american_to_prob(150)
        assert round(prob, 4) == 0.4


class TestExtractObservations:
    """Tests for _extract_observations method."""

    def test_dict_format(self, sample_player_logs_dict: list[dict]) -> None:
        eval = AlternateLineEvaluator(
            player_history=sample_player_logs_dict,
            stat_type="points",
            player_name="Test Player",
        )
        assert eval.sample_size == 10
        assert 28 in eval.observations
        assert 35 in eval.observations

    def test_int_format(self, sample_player_logs_int: list[int]) -> None:
        eval = AlternateLineEvaluator(
            player_history=sample_player_logs_int,
            stat_type="points",
            player_name="Test Player",
        )
        assert eval.sample_size == 10
        assert 28 in eval.observations
        assert 35 in eval.observations

    def test_mixed_format(self, sample_player_logs_mixed: list) -> None:
        eval = AlternateLineEvaluator(
            player_history=sample_player_logs_mixed,
            stat_type="points",
            player_name="Test Player",
        )
        assert eval.sample_size == 7

    def test_empty_history(self) -> None:
        eval = AlternateLineEvaluator(
            player_history=[],
            stat_type="points",
            player_name="Test Player",
        )
        assert eval.sample_size == 0
        assert not eval.has_data

    def test_underscore_format(self) -> None:
        logs = [
            {"player_points": 25},
            {"player_points": 30},
            {"player_points": 28},
        ]
        eval = AlternateLineEvaluator(
            player_history=logs,
            stat_type="player_points",
            player_name="Test Player",
        )
        assert eval.sample_size == 3


class TestCalculateProbability:
    """Tests for probability calculation."""

    def test_probability_calculation(self, sample_player_logs_dict: list[dict]) -> None:
        eval = AlternateLineEvaluator(
            player_history=sample_player_logs_dict,
            stat_type="points",
            player_name="Test Player",
        )
        prob = eval.get_probability_at_threshold(20.0)
        assert abs(prob - 1.0) < 0.01

        prob = eval.get_probability_at_threshold(30.0)
        assert abs(prob - 0.4) < 0.15

        prob = eval.get_probability_at_threshold(50.0)
        assert prob < 0.001


class TestCalculateEV:
    """Tests for EV calculation."""

    def test_ev_calculation(self, sample_player_logs_dict: list[dict]) -> None:
        eval = AlternateLineEvaluator(
            player_history=sample_player_logs_dict,
            stat_type="points",
            player_name="Test Player",
        )
        result = eval.evaluate(30.0, -110)
        assert result is not None
        assert result.ev_percent < 0

    def test_positive_ev(self) -> None:
        logs = [
            {"points": 36},
            {"points": 38},
            {"points": 35},
            {"points": 37},
            {"points": 36},
            {"points": 35},
            {"points": 38},
            {"points": 35},
            {"points": 20},
            {"points": 18},
        ]
        eval = AlternateLineEvaluator(
            player_history=logs,
            stat_type="points",
            player_name="High Scorer",
        )
        result = eval.evaluate(30.0, 150)
        assert result is not None
        assert result.model_probability > 0
        assert result.breakeven_probability == 0.4


class TestEdgeCases:
    """Tests for edge cases."""

    def test_zero_occurrences(self) -> None:
        logs = [
            {"points": 10},
            {"points": 12},
            {"points": 11},
            {"points": 13},
            {"points": 14},
            {"points": 15},
        ]
        eval = AlternateLineEvaluator(
            player_history=logs,
            stat_type="points",
            player_name="Test Player",
        )
        result = eval.evaluate(50.0, -110)
        assert result is not None
        assert result.model_probability == 0.0
        assert result.historical_hit_rate == 0.0

    def test_all_occurrences(self) -> None:
        logs = [
            {"points": 20},
            {"points": 22},
            {"points": 21},
            {"points": 23},
            {"points": 24},
            {"points": 25},
        ]
        eval = AlternateLineEvaluator(
            player_history=logs,
            stat_type="points",
            player_name="Test Player",
        )
        result = eval.evaluate(10.0, -110)
        assert result is not None
        assert result.model_probability == 1.0
        assert result.historical_hit_rate == 1.0

    def test_negative_threshold(self) -> None:
        logs = [
            {"points": 20},
            {"points": 22},
            {"points": 21},
            {"points": 23},
            {"points": 24},
            {"points": 25},
        ]
        eval = AlternateLineEvaluator(
            player_history=logs,
            stat_type="points",
            player_name="Test Player",
        )
        result = eval.evaluate(-5.0, -110)
        assert result is not None
        assert result.distribution_type == "edge_case"
        assert result.model_probability == 1.0
        assert result.recommended


class TestEvaluate:
    """Tests for evaluate method."""

    def test_insufficient_data(self) -> None:
        logs = [
            {"points": 20},
            {"points": 22},
        ]
        eval = AlternateLineEvaluator(
            player_history=logs,
            stat_type="points",
            player_name="Test Player",
        )
        assert not eval.has_data
        result = eval.evaluate(25.0, -110)
        assert result is None

    def test_recommendation_logic(self) -> None:
        logs = [
            {"points": 30},
            {"points": 35},
        ]
        eval = AlternateLineEvaluator(
            player_history=logs,
            stat_type="points",
            player_name="Test Player",
        )
        result = eval.evaluate(30.0, 200)
        if result and result.ev_percent > 0:
            assert result.recommended is False


class TestEvaluateMultipleThresholds:
    """Tests for evaluate_multiple_thresholds."""

    def test_multiple_thresholds(self, sample_player_logs_dict: list[dict]) -> None:
        eval = AlternateLineEvaluator(
            player_history=sample_player_logs_dict,
            stat_type="points",
            player_name="Test Player",
        )
        odds_map = {
            20.0: -110,
            25.0: -105,
            30.0: +120,
        }
        results = eval.evaluate_multiple_thresholds([20.0, 25.0, 30.0], odds_map)
        assert len(results) == 3
        assert results[0].ev_percent >= results[1].ev_percent
        assert results[1].ev_percent >= results[2].ev_percent


class TestQuickEvaluate:
    """Tests for quick_evaluate convenience function."""

    def test_quick_evaluate(self) -> None:
        observations = [28, 35, 22, 31, 29, 33, 27, 30, 25, 32]
        result = quick_evaluate(
            observations=observations,
            threshold=30.0,
            odds=-110,
            stat_type="points",
            player_name="Test Player",
        )
        assert result is not None
        assert result.player_name == "Test Player"
        assert result.threshold == 30.0


class TestDistributionSummary:
    """Tests for get_distribution_summary."""

    def test_summary(self, sample_player_logs_dict: list[dict]) -> None:
        eval = AlternateLineEvaluator(
            player_history=sample_player_logs_dict,
            stat_type="points",
            player_name="Test Player",
        )
        summary = eval.get_distribution_summary()
        assert "distribution_type" in summary
        assert "sample_size" in summary
        assert "mean" in summary
        assert summary["sample_size"] == 10
