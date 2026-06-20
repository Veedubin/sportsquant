"""Tests for backtesting framework (migrated from sports-bet)."""

from datetime import date

import pytest

from quantitative_sports.models.analysis.backtest import (
    BacktestEngine,
)
from quantitative_sports.models.analysis.backtest_result import BacktestResult
from quantitative_sports.models.analysis.parameter_sweep import ParameterSweep, summarize_sweep_results
from quantitative_sports.models.analysis.strategies import Strategy, StrategyLibrary


# =============================================================================
# Strategy Tests
# =============================================================================


class TestStrategy:
    """Tests for Strategy class."""

    def test_should_bet_ev_threshold(self):
        """Test EV threshold filtering."""
        strategy = Strategy(name="test", min_ev=0.10)

        assert strategy.should_bet(
            ev=0.15, confidence=50, odds=-110, site="prizepicks", stat_type="pts"
        )
        assert not strategy.should_bet(
            ev=0.05, confidence=50, odds=-110, site="prizepicks", stat_type="pts"
        )

    def test_should_bet_confidence_threshold(self):
        """Test confidence threshold filtering."""
        strategy = Strategy(name="test", min_confidence=60)

        assert strategy.should_bet(
            ev=0.10, confidence=70, odds=-110, site="prizepicks", stat_type="pts"
        )
        assert not strategy.should_bet(
            ev=0.10, confidence=50, odds=-110, site="prizepicks", stat_type="pts"
        )

    def test_should_bet_odds_limit(self):
        """Test maximum odds filtering."""
        strategy = Strategy(name="test", max_odds=200)

        assert strategy.should_bet(
            ev=0.10, confidence=50, odds=150, site="prizepicks", stat_type="pts"
        )
        assert not strategy.should_bet(
            ev=0.10, confidence=50, odds=300, site="prizepicks", stat_type="pts"
        )

    def test_should_bet_site_filter(self):
        """Test site filtering."""
        strategy = Strategy(name="test", sites=["prizepicks", "underdog"])

        assert strategy.should_bet(
            ev=0.10, confidence=50, odds=-110, site="prizepicks", stat_type="pts"
        )
        assert strategy.should_bet(
            ev=0.10, confidence=50, odds=-110, site="underdog", stat_type="pts"
        )
        assert not strategy.should_bet(
            ev=0.10, confidence=50, odds=-110, site="draftkings", stat_type="pts"
        )

    def test_should_bet_stat_filter(self):
        """Test stat type filtering."""
        strategy = Strategy(name="test", stats=["Points", "Rebounds"])

        assert strategy.should_bet(
            ev=0.10, confidence=50, odds=-110, site="prizepicks", stat_type="Points"
        )
        assert strategy.should_bet(
            ev=0.10, confidence=50, odds=-110, site="prizepicks", stat_type="Rebounds"
        )
        assert not strategy.should_bet(
            ev=0.10, confidence=50, odds=-110, site="prizepicks", stat_type="Assists"
        )

    def test_flat_stake_calculation(self):
        """Test flat stake calculation."""
        strategy = Strategy(name="test", stake_method="flat", flat_stake=25.0)

        stake = strategy.calculate_stake(bankroll=10000, probability=0.55, odds=-110)
        assert stake == 25.0

    def test_kelly_stake_calculation(self):
        """Test Kelly criterion stake calculation."""
        strategy = Strategy(name="test", stake_method="kelly", kelly_fraction=0.25)

        # For -110 odds (1.909 decimal), 55% probability
        # Kelly = (0.909 * 0.55 - 0.45) / 0.909 = 0.04995
        # Quarter Kelly = 0.0125
        stake = strategy.calculate_stake(bankroll=10000, probability=0.55, odds=-110)
        assert 0 < stake < 200  # Should be positive but reasonable

    def test_kelly_with_negative_ev(self):
        """Test Kelly returns 0 for negative EV."""
        strategy = Strategy(name="test", stake_method="kelly", kelly_fraction=0.25)

        # For -110 odds, 45% probability (negative EV)
        stake = strategy.calculate_stake(bankroll=10000, probability=0.45, odds=-110)
        assert stake == 0.0


