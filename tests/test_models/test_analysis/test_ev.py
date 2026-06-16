"""Tests for EV calculator (new)."""

import pytest

from sportsquant.models.analysis.ev_calculator import (
    EVCalculator,
    calculate_kelly_stake,
    calculate_breakeven_probability,
)


class TestEVCalculator:
    """Tests for EVCalculator class."""

    def setup_method(self):
        self.calc = EVCalculator()

    def test_calculate_ev_positive(self):
        """Test EV calculation with positive edge."""
        result = self.calc.calculate(
            probability=0.60,
            odds_american=-110,
        )
        assert result.ev > 0
        assert result.ev_percent > 0

    def test_calculate_ev_negative(self):
        """Test EV calculation with negative edge."""
        result = self.calc.calculate(
            probability=0.45,
            odds_american=-110,
        )
        assert result.ev < 0
        assert result.ev_percent < 0

    def test_calculate_ev_breakeven(self):
        """Test EV calculation at breakeven."""
        result = self.calc.calculate(
            probability=0.5238,
            odds_american=-110,
        )
        assert result.ev == pytest.approx(0.0, abs=0.01)

    def test_calculate_with_stake(self):
        """Test EV calculation with stake."""
        result = self.calc.calculate(
            probability=0.60,
            odds_american=-110,
            stake=100.0,
        )
        assert result.expected_profit > 0
        assert result.expected_profit == pytest.approx(result.ev * 100, abs=0.01)

    def test_calculate_with_decimal_odds(self):
        """Test EV calculation with decimal odds."""
        result = self.calc.calculate(
            probability=0.60,
            odds_decimal=2.0,
        )
        assert result.ev == pytest.approx(0.20, abs=0.01)

    def test_calculate_american_odds_preferred(self):
        """Test that American odds take precedence when both provided."""
        result = self.calc.calculate(
            probability=0.60,
            odds_american=-110,
            odds_decimal=2.0,
        )
        # Should use -110 (1.909), not 2.0
        assert result.ev != pytest.approx(0.20, abs=0.01)

    def test_calculate_no_odds(self):
        """Test EV calculation with no odds raises error."""
        with pytest.raises(ValueError):
            self.calc.calculate(probability=0.60)

    def test_calculate_invalid_probability(self):
        """Test EV calculation with invalid probability."""
        with pytest.raises(ValueError):
            self.calc.calculate(probability=1.5, odds_american=-110)

    def test_calculate_high_odds(self):
        """Test EV calculation with high odds."""
        result = self.calc.calculate(
            probability=0.40,
            odds_american=200,
        )
        # +200 odds = 3.0 decimal, breakeven = 0.333
        # EV = 0.4 * 2.0 - 0.6 = 0.2
        assert result.ev == pytest.approx(0.20, abs=0.01)

    def test_ev_result_attributes(self):
        """Test EVResult has all expected attributes."""
        result = self.calc.calculate(
            probability=0.60,
            odds_american=-110,
            stake=100.0,
        )
        assert hasattr(result, "ev")
        assert hasattr(result, "ev_percent")
        assert hasattr(result, "expected_profit")
        assert hasattr(result, "breakeven_probability")
        assert hasattr(result, "probability")
        assert hasattr(result, "odds_american")
        assert hasattr(result, "odds_decimal")


class TestCalculateKellyStake:
    """Tests for calculate_kelly_stake function."""

    def test_kelly_stake_positive(self):
        """Test Kelly stake with positive edge."""
        stake = calculate_kelly_stake(
            probability=0.60,
            odds_american=-110,
            bankroll=10000,
        )
        assert stake > 0
        assert stake < 10000

    def test_kelly_stake_negative_edge(self):
        """Test Kelly stake with negative edge returns 0."""
        stake = calculate_kelly_stake(
            probability=0.45,
            odds_american=-110,
            bankroll=10000,
        )
        assert stake == 0.0

    def test_kelly_stake_fractional(self):
        """Test fractional Kelly stake."""
        full = calculate_kelly_stake(
            probability=0.60,
            odds_american=-110,
            bankroll=10000,
            fraction=1.0,
        )
        half = calculate_kelly_stake(
            probability=0.60,
            odds_american=-110,
            bankroll=10000,
            fraction=0.5,
        )
        assert half == pytest.approx(full * 0.5, rel=0.01)

    def test_kelly_stake_quarter(self):
        """Test quarter Kelly stake."""
        full = calculate_kelly_stake(
            probability=0.60,
            odds_american=-110,
            bankroll=10000,
            fraction=1.0,
        )
        quarter = calculate_kelly_stake(
            probability=0.60,
            odds_american=-110,
            bankroll=10000,
            fraction=0.25,
        )
        assert quarter == pytest.approx(full * 0.25, rel=0.01)


class TestCalculateBreakevenProbability:
    """Tests for calculate_breakeven_probability function."""

    def test_breakeven_negative_odds(self):
        """Test breakeven for negative American odds."""
        prob = calculate_breakeven_probability(-110)
        assert prob == pytest.approx(0.5238, rel=0.01)

    def test_breakeven_positive_odds(self):
        """Test breakeven for positive American odds."""
        prob = calculate_breakeven_probability(150)
        assert prob == pytest.approx(0.4, rel=0.01)

    def test_breakeven_even_odds(self):
        """Test breakeven for even (+100) odds."""
        prob = calculate_breakeven_probability(100)
        assert prob == pytest.approx(0.5, rel=0.01)

    def test_breakeven_decimal_odds(self):
        """Test breakeven for decimal odds."""
        prob = calculate_breakeven_probability(odds_decimal=2.0)
        assert prob == pytest.approx(0.5, rel=0.01)

    def test_breakeven_no_odds(self):
        """Test breakeven with no odds raises error."""
        with pytest.raises(ValueError):
            calculate_breakeven_probability()
