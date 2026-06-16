"""Unit tests for KellyCalculator in kelly_enhanced.py (migrated from Sports-Platform)."""
# pylint: disable=attribute-defined-outside-init

import pytest
from pytest import approx

from sportsquant.core.betting.kelly import (
    KellyCalculator,
    KellyCalculatorConfig,
    AdaptiveKellyContext,
    BankrollManager,
    BankrollManagerConfig,
    EdgeCalculator,
    ExposureLimits,
)


class TestKellyCalculatorConfig:
    """Tests for KellyCalculatorConfig dataclass."""

    def test_default_config(self):
        """Test default configuration values."""
        config = KellyCalculatorConfig()
        assert config.min_odds == approx(1.01)
        assert config.max_odds == approx(100.0)
        assert config.min_probability == approx(0.001)
        assert config.max_probability == approx(0.999)

    def test_custom_config(self):
        """Test custom configuration values."""
        config = KellyCalculatorConfig(min_odds=1.05, max_odds=50.0)
        assert config.min_odds == approx(1.05)
        assert config.max_odds == approx(50.0)


class TestKellyCalculator:
    """Tests for KellyCalculator class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.calculator = KellyCalculator()

    def test_compute_kelly_positive_edge(self):
        """Test Kelly calculation with positive edge."""
        # 60% win probability at 2.0 odds (fair odds would be 1.67)
        kelly = self.calculator.compute_kelly(probability=0.60, odds=2.0)
        assert kelly > 0
        assert kelly <= 1.0

    def test_compute_kelly_negative_edge(self):
        """Test Kelly calculation with negative edge."""
        # 40% win probability at 2.0 odds (breakeven is 50%)
        kelly = self.calculator.compute_kelly(probability=0.40, odds=2.0)
        assert kelly <= 0

    def test_compute_kelly_breakeven(self):
        """Test Kelly at breakeven probability."""
        # 50% win probability at 2.0 odds = breakeven
        kelly = self.calculator.compute_kelly(probability=0.50, odds=2.0)
        assert kelly == approx(0.0)

    def test_compute_kelly_invalid_probability_low(self):
        """Test Kelly with probability below minimum."""
        with pytest.raises(ValueError):
            self.calculator.compute_kelly(probability=0.0005, odds=2.0)

    def test_compute_kelly_invalid_probability_high(self):
        """Test Kelly with probability above maximum."""
        with pytest.raises(ValueError):
            self.calculator.compute_kelly(probability=0.9995, odds=2.0)

    def test_compute_kelly_invalid_odds_low(self):
        """Test Kelly with odds below minimum."""
        with pytest.raises(ValueError):
            self.calculator.compute_kelly(probability=0.6, odds=1.0)

    def test_compute_kelly_invalid_odds_high(self):
        """Test Kelly with odds above maximum."""
        with pytest.raises(ValueError):
            self.calculator.compute_kelly(probability=0.6, odds=101.0)

    def test_compute_kelly_odds_at_minimum(self):
        """Test Kelly with odds at minimum (1.01) needs very high probability."""
        # At 1.01 odds, you need > 99% probability to have positive Kelly
        kelly = self.calculator.compute_kelly(probability=0.995, odds=1.01)
        assert kelly > 0

    def test_compute_fractional_kelly_half(self):
        """Test half Kelly calculation."""
        full_kelly = self.calculator.compute_kelly(probability=0.60, odds=2.0)
        half_kelly = self.calculator.compute_fractional_kelly(
            probability=0.60, odds=2.0, fraction=0.5
        )
        assert half_kelly == pytest.approx(full_kelly * 0.5, rel=1e-6)

    def test_compute_fractional_kelly_quarter(self):
        """Test quarter Kelly calculation."""
        full_kelly = self.calculator.compute_kelly(probability=0.60, odds=2.0)
        quarter_kelly = self.calculator.compute_fractional_kelly(
            probability=0.60, odds=2.0, fraction=0.25
        )
        assert quarter_kelly == pytest.approx(full_kelly * 0.25, rel=1e-6)

    def test_compute_fractional_kelly_invalid_fraction(self):
        """Test fractional Kelly with invalid fraction."""
        with pytest.raises(ValueError):
            self.calculator.compute_fractional_kelly(probability=0.60, odds=2.0, fraction=1.5)

    def test_compute_adaptive_kelly(self):
        """Test adaptive Kelly calculation."""
        ctx = AdaptiveKellyContext(
            probability=0.60,
            odds=2.0,
            fraction=0.5,
            volatility=0.3,
            max_fraction=0.5,
        )
        adaptive = self.calculator.compute_adaptive_kelly(ctx)
        assert adaptive >= 0
        assert adaptive <= 0.5  # Limited by max_fraction

    def test_compute_adaptive_kelly_high_volatility(self):
        """Test adaptive Kelly with high volatility reduces size."""
        ctx_low_vol = AdaptiveKellyContext(probability=0.60, odds=2.0, fraction=0.5, volatility=0.1)
        ctx_high_vol = AdaptiveKellyContext(
            probability=0.60, odds=2.0, fraction=0.5, volatility=0.8
        )
        low_vol_kelly = self.calculator.compute_adaptive_kelly(ctx_low_vol)
        high_vol_kelly = self.calculator.compute_adaptive_kelly(ctx_high_vol)
        assert low_vol_kelly > high_vol_kelly

    def test_compute_kelly_multi_bet(self):
        """Test multi-bet Kelly with correlation adjustment."""
        probs = [0.60, 0.55, 0.65]
        odds = [2.0, 1.9, 2.1]
        kelly_fractions = self.calculator.compute_kelly_multi_bet(probs, odds)
        assert len(kelly_fractions) == 3
        assert all(k >= 0 for k in kelly_fractions)

    def test_compute_kelly_multi_bet_with_correlation(self):
        """Test multi-bet Kelly with correlation reduces exposure."""
        probs = [0.60, 0.55]
        odds = [2.0, 2.0]
        # Without correlation
        kelly_no_corr = self.calculator.compute_kelly_multi_bet(probs, odds)
        # With correlation (positive correlation reduces exposure)
        kelly_with_corr = self.calculator.compute_kelly_multi_bet(probs, odds, correlations=[0.5])
        # First bet should be reduced due to correlation
        assert kelly_with_corr[0] <= kelly_no_corr[0]

    def test_compute_kelly_multi_bet_length_mismatch(self):
        """Test multi-bet with mismatched input lengths."""
        with pytest.raises(ValueError):
            self.calculator.compute_kelly_multi_bet(probabilities=[0.6, 0.5], odds=[2.0])


class TestBankrollManager:
    """Tests for BankrollManager class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.manager = BankrollManager(bankroll=10000.0)

    def test_default_bankroll(self):
        """Test bankroll manager with default config."""
        assert self.manager.bankroll == approx(10000.0)

    def test_negative_bankroll_raises(self):
        """Test that negative bankroll raises ValueError."""
        with pytest.raises(ValueError):
            BankrollManager(bankroll=-100.0)

    def test_invalid_max_position_raises(self):
        """Test invalid max position percentage raises ValueError."""
        # Create custom exposure limits
        config = BankrollManagerConfig(
            kelly_fraction=0.25,
            exposure_limits=ExposureLimits(max_position_pct=1.5),  # Invalid
        )
        with pytest.raises(ValueError):
            BankrollManager(bankroll=10000.0, config=config)

    def test_compute_bet_size_basic(self):
        """Test basic bet size calculation."""
        bet_size = self.manager.compute_bet_size(
            kelly_fraction=0.05, odds=2.0, win_probability=0.60
        )
        assert bet_size >= 0
        assert bet_size <= 1000.0  # Max position 10%

    def test_compute_bet_size_no_edge(self):
        """Test bet size returns 0 when no edge."""
        bet_size = self.manager.compute_bet_size(kelly_fraction=0.0, odds=2.0, win_probability=0.50)
        assert bet_size == approx(0.0)

    def test_apply_position_limits_under_max(self):
        """Test position limits with bet under max."""
        limited = self.manager.apply_position_limits(bet_size=500.0)
        assert limited == approx(500.0)

    def test_apply_position_limits_over_max(self):
        """Test position limits reduce oversized bet."""
        limited = self.manager.apply_position_limits(bet_size=2000.0)
        assert limited == approx(1000.0)  # 10% of 10000

    def test_apply_position_limits_under_min(self):
        """Test position limits return 0 for bet under minimum."""
        limited = self.manager.apply_position_limits(bet_size=0.50)
        assert limited == approx(0.0)

    def test_update_bankroll_win(self):
        """Test updating bankroll after win."""
        new_bankroll = self.manager.update_bankroll(10000.0, profit=100.0)
        assert new_bankroll == approx(10100.0)

    def test_update_bankroll_loss(self):
        """Test updating bankroll after loss."""
        new_bankroll = self.manager.update_bankroll(10000.0, profit=-100.0)
        assert new_bankroll == approx(9900.0)

    def test_update_bankroll_explicit_loss(self):
        """Test updating bankroll with explicit loss."""
        new_bankroll = self.manager.update_bankroll(10000.0, profit=0.0, loss=100.0)
        assert new_bankroll == approx(9900.0)

    def test_update_bankroll_cannot_go_negative(self):
        """Test bankroll cannot go below zero."""
        manager = BankrollManager(bankroll=50.0)
        new_bankroll = manager.update_bankroll(50.0, profit=-100.0)
        assert new_bankroll == approx(0.0)

    def test_get_exposure_percentages(self):
        """Test exposure percentage calculation."""
        exposure = self.manager.get_exposure_percentages(bet_size=500.0, current_exposure=200.0)
        assert "position_pct" in exposure
        assert "portfolio_pct" in exposure
        assert "remaining_capacity" in exposure
        assert "kelly_recommended" in exposure


