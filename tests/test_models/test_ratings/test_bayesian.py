"""Tests for Bayesian priors (new)."""

import pytest

from sportsquant.models.ratings.bayesian_priors import (
    BayesianPriorCalculator,
    PriorConfig,
    compute_posterior,
    beta_binomial_posterior,
)


class TestPriorConfig:
    """Tests for PriorConfig dataclass."""

    def test_default_config(self):
        """Test default prior configuration."""
        config = PriorConfig()
        assert config.alpha_prior == 2.0
        assert config.beta_prior == 2.0
        assert config.prior_weight == 10.0

    def test_custom_config(self):
        """Test custom prior configuration."""
        config = PriorConfig(alpha_prior=5.0, beta_prior=5.0, prior_weight=20.0)
        assert config.alpha_prior == 5.0
        assert config.beta_prior == 5.0
        assert config.prior_weight == 20.0

    def test_uninformative_prior(self):
        """Test uninformative (flat) prior."""
        config = PriorConfig(alpha_prior=1.0, beta_prior=1.0, prior_weight=2.0)
        assert config.alpha_prior == 1.0
        assert config.beta_prior == 1.0


class TestBetaBinomialPosterior:
    """Tests for beta_binomial_posterior function."""

    def test_posterior_mean(self):
        """Test posterior mean calculation."""
        # Prior: Beta(2, 2), Observations: 8 successes, 2 failures
        # Posterior: Beta(10, 4), Mean = 10/14 = 0.714
        alpha_post, beta_post = beta_binomial_posterior(
            alpha_prior=2,
            beta_prior=2,
            successes=8,
            failures=2,
        )
        posterior_mean = alpha_post / (alpha_post + beta_post)
        assert posterior_mean == pytest.approx(10 / 14, rel=0.01)

    def test_posterior_with_no_observations(self):
        """Test posterior equals prior with no observations."""
        alpha_post, beta_post = beta_binomial_posterior(
            alpha_prior=2,
            beta_prior=2,
            successes=0,
            failures=0,
        )
        assert alpha_post == 2.0
        assert beta_post == 2.0

    def test_posterior_with_many_observations(self):
        """Test posterior dominated by data with many observations."""
        alpha_post, beta_post = beta_binomial_posterior(
            alpha_prior=2,
            beta_prior=2,
            successes=500,
            failures=500,
        )
        posterior_mean = alpha_post / (alpha_post + beta_post)
        # With 1000 observations, posterior should be close to 0.5
        assert posterior_mean == pytest.approx(0.5, abs=0.02)

    def test_posterior_extreme_data(self):
        """Test posterior with extreme data (all successes)."""
        alpha_post, beta_post = beta_binomial_posterior(
            alpha_prior=2,
            beta_prior=2,
            successes=10,
            failures=0,
        )
        posterior_mean = alpha_post / (alpha_post + beta_post)
        # 12/14 = 0.857
        assert posterior_mean == pytest.approx(12 / 14, rel=0.01)


class TestComputePosterior:
    """Tests for compute_posterior function."""

    def test_basic_posterior(self):
        """Test basic posterior computation."""
        result = compute_posterior(
            prior_mean=0.5,
            prior_weight=10,
            observed_mean=0.6,
            observed_weight=20,
        )
        # (0.5 * 10 + 0.6 * 20) / (10 + 20) = 17/30 = 0.567
        assert result == pytest.approx(17 / 30, rel=0.01)

    def test_posterior_with_zero_prior_weight(self):
        """Test posterior with zero prior weight equals observed."""
        result = compute_posterior(
            prior_mean=0.5,
            prior_weight=0,
            observed_mean=0.6,
            observed_weight=20,
        )
        assert result == pytest.approx(0.6, rel=0.01)

    def test_posterior_with_zero_observed_weight(self):
        """Test posterior with zero observed weight equals prior."""
        result = compute_posterior(
            prior_mean=0.5,
            prior_weight=10,
            observed_mean=0.6,
            observed_weight=0,
        )
        assert result == pytest.approx(0.5, rel=0.01)

    def test_posterior_equal_weights(self):
        """Test posterior with equal weights is average."""
        result = compute_posterior(
            prior_mean=0.4,
            prior_weight=10,
            observed_mean=0.8,
            observed_weight=10,
        )
        assert result == pytest.approx(0.6, rel=0.01)


class TestBayesianPriorCalculator:
    """Tests for BayesianPriorCalculator class."""

    def setup_method(self):
        self.calculator = BayesianPriorCalculator()

    def test_calculate_player_prior(self):
        """Test calculating prior for a player."""
        # Player with 50 games, 55% hit rate
        prior = self.calculator.calculate_player_prior(
            player_name="Test Player",
            n_games=50,
            historical_hit_rate=0.55,
        )
        assert 0.0 <= prior <= 1.0
        # Should be pulled toward league average (0.5)
        assert prior < 0.55  # Shrunk toward mean

    def test_calculate_player_prior_few_games(self):
        """Test prior with very few games (strong shrinkage)."""
        prior = self.calculator.calculate_player_prior(
            player_name="Rookie",
            n_games=5,
            historical_hit_rate=0.80,
        )
        # With only 5 games, should be heavily shrunk toward league average
        assert prior < 0.70

    def test_calculate_player_prior_many_games(self):
        """Test prior with many games (minimal shrinkage)."""
        prior = self.calculator.calculate_player_prior(
            player_name="Veteran",
            n_games=200,
            historical_hit_rate=0.55,
        )
        # With 200 games, should be close to observed rate
        assert prior == pytest.approx(0.55, abs=0.02)

    def test_calculate_league_prior(self):
        """Test calculating league-wide prior."""
        # All players in the league
        player_rates = [0.48, 0.52, 0.50, 0.51, 0.49, 0.53, 0.47, 0.50]
        league_prior = self.calculator.calculate_league_prior(player_rates)
        assert 0.0 <= league_prior <= 1.0
        assert league_prior == pytest.approx(0.5, abs=0.02)

    def test_calculate_position_prior(self):
        """Test calculating position-specific prior."""
        # Guards tend to have different rates than centers
        guard_rates = [0.48, 0.50, 0.49, 0.51]
        center_rates = [0.55, 0.53, 0.54, 0.56]

        guard_prior = self.calculator.calculate_position_prior("guard", guard_rates)
        center_prior = self.calculator.calculate_position_prior("center", center_rates)

        assert guard_prior < center_prior

    def test_shrinkage_factor(self):
        """Test shrinkage factor calculation."""
        # More data = less shrinkage
        low_shrinkage = self.calculator.shrinkage_factor(n=100, prior_weight=10)
        high_shrinkage = self.calculator.shrinkage_factor(n=5, prior_weight=10)
        assert low_shrinkage < high_shrinkage

    def test_shrinkage_factor_zero_data(self):
        """Test shrinkage factor with zero data points."""
        shrinkage = self.calculator.shrinkage_factor(n=0, prior_weight=10)
        assert shrinkage == 1.0  # Complete shrinkage to prior

    def test_custom_config(self):
        """Test calculator with custom configuration."""
        config = PriorConfig(alpha_prior=5.0, beta_prior=5.0, prior_weight=20.0)
        calculator = BayesianPriorCalculator(config=config)
        assert calculator.config.prior_weight == 20.0