class TestStrategyLibrary:
    """Tests for StrategyLibrary pre-built strategies."""

    def test_conservative_strategy(self):
        """Test conservative strategy parameters."""
        strategy = StrategyLibrary.conservative()

        assert strategy.name == "conservative"
        assert strategy.min_ev == 0.15
        assert strategy.min_confidence == 60
        assert strategy.stake_method == "flat"

    def test_aggressive_strategy(self):
        """Test aggressive strategy parameters."""
        strategy = StrategyLibrary.aggressive()

        assert strategy.name == "aggressive"
        assert strategy.min_ev == 0.0
        assert strategy.min_confidence == 0.0
        assert strategy.stake_method == "kelly"

    def test_elite_only_strategy(self):
        """Test elite only strategy parameters."""
        strategy = StrategyLibrary.elite_only()

        assert strategy.name == "elite_only"
        assert strategy.min_ev == 0.20
        assert strategy.min_confidence == 70
        assert strategy.flat_stake == 25.0

    def test_custom_strategy(self):
        """Test custom strategy creation."""
        strategy = StrategyLibrary.custom(
            name="my_strategy",
            min_ev=0.08,
            min_confidence=55,
            sites=["prizepicks"],
            flat_stake=20.0,
        )

        assert strategy.name == "my_strategy"
        assert strategy.min_ev == 0.08
        assert strategy.min_confidence == 55
        assert strategy.sites == ["prizepicks"]
        assert strategy.flat_stake == 20.0


# =============================================================================
# BacktestResult Tests
# =============================================================================


class TestBacktestResult:
    """Tests for BacktestResult calculations."""

    def test_empty_results(self):
        """Test backtest with no bets."""
        strategy = Strategy(name="test")
        result = BacktestResult.calculate(
            strategy=strategy,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            bets=[],
        )

        assert result.total_bets == 0
        assert result.wins == 0
        assert result.losses == 0
        assert result.total_profit == 0.0
        assert result.roi_percent == 0.0

    def test_all_wins(self):
        """Test backtest with all winning bets."""
        strategy = Strategy(name="test", flat_stake=10.0)
        bets = [
            {"stake": 10, "profit": 9.09, "odds": -110, "outcome": "win", "date": "2024-01-01"},
            {"stake": 10, "profit": 9.09, "odds": -110, "outcome": "win", "date": "2024-01-02"},
        ]

        result = BacktestResult.calculate(
            strategy=strategy,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            bets=bets,
        )

        assert result.total_bets == 2
        assert result.wins == 2
        assert result.losses == 0
        assert result.win_rate == 1.0
        assert result.total_profit > 0

    def test_all_losses(self):
        """Test backtest with all losing bets."""
        strategy = Strategy(name="test", flat_stake=10.0)
        bets = [
            {"stake": 10, "profit": -10, "odds": -110, "outcome": "loss", "date": "2024-01-01"},
            {"stake": 10, "profit": -10, "odds": -110, "outcome": "loss", "date": "2024-01-02"},
        ]

        result = BacktestResult.calculate(
            strategy=strategy,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            bets=bets,
        )

        assert result.total_bets == 2
        assert result.wins == 0
        assert result.losses == 2
        assert result.win_rate == 0.0
        assert result.total_profit == -20.0

    def test_mixed_outcomes(self):
        """Test backtest with mixed outcomes."""
        strategy = Strategy(name="test", flat_stake=10.0)
        bets = [
            {"stake": 10, "profit": 9.09, "odds": -110, "outcome": "win", "date": "2024-01-01"},
            {"stake": 10, "profit": -10, "odds": -110, "outcome": "loss", "date": "2024-01-02"},
            {"stake": 10, "profit": 0, "odds": -110, "outcome": "push", "date": "2024-01-03"},
        ]

        result = BacktestResult.calculate(
            strategy=strategy,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            bets=bets,
        )

        assert result.total_bets == 3
        assert result.wins == 1
        assert result.losses == 1
        assert result.pushes == 1
        assert result.win_rate == pytest.approx(1 / 3, rel=0.01)
        assert result.total_profit == pytest.approx(-0.91, rel=0.01)

    def test_roi_calculation(self):
        """Test ROI percentage calculation."""
        strategy = Strategy(name="test", flat_stake=10.0)
        bets = [
            {"stake": 100, "profit": 50, "odds": -200, "outcome": "win", "date": "2024-01-01"},
        ]

        result = BacktestResult.calculate(
            strategy=strategy,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            bets=bets,
        )

        assert result.roi_percent == 50.0

    def test_profit_timeline(self):
        """Test cumulative profit timeline calculation."""
        strategy = Strategy(name="test", flat_stake=10.0)
        bets = [
            {"stake": 10, "profit": 10, "odds": -110, "outcome": "win", "date": "2024-01-01"},
            {"stake": 10, "profit": -5, "odds": -110, "outcome": "loss", "date": "2024-01-02"},
            {"stake": 10, "profit": 15, "odds": -110, "outcome": "win", "date": "2024-01-03"},
        ]

        result = BacktestResult.calculate(
            strategy=strategy,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            bets=bets,
        )

        assert len(result.profit_over_time) == 3
        assert result.profit_over_time[0]["cumulative_profit"] == 10
        assert result.profit_over_time[1]["cumulative_profit"] == 5
        assert result.profit_over_time[2]["cumulative_profit"] == 20

    def test_max_drawdown(self):
        """Test maximum drawdown calculation."""
        strategy = Strategy(name="test", flat_stake=10.0)
        bets = [
            {"stake": 10, "profit": 100, "odds": -110, "outcome": "win", "date": "2024-01-01"},
            {"stake": 10, "profit": -50, "odds": -110, "outcome": "loss", "date": "2024-01-02"},
            {"stake": 10, "profit": -30, "odds": -110, "outcome": "loss", "date": "2024-01-03"},
            {"stake": 10, "profit": 20, "odds": -110, "outcome": "win", "date": "2024-01-04"},
        ]

        result = BacktestResult.calculate(
            strategy=strategy,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            bets=bets,
        )

        # Max drawdown should be 80 (from 100 peak to 20 trough)
        assert result.max_drawdown == 80.0

    def test_to_dict(self):
        """Test dict serialization."""
        strategy = Strategy(name="test", min_ev=0.10)
        result = BacktestResult(
            strategy=strategy,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            total_bets=5,
            wins=3,
            losses=2,
            pushes=0,
            total_stake=50.0,
            total_profit=10.0,
            roi_percent=20.0,
            win_rate=0.6,
            sharpe_ratio=1.5,
            max_drawdown=25.0,
            avg_odds=-110,
        )

        result_dict = result.to_dict()

        assert result_dict["strategy_name"] == "test"
        assert result_dict["total_bets"] == 5
        assert result_dict["wins"] == 3
        assert result_dict["losses"] == 2
        assert result_dict["roi_percent"] == 20.0


