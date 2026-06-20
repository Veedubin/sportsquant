"""
Arbitrage betting strategy - exploits odds discrepancies for guaranteed profit.

Detects arbitrage opportunities where betting both sides can guarantee profit
regardless of outcome.
"""

from quantitative_sports.core.betting.strategies.base import (
    BetDecision,
    BettingOpportunity,
    BettingStrategy,
    make_bet_decision,
)


class ArbitrageStrategy(BettingStrategy):
    """
    Strategy that identifies and exploits arbitrage opportunities.

    An arbitrage opportunity exists when:
    (1/odds_over) + (1/odds_under) < 1.0

    The strategy calculates optimal stakes for both sides to guarantee profit.
    """

    def __init__(
        self,
        name: str = "Arbitrage",
        bankroll: float = 1000.0,
        min_profit_pct: float = 1.0,  # Minimum 1% guaranteed profit
        max_stake_pct: float = 0.10,  # Max 10% of bankroll per arbitrage
    ):
        """
        Initialize arbitrage strategy.

        Args:
            name: Strategy name
            bankroll: Available bankroll
            min_profit_pct: Minimum profit percentage to execute arbitrage
            max_stake_pct: Maximum total stake as percentage of bankroll
        """
        super().__init__(name, bankroll)
        self.min_profit_pct = min_profit_pct / 100.0
        self.max_stake_pct = max_stake_pct

    def detect_arbitrage(self, odds_over: float, odds_under: float) -> tuple[bool, float]:
        """
        Detect arbitrage opportunity and calculate guaranteed profit rate.

        Args:
            odds_over: Decimal odds for over
            odds_under: Decimal odds for under

        Returns:
            Tuple of (is_arbitrage, profit_rate)
        """
        if odds_over <= 1.0 or odds_under <= 1.0:
            return False, 0.0

        # Sum of implied probabilities
        implied_sum = (1.0 / odds_over) + (1.0 / odds_under)

        # Arbitrage exists if sum < 1.0
        is_arb = implied_sum < 1.0

        # Profit rate calculation
        if is_arb:
            profit_rate = (1.0 / implied_sum) - 1.0
        else:
            profit_rate = 0.0

        return is_arb, profit_rate

    def calculate_optimal_stakes(
        self, total_stake: float, odds_over: float, odds_under: float
    ) -> tuple[float, float]:
        """
        Calculate optimal stakes for both sides to guarantee equal profit.

        Args:
            total_stake: Total amount to stake across both bets
            odds_over: Decimal odds for over
            odds_under: Decimal odds for under

        Returns:
            Tuple of (stake_over, stake_under)
        """
        # Optimal stake distribution for equal profit regardless of outcome
        stake_over = total_stake / (1.0 + (odds_over / odds_under))
        stake_under = total_stake - stake_over

        return stake_over, stake_under

    def evaluate_opportunity(self, opportunity: BettingOpportunity) -> BetDecision:
        """
        Evaluate opportunity for arbitrage.

        Note: This strategy conceptually requires betting BOTH sides, but the
        BetDecision interface only supports single-side decisions. In practice,
        arbitrage would need special handling or dual bets.

        For now, we detect arbitrage and bet the side with lower implied probability.

        Args:
            opportunity: Betting opportunity info

        Returns:
            BetDecision (skip if no arbitrage)
        """
        is_arb, profit_rate = self.detect_arbitrage(
            opportunity.odds_over_decimal,
            opportunity.odds_under_decimal,
        )

        if not is_arb or profit_rate < self.min_profit_pct:
            return BetDecision(
                should_bet=False,
                side="skip",
                stake=0.0,
                reason=f"No arbitrage (profit_rate={profit_rate * 100:.2f}%)",
            )

        # Calculate total stake for arbitrage
        max_total_stake = self.bankroll * self.max_stake_pct

        # Calculate optimal stakes
        stake_over, stake_under = self.calculate_optimal_stakes(
            max_total_stake,
            opportunity.odds_over_decimal,
            opportunity.odds_under_decimal,
        )

        # For single-bet interface, choose side with larger stake
        # (In real implementation, both would be placed)
        if stake_over >= stake_under:
            side = "over"
            stake = stake_over
        else:
            side = "under"
            stake = stake_under

        reason = f"ARBITRAGE {side.upper()} (profit={profit_rate * 100:.2f}%, total={max_total_stake:.2f})"

        return make_bet_decision(side=side, stake=stake, reason=reason)
