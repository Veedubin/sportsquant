"""
Probability threshold strategy - only bets when model edge exceeds threshold.

This is more intuitive than EV-based: bet when P(over) - implied_prob >= X%
"""

from dataclasses import dataclass

from sportsquant.core.betting.strategies.base import (
    BetDecision,
    BettingOpportunity,
    BettingStrategy,
)


@dataclass(frozen=True)
class ProbabilityThresholdConfig:
    """Configuration for probability threshold strategy."""

    min_edge_pct: float = 3.0
    kelly_fraction: float = 0.25
    max_stake_pct: float = 0.05
    prefer_over: bool = True


class ProbabilityThresholdStrategy(BettingStrategy):
    """
    Strategy that only bets when model probability exceeds implied by threshold.

    Example: If implied probability is 50% (even odds) and threshold is 3%,
             only bet if model says over has >= 53% probability.
    """

    def __init__(
        self,
        name: str = "ProbabilityThreshold",
        bankroll: float = 1000.0,
        config: ProbabilityThresholdConfig | None = None,
    ):
        super().__init__(name, bankroll)
        cfg = config or ProbabilityThresholdConfig()
        self.min_edge_pct = cfg.min_edge_pct / 100.0
        self.kelly_fraction = cfg.kelly_fraction
        self.max_stake_pct = cfg.max_stake_pct
        self.prefer_over = cfg.prefer_over

    def evaluate_opportunity(self, opportunity: BettingOpportunity) -> BetDecision:
        implied_over = 1.0 / opportunity.odds_over_decimal
        implied_under = 1.0 / opportunity.odds_under_decimal

        edge_over = opportunity.p_over - implied_over
        edge_under = opportunity.p_under - implied_under

        if edge_over >= edge_under:
            best_side = "over"
            best_edge = edge_over
            best_kelly = opportunity.kelly_over
        else:
            best_side = "under"
            best_edge = edge_under
            best_kelly = opportunity.kelly_under

        if best_edge < self.min_edge_pct:
            return BetDecision(
                should_bet=False,
                side="skip",
                stake=0.0,
                reason=f"No edge (best={best_edge * 100:.2f}%, min={self.min_edge_pct * 100:.2f}%)",
            )

        stake = self.bankroll * best_kelly * self.kelly_fraction
        max_stake = self.bankroll * self.max_stake_pct
        stake = max(0.0, min(stake, max_stake))

        return BetDecision(
            should_bet=True,
            side=best_side,
            stake=stake,
            reason=f"{best_side.upper()} (edge={best_edge * 100:.2f}%, kelly={best_kelly:.4f})",
        )