# =============================================================================
# BacktestEngine Tests
# =============================================================================


class TestBacktestEngine:
    """Tests for BacktestEngine."""

    def test_in_date_range(self):
        """Test date range filtering."""
        engine = BacktestEngine(
            strategy=Strategy(name="test"),
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        )

        assert engine._in_date_range(date(2024, 1, 15))
        assert engine._in_date_range(date(2024, 1, 1))
        assert engine._in_date_range(date(2024, 1, 31))
        assert not engine._in_date_range(date(2023, 12, 31))
        assert not engine._in_date_range(date(2024, 2, 1))
        assert not engine._in_date_range(None)

    def test_meets_strategy_criteria(self):
        """Test strategy criteria filtering."""
        strategy = Strategy(name="test", min_ev=0.10, min_confidence=50)
        engine = BacktestEngine(
            strategy=strategy,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        )

        good_proj = {
            "ev": 0.15,
            "confidence": 60,
            "odds": -110,
            "site": "prizepicks",
            "stat_type": "pts",
        }
        bad_ev = {
            "ev": 0.05,
            "confidence": 60,
            "odds": -110,
            "site": "prizepicks",
            "stat_type": "pts",
        }
        bad_conf = {
            "ev": 0.15,
            "confidence": 40,
            "odds": -110,
            "site": "prizepicks",
            "stat_type": "pts",
        }

        assert engine._meets_strategy_criteria(good_proj)
        assert not engine._meets_strategy_criteria(bad_ev)
        assert not engine._meets_strategy_criteria(bad_conf)

    def test_simulate_outcome_with_actual_results(self):
        """Test outcome simulation with actual results."""
        engine = BacktestEngine(
            strategy=Strategy(name="test"),
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        )

        # Test OVER bet that won
        projection = {
            "player_name": "Test Player",
            "stat_type": "Points",
            "line_score": 25.5,
            "recommendation": "OVER",
            "model_prob": 0.60,
            "game_date": date(2024, 1, 15),
        }
        actual_results = {("Test Player", "Points", date(2024, 1, 15)): {"actual_stat": 28.0}}

        outcome, actual = engine._simulate_outcome(projection, actual_results)
        assert outcome == "win"
        assert actual == 28.0

        # Test UNDER bet that lost
        projection["recommendation"] = "UNDER"
        outcome, actual = engine._simulate_outcome(projection, actual_results)
        assert outcome == "loss"

        # Test push
        projection["recommendation"] = "OVER"
        actual_results = {("Test Player", "Points", date(2024, 1, 15)): {"actual_stat": 25.5}}
        outcome, actual = engine._simulate_outcome(projection, actual_results)
        assert outcome == "push"

    def test_simulate_outcome_monte_carlo(self):
        """Test Monte Carlo simulation when no actual results."""
        engine = BacktestEngine(
            strategy=Strategy(name="test"),
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        )

        projection = {
            "player_name": "Test Player",
            "stat_type": "Points",
            "line_score": 25.5,
            "recommendation": "OVER",
            "model_prob": 0.70,  # 70% win rate
            "game_date": date(2024, 1, 15),
        }

        # Run many simulations to verify Monte Carlo approximates model probability
        wins = 0
        trials = 1000
        for _ in range(trials):
            outcome, _ = engine._simulate_outcome(projection, None)
            if outcome == "win":
                wins += 1

        # Should be approximately 70%
        win_rate = wins / trials
        assert 0.65 < win_rate < 0.75

    def test_calculate_profit(self):
        """Test profit calculation."""
        engine = BacktestEngine(
            strategy=Strategy(name="test"),
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        )

        # Win with -110 odds
        profit = engine._calculate_profit("win", 10, -110)
        assert profit == pytest.approx(9.09, rel=0.01)

        # Loss
        profit = engine._calculate_profit("loss", 10, -110)
        assert profit == -10

        # Push
        profit = engine._calculate_profit("push", 10, -110)
        assert profit == 0

        # Win with +150 odds
        profit = engine._calculate_profit("win", 10, 150)
        assert profit == 15.0


