"""
Value betting strategy - only bets when edge exceeds a minimum threshold.

More conservative than over/under, filtering for opportunities with significant
positive expected value.
"""

# pylint: disable=too-many-arguments,too-many-positional-arguments

from quantitative_sports.core.betting.strategies.base import (
    BetDecision,
    BettingOpportunity,
    BettingStrategy,
)


class ValueBettingStrategy(BettingStrategy):
    """
    Strategy that only bets when EV exceeds a minimum threshold.

    This is a conservative approach that waits for strong edges before placing bets.
    Uses fractional Kelly sizing to manage risk.
    """

    def __init__(
        self,
        name: str = "ValueBetting",
        bankroll: float = 1000.0,
        min_ev: float = 0.05,  # Minimum 5% edge
        min_edge_pct: float = 5.0,  # Minimum 5% value bet edge
        kelly_fraction: float = 0.25,  # Quarter-Kelly for safety
        max_stake_pct: float = 0.05,  # Max 5% of bankroll per bet
    ):
        """
        Initialize value betting strategy.

        Args:
            name: Strategy name
            bankroll: Available bankroll
            min_ev: Minimum expected value to place bet (per $1 staked)
            min_edge_pct: Minimum edge percentage (true prob - implied prob)
            kelly_fraction: Fraction of Kelly to use (conservative)
            max_stake_pct: Maximum stake as percentage of bankroll
        """
        super().__init__(name, bankroll)
        self.min_ev = min_ev
        self.min_edge_pct = min_edge_pct / 100.0  # Convert to decimal
        self.kelly_fraction = kelly_fraction
        self.max_stake_pct = max_stake_pct

    def evaluate_opportunity(self, opportunity: BettingOpportunity) -> BetDecision:
        """
        Evaluate opportunity and bet only if value exceeds threshold.

        Args:
            opportunity: Betting opportunity info

        Returns:
            BetDecision (may be skip if no value)
        """
        # Calculate value bet edges (true prob - implied prob)
        implied_over = 1.0 / opportunity.odds_over_decimal
        implied_under = 1.0 / opportunity.odds_under_decimal

        edge_over = opportunity.p_over - implied_over
        edge_under = opportunity.p_under - implied_under

        # Check both sides for value
        best_side = None
        best_ev = 0.0
        best_edge = 0.0
        best_kelly = 0.0

        if opportunity.ev_over > best_ev and edge_over > self.min_edge_pct:
            best_side = "over"
            best_ev = opportunity.ev_over
            best_edge = edge_over
            best_kelly = opportunity.kelly_over

        if opportunity.ev_under > best_ev and edge_under > self.min_edge_pct:
            best_side = "under"
            best_ev = opportunity.ev_under
            best_edge = edge_under
            best_kelly = opportunity.kelly_under

        # Check if we meet minimum EV threshold
        if best_side is None or best_ev < self.min_ev:
            return BetDecision(
                should_bet=False,
                side="skip",
                stake=0.0,
                reason=f"No value (best_ev={best_ev:.4f}, min={self.min_ev:.4f})",
            )

        # Calculate stake using fractional Kelly
        stake = self.bankroll * best_kelly * self.kelly_fraction

        # Apply maximum stake percentage
        max_stake = self.bankroll * self.max_stake_pct
        stake = min(stake, max_stake)

        # Clamp to non-negative
        stake = max(0.0, stake)

        reason = f"{best_side.upper()} (EV={best_ev:.4f}, edge={best_edge * 100:.2f}%)"

        return BetDecision(
            should_bet=True,
            side=best_side,
            stake=stake,
            reason=reason,
        )
