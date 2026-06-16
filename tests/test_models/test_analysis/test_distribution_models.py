"""Tests for distribution models (migrated from sports-bet)."""

import numpy as np
import pytest
from scipy.stats import kstest

from sportsquant.models.analysis.distribution_models import (
    DistributionSelector,
    EmpiricalCDF,
    GammaDistribution,
    LogNormalDistribution,
    NegativeBinomialDistribution,
    clamp,
)


class TestClamp:
    """Tests for clamp helper function."""

    def test_within_bounds(self) -> None:
        assert clamp(5.0, 0.0, 10.0) == 5.0

    def test_below_lo(self) -> None:
        assert clamp(-5.0, 0.0, 10.0) == 0.0

    def test_above_hi(self) -> None:
        assert clamp(15.0, 0.0, 10.0) == 10.0


class TestEmpiricalCDF:
    """Tests for EmpiricalCDF distribution."""

    def test_basic_probability(self) -> None:
        obs = [10.0, 20.0, 30.0, 40.0, 50.0]
        dist = EmpiricalCDF(obs)

        assert dist.probability(15.0) == 0.8
        assert dist.probability(25.0) == 0.6
        assert dist.probability(50.0) == 0.2
        assert dist.probability(55.0) == 0.0
        assert dist.probability(0.0) == 1.0
        assert dist.probability(-10.0) == 1.0

    def test_empty_observations_raises(self) -> None:
        with pytest.raises(ValueError):
            EmpiricalCDF([])

    def test_fit_quality(self) -> None:
        obs_30 = list(range(30))
        dist_30 = EmpiricalCDF(obs_30)
        assert dist_30.fit_quality() == 0.95

        obs_20 = list(range(20))
        dist_20 = EmpiricalCDF(obs_20)
        assert dist_20.fit_quality() == 0.85

        obs_15 = list(range(15))
        dist_15 = EmpiricalCDF(obs_15)
        assert dist_15.fit_quality() == 0.75

        obs_10 = list(range(10))
        dist_10 = EmpiricalCDF(obs_10)
        assert dist_10.fit_quality() == 0.5

    def test_sample(self) -> None:
        obs = [10.0, 20.0, 30.0, 40.0, 50.0]
        dist = EmpiricalCDF(obs)
        samples = dist.sample(100)
        assert len(samples) == 100
        assert all(s in obs for s in samples)


class TestGammaFit:
    """Tests for GammaDistribution."""

    def test_gamma_fit(self) -> None:
        obs = [8.0, 6.0, 7.0, 9.0, 5.0, 8.0, 6.0, 7.0, 10.0, 5.0]
        dist = GammaDistribution(obs)
        prob = dist.probability(6.0)
        assert 0.0 <= prob <= 1.0
        assert dist.probability(0.0) == 1.0

    def test_gamma_empty_raises(self) -> None:
        with pytest.raises(ValueError):
            GammaDistribution([])

    def test_gamma_edge_case_zero_variance(self) -> None:
        obs = [5.0, 5.0, 5.0, 5.0, 5.0]
        dist = GammaDistribution(obs)
        assert dist.probability(5.0) == 1.0
        assert dist.probability(10.0) == 0.0


class TestLogNormalFit:
    """Tests for LogNormalDistribution."""

    def test_log_normal_fit(self) -> None:
        obs = [25.0, 28.0, 32.0, 22.0, 35.0, 18.0, 30.0, 27.0, 29.0, 33.0]
        dist = LogNormalDistribution(obs)
        prob = dist.probability(20.0)
        assert 0.5 <= prob <= 1.0
        assert dist.probability(0.0) == 1.0

    def test_log_normal_empty_raises(self) -> None:
        with pytest.raises(ValueError):
            LogNormalDistribution([])

    def test_log_normal_sample(self) -> None:
        obs = [25.0, 28.0, 32.0, 22.0, 35.0]
        dist = LogNormalDistribution(obs)
        samples = dist.sample(50)
        assert len(samples) == 50
        assert all(s >= 0 for s in samples)


class TestNegativeBinomial:
    """Tests for NegativeBinomialDistribution."""

    def test_negative_binomial(self) -> None:
        obs = [8.0, 6.0, 7.0, 9.0, 5.0, 8.0, 6.0, 7.0, 10.0, 5.0]
        dist = NegativeBinomialDistribution(obs)
        prob = dist.probability(6.0)
        assert 0.0 <= prob <= 1.0
        assert dist.probability(0.0) == 1.0

    def test_negative_binomial_empty_raises(self) -> None:
        with pytest.raises(ValueError):
            NegativeBinomialDistribution([])


class TestDistributionSelector:
    """Tests for DistributionSelector auto-selection logic."""

    def test_selector_empirical_large_sample(self) -> None:
        obs = list(range(20))
        selector = DistributionSelector(obs, stat_type="points")
        assert selector.get_selected_type() == "empirical"

    def test_selector_gamma_for_count_stats(self) -> None:
        obs = [8.0, 6.0, 7.0, 9.0, 5.0, 8.0, 6.0, 7.0, 10.0, 5.0]
        selector = DistributionSelector(obs, stat_type="rebounds")
        assert selector.get_selected_type() == "gamma"

    def test_selector_lognormal_for_points(self) -> None:
        obs = [25.0, 28.0, 32.0, 22.0, 35.0]
        selector = DistributionSelector(obs, stat_type="points")
        assert selector.get_selected_type() == "lognormal"

    def test_selector_empty_raises(self) -> None:
        with pytest.raises(ValueError):
            DistributionSelector([], stat_type="points")

    def test_coefficient_of_variation(self) -> None:
        obs = [10.0, 20.0, 30.0, 40.0, 50.0]
        selector = DistributionSelector(obs, stat_type="points")
        cv = selector.coefficient_of_variation()
        assert cv > 0

    def test_historical_hit_rate(self) -> None:
        obs = [10.0, 20.0, 30.0, 40.0, 50.0]
        selector = DistributionSelector(obs, stat_type="points")
        hit_rate = selector.historical_hit_rate(25.0)
        assert hit_rate == 0.6

    def test_get_all_probabilities(self) -> None:
        obs = [10.0, 20.0, 30.0, 40.0, 50.0]
        selector = DistributionSelector(obs, stat_type="points")
        probs = selector.get_all_probabilities(25.0)
        assert "empirical" in probs
        assert "gamma" in probs
        assert "lognormal" in probs
        assert "negative_binomial" in probs

    def test_extreme_probability_uses_parametric(self) -> None:
        obs = [20.0, 25.0, 30.0, 35.0, 40.0]
        selector = DistributionSelector(obs, stat_type="points")
        prob = selector.probability(20.0)
        assert 0.9 < prob < 1.0

    def test_probability_edge_cases(self) -> None:
        obs = [10.0, 20.0, 30.0]
        selector = DistributionSelector(obs, stat_type="points")
        assert selector.probability(0.0) == 1.0
        assert selector.probability(-5.0) == 1.0
