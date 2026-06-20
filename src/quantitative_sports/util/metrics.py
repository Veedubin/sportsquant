"""Metrics stubs for Quant-Sports.

Provides Prometheus-style metric objects as no-op counters for modules
that reference them. In production, replace with OpenTelemetry metrics
from quantitative_sports.util.telemetry.
"""

from __future__ import annotations

from typing import Any


class _NoOpCounter:
    """No-op counter that accepts all method calls silently."""

    def inc(self, amount: float = 1) -> None:
        pass

    def labels(self, **kwargs: Any) -> _NoOpCounter:
        return self

    def __call__(self, *args: Any, **kwargs: Any) -> _NoOpCounter:
        return self


class _NoOpGauge:
    """No-op gauge that accepts all method calls silently."""

    def set(self, value: float) -> None:
        pass

    def inc(self, amount: float = 1) -> None:
        pass

    def dec(self, amount: float = 1) -> None:
        pass

    def labels(self, **kwargs: Any) -> _NoOpGauge:
        return self


class _NoOpHistogram:
    """No-op histogram that accepts all method calls silently."""

    def observe(self, amount: float) -> None:
        pass

    def labels(self, **kwargs: Any) -> _NoOpHistogram:
        return self


# =============================================================================
# Betting Metrics
# =============================================================================

BETTING_BETS_PLACED_TOTAL: _NoOpCounter = _NoOpCounter()
BETTING_BETS_SETTLED_TOTAL: _NoOpCounter = _NoOpCounter()
BETTING_EDGE_CALCULATIONS_TOTAL: _NoOpCounter = _NoOpCounter()
BETTING_KELLY_RECOMMENDATIONS_TOTAL: _NoOpCounter = _NoOpCounter()

# =============================================================================
# Backtest Metrics
# =============================================================================

BACKTEST_ROI: _NoOpGauge = _NoOpGauge()
BACKTEST_PNL: _NoOpGauge = _NoOpGauge()
BACKTEST_WIN_RATE: _NoOpGauge = _NoOpGauge()
BACKTEST_N_BETS: _NoOpCounter = _NoOpCounter()
BACKTEST_SHARPE_RATIO: _NoOpGauge = _NoOpGauge()
BACKTEST_MAX_DRAWDOWN: _NoOpGauge = _NoOpGauge()
BACKTEST_AVG_ODDS: _NoOpGauge = _NoOpGauge()
BACKTEST_KELLY_FRACTION: _NoOpGauge = _NoOpGauge()
BACKTEST_TURNOVER: _NoOpGauge = _NoOpGauge()

# =============================================================================
# Poller Metrics
# =============================================================================

POLLER_REQUESTS_TOTAL: _NoOpCounter = _NoOpCounter()
POLLER_ERRORS_TOTAL: _NoOpCounter = _NoOpCounter()
POLLER_LATENCY: _NoOpHistogram = _NoOpHistogram()
POLLER_ACTIVE_LEAGUES: _NoOpGauge = _NoOpGauge()

# =============================================================================
# Pipeline Metrics
# =============================================================================

PIPELINE_MESSAGES_PRODUCED: _NoOpCounter = _NoOpCounter()
PIPELINE_MESSAGES_CONSUMED: _NoOpCounter = _NoOpCounter()
PIPELINE_CONSUMER_LAG: _NoOpGauge = _NoOpGauge()
PIPELINE_ERRORS_TOTAL: _NoOpCounter = _NoOpCounter()

__all__ = [
    "BETTING_BETS_PLACED_TOTAL",
    "BETTING_BETS_SETTLED_TOTAL",
    "BETTING_EDGE_CALCULATIONS_TOTAL",
    "BETTING_KELLY_RECOMMENDATIONS_TOTAL",
    "BACKTEST_ROI",
    "BACKTEST_PNL",
    "BACKTEST_WIN_RATE",
    "BACKTEST_N_BETS",
    "BACKTEST_SHARPE_RATIO",
    "BACKTEST_MAX_DRAWDOWN",
    "BACKTEST_AVG_ODDS",
    "BACKTEST_KELLY_FRACTION",
    "BACKTEST_TURNOVER",
    "POLLER_REQUESTS_TOTAL",
    "POLLER_ERRORS_TOTAL",
    "POLLER_LATENCY",
    "POLLER_ACTIVE_LEAGUES",
    "PIPELINE_MESSAGES_PRODUCED",
    "PIPELINE_MESSAGES_CONSUMED",
    "PIPELINE_CONSUMER_LAG",
    "PIPELINE_ERRORS_TOTAL",
]