# =============================================================================
# ParameterSweep Tests
# =============================================================================


class TestParameterSweep:
    """Tests for ParameterSweep."""

    @pytest.mark.asyncio
    async def test_sweep_ev_threshold(self):
        """Test EV threshold sweep."""
        base_strategy = Strategy(name="test", min_ev=0.05, min_confidence=50)
        projections = [
            {
                "ev": 0.03,
                "confidence": 60,
                "odds": -110,
                "site": "prizepicks",
                "stat_type": "pts",
                "line_score": 25.5,
                "player_name": "Player 1",
                "model_prob": 0.55,
                "recommendation": "OVER",
                "game_date": date(2024, 1, 1),
            },
            {
                "ev": 0.08,
                "confidence": 60,
                "odds": -110,
                "site": "prizepicks",
                "stat_type": "pts",
                "line_score": 25.5,
                "player_name": "Player 2",
                "model_prob": 0.55,
                "recommendation": "OVER",
                "game_date": date(2024, 1, 2),
            },
            {
                "ev": 0.12,
                "confidence": 60,
                "odds": -110,
                "site": "prizepicks",
                "stat_type": "pts",
                "line_score": 25.5,
                "player_name": "Player 3",
                "model_prob": 0.55,
                "recommendation": "OVER",
                "game_date": date(2024, 1, 3),
            },
            {
                "ev": 0.18,
                "confidence": 60,
                "odds": -110,
                "site": "prizepicks",
                "stat_type": "pts",
                "line_score": 25.5,
                "player_name": "Player 4",
                "model_prob": 0.55,
                "recommendation": "OVER",
                "game_date": date(2024, 1, 4),
            },
        ]

        sweep = ParameterSweep(base_strategy=base_strategy, projections=projections)
        results = await sweep.sweep_ev_threshold(start=0.0, end=0.15, step=0.05)

        assert len(results) == 4  # 0%, 5%, 10%, 15%

        # EV=0% should have all 4 bets
        assert results[0].total_bets == 4
        # EV=5% should have 3 bets (excluding the 3% one)
        assert results[1].total_bets == 3
        # EV=10% should have 2 bets
        assert results[2].total_bets == 2
        # EV=15% should have 1 bet
        assert results[3].total_bets == 1

    @pytest.mark.asyncio
    async def test_sweep_confidence(self):
        """Test confidence threshold sweep."""
        base_strategy = Strategy(name="test", min_ev=0.0, min_confidence=50)
        projections = [
            {
                "ev": 0.10,
                "confidence": 30,
                "odds": -110,
                "site": "prizepicks",
                "stat_type": "pts",
                "line_score": 25.5,
                "player_name": "Player 1",
                "model_prob": 0.55,
                "recommendation": "OVER",
                "game_date": date(2024, 1, 1),
            },
            {
                "ev": 0.10,
                "confidence": 50,
                "odds": -110,
                "site": "prizepicks",
                "stat_type": "pts",
                "line_score": 25.5,
                "player_name": "Player 2",
                "model_prob": 0.55,
                "recommendation": "OVER",
                "game_date": date(2024, 1, 2),
            },
            {
                "ev": 0.10,
                "confidence": 70,
                "odds": -110,
                "site": "prizepicks",
                "stat_type": "pts",
                "line_score": 25.5,
                "player_name": "Player 3",
                "model_prob": 0.55,
                "recommendation": "OVER",
                "game_date": date(2024, 1, 3),
            },
        ]

        sweep = ParameterSweep(base_strategy=base_strategy, projections=projections)
        # Use step=30 to get: 0, 30, 60, 90
        results = await sweep.sweep_confidence(start=0, end=100, step=30)

        assert len(results) == 4  # 0%, 30%, 60%, 90%
        assert results[0].total_bets == 3  # All pass 0% threshold
        assert results[1].total_bets == 3  # 30, 50, 70 all pass >= 30% threshold
        assert results[2].total_bets == 1  # Only 70 passes >= 60% threshold
        assert results[3].total_bets == 0  # Nothing passes >= 90% threshold

    @pytest.mark.asyncio
    async def test_sweep_stake_size(self):
        """Test stake size sweep."""
        base_strategy = Strategy(name="test", min_ev=0.0, min_confidence=0)
        projections = [
            {
                "ev": 0.10,
                "confidence": 60,
                "odds": -110,
                "site": "prizepicks",
                "stat_type": "pts",
                "line_score": 25.5,
                "player_name": "Player 1",
                "model_prob": 0.55,
                "recommendation": "OVER",
                "game_date": date(2024, 1, 1),
            },
        ]

        sweep = ParameterSweep(base_strategy=base_strategy, projections=projections)
        results = await sweep.sweep_stake_size(sizes=[10, 25, 50])

        assert len(results) == 3
        assert results[0].total_stake == 10.0
        assert results[1].total_stake == 25.0
        assert results[2].total_stake == 50.0


def test_summarize_sweep_results():
    """Test sweep results summarization."""
    strategies = [
        Strategy(name="s1"),
        Strategy(name="s2"),
        Strategy(name="s3"),
    ]

    results = [
        BacktestResult(
            strategy=strategies[0],
            start_date=date.today(),
            end_date=date.today(),
            total_bets=10,
            total_profit=5,
            roi_percent=50,
            sharpe_ratio=1.0,
        ),
        BacktestResult(
            strategy=strategies[1],
            start_date=date.today(),
            end_date=date.today(),
            total_bets=20,
            total_profit=20,
            roi_percent=100,
            sharpe_ratio=2.0,
        ),
        BacktestResult(
            strategy=strategies[2],
            start_date=date.today(),
            end_date=date.today(),
            total_bets=5,
            total_profit=-10,
            roi_percent=-200,
            sharpe_ratio=-0.5,
        ),
    ]

    summary = summarize_sweep_results(results)

    assert summary["total_strategies_tested"] == 3
    assert summary["best_roi"]["strategy"] == "s2"
    assert summary["best_sharpe"]["strategy"] == "s2"
    assert summary["best_profit"]["strategy"] == "s2"
    assert summary["most_bets"]["strategy"] == "s2"
