"""Tests for Kelly calculator (migrated from Sports-Platform)."""

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
        config = KellyCalculatorConfig()
        assert config.min_odds == approx(1.01)
        assert config.max_odds == approx(100.0)
        assert config.min_probability == approx(0.001)
        assert config.max_probability == approx(0.999)

    def test_custom_config(self):
        config = KellyCalculatorConfig(min_odds=1.05, max_odds=50.0)
        assert config.min_odds == approx(1.05)
        assert config.max_odds == approx(50.0)


class TestKellyCalculator:
    """Tests for KellyCalculator class."""

    def setup_method(self):
        self.calculator = KellyCalculator()

    def test_compute_kelly_positive_edge(self):
        kelly = self.calculator.compute_kelly(probability=0.60, odds=2.0)
        assert kelly > 0
        assert kelly <= 1.0

    def test_compute_kelly_negative_edge(self):
        kelly = self.calculator.compute_kelly(probability=0.40, odds=2.0)
        assert kelly <= 0

    def test_compute_kelly_breakeven(self):
        kelly = self.calculator.compute_kelly(probability=0.50, odds=2.0)
        assert kelly == approx(0.0)

    def test_compute_kelly_invalid_probability_low(self):
        with pytest.raises(ValueError):
            self.calculator.compute_kelly(probability=0.0005, odds=2.0)

    def test_compute_kelly_invalid_probability_high(self):
        with pytest.raises(ValueError):
            self.calculator.compute_kelly(probability=0.9995, odds=2.0)

    def test_compute_kelly_invalid_odds_low(self):
        with pytest.raises(ValueError):
            self.calculator.compute_kelly(probability=0.6, odds=1.0)

    def test_compute_kelly_invalid_odds_high(self):
        with pytest.raises(ValueError):
            self.calculator.compute_kelly(probability=0.6, odds=101.0)

    def test_compute_kelly_odds_at_minimum(self):
        kelly = self.calculator.compute_kelly(probability=0.995, odds=1.01)
        assert kelly > 0

    def test_compute_fractional_kelly_half(self):
        full_kelly = self.calculator.compute_kelly(probability=0.60, odds=2.0)
        half_kelly = self.calculator.compute_fractional_kelly(
            probability=0.60, odds=2.0, fraction=0.5
        )
        assert half_kelly == pytest.approx(full_kelly * 0.5, rel=1e-6)

    def test_compute_fractional_kelly_quarter(self):
        full_kelly = self.calculator.compute_kelly(probability=0.60, odds=2.0)
        quarter_kelly = self.calculator.compute_fractional_kelly(
            probability=0.60, odds=2.0, fraction=0.25
        )
        assert quarter_kelly == pytest.approx(full_kelly * 0.25, rel=1e-6)

    def test_compute_fractional_kelly_invalid_fraction(self):
        with pytest.raises(ValueError):
            self.calculator.compute_fractional_kelly(probability=0.60, odds=2.0, fraction=1.5)

    def test_compute_adaptive_kelly(self):
        ctx = AdaptiveKellyContext(
            probability=0.60,
            odds=2.0,
            fraction=0.5,
            volatility=0.3,
            max_fraction=0.5,
        )
        adaptive = self.calculator.compute_adaptive_kelly(ctx)
        assert adaptive >= 0
        assert adaptive <= 0.5

    def test_compute_adaptive_kelly_high_volatility(self):
        ctx_low_vol = AdaptiveKellyContext(probability=0.60, odds=2.0, fraction=0.5, volatility=0.1)
        ctx_high_vol = AdaptiveKellyContext(
            probability=0.60, odds=2.0, fraction=0.5, volatility=0.8
        )
        low_vol_kelly = self.calculator.compute_adaptive_kelly(ctx_low_vol)
        high_vol_kelly = self.calculator.compute_adaptive_kelly(ctx_high_vol)
        assert low_vol_kelly > high_vol_kelly

    def test_compute_kelly_multi_bet(self):
        probs = [0.60, 0.55, 0.65]
        odds = [2.0, 1.9, 2.1]
        kelly_fractions = self.calculator.compute_kelly_multi_bet(probs, odds)
        assert len(kelly_fractions) == 3
        assert all(k >= 0 for k in kelly_fractions)

    def test_compute_kelly_multi_bet_with_correlation(self):
        probs = [0.60, 0.55]
        odds = [2.0, 2.0]
        kelly_no_corr = self.calculator.compute_kelly_multi_bet(probs, odds)
        kelly_with_corr = self.calculator.compute_kelly_multi_bet(probs, odds, correlations=[0.5])
        assert kelly_with_corr[0] <= kelly_no_corr[0]

    def test_compute_kelly_multi_bet_length_mismatch(self):
        with pytest.raises(ValueError):
            self.calculator.compute_kelly_multi_bet(probabilities=[0.6, 0.5], odds=[2.0])


