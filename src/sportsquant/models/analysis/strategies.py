"""Strategy framework for betting strategies.

This module defines the Strategy dataclass and StrategyLibrary with
pre-built strategies for backtesting.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Strategy:
    """Defines a betting strategy with configurable parameters.

    Attributes:
        name: Strategy name for identification
        min_ev: Minimum EV percentage to bet (e.g., 0.05 = 5% EV)
        min_confidence: Minimum confidence score (0-100)
        max_odds: Maximum American odds to bet on
        sites: List of site names to bet on (None = all sites)
        stats: List of stat types to bet on (None = all stats)
        stake_method: "flat" for fixed stake, "kelly" for Kelly criterion
        flat_stake: Fixed stake amount when using flat staking
        kelly_fraction: Fraction of Kelly to use (0.25 = quarter Kelly)
    """

    name: str
    min_ev: float = 0.0
    min_confidence: float = 0.0
    max_odds: int = 1000
    sites: Optional[list[str]] = None
    stats: Optional[list[str]] = None
    stake_method: str = "flat"
    flat_stake: float = 10.0
    kelly_fraction: float = 0.25

    def should_bet(
        self,
        ev: float,
        confidence: float,
        odds: int,
        site: str,
        stat_type: str,
    ) -> bool:
        """Check if a prop meets strategy criteria.

        Args:
            ev: Expected value as decimal (e.g., 0.10 for 10% EV)
            confidence: Confidence score (0-100)
            odds: American odds
            site: Site name
            stat_type: Stat type

        Returns:
            True if this prop meets all strategy filters
        """
        # Check EV threshold
        if ev < self.min_ev:
            return False

        # Check confidence threshold
        if confidence < self.min_confidence:
            return False

        # Check odds limit
        if odds > self.max_odds:
            return False

        # Check site filter
        if self.sites is not None and site not in self.sites:
            return False

        # Check stat filter
        if self.stats is not None and stat_type not in self.stats:
            return False

        return True

    def calculate_stake(
        self,
        bankroll: float,
        probability: float,
        odds: int,
    ) -> float:
        """Calculate stake amount based on staking method.

        Args:
            bankroll: Total bankroll
            probability: Win probability
            odds: American odds

        Returns:
            Stake amount
        """
        if self.stake_method == "kelly":
            # Convert American odds to decimal
            if odds >= 0:
                decimal_odds = (odds / 100) + 1
            else:
                decimal_odds = (100 / abs(odds)) + 1

            # Kelly formula: f* = (bp - q) / b
            b = decimal_odds - 1
            p = probability
            q = 1 - p

            kelly = (b * p - q) / b
            if kelly <= 0:
                return 0.0

            # Apply fractional Kelly
            return bankroll * kelly * self.kelly_fraction

        # Flat stake
        return self.flat_stake


class StrategyLibrary:
    """Pre-built strategies for common betting approaches."""

    @staticmethod
    def conservative() -> Strategy:
        """Only bet high EV + high confidence plays.

        Use when: Minimizing variance, preserving bankroll
        Criteria: EV > 15%, Confidence > 60%
        """
        return Strategy(
            name="conservative",
            min_ev=0.15,
            min_confidence=60,
            stake_method="flat",
            flat_stake=10.0,
        )

    @staticmethod
    def moderate() -> Strategy:
        """Bet positive EV with moderate confidence.

        Use when: Balanced approach
        Criteria: EV > 5%, Confidence > 50%
        """
        return Strategy(
            name="moderate",
            min_ev=0.05,
            min_confidence=50,
            stake_method="flat",
            flat_stake=10.0,
        )

    @staticmethod
    def aggressive() -> Strategy:
        """Bet any positive EV.

        Use when: Maximizing action, accepting variance
        Criteria: EV > 0%, any confidence
        """
        return Strategy(
            name="aggressive",
            min_ev=0.0,
            min_confidence=0.0,
            stake_method="kelly",
            kelly_fraction=0.25,
        )

    @staticmethod
    def elite_only() -> Strategy:
        """Only bet elite tier opportunities.

        Use when: Only the strongest signals
        Criteria: EV >= 20%, Confidence >= 70%
        """
        return Strategy(
            name="elite_only",
            min_ev=0.20,
            min_confidence=70,
            stake_method="flat",
            flat_stake=25.0,
        )

    @staticmethod
    def high_volume() -> Strategy:
        """Bet many props with lower thresholds.

        Use when: Law of large numbers, market efficiency
        Criteria: EV > 3%, Confidence > 45%
        """
        return Strategy(
            name="high_volume",
            min_ev=0.03,
            min_confidence=45,
            stake_method="flat",
            flat_stake=5.0,
        )

    @staticmethod
    def prizepicks_only() -> Strategy:
        """Bet only PrizePicks props.

        Use when: Focusing on single market
        Criteria: EV > 5%, any confidence, PrizePicks only
        """
        return Strategy(
            name="prizepicks_only",
            min_ev=0.05,
            min_confidence=0.0,
            sites=["prizepicks"],
            stake_method="flat",
            flat_stake=10.0,
        )

    @staticmethod
    def draftkings_only() -> Strategy:
        """Bet only DraftKings props.

        Use when: Focusing on DK lines
        Criteria: EV > 5%, any confidence, DraftKings only
        """
        return Strategy(
            name="draftkings_only",
            min_ev=0.05,
            min_confidence=0.0,
            sites=["draftkings"],
            stake_method="flat",
            flat_stake=10.0,
        )

    @staticmethod
    def custom(
        name: str,
        min_ev: float = 0.05,
        min_confidence: float = 50.0,
        sites: Optional[list[str]] = None,
        stats: Optional[list[str]] = None,
        stake_method: str = "flat",
        flat_stake: float = 10.0,
        kelly_fraction: float = 0.25,
    ) -> Strategy:
        """Create a custom strategy with specified parameters.

        Args:
            name: Strategy name
            min_ev: Minimum EV as decimal
            min_confidence: Minimum confidence (0-100)
            sites: List of allowed sites (None = all)
            stats: List of allowed stats (None = all)
            stake_method: "flat" or "kelly"
            flat_stake: Amount for flat staking
            kelly_fraction: Kelly fraction for Kelly staking

        Returns:
            Custom Strategy instance
        """
        return Strategy(
            name=name,
            min_ev=min_ev,
            min_confidence=min_confidence,
            sites=sites,
            stats=stats,
            stake_method=stake_method,
            flat_stake=flat_stake,
            kelly_fraction=kelly_fraction,
        )
