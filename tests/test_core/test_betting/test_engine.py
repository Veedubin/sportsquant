"""Tests for betting engine — EV calculation, arbitrage detection, BetDecision (new)."""

import pytest

from sportsquant.core.betting.engine import (
    BetDecision,
    BetResult,
    calculate_ev,
    detect_arbitrage,
)


class TestCalculateEV:
    """Tests for EV calculation."""

    def test_positive_ev(self):
        """Test positive expected value calculation."""
        # 60% win prob at -110 odds (1.909 decimal)
        # EV = 0.6 * 0.909 - 0.4 = 0.1454
        ev = calculate_ev(probability=0.60, odds=-110)
        assert ev > 0
        assert ev == pytest.approx(0.1454, abs=0.01)

    def test_negative_ev(self):
        """Test negative expected value calculation."""
        # 45% win prob at -110 odds
        ev = calculate_ev(probability=0.45, odds=-110)
        assert ev < 0

    def test_breakeven_ev(self):
        """Test breakeven EV (approximately 0)."""
        # 52.38% win prob at -110 odds (breakeven)
        ev = calculate_ev(probability=0.5238, odds=-110)
        assert ev == pytest.approx(0.0, abs=0.01)

    def test_ev_with_decimal_odds(self):
        """Test EV with decimal odds input."""
        ev = calculate_ev(probability=0.60, odds=2.0)
        assert ev == pytest.approx(0.20, abs=0.01)

    def test_ev_with_positive_odds(self):
        """Test EV with positive American odds."""
        # 40% win prob at +150 odds (2.5 decimal)
        # EV = 0.4 * 1.5 - 0.6 = 0.0
        ev = calculate_ev(probability=0.40, odds=150)
        assert ev == pytest.approx(0.0, abs=0.01)

    def test_ev_certainty(self):
        """Test EV with 100% probability."""
        ev = calculate_ev(probability=1.0, odds=-110)
        assert ev == pytest.approx(0.909, abs=0.01)

    def test_ev_impossible(self):
        """Test EV with 0% probability."""
        ev = calculate_ev(probability=0.0, odds=-110)
        assert ev == pytest.approx(-1.0, abs=0.01)


class TestDetectArbitrage:
    """Tests for arbitrage detection."""

    def test_no_arbitrage(self):
        """Test no arbitrage in a normal market."""
        # Standard market: over -110, under -110
        # Total implied prob = 0.5238 + 0.5238 = 1.0476 > 1.0
        arb = detect_arbitrage(odds_over=-110, odds_under=-110)
        assert arb is None or arb.get("arb_percent", 0) <= 0

    def test_arbitrage_opportunity(self):
        """Test arbitrage detection with a real opportunity."""
        # Over at +105, Under at +105
        # Total implied prob = 0.4878 + 0.4878 = 0.9756 < 1.0
        arb = detect_arbitrage(odds_over=105, odds_under=105)
        assert arb is not None
        assert arb.get("arb_percent", 0) > 0

    def test_arbitrage_calculation(self):
        """Test arbitrage percentage calculation."""
        arb = detect_arbitrage(odds_over=100, odds_under=100)
        if arb:
            # Both at +100 (2.0 decimal), total implied = 0.5 + 0.5 = 1.0
            # No arbitrage
            assert arb.get("arb_percent", 0) == pytest.approx(0.0, abs=0.01)

    def test_arbitrage_stake_calculation(self):
        """Test arbitrage stake allocation."""
        arb = detect_arbitrage(odds_over=105, odds_under=105, total_stake=1000)
        if arb and arb.get("arb_percent", 0) > 0:
            assert "stake_over" in arb
            assert "stake_under" in arb
            assert abs(arb["stake_over"] + arb["stake_under"] - 1000) < 1

    def test_arbitrage_extreme(self):
        """Test extreme arbitrage scenario."""
        # Over at +200, Under at +200 (very unlikely but tests math)
        arb = detect_arbitrage(odds_over=200, odds_under=200)
        if arb:
            assert arb.get("arb_percent", 0) > 0


class TestBetDecision:
    """Tests for BetDecision model."""

    def test_bet_decision_creation(self):
        """Test creating a BetDecision."""
        decision = BetDecision(
            player_name="LeBron James",
            stat_type="Points",
            line=25.5,
            side="OVER",
            odds=-110,
            ev=0.15,
            stake=100.0,
            confidence=0.75,
        )
        assert decision.player_name == "LeBron James"
        assert decision.ev == 0.15
        assert decision.stake == 100.0

    def test_bet_decision_expected_profit(self):
        """Test expected profit calculation."""
        decision = BetDecision(
            player_name="Test",
            stat_type="Points",
            line=10.5,
            side="OVER",
            odds=-110,
            ev=0.10,
            stake=100.0,
            confidence=0.60,
        )
        # Expected profit = stake * ev = 100 * 0.10 = 10
        assert decision.expected_profit == pytest.approx(10.0, abs=0.01)

    def test_bet_decision_negative_ev(self):
        """Test BetDecision with negative EV."""
        decision = BetDecision(
            player_name="Test",
            stat_type="Points",
            line=10.5,
            side="OVER",
            odds=-110,
            ev=-0.05,
            stake=0.0,
            confidence=0.40,
        )
        assert decision.expected_profit < 0

    def test_bet_decision_to_dict(self):
        """Test BetDecision serialization."""
        decision = BetDecision(
            player_name="Test",
            stat_type="Points",
            line=10.5,
            side="OVER",
            odds=-110,
            ev=0.10,
            stake=50.0,
            confidence=0.65,
        )
        d = decision.to_dict()
        assert d["player_name"] == "Test"
        assert d["ev"] == 0.10
        assert d["stake"] == 50.0


class TestBetResult:
    """Tests for BetResult model."""

    def test_bet_result_win(self):
        """Test winning bet result."""
        result = BetResult(
            decision=BetDecision(
                player_name="Test",
                stat_type="Points",
                line=10.5,
                side="OVER",
                odds=-110,
                ev=0.10,
                stake=100.0,
                confidence=0.60,
            ),
            outcome="win",
            actual_stat=15.0,
            profit=90.9,
        )
        assert result.outcome == "win"
        assert result.profit == 90.9

    def test_bet_result_loss(self):
        """Test losing bet result."""
        result = BetResult(
            decision=BetDecision(
                player_name="Test",
                stat_type="Points",
                line=10.5,
                side="OVER",
                odds=-110,
                ev=0.10,
                stake=100.0,
                confidence=0.60,
            ),
            outcome="loss",
            actual_stat=5.0,
            profit=-100.0,
        )
        assert result.outcome == "loss"
        assert result.profit == -100.0

    def test_bet_result_push(self):
        """Test push result."""
        result = BetResult(
            decision=BetDecision(
                player_name="Test",
                stat_type="Points",
                line=10.5,
                side="OVER",
                odds=-110,
                ev=0.10,
                stake=100.0,
                confidence=0.60,
            ),
            outcome="push",
            actual_stat=10.5,
            profit=0.0,
        )
        assert result.outcome == "push"
        assert result.profit == 0.0
