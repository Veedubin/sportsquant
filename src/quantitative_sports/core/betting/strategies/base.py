"""
Base classes and interfaces for betting strategies.

Defines the strategy pattern for pluggable betting approaches.
"""

# pylint: disable=too-many-instance-attributes

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class BetDecision:
    """Decision to place a bet or skip."""

    should_bet: bool
    side: str  # "over", "under", or "skip"
    stake: float  # Bet size in currency units
    reason: str  # Human-readable explanation


def make_bet_decision(*, side: str, stake: float, reason: str) -> BetDecision:
    """Helper for constructing a bet decision with should_bet=True."""
    return BetDecision(should_bet=True, side=side, stake=stake, reason=reason)


@dataclass(frozen=True)
class BettingOpportunity:
    """Information about a betting opportunity."""

    line: float
    p_over: float  # Predicted probability of over
    p_under: float  # Predicted probability of under (typically 1 - p_over)
    odds_over_decimal: float
    odds_under_decimal: float
    ev_over: float  # Expected value for over bet
    ev_under: float  # Expected value for under bet
    kelly_over: float  # Kelly fraction for over
    kelly_under: float  # Kelly fraction for under

    # Optional context
    player_id: Optional[int] = None
    player_name: Optional[str] = None
    game_date: Optional[str] = None


class BettingStrategy(ABC):
    """
    Abstract base class for betting strategies.

    Strategies decide whether to bet, which side to bet, and how much to stake.
    """

    def __init__(self, name: str, bankroll: float = 1000.0):
        """
        Initialize strategy.

        Args:
            name: Strategy identifier
            bankroll: Available bankroll for sizing bets
        """
        self._name = name
        self._bankroll = bankroll

    @property
    def name(self) -> str:
        """Strategy identifier."""
        return self._name

    @property
    def bankroll(self) -> float:
        """Current bankroll."""
        return self._bankroll

    def update_bankroll(self, amount: float) -> None:
        """Update bankroll after a bet result."""
        self._bankroll += amount

    @abstractmethod
    def evaluate_opportunity(self, opportunity: BettingOpportunity) -> BetDecision:
        """
        Evaluate a betting opportunity and make a decision.

        Args:
            opportunity: Information about the betting opportunity

        Returns:
            BetDecision with action to take
        """
        raise NotImplementedError(f"{self.__class__.__name__} must implement evaluate_bet")

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r}, bankroll={self.bankroll:.2f})"
