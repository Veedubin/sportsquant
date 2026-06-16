"""
Portfolio Optimization

Adapted from sports_analytics.model.portfolio
Changes:
- Replaced sports_analytics.util.logging with standard logging
- Replaced sports_analytics.model.market_impact with local market_impact module

Implements bet sizing and portfolio optimization:
1. Kelly Criterion with correlation adjustment
2. Fractional Kelly for risk management
3. Position sizing across multiple markets
4. Portfolio heat and risk limits
5. Expected value calculations
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np

from .market_impact import CLVThrottleConfig, CLVThrottler

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class KellyConfig:
    """Configuration for Kelly betting."""

    kelly_fraction: float = 0.25
    max_kelly: float = 0.20
    min_edge_for_bet: float = 0.02
    min_prob_for_bet: float = 0.50
    correlation_decay: float = 0.95


@dataclass(frozen=True)
# pylint: disable=too-many-instance-attributes
class PositionSizingConfig:
    """Configuration for position sizing."""

    max_position_size: float = 0.10
    max_portfolio_exposure: float = 0.50
    max_market_exposure: float = 0.25
    max_book_exposure: float = 0.30
    min_bet_size: float = 0.01
    portfolio_heat_limit: float = 0.35
    min_edge_for_bet: float = 0.02
    clv_throttle_config: Optional[CLVThrottleConfig] = None


@dataclass(frozen=True)
class PortfolioRiskConfig:
    """Configuration for portfolio risk management."""

    max_position_size: float = 0.10
    max_portfolio_exposure: float = 0.50
    max_daily_loss_pct: float = 0.05
    max_drawdown_pct: float = 0.15
    max_correlated_exposure: float = 0.40
    var_confidence: float = 0.95
    concentration_limit: float = 0.20


class KellyBettor:
    """Kelly Criterion betting calculations."""

    def __init__(self, config: Optional[KellyConfig] = None):
        self.config = config or KellyConfig()

    def compute_kelly(
        self,
        win_prob: float,
        odds_decimal: float,
        kelly_fraction: Optional[float] = None,
    ) -> float:
        """Compute Kelly bet size as fraction of bankroll.

        Kelly formula: f* = (bp - q) / b
        Where:
            b = odds decimal - 1
            p = probability of winning
            q = probability of losing (1 - p)

        Args:
            win_prob: Your estimated probability of winning
            odds_decimal: Decimal odds (e.g., 2.00 for even money)
            kelly_fraction: Fraction of full Kelly to use (default: config value)

        Returns:
            Kelly fraction (0 = don't bet, negative = don't bet opposite)
        """
        kelly_fraction = kelly_fraction or self.config.kelly_fraction

        b = odds_decimal - 1
        p = win_prob
        q = 1 - p

        if b <= 0:
            return 0.0

        kelly = (b * p - q) / b

        kelly = max(0, kelly)
        kelly = min(kelly, self.config.max_kelly)

        return kelly * kelly_fraction

    def compute_kelly_with_correlation(
        self,
        win_prob: float,
        odds_decimal: float,
        correlation: float = 0.0,
        existing_exposure: float = 0.0,
    ) -> float:
        """Compute Kelly adjusted for correlation with existing bets.

        When you have correlated bets, you should reduce position sizes.
        """
        base_kelly = self.compute_kelly(win_prob, odds_decimal)

        if correlation > 0:
            decay_factor = self.config.correlation_decay ** (correlation * 10)
            adjusted_kelly = base_kelly * decay_factor
        else:
            adjusted_kelly = base_kelly

        adjusted_kelly = adjusted_kelly * (1 - existing_exposure * 0.5)

        return max(0, adjusted_kelly)

    def compute_expected_value(
        self,
        win_prob: float,
        odds_decimal: float,
        stake: float = 1.0,
    ) -> float:
        """Compute expected value of a bet.

        EV = (win_prob * (odds - 1) * stake) - ((1 - win_prob) * stake)
        """
        win_amount = win_prob * (odds_decimal - 1) * stake
        lose_amount = (1 - win_prob) * stake
        return win_amount - lose_amount

    def compute_roi(
        self,
        win_prob: float,
        odds_decimal: float,
        kelly_fraction: Optional[float] = None,
    ) -> float:
        """Compute expected ROI for Kelly-optimal bet."""
        kelly = self.compute_kelly(win_prob, odds_decimal, kelly_fraction)
        if kelly <= 0:
            return 0.0

        ev = self.compute_expected_value(win_prob, odds_decimal, kelly)
        return ev / kelly if kelly > 0 else 0.0

    def compute_edge(
        self,
        win_prob: float,
        odds_decimal: float,
    ) -> float:
        """Compute edge over the house."""
        implied_prob = 1 / odds_decimal
        return win_prob - implied_prob


class PositionSizer:
    """Position sizing with risk limits and CLV-based throttling."""

    def __init__(
        self,
        config: Optional[PositionSizingConfig] = None,
        clv_throttler: Optional[CLVThrottler] = None,
    ):
        self.config = config or PositionSizingConfig()
        self.clv_throttler = clv_throttler
        if self.config.clv_throttle_config and self.clv_throttler is None:
            self.clv_throttler = CLVThrottler(self.config.clv_throttle_config)

    def compute_position_size(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        kelly_fraction: float,
        edge: float,
        bankroll: float,
        current_portfolio_exposure: float = 0.0,
        current_market_exposure: float = 0.0,
        current_book_exposure: float = 0.0,
    ) -> float:
        """Compute position size respecting all limits.

        Args:
            kelly_fraction: Kelly bet size
            edge: Edge over the market
            bankroll: Total bankroll
            current_portfolio_exposure: Current total portfolio exposure
            current_market_exposure: Current exposure to this market (pts/reb/ast)
            current_book_exposure: Current exposure to this book

        Returns:
            Position size as dollar amount
        """
        if edge < self.config.min_edge_for_bet:
            return 0.0

        # Convert exposures to fractions of bankroll for proper calculation
        current_portfolio_frac = current_portfolio_exposure / bankroll if bankroll > 0 else 0.0
        current_market_frac = current_market_exposure / bankroll if bankroll > 0 else 0.0
        current_book_frac = current_book_exposure / bankroll if bankroll > 0 else 0.0

        max_position = bankroll * self.config.max_position_size
        max_portfolio = bankroll * max(
            0.0, self.config.max_portfolio_exposure - current_portfolio_frac
        )
        max_market = bankroll * max(0.0, self.config.max_market_exposure - current_market_frac)
        max_book = bankroll * max(0.0, self.config.max_book_exposure - current_book_frac)

        position = kelly_fraction * bankroll

        position = min(position, max_position)
        position = min(position, max_portfolio)
        position = min(position, max_market)
        position = min(position, max_book)

        if position < bankroll * self.config.min_bet_size:
            return 0.0

        return position

    def compute_throttled_position_size(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
        self,
        kelly_fraction: float,
        edge: float,
        bankroll: float,
        clv_trend: str = "flat",
        line_reversal: bool = False,
        market_impact_penalty: float = 1.0,
        current_portfolio_exposure: float = 0.0,
        current_market_exposure: float = 0.0,
        current_book_exposure: float = 0.0,
    ) -> float:
        """Compute position size with CLV throttling and market impact.

        This method extends compute_position_size by applying CLV-based throttling
        and market impact penalties to the calculated position size.

        Args:
            kelly_fraction: Kelly bet size
            edge: Edge over the market
            bankroll: Total bankroll
            clv_trend: CLV trend category ('improving', 'flat', 'degrading', 'hard_cap', 'suspend')
            line_reversal: Whether line has reversed against bet
            market_impact_penalty: Market impact penalty factor (0.0 to 1.0)
            current_portfolio_exposure: Current total portfolio exposure
            current_market_exposure: Current exposure to this market (pts/reb/ast)
            current_book_exposure: Current exposure to this book

        Returns:
            Throttled position size as dollar amount (0.0 if should suspend)
        """
        if self.clv_throttler and self.clv_throttler.should_suspend_betting(
            clv_trend, line_reversal
        ):
            logger.info(
                "Betting suspended: clv_trend=%s, line_reversal=%s",
                clv_trend,
                line_reversal,
            )
            return 0.0

        if edge < self.config.min_edge_for_bet:
            return 0.0

        current_portfolio_frac = current_portfolio_exposure / bankroll if bankroll > 0 else 0.0
        current_market_frac = current_market_exposure / bankroll if bankroll > 0 else 0.0
        current_book_frac = current_book_exposure / bankroll if bankroll > 0 else 0.0

        max_position = bankroll * self.config.max_position_size
        max_portfolio = bankroll * max(
            0.0, self.config.max_portfolio_exposure - current_portfolio_frac
        )
        max_market = bankroll * max(0.0, self.config.max_market_exposure - current_market_frac)
        max_book = bankroll * max(0.0, self.config.max_book_exposure - current_book_frac)

        base_position = kelly_fraction * bankroll

        base_position = min(base_position, max_position)
        base_position = min(base_position, max_portfolio)
        base_position = min(base_position, max_market)
        base_position = min(base_position, max_book)

        if base_position < bankroll * self.config.min_bet_size:
            return 0.0

        if self.clv_throttler:
            throttled_position = self.clv_throttler.apply_throttling(
                base_stake=base_position,
                clv_trend=clv_trend,
                impact_penalty=market_impact_penalty,
            )
        else:
            throttled_position = base_position * market_impact_penalty

        logger.debug(
            "Throttled position: base=%.2f, clv_trend=%s, impact_penalty=%.2f, result=%.2f",
            base_position,
            clv_trend,
            market_impact_penalty,
            throttled_position,
        )

        return throttled_position

    def compute_parlay_size(
        self,
        leg_kelly_fractions: list[float],
        leg_edges: list[float],
        bankroll: float,
        num_legs: int,
    ) -> float:
        """Compute parlay position size with reduced exposure."""
        avg_kelly = np.mean(leg_kelly_fractions)
        avg_edge = np.mean(leg_edges)

        if avg_edge < self.config.min_edge_for_bet:
            return 0.0

        parlay_reduction = 1 / np.sqrt(num_legs)
        adjusted_kelly = avg_kelly * parlay_reduction

        return min(adjusted_kelly * bankroll, bankroll * self.config.max_position_size)

    def compute_round_robin_size(
        self,
        leg_kelly_fractions: list[float],
        leg_edges: list[float],
        bankroll: float,
        combinations: int,
    ) -> float:
        """Compute round robin position size."""
        total_kelly = sum(leg_kelly_fractions)
        avg_edge = np.mean(leg_edges)

        if avg_edge < self.config.min_edge_for_bet:
            return 0.0

        round_robin_reduction = 1 / np.sqrt(combinations)
        adjusted_kelly = (total_kelly / len(leg_kelly_fractions)) * round_robin_reduction

        return min(adjusted_kelly * bankroll, bankroll * self.config.max_position_size)


class PortfolioManager:  # pylint: disable=too-many-instance-attributes
    """Manage portfolio of bets with risk limits."""

    def __init__(
        self,
        kelly_config: Optional[KellyConfig] = None,
        position_config: Optional[PositionSizingConfig] = None,
        risk_config: Optional[PortfolioRiskConfig] = None,
    ):
        self.kelly = KellyBettor(kelly_config)
        self.sizer = PositionSizer(position_config)
        self.risk_config = risk_config or PortfolioRiskConfig()
        self.position_config = position_config or PositionSizingConfig()

        self.bankroll: float = 10000.0
        self.current_exposure: float = 0.0
        self.daily_pnl: float = 0.0
        self.bet_history: list[dict] = []

    def set_bankroll(self, bankroll: float) -> None:
        """Set current bankroll."""
        self.bankroll = bankroll

    def can_place_bet(
        self,
        market: str,
        book: str,
        proposed_size: float,
    ) -> tuple[bool, str]:
        """Check if bet can be placed given risk limits."""
        fail_reason: str | None = None
        market_exposure = self.get_market_exposure(market)
        book_exposure = self.get_book_exposure(book)
        portfolio_heat = self.compute_portfolio_heat()

        checks = [
            (
                self.daily_pnl < -self.bankroll * self.risk_config.max_daily_loss_pct,
                "Daily loss limit exceeded",
            ),
            (
                proposed_size > self.bankroll * self.position_config.max_position_size,
                "Position size exceeds maximum",
            ),
            (
                self.current_exposure + proposed_size
                > self.bankroll * self.position_config.max_portfolio_exposure,
                "Portfolio exposure limit exceeded",
            ),
            (
                market_exposure + proposed_size
                > self.bankroll * self.position_config.max_market_exposure,
                "Market exposure limit exceeded",
            ),
            (
                book_exposure + proposed_size
                > self.bankroll * self.position_config.max_book_exposure,
                "Book exposure limit exceeded",
            ),
            (
                portfolio_heat > self.position_config.portfolio_heat_limit,
                "Portfolio heat limit exceeded",
            ),
        ]

        for condition, reason in checks:
            if condition:
                fail_reason = reason
                break

        if fail_reason:
            return False, fail_reason

        return True, "Bet approved"

    def place_bet(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
        self,
        player_id: str,
        market: str,
        line: float,
        odds_decimal: float,
        win_prob: float,
        side: str,
        book: str,
    ) -> dict:
        """Place a bet and update portfolio state."""
        edge = self.kelly.compute_edge(win_prob, odds_decimal)
        kelly = self.kelly.compute_kelly(win_prob, odds_decimal)

        if edge < self.kelly.config.min_edge_for_bet:
            logger.info(
                "Bet rejected: edge %.4f below minimum %s",
                edge,
                self.kelly.config.min_edge_for_bet,
            )
            return {"status": "rejected", "reason": "Insufficient edge", "size": 0.0}

        current_exposure = self.get_total_exposure()
        market_exposure = self.get_market_exposure(market)
        book_exposure = self.get_book_exposure(book)

        position_size = self.sizer.compute_position_size(
            kelly,
            edge,
            self.bankroll,
            current_exposure,
            market_exposure,
            book_exposure,
        )

        can_bet, reason = self.can_place_bet(market, book, position_size)

        if not can_bet:
            logger.info("Bet rejected: %s", reason)
            return {"status": "rejected", "reason": reason, "size": 0.0}

        ev = self.kelly.compute_expected_value(win_prob, odds_decimal, position_size)

        bet = {
            "player_id": player_id,
            "market": market,
            "line": line,
            "odds_decimal": odds_decimal,
            "win_prob": win_prob,
            "edge": edge,
            "kelly": kelly,
            "position_size": position_size,
            "expected_value": ev,
            "side": side,
            "book": book,
            "status": "pending",
            "result": None,
        }

        self.bet_history.append(bet)
        self.current_exposure += position_size

        logger.info(
            "Bet placed: %s %s %s %s @ %s $%.2f (EV: $%.2f)",
            player_id,
            market,
            side,
            line,
            odds_decimal,
            position_size,
            ev,
        )

        return bet

    def settle_bet(self, bet_index: int, result: int) -> float:
        """Settle a bet and update bankroll.

        Args:
            bet_index: Index of bet in history
            result: 1 if won, 0 if lost

        Returns:
            P&L from this bet
        """
        if bet_index >= len(self.bet_history):
            raise ValueError(f"Bet index {bet_index} not found")

        bet = self.bet_history[bet_index]
        if bet["status"] != "pending":
            raise ValueError(f"Bet {bet_index} already settled")

        stake = bet["position_size"]
        odds = bet["odds_decimal"]

        if result == 1:
            payout = stake * odds
            pnl = payout - stake
        else:
            pnl = -stake

        bet["status"] = "settled"
        bet["result"] = result
        bet["pnl"] = pnl

        self.bankroll += pnl
        self.current_exposure -= stake
        self.daily_pnl += pnl

        logger.info("Bet settled: %s %s - P&L: $%.2f", bet["player_id"], bet["market"], pnl)

        return pnl

    def get_total_exposure(self) -> float:
        """Get total pending exposure."""
        return sum(bet["position_size"] for bet in self.bet_history if bet["status"] == "pending")

    def get_market_exposure(self, market: str) -> float:
        """Get exposure for a specific market."""
        return sum(
            bet["position_size"]
            for bet in self.bet_history
            if bet["status"] == "pending" and bet["market"] == market
        )

    def get_book_exposure(self, book: str) -> float:
        """Get exposure for a specific book."""
        return sum(
            bet["position_size"]
            for bet in self.bet_history
            if bet["status"] == "pending" and bet["book"] == book
        )

    def get_player_exposure(self, player_id: str) -> float:
        """Get exposure for a specific player."""
        return sum(
            bet["position_size"]
            for bet in self.bet_history
            if bet["status"] == "pending" and bet["player_id"] == player_id
        )

    def compute_portfolio_heat(self) -> float:
        """Compute portfolio heat (risk level)."""
        if self.bankroll <= 0:
            return 1.0

        exposure = self.get_total_exposure()
        pending_pnl = sum(
            bet["expected_value"] for bet in self.bet_history if bet["status"] == "pending"
        )

        heat = (exposure / self.bankroll) * 0.6 + (abs(pending_pnl) / self.bankroll) * 0.4

        return min(heat, 1.0)

    def compute_concentration_risk(self) -> float:
        """Compute concentration risk (largest positions)."""
        if not self.bet_history:
            return 0.0

        pending_sizes = [
            bet["position_size"] for bet in self.bet_history if bet["status"] == "pending"
        ]

        if not pending_sizes:
            return 0.0

        largest = max(pending_sizes)
        return largest / self.bankroll

    def compute_var(
        self,
        confidence: Optional[float] = None,
    ) -> float:
        """Compute Value at Risk (VaR) for pending bets."""
        confidence = confidence or self.risk_config.var_confidence

        pnl_values = [
            bet["expected_value"] for bet in self.bet_history if bet["status"] == "pending"
        ]

        if not pnl_values:
            return 0.0

        pnl_array = np.array(pnl_values)
        var_index = int((1 - confidence) * len(pnl_array))
        var = np.sort(pnl_array)[var_index]

        return abs(var)

    def reset_daily_pnl(self) -> None:
        """Reset daily P&L counter (call at start of each day)."""
        self.daily_pnl = 0.0

    def get_portfolio_summary(self) -> dict:  # pylint: disable=too-many-return-statements
        """Get comprehensive portfolio summary."""
        pending_bets = [b for b in self.bet_history if b["status"] == "pending"]
        settled_bets = [b for b in self.bet_history if b["status"] == "settled"]

        total_won = sum(1 for b in settled_bets if b["result"] == 1)
        total_lost = sum(1 for b in settled_bets if b["result"] == 0)
        win_rate = total_won / (total_won + total_lost) if (total_won + total_lost) > 0 else 0.0

        total_pnl = sum(b.get("pnl", 0) for b in settled_bets)
        total_ev = sum(b["expected_value"] for b in pending_bets)

        return {
            "bankroll": self.bankroll,
            "daily_pnl": self.daily_pnl,
            "total_exposure": self.get_total_exposure(),
            "pending_bets": len(pending_bets),
            "settled_bets": len(settled_bets),
            "win_rate": win_rate,
            "total_pnl": total_pnl,
            "total_expected_value": total_ev,
            "portfolio_heat": self.compute_portfolio_heat(),
            "concentration_risk": self.compute_concentration_risk(),
            "var_95": self.compute_var(0.95),
        }


__all__ = [
    "KellyConfig",
    "PositionSizingConfig",
    "PortfolioRiskConfig",
    "KellyBettor",
    "PositionSizer",
    "PortfolioManager",
]