class TestEdgeCalculator:
    """Tests for EdgeCalculator class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.calculator = EdgeCalculator()

    def test_compute_edge_positive(self):
        """Test edge calculation with positive edge."""
        edge = self.calculator.compute_edge(win_probability=0.60, odds=2.0)
        assert edge > 0

    def test_compute_edge_negative(self):
        """Test edge calculation with negative edge."""
        edge = self.calculator.compute_edge(win_probability=0.40, odds=2.0)
        assert edge < 0

    def test_compute_edge_breakeven(self):
        """Test edge at breakeven."""
        edge = self.calculator.compute_edge(win_probability=0.50, odds=2.0)
        assert edge == approx(0.0)

    def test_compute_edge_invalid_probability(self):
        """Test edge with invalid probability."""
        with pytest.raises(ValueError):
            self.calculator.compute_edge(win_probability=1.5, odds=2.0)

    def test_compute_edge_invalid_odds(self):
        """Test edge with invalid odds."""
        with pytest.raises(ValueError):
            self.calculator.compute_edge(win_probability=0.6, odds=0.5)

    def test_compute_expected_value(self):
        """Test expected value calculation."""
        ev = self.calculator.compute_expected_value(win_probability=0.60, odds=2.0, stake=100.0)
        assert isinstance(ev, float)

    def test_confidence_interval(self):
        """Test confidence interval calculation."""
        lower, upper, _ = self.calculator.confidence_interval(
            win_probability=0.60, n_samples=100, confidence=0.95
        )
        assert lower <= 0.60 <= upper
        assert lower < upper

    def test_confidence_interval_low_samples(self):
        """Test confidence interval with low sample count."""
        lower, upper, _ = self.calculator.confidence_interval(
            win_probability=0.60, n_samples=10, confidence=0.95
        )
        assert lower < upper
        # Wide interval expected with low samples
        assert (upper - lower) > 0.1

    def test_confidence_interval_invalid_samples(self):
        """Test confidence interval with invalid sample count."""
        with pytest.raises(ValueError):
            self.calculator.confidence_interval(win_probability=0.6, n_samples=0)

    def test_confidence_interval_invalid_confidence(self):
        """Test confidence interval with invalid confidence level."""
        with pytest.raises(ValueError):
            self.calculator.confidence_interval(win_probability=0.6, n_samples=100, confidence=1.5)

    def test_is_significant_edge_positive(self):
        """Test significance check with positive edge."""
        is_sig = self.calculator.is_significant_edge(win_probability=0.70, odds=2.0, n_samples=1000)
        assert isinstance(is_sig, bool)

    def test_is_significant_edge_negative(self):
        """Test significance check with no edge."""
        is_sig = self.calculator.is_significant_edge(win_probability=0.45, odds=2.0, n_samples=100)
        assert is_sig is False

    def test_roi_break_even(self):
        """Test break-even win rate calculation."""
        break_even = self.calculator.roi_break_even(odds=2.0)
        assert break_even == approx(0.5)

    def test_roi_break_even_fractional_kelly(self):
        """Test break-even with fractional Kelly."""
        break_even = self.calculator.roi_break_even(odds=2.0, kelly_fraction=0.25)
        # The formula adjusts the break-even probability
        assert break_even > 0

    def test_roi_break_even_invalid_odds(self):
        """Test break-even with invalid odds."""
        with pytest.raises(ValueError):
            self.calculator.roi_break_even(odds=0.5)
