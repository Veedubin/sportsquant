"""
Betting Engine - Core Bet Decision Logic

Adapted from sports_analytics.betting.engine
Changes: Replaced sports_analytics.betting.odds with local Odds class

This module provides the core bet decision logic for over/under betting
including expected value calculations and Kelly criterion.
"""

# pylint: disable=too-many-arguments,too-many-locals

import logging
import math
from dataclasses import dataclass
from typing import Final

from sportsquant.util.metrics import (
    BETTING_BETS_PLACED_TOTAL,
    BETTING_BETS_SETTLED_TOTAL,
    BETTING_EDGE_CALCULATIONS_TOTAL,
    BETTING_KELLY_RECOMMENDATIONS_TOTAL,
)

from .odds import Odds

logger = logging.getLogger(__name__)

DEFAULT_PROBABILITY: Final[float] = 0.5

__all__ = [
    "BetDecision",
    "expected_value",
    "kelly_fraction",
    "decide_over_under",
]


def _clamp_probability(value: float, *, fallback: float = DEFAULT_PROBABILITY) -> float:
    """Clamp a float to [0, 1] with a fallback for non-finite inputs."""
    try:
        val = float(value)
    except (TypeError, ValueError):
        val = fallback
    if not math.isfinite(val):
        val = fallback
    return float(max(0.0, min(1.0, val)))


def _detect_arbitrage(decimal_over: float, decimal_under: float) -> bool:
    """Detect whether the supplied decimal odds create an arbitrage opportunity."""
    if decimal_over <= 1.0 or decimal_under <= 1.0:
        return False
    implied_sum = (1.0 / decimal_over) + (1.0 / decimal_under)
    return implied_sum < 1.0


def _value_bet(true_prob: float, decimal_odds: float) -> float:
    """Compute the value bet metric on decimal odds."""
    if decimal_odds <= 0.0:
        raise ValueError("decimal odds must be positive")
    implied = 1.0 / decimal_odds
    return float(true_prob - implied)


@dataclass(frozen=True)
class BetDecision:
    """Represents a bet decision with all relevant metrics.

    Attributes:
        side: 'over' or 'under'
        line: The betting line (e.g., 10.5)
        p_win: Estimated probability of winning
        decimal_odds: Decimal odds (e.g., 1.91)
        ev: Expected value per $1 staked
        kelly_fraction: Recommended Kelly fraction (0-1)
    """

    side: str  # "over" or "under"
    line: float
    p_win: float
    decimal_odds: float
    ev: float
    kelly_fraction: float


def expected_value(_p: float, odds: Odds, true_prob: float) -> float:
    """Expected profit (per $1 staked) including value bet signal."""
    decimal = odds.to_decimal()
    value = _value_bet(true_prob, decimal)
    if value > 0:
        logger.info("Value bet detected: %s", value)
    return float(true_prob * (decimal - 1.0) - (1.0 - true_prob))


def kelly_fraction(p: float, odds: Odds, *, clamp: tuple[float, float] = (0.0, 1.0)) -> float:
    """Kelly criterion fraction for a binary bet."""
    decimal = odds.to_decimal()
    b = decimal - 1.0
    if b <= 0:
        return 0.0
    f = (p * b - (1.0 - p)) / b
    lo, hi = clamp
    return float(max(lo, min(hi, f)))


def decide_over_under(
    *,
    line: float,
    p_over: float,
    odds_over: Odds,
    odds_under: Odds,
    true_prob_over: float,
    true_prob_under: float,
) -> BetDecision:
    """Determine a decision between the over/under sides."""

    p_over_clamped = _clamp_probability(p_over)
    p_under = _clamp_probability(1.0 - p_over_clamped)
    true_prob_over = _clamp_probability(true_prob_over, fallback=p_over_clamped)
    true_prob_under = _clamp_probability(true_prob_under, fallback=p_under)

    decimal_over = odds_over.to_decimal()
    decimal_under = odds_under.to_decimal()

    if _detect_arbitrage(decimal_over, decimal_under):
        logger.warning("Arbitrage opportunity detected between over and under odds!")

    value_over = _value_bet(true_prob_over, decimal_over)
    value_under = _value_bet(true_prob_under, decimal_under)
    if value_over > 0:
        logger.info("Value bet detected on over: %s", value_over)
    if value_under > 0:
        logger.info("Value bet detected on under: %s", value_under)

    ev_over = expected_value(p_over_clamped, odds_over, true_prob_over)
    ev_under = expected_value(p_under, odds_under, true_prob_under)

    if ev_over >= ev_under:
        chosen_side = "over"
        chosen_odds = odds_over
        chosen_decimal = decimal_over
        chosen_ev = ev_over
        chosen_p = p_over_clamped
    else:
        chosen_side = "under"
        chosen_odds = odds_under
        chosen_decimal = decimal_under
        chosen_ev = ev_under
        chosen_p = p_under

    decision = BetDecision(
        side=chosen_side,
        line=line,
        p_win=chosen_p,
        decimal_odds=chosen_decimal,
        ev=chosen_ev,
        kelly_fraction=kelly_fraction(chosen_p, chosen_odds),
    )
    return decision


def record_bet_placed(market: str, bet_type: str = "single", success: bool = True) -> None:
    """Record a bet placement metric.

    Args:
        market: Market name (e.g., "nba", "nfl")
        bet_type: Type of bet (e.g., "single", "parlay")
        success: Whether the placement was successful
    """
    BETTING_BETS_PLACED_TOTAL.labels(
        market=market,
        bet_type=bet_type,
        status="success" if success else "error",
    ).inc()


def record_bet_settled(market: str, outcome: str) -> None:
    """Record a bet settlement metric.

    Args:
        market: Market name
        outcome: Bet outcome ("win", "loss", "push")
    """
    BETTING_BETS_SETTLED_TOTAL.labels(
        market=market,
        outcome=outcome,
    ).inc()


def record_edge_calculation(model: str, status: str = "success") -> None:
    """Record an edge calculation metric.

    Args:
        model: Model name
        status: Calculation status ("success", "error", "no_edge")
    """
    BETTING_EDGE_CALCULATIONS_TOTAL.labels(
        model=model,
        status=status,
    ).inc()


def record_kelly_recommendation(market: str, kelly_type: str) -> None:
    """Record a Kelly criterion recommendation metric.

    Args:
        market: Market name
        kelly_type: Type of Kelly calculation ("full", "fractional", "hedge", "none")
    """
    BETTING_KELLY_RECOMMENDATIONS_TOTAL.labels(
        market=market,
        kelly_type=kelly_type,
    ).inc()
