"""
Over/under strategy - selects the side with highest expected value.

This is the default strategy used in the original backtest implementation.
"""

# pylint: disable=too-many-arguments,too-many-positional-arguments

from sportsquant.core.betting.strategies.base import (
    BetDecision,
    BettingOpportunity,
    BettingStrategy,
)


class OverUnderStrategy(BettingStrategy):
    """
    Strategy that picks the over or under side with highest EV.

    Always bets on whichever side has higher expected value, with configurable
    stake sizing (flat or Kelly-based).
    """

    def __init__(
        self,
        name: str = "OverUnder",
        bankroll: float = 1000.0,
        use_kelly: bool = False,
        kelly_fraction: float = 1.0,
        flat_stake: float = 1.0,
        max_stake: float | None = None,
    ):
        """
        Initialize over/under strategy.

        Args:
            name: Strategy name
            bankroll: Available bankroll
            use_kelly: Whether to use Kelly criterion for sizing
            kelly_fraction: Fraction of Kelly to use (e.g., 0.25 for quarter-Kelly)
            flat_stake: Fixed stake if not using Kelly
            max_stake: Maximum bet size cap (optional)
        """
        super().__init__(name, bankroll)
        self.use_kelly = use_kelly
        self.kelly_fraction = kelly_fraction
        self.flat_stake = flat_stake
        self.max_stake = max_stake

    def evaluate_opportunity(self, opportunity: BettingOpportunity) -> BetDecision:
        """
        Evaluate opportunity and bet on side with higher EV.

        Args:
            opportunity: Betting opportunity info

        Returns:
            BetDecision with selected side and stake
        """
        # Choose side with higher EV
        if opportunity.ev_over >= opportunity.ev_under:
            side = "over"
            ev = opportunity.ev_over
            kelly = opportunity.kelly_over
        else:
            side = "under"
            ev = opportunity.ev_under
            kelly = opportunity.kelly_under

        # Determine stake
        if self.use_kelly:
            # Kelly sizing with fractional multiplier
            stake = self.bankroll * kelly * self.kelly_fraction
        else:
            stake = self.flat_stake

        # Apply maximum stake cap if set
        if self.max_stake is not None:
            stake = min(stake, self.max_stake)

        # Clamp to non-negative
        stake = max(0.0, stake)

        reason = f"{side.upper()} (EV={ev:.4f}, kelly={kelly:.4f})"

        return BetDecision(
            should_bet=True,
            side=side,
            stake=stake,
            reason=reason,
        )
