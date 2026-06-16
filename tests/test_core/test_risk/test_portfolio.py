"""Unit tests for Portfolio management (migrated from Sports-Platform)."""
# pylint: disable=attribute-defined-outside-init

import pytest
from pytest import approx

from sportsquant.core.risk.portfolio import (
    KellyBettor,
    KellyConfig,
    PortfolioManager,
    PortfolioRiskConfig,
    PositionSizer,
    PositionSizingConfig,
)


class TestKellyConfig:
    """Tests for KellyConfig dataclass."""

    def test_default_config(self):
        """Test default Kelly configuration."""
        config = KellyConfig()
        assert config.kelly_fraction == approx(0.25)
        assert config.max_kelly == approx(0.20)
        assert config.min_edge_for_bet == approx(0.02)

    def test_custom_config(self):
        """Test custom Kelly configuration."""
        config = KellyConfig(kelly_fraction=0.5, max_kelly=0.30)
        assert config.kelly_fraction == approx(0.5)
        assert config.max_kelly == approx(0.30)


class TestKellyBettor:
    """Tests for KellyBettor class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.bettor = KellyBettor()

    def test_compute_kelly_basic(self):
        """Test basic Kelly calculation."""
        kelly = self.bettor.compute_kelly(win_prob=0.60, odds_decimal=2.0)
        assert kelly > 0
        assert kelly <= self.bettor.config.max_kelly

    def test_compute_kelly_breakeven(self):
        """Test Kelly at breakeven probability."""
        kelly = self.bettor.compute_kelly(win_prob=0.50, odds_decimal=2.0)
        assert kelly == approx(0.0)

    def test_compute_kelly_no_edge(self):
        """Test Kelly with no edge."""
        kelly = self.bettor.compute_kelly(win_prob=0.45, odds_decimal=2.0)
        assert kelly == approx(0.0)

    def test_compute_kelly_with_fraction(self):
        """Test Kelly with custom fraction."""
        kelly = self.bettor.compute_kelly(win_prob=0.60, odds_decimal=2.0, kelly_fraction=0.5)
        half_kelly = self.bettor.compute_kelly(win_prob=0.60, odds_decimal=2.0, kelly_fraction=0.25)
        assert kelly == pytest.approx(half_kelly * 2, rel=1e-6)

    def test_compute_kelly_max_limit(self):
        """Test Kelly is capped at max_kelly."""
        # Very favorable odds should still be capped
        kelly = self.bettor.compute_kelly(win_prob=0.95, odds_decimal=10.0)
        assert kelly <= self.bettor.config.max_kelly

    def test_compute_kelly_with_correlation(self):
        """Test Kelly with correlation adjustment."""
        base_kelly = self.bettor.compute_kelly(win_prob=0.60, odds_decimal=2.0)
        correlated_kelly = self.bettor.compute_kelly_with_correlation(
            win_prob=0.60, odds_decimal=2.0, correlation=0.5
        )
        assert correlated_kelly <= base_kelly

    def test_compute_expected_value(self):
        """Test expected value calculation."""
        ev = self.bettor.compute_expected_value(win_prob=0.60, odds_decimal=2.0, stake=100.0)
        assert ev == pytest.approx(20.0, rel=1e-6)

    def test_compute_edge(self):
        """Test edge calculation."""
        edge = self.bettor.compute_edge(win_prob=0.60, odds_decimal=2.0)
        assert edge == pytest.approx(0.10, rel=1e-6)

    def test_compute_roi(self):
        """Test ROI calculation."""
        roi = self.bettor.compute_roi(win_prob=0.60, odds_decimal=2.0)
        assert roi > 0


class TestPositionSizingConfig:
    """Tests for PositionSizingConfig dataclass."""

    def test_default_config(self):
        """Test default position sizing configuration."""
        config = PositionSizingConfig()
        assert config.max_position_size == approx(0.10)
        assert config.max_portfolio_exposure == approx(0.50)
        assert config.min_bet_size == approx(0.01)


class TestPositionSizer:
    """Tests for PositionSizer class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.sizer = PositionSizer()

    def test_compute_position_size_basic(self):
        """Test basic position size calculation."""
        position = self.sizer.compute_position_size(
            kelly_fraction=0.10,
            edge=0.05,
            bankroll=10000.0,
        )
        assert position >= 0
        assert position <= 1000.0  # Max 10% of bankroll

    def test_compute_position_size_no_edge(self):
        """Test position size returns 0 when edge is too small."""
        position = self.sizer.compute_position_size(
            kelly_fraction=0.10,
            edge=0.01,  # Below min_edge_for_bet
            bankroll=10000.0,
        )
        assert position == approx(0.0)

    def test_compute_position_size_exposure_limits(self):
        """Test position size respects exposure limits."""
        position = self.sizer.compute_position_size(
            kelly_fraction=0.50,  # Large Kelly
            edge=0.10,
            bankroll=10000.0,
            current_portfolio_exposure=4000.0,  # 40% already exposed
        )
        # Should be reduced due to portfolio exposure limit
        assert position < 5000.0  # Less than 50% max

    def test_compute_parlay_size(self):
        """Test parlay position size calculation."""
        parlay = self.sizer.compute_parlay_size(
            leg_kelly_fractions=[0.05, 0.05, 0.05],
            leg_edges=[0.05, 0.05, 0.05],
            bankroll=10000.0,
            num_legs=3,
        )
        assert parlay >= 0
        assert parlay <= 1000.0  # Max position size

    def test_compute_parlay_size_no_edge(self):
        """Test parlay size returns 0 when average edge is too small."""
        parlay = self.sizer.compute_parlay_size(
            leg_kelly_fractions=[0.05, 0.05, 0.05],
            leg_edges=[0.01, 0.01, 0.01],  # Below min_edge
            bankroll=10000.0,
            num_legs=3,
        )
        assert parlay == approx(0.0)

    def test_compute_round_robin_size(self):
        """Test round robin position size calculation."""
        rr = self.sizer.compute_round_robin_size(
            leg_kelly_fractions=[0.05, 0.05],
            leg_edges=[0.05, 0.05],
            bankroll=10000.0,
            combinations=3,
        )
        assert rr >= 0