class TestBankrollManager:
    """Tests for BankrollManager class."""

    def setup_method(self):
        self.manager = BankrollManager(bankroll=10000.0)

    def test_default_bankroll(self):
        assert self.manager.bankroll == approx(10000.0)

    def test_negative_bankroll_raises(self):
        with pytest.raises(ValueError):
            BankrollManager(bankroll=-100.0)

    def test_invalid_max_position_raises(self):
        config = BankrollManagerConfig(
            kelly_fraction=0.25,
            exposure_limits=ExposureLimits(max_position_pct=1.5),
        )
        with pytest.raises(ValueError):
            BankrollManager(bankroll=10000.0, config=config)

    def test_compute_bet_size_basic(self):
        bet_size = self.manager.compute_bet_size(
            kelly_fraction=0.05, odds=2.0, win_probability=0.60
        )
        assert bet_size >= 0
        assert bet_size <= 1000.0

    def test_compute_bet_size_no_edge(self):
        bet_size = self.manager.compute_bet_size(kelly_fraction=0.0, odds=2.0, win_probability=0.50)
        assert bet_size == approx(0.0)

    def test_apply_position_limits_under_max(self):
        limited = self.manager.apply_position_limits(bet_size=500.0)
        assert limited == approx(500.0)

    def test_apply_position_limits_over_max(self):
        limited = self.manager.apply_position_limits(bet_size=2000.0)
        assert limited == approx(1000.0)

    def test_apply_position_limits_under_min(self):
        limited = self.manager.apply_position_limits(bet_size=0.50)
        assert limited == approx(0.0)

    def test_update_bankroll_win(self):
        new_bankroll = self.manager.update_bankroll(10000.0, profit=100.0)
        assert new_bankroll == approx(10100.0)

    def test_update_bankroll_loss(self):
        new_bankroll = self.manager.update_bankroll(10000.0, profit=-100.0)
        assert new_bankroll == approx(9900.0)

    def test_update_bankroll_explicit_loss(self):
        new_bankroll = self.manager.update_bankroll(10000.0, profit=0.0, loss=100.0)
        assert new_bankroll == approx(9900.0)

    def test_update_bankroll_cannot_go_negative(self):
        manager = BankrollManager(bankroll=50.0)
        new_bankroll = manager.update_bankroll(50.0, profit=-100.0)
        assert new_bankroll == approx(0.0)

    def test_get_exposure_percentages(self):
        exposure = self.manager.get_exposure_percentages(bet_size=500.0, current_exposure=200.0)
        assert "position_pct" in exposure
        assert "portfolio_pct" in exposure
        assert "remaining_capacity" in exposure
        assert "kelly_recommended" in exposure


class TestEdgeCalculator:
    """Tests for EdgeCalculator class."""

    def setup_method(self):
        self.calculator = EdgeCalculator()

    def test_compute_edge_positive(self):
        edge = self.calculator.compute_edge(win_probability=0.60, odds=2.0)
        assert edge > 0

    def test_compute_edge_negative(self):
        edge = self.calculator.compute_edge(win_probability=0.40, odds=2.0)
        assert edge < 0

    def test_compute_edge_breakeven(self):
        edge = self.calculator.compute_edge(win_probability=0.50, odds=2.0)
        assert edge == approx(0.0)

    def test_compute_edge_invalid_probability(self):
        with pytest.raises(ValueError):
            self.calculator.compute_edge(win_probability=1.5, odds=2.0)

    def test_compute_edge_invalid_odds(self):
        with pytest.raises(ValueError):
            self.calculator.compute_edge(win_probability=0.6, odds=0.5)

    def test_compute_expected_value(self):
        ev = self.calculator.compute_expected_value(win_probability=0.60, odds=2.0, stake=100.0)
        assert isinstance(ev, float)

    def test_confidence_interval(self):
        lower, upper, _ = self.calculator.confidence_interval(
            win_probability=0.60, n_samples=100, confidence=0.95
        )
        assert lower <= 0.60 <= upper
        assert lower < upper

    def test_confidence_interval_low_samples(self):
        lower, upper, _ = self.calculator.confidence_interval(
            win_probability=0.60, n_samples=10, confidence=0.95
        )
        assert lower < upper
        assert (upper - lower) > 0.1

    def test_confidence_interval_invalid_samples(self):
        with pytest.raises(ValueError):
            self.calculator.confidence_interval(win_probability=0.6, n_samples=0)

    def test_confidence_interval_invalid_confidence(self):
        with pytest.raises(ValueError):
            self.calculator.confidence_interval(win_probability=0.6, n_samples=100, confidence=1.5)

    def test_is_significant_edge_positive(self):
        is_sig = self.calculator.is_significant_edge(win_probability=0.70, odds=2.0, n_samples=1000)
        assert isinstance(is_sig, bool)

    def test_is_significant_edge_negative(self):
        is_sig = self.calculator.is_significant_edge(win_probability=0.45, odds=2.0, n_samples=100)
        assert is_sig is False

    def test_roi_break_even(self):
        break_even = self.calculator.roi_break_even(odds=2.0)
        assert break_even == approx(0.5)

    def test_roi_break_even_fractional_kelly(self):
        break_even = self.calculator.roi_break_even(odds=2.0, kelly_fraction=0.25)
        assert break_even > 0

    def test_roi_break_even_invalid_odds(self):
        with pytest.raises(ValueError):
            self.calculator.roi_break_even(odds=0.5)
