"""Tests for performance metrics factory."""

from __future__ import annotations

from quantitative_sports.core.betting.metrics import empty_performance_metrics


def test_empty_performance_metrics_returns_zero_metrics() -> None:
    """Factory returns a PerformanceMetrics with all numeric fields zeroed."""
    metrics = empty_performance_metrics()
    assert metrics.core.total_bets == 0
    assert metrics.core.win_rate == 0.0
    assert metrics.core.total_pnl == 0.0
    assert metrics.risk_adjusted.sharpe_ratio == 0.0
    assert metrics.risk_adjusted.profit_factor == 0.0
    assert metrics.drawdown.max_drawdown == 0.0
    assert metrics.drawdown.max_drawdown_duration == 0
    assert metrics.streaks.max_win_streak == 0
    assert metrics.streaks.max_loss_streak == 0
    assert metrics.streaks.current_streak == 0
    assert metrics.streaks.current_streak_type == "none"


def test_empty_performance_metrics_to_dict_renders_cleanly() -> None:
    """Output of to_dict() is JSON-serializable (used by StrategyRegistry)."""
    import json

    metrics = empty_performance_metrics()
    as_dict = metrics.to_dict()
    json.dumps(as_dict)  # must not raise
    # to_dict() flattens nested dataclasses
    assert as_dict["total_bets"] == 0
    assert as_dict["max_win_streak"] == 0
    assert as_dict["total_return_pct"] == 0.0