class TestPortfolioRiskConfig:
    """Tests for PortfolioRiskConfig dataclass."""

    def test_default_config(self):
        """Test default portfolio risk configuration."""
        config = PortfolioRiskConfig()
        assert config.max_daily_loss_pct == approx(0.05)
        assert config.max_drawdown_pct == approx(0.15)
        assert config.var_confidence == approx(0.95)


class TestPortfolioManager:
    """Tests for PortfolioManager class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.manager = PortfolioManager()

    def test_set_bankroll(self):
        """Test setting bankroll."""
        self.manager.set_bankroll(20000.0)
        assert self.manager.bankroll == approx(20000.0)

    def test_can_place_bet_approved(self):
        """Test bet approval when within limits."""
        can_bet, reason = self.manager.can_place_bet(
            market="pts", book="draftkings", proposed_size=500.0
        )
        assert can_bet is True
        assert reason == "Bet approved"

    def test_can_place_bet_daily_loss_exceeded(self):
        """Test bet rejection due to daily loss limit."""
        self.manager.daily_pnl = -600.0  # -6% of 10000
        can_bet, reason = self.manager.can_place_bet(
            market="pts", book="draftkings", proposed_size=500.0
        )
        assert can_bet is False
        assert "Daily loss limit exceeded" in reason

    def test_can_place_bet_position_exceeded(self):
        """Test bet rejection due to position size limit."""
        can_bet, reason = self.manager.can_place_bet(
            market="pts",
            book="draftkings",
            proposed_size=2000.0,  # > 10% of 10000
        )
        assert can_bet is False
        assert "Position size exceeds maximum" in reason

    def test_place_bet_approved(self):
        """Test placing a bet that is approved."""
        bet = self.manager.place_bet(
            player_id="lebron-james",
            market="pts",
            line=25.5,
            odds_decimal=2.0,
            win_prob=0.60,
            side="over",
            book="draftkings",
        )
        assert bet["status"] == "pending"
        assert bet["position_size"] > 0

    def test_place_bet_rejected_no_edge(self):
        """Test bet rejection due to insufficient edge."""
        bet = self.manager.place_bet(
            player_id="lebron-james",
            market="pts",
            line=25.5,
            odds_decimal=1.5,  # Low odds, likely no edge
            win_prob=0.55,  # Edge: 0.55 - 0.67 = negative
            side="over",
            book="draftkings",
        )
        assert bet["status"] == "rejected"
        assert bet["size"] == approx(0.0)

    def test_place_bet_updates_exposure(self):
        """Test placing bet updates portfolio exposure."""
        initial_exposure = self.manager.current_exposure
        self.manager.place_bet(
            player_id="lebron-james",
            market="pts",
            line=25.5,
            odds_decimal=2.0,
            win_prob=0.60,
            side="over",
            book="draftkings",
        )
        assert self.manager.current_exposure > initial_exposure

    def test_settle_bet_win(self):
        """Test settling a winning bet."""
        _ = self.manager.place_bet(
            player_id="lebron-james",
            market="pts",
            line=25.5,
            odds_decimal=2.0,
            win_prob=0.60,
            side="over",
            book="draftkings",
        )
        bet_index = 0
        pnl = self.manager.settle_bet(bet_index=bet_index, result=1)
        assert pnl > 0
        assert self.manager.bankroll > 10000.0

    def test_settle_bet_loss(self):
        """Test settling a losing bet."""
        _ = self.manager.place_bet(
            player_id="lebron-james",
            market="pts",
            line=25.5,
            odds_decimal=2.0,
            win_prob=0.60,
            side="over",
            book="draftkings",
        )
        bet_index = 0
        pnl = self.manager.settle_bet(bet_index=bet_index, result=0)
        assert pnl < 0
        assert self.manager.bankroll < 10000.0

    def test_settle_bet_invalid_index(self):
        """Test settling bet with invalid index raises error."""
        with pytest.raises(ValueError):
            self.manager.settle_bet(bet_index=999, result=1)

    def test_get_total_exposure(self):
        """Test getting total portfolio exposure."""
        self.manager.place_bet(
            player_id="lebron-james",
            market="pts",
            line=25.5,
            odds_decimal=2.0,
            win_prob=0.60,
            side="over",
            book="draftkings",
        )
        exposure = self.manager.get_total_exposure()
        assert exposure > 0

    def test_get_market_exposure(self):
        """Test getting exposure for specific market."""
        self.manager.place_bet(
            player_id="lebron-james",
            market="pts",
            line=25.5,
            odds_decimal=2.0,
            win_prob=0.60,
            side="over",
            book="draftkings",
        )
        exposure = self.manager.get_market_exposure("pts")
        assert exposure > 0

    def test_get_market_exposure_zero(self):
        """Test getting exposure for market with no bets."""
        exposure = self.manager.get_market_exposure("reb")
        assert exposure == approx(0.0)

    def test_get_book_exposure(self):
        """Test getting exposure for specific book."""
        self.manager.place_bet(
            player_id="lebron-james",
            market="pts",
            line=25.5,
            odds_decimal=2.0,
            win_prob=0.60,
            side="over",
            book="draftkings",
        )
        exposure = self.manager.get_book_exposure("draftkings")
        assert exposure > 0

    def test_compute_portfolio_heat(self):
        """Test portfolio heat calculation."""
        heat = self.manager.compute_portfolio_heat()
        assert 0.0 <= heat <= 1.0

    def test_compute_concentration_risk(self):
        """Test concentration risk calculation."""
        risk = self.manager.compute_concentration_risk()
        assert 0.0 <= risk <= 1.0

    def test_compute_var(self):
        """Test Value at Risk calculation."""
        var = self.manager.compute_var()
        assert var >= 0

    def test_reset_daily_pnl(self):
        """Test daily P&L reset."""
        self.manager.daily_pnl = -500.0
        self.manager.reset_daily_pnl()
        assert self.manager.daily_pnl == approx(0.0)

    def test_get_portfolio_summary(self):
        """Test portfolio summary generation."""
        summary = self.manager.get_portfolio_summary()
        assert "bankroll" in summary
        assert "daily_pnl" in summary
        assert "total_exposure" in summary
        assert "pending_bets" in summary
        assert "win_rate" in summary
