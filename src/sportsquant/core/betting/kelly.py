"""
Enhanced Kelly Criterion and Bankroll Management

Adapted from sports_analytics.model.kelly_enhanced
Changes: Replaced sports_analytics.util.logging with standard logging

This module provides comprehensive Kelly Criterion calculations including:
- Standard Kelly calculation
- Fractional Kelly for risk management
- Adaptive Kelly based on volatility
- Multi-bet correlation adjustments
- Bankroll management with exposure limits
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from scipy import stats

logger = logging.getLogger(__name__)


__all__ = [
    "KellyFloat",
    "KellyCalculatorConfig",
    "KellyCalculator",
    "BankrollManagerConfig",
    "BankrollManager",
    "EdgeCalculatorConfig",
    "EdgeCalculator",
]


KellyFloat = float | np.floating[Any]


@dataclass(frozen=True)
class KellyCalculatorConfig:
    """Configuration for Kelly calculations."""

    min_odds: float = 1.01
    max_odds: float = 100.0
    min_probability: float = 0.001
    max_probability: float = 0.999


@dataclass(frozen=True)
class AdaptiveKellyContext:
    """Context for adaptive Kelly calculations.

    Attributes:
        probability: Estimated probability of winning.
        odds: Decimal odds.
        fraction: Base Kelly fraction to use.
        volatility: Volatility adjustment factor (0-1).
        max_fraction: Maximum Kelly fraction to allow.
    """

    probability: float
    odds: float
    fraction: float
    volatility: float
    max_fraction: float = 0.5


class KellyCalculator:
    """Enhanced Kelly Criterion calculator with fractional and adaptive options.

    The Kelly Criterion determines the optimal bet size to maximize logarithmic
    wealth growth over time. This implementation includes fractional and adaptive
    variants for risk management.

    Attributes:
        config: Configuration parameters for Kelly calculations.
    """

    def __init__(self, config: KellyCalculatorConfig | None = None) -> None:
        """Initialize Kelly calculator with optional configuration.

        Args:
            config: Optional configuration for Kelly calculations.
        """
        self.config = config if config is not None else KellyCalculatorConfig()
        logger.debug("KellyCalculator initialized with config: %s", self.config)

    def compute_kelly(self, probability: float, odds: float) -> float:
        """Calculate standard Kelly bet fraction.

        The Kelly formula: f = (p * b - 1) / (b - 1)
        where p is probability of winning and b is decimal odds minus 1.

        Args:
            probability: Estimated probability of winning (0-1).
            odds: Decimal odds (e.g., 2.0 for +100).

        Returns:
            Kelly fraction as decimal. Positive = edge, negative = don't bet.

        Raises:
            ValueError: If probability or odds are outside valid ranges.
        """
        if not self.config.min_probability <= probability <= self.config.max_probability:
            raise ValueError(
                f"Probability {probability} outside valid range "
                f"[{self.config.min_probability}, {self.config.max_probability}]"
            )
        if not self.config.min_odds <= odds <= self.config.max_odds:
            raise ValueError(
                f"Odds {odds} outside valid range [{self.config.min_odds}, {self.config.max_odds}]"
            )

        if math.isclose(odds, 1.0):
            logger.warning("Odds of 1.0 would cause division by zero")
            return 0.0

        net_odds = odds - 1.0

        if net_odds <= 0:
            if probability > 1 / odds:
                return -1.0
            return 0.0

        kelly_fraction = (probability * net_odds - (1 - probability)) / net_odds

        logger.debug(
            "Kelly calculation: prob=%.3f, odds=%.2f, kelly=%.4f",
            probability,
            odds,
            kelly_fraction,
        )

        return kelly_fraction

    def compute_fractional_kelly(
        self, probability: float, odds: float, fraction: float = 0.25
    ) -> float:
        """Calculate fractional Kelly bet fraction.

        Fractional Kelly applies a multiplier to the full Kelly fraction,
        reducing variance while maintaining positive expected growth.
        Common fractions: 0.5 (half-Kelly), 0.25 (quarter-Kelly).

        Args:
            probability: Estimated probability of winning (0-1).
            odds: Decimal odds (e.g., 2.0 for +100).
            fraction: Fraction of full Kelly to use (0-1).

        Returns:
            Fractional Kelly bet size as decimal of bankroll.

        Raises:
            ValueError: If fraction is outside [0, 1].
        """
        if not 0.0 <= fraction <= 1.0:
            raise ValueError(f"Fraction {fraction} must be between 0 and 1")

        full_kelly = self.compute_kelly(probability, odds)

        if full_kelly <= 0:
            return 0.0

        fractional_kelly = full_kelly * fraction

        logger.debug(
            "Fractional Kelly: full=%.4f, fraction=%.2f, result=%.4f",
            full_kelly,
            fraction,
            fractional_kelly,
        )

        return fractional_kelly

    def compute_adaptive_kelly(self, ctx: AdaptiveKellyContext) -> float:
        """Calculate adaptive Kelly based on volatility.

        Adaptive Kelly reduces the Kelly fraction based on estimated volatility
        of the edge, providing more conservative sizing during uncertain periods.

        Args:
            ctx: Context describing the adaptive kelly parameters.

        Returns:
            Adaptive Kelly bet size as decimal of bankroll.
        """
        if not 0.0 <= ctx.volatility <= 1.0:
            raise ValueError(f"Volatility {ctx.volatility} must be between 0 and 1")

        if not 0.0 <= ctx.fraction <= 1.0:
            raise ValueError(f"Base fraction {ctx.fraction} must be between 0 and 1")

        full_kelly = self.compute_kelly(ctx.probability, ctx.odds)

        if full_kelly <= 0:
            return 0.0

        volatility_adjustment = 1.0 - ctx.volatility

        adaptive_fraction = ctx.fraction * volatility_adjustment
        adaptive_fraction = min(adaptive_fraction, ctx.max_fraction)

        adaptive_kelly = full_kelly * adaptive_fraction

        logger.debug(
            "Adaptive Kelly: full=%.4f, vol=%.3f, adj=%.3f, result=%.4f",
            full_kelly,
            ctx.volatility,
            volatility_adjustment,
            adaptive_kelly,
        )

        return adaptive_kelly

    def compute_kelly_multi_bet(
        self,
        probabilities: list[float],
        odds: list[float],
        correlations: list[float] | None = None,
    ) -> list[float]:
        """Calculate Kelly fractions for multiple correlated bets.

        When betting on multiple correlated outcomes, we must account for
        covariance to avoid overbetting. This method adjusts individual
        Kelly fractions based on pairwise correlations.

        Args:
            probabilities: List of win probabilities.
            odds: List of decimal odds.
            correlations: Optional list of correlation coefficients between bets.

        Returns:
            List of adjusted Kelly fractions.

        Raises:
            ValueError: If inputs have different lengths or invalid correlations.
        """
        if len(probabilities) != len(odds):
            raise ValueError(
                f"Probabilities ({len(probabilities)}) and odds ({len(odds)}) must have same length"
            )

        if correlations is not None and len(correlations) != len(probabilities) - 1:
            raise ValueError(
                f"Correlations ({len(correlations) if correlations else 0}) must be "
                f"length of probabilities minus 1 ({len(probabilities) - 1})"
            )

        kelly_fractions = np.array([self.compute_kelly(p, o) for p, o in zip(probabilities, odds)])

        if correlations is not None:
            for i, corr in enumerate(correlations):
                if not -1.0 <= corr <= 1.0:
                    raise ValueError(f"Correlation {corr} must be between -1 and 1")
                kelly_fractions[i] *= 1.0 - abs(corr) * 0.5

        return kelly_fractions.tolist()


@dataclass(frozen=True)
class ExposureLimits:
    """Exposure limits configuration."""

    max_position_pct: float = 0.1
    max_portfolio_exposure: float = 0.5
    max_market_exposure: float = 0.25
    max_book_exposure: float = 0.3


@dataclass(frozen=True)
class BankrollManagerConfig:
    """Configuration for bankroll management."""

    min_bet_size: float = 1.0
    max_bet_size: float = 10000.0
    min_bankroll: float = 100.0
    kelly_fraction: float = 0.25
    exposure_limits: ExposureLimits = field(default_factory=ExposureLimits)


class BankrollManager:
    """Manages bankroll and position sizing with protection rules.

    This class handles bankroll management including bet sizing calculations,
    position limits, and bankroll updates. It incorporates multiple protection
    rules to prevent overbetting and ensure long-term survivability.

    Attributes:
        config: Configuration parameters for bankroll management.
    """

    def __init__(
        self,
        bankroll: float,
        config: BankrollManagerConfig | None = None,
    ) -> None:
        """Initialize bankroll manager.

        Args:
            bankroll: Initial bankroll amount.
            config: Optional configuration for bankroll management.

        Raises:
            ValueError: If bankroll or percentages are invalid.
        """
        if bankroll < 0:
            raise ValueError(f"Bankroll {bankroll} cannot be negative")
        if not config:
            config = BankrollManagerConfig()
        limits = config.exposure_limits
        if not 0.0 < limits.max_position_pct <= 1.0:
            raise ValueError(
                f"Max position percentage {limits.max_position_pct} must be between 0 and 1"
            )
        if not 0.0 < limits.max_portfolio_exposure <= 1.0:
            raise ValueError(
                f"Max portfolio exposure {limits.max_portfolio_exposure} must be between 0 and 1"
            )
        if not 0.0 < config.kelly_fraction <= 1.0:
            raise ValueError(f"Kelly fraction {config.kelly_fraction} must be between 0 and 1")

        self._bankroll = bankroll
        self.config = config

        logger.info(
            "BankrollManager initialized: bankroll=%.2f, max_pos=%.1f%%",
            bankroll,
            self.config.exposure_limits.max_position_pct * 100,
        )

    @property
    def bankroll(self) -> float:
        """Get current bankroll."""
        return self._bankroll

    def compute_bet_size(
        self,
        kelly_fraction: float,
        odds: float,
        win_probability: float,
        current_exposure: float = 0.0,
    ) -> float:
        """Calculate bet size based on Kelly fraction and constraints.

        Args:
            kelly_fraction: Calculated Kelly fraction.
            odds: Decimal odds.
            win_probability: Estimated win probability.
            current_exposure: Current exposure to this market/player.

        Returns:
            Recommended bet size after applying constraints.

        Raises:
            ValueError: If inputs are invalid.
        """
        if not 0.0 <= win_probability <= 1.0:
            raise ValueError(f"Win probability {win_probability} must be between 0 and 1")
        if odds <= 1.0:
            raise ValueError(f"Odds {odds} must be greater than 1.0")
        if not 0.0 <= kelly_fraction <= 1.0:
            raise ValueError(f"Kelly fraction {kelly_fraction} must be between 0 and 1")
        if current_exposure < 0:
            raise ValueError(f"Current exposure {current_exposure} cannot be negative")

        if kelly_fraction <= 0 or win_probability <= 1 / odds:
            logger.debug("No edge: kelly=%.4f, breakeven_prob=%.3f", kelly_fraction, 1 / odds)
            return 0.0

        max_bet_by_kelly = self._bankroll * kelly_fraction
        max_bet_by_position = self._bankroll * self.config.exposure_limits.max_position_pct
        max_bet_by_exposure = (
            self._bankroll * self.config.exposure_limits.max_portfolio_exposure - current_exposure
        )

        bet_size = min(max_bet_by_kelly, max_bet_by_position, max_bet_by_exposure)
        bet_size = max(bet_size, 0.0)

        logger.debug(
            "Bet size calculation: kelly_max=%.2f, pos_max=%.2f, exp_max=%.2f, result=%.2f",
            max_bet_by_kelly,
            max_bet_by_position,
            max_bet_by_exposure,
            bet_size,
        )

        return bet_size

    def apply_position_limits(
        self,
        bet_size: float,
        bankroll: float | None = None,
    ) -> float:
        """Apply position limits to a bet size.

        Args:
            bet_size: Proposed bet size.
            bankroll: Bankroll to use (defaults to current).

        Returns:
            Bet size after applying all limits.
        """
        effective_bankroll = bankroll if bankroll is not None else self._bankroll

        max_position_size = effective_bankroll * self.config.exposure_limits.max_position_pct
        max_bet = max_position_size

        if bet_size > max_bet:
            logger.warning(
                "Bet size %.2f exceeds max position %.2f, reduced to max",
                bet_size,
                max_bet,
            )
            bet_size = max_bet

        if bet_size < self.config.min_bet_size:
            logger.debug(
                "Bet size %.2f below minimum %.2f, returning 0",
                bet_size,
                self.config.min_bet_size,
            )
            return 0.0

        return min(bet_size, self.config.max_bet_size)

    def apply_multi_market_limits(
        self,
        bet_size: float,
        current_market_exposure: float,
        current_book_exposure: float,
    ) -> float:
        """Apply exposure limits across markets and books.

        Args:
            bet_size: Proposed bet size.
            current_market_exposure: Current exposure to this market.
            current_book_exposure: Current exposure to this book.

        Returns:
            Bet size after applying exposure limits.
        """
        max_market_size = (
            self._bankroll * self.config.exposure_limits.max_market_exposure
            - current_market_exposure
        )
        max_book_size = (
            self._bankroll * self.config.exposure_limits.max_book_exposure - current_book_exposure
        )

        effective_max = min(
            max_market_size,
            max_book_size,
            self._bankroll * self.config.exposure_limits.max_position_pct,
        )
        effective_max = max(effective_max, 0.0)

        if bet_size > effective_max:
            logger.debug(
                "Bet reduced by market/book limits: %.2f -> %.2f",
                bet_size,
                effective_max,
            )
            bet_size = effective_max

        return bet_size

    def update_bankroll(
        self,
        current_bankroll: float,
        profit: float,
        loss: float | None = None,
    ) -> float:
        """Update bankroll after a bet result.

        Args:
            current_bankroll: Current bankroll before update.
            profit: Profit from winning bet (negative for loss if loss not provided).
            loss: Optional explicit loss amount (used instead of -profit).

        Returns:
            Updated bankroll amount.
        """
        if loss is not None:
            new_bankroll = current_bankroll - loss
        else:
            new_bankroll = current_bankroll + profit

        new_bankroll = max(new_bankroll, 0.0)

        logger.debug(
            "Bankroll update: %.2f -> %.2f (profit=%.2f)",
            current_bankroll,
            new_bankroll,
            profit,
        )

        return new_bankroll

    def get_exposure_percentages(
        self,
        bet_size: float,
        current_exposure: float,
    ) -> dict[str, float]:
        """Calculate current exposure percentages.

        Args:
            bet_size: Size of potential new bet.
            current_exposure: Current exposure to this market.

        Returns:
            Dictionary with exposure metrics.
        """
        total_exposure = current_exposure + bet_size

        return {
            "position_pct": total_exposure / self._bankroll,
            "portfolio_pct": total_exposure / self._bankroll,
            "remaining_capacity": 1.0 - (total_exposure / self._bankroll),
            "kelly_recommended": self._bankroll * self.config.kelly_fraction,
        }


@dataclass(frozen=True)
class EdgeCalculatorConfig:
    """Configuration for edge calculations."""

    min_edge_threshold: float = 0.02
    significant_edge_threshold: float = 0.05
    confidence_level: float = 0.95


class EdgeCalculator:
    """Calculate edge over bookmaker with statistical confidence.

    This class provides methods to calculate and analyze the edge
    a bettor has over bookmaker odds, including confidence intervals
    for probability estimates.

    Attributes:
        config: Configuration parameters for edge calculations.
    """

    def __init__(self, config: EdgeCalculatorConfig | None = None) -> None:
        """Initialize edge calculator.

        Args:
            config: Optional configuration for edge calculations.
        """
        self.config = config if config is not None else EdgeCalculatorConfig()
        logger.debug("EdgeCalculator initialized with config: %s", self.config)

    def compute_edge(self, win_probability: float, odds: float) -> float:
        """Calculate edge over bookmaker.

        Edge is positive when the estimated probability implies
        a higher win rate than the odds suggest.

        Formula: Edge = (p_implied * odds) - 1
        where p_implied = 1/odds

        Args:
            win_probability: Estimated probability of winning (0-1).
            odds: Decimal odds from bookmaker.

        Returns:
            Edge as decimal. Positive = advantage, Negative = disadvantage.

        Raises:
            ValueError: If probability or odds are invalid.
        """
        if not 0.0 <= win_probability <= 1.0:
            raise ValueError(f"Win probability {win_probability} must be between 0 and 1")
        if odds <= 1.0:
            raise ValueError(f"Odds {odds} must be greater than 1.0")

        implied_probability = 1.0 / odds
        edge = (win_probability * odds) - 1.0

        edge_percentage = edge * 100
        p_implied_percentage = implied_probability * 100

        logger.debug(
            "Edge calculation: prob=%.1f%%, implied=%.1f%%, odds=%.2f, edge=%.2f%%",
            win_probability * 100,
            p_implied_percentage,
            odds,
            edge_percentage,
        )

        return edge

    def compute_expected_value(
        self,
        win_probability: float,
        odds: float,
        stake: float = 1.0,
    ) -> float:
        """Calculate expected value of a bet.

        EV = (win_prob * win_amount) - (loss_prob * stake)

        Args:
            win_probability: Estimated probability of winning (0-1).
            odds: Decimal odds from bookmaker.
            stake: Amount staked (default 1 unit).

        Returns:
            Expected value in units of stake.
        """
        if not 0.0 <= win_probability <= 1.0:
            raise ValueError(f"Win probability {win_probability} must be between 0 and 1")
        if stake < 0:
            raise ValueError(f"Stake {stake} cannot be negative")

        win_amount = (odds - 1) * stake
        loss_amount = stake * (1 - win_probability)

        expected_value = (win_probability * win_amount) - loss_amount

        logger.debug(
            "EV calculation: prob=%.1f%%, odds=%.2f, stake=%.2f, EV=%.4f",
            win_probability * 100,
            odds,
            stake,
            expected_value,
        )

        return expected_value

    def confidence_interval(
        self,
        win_probability: float,
        n_samples: int,
        confidence: float = 0.95,
    ) -> tuple[float, float, float]:
        """Calculate confidence interval for probability estimate.

        Uses Wilson score interval for binary proportions,
        which is more accurate for probabilities near 0 or 1.

        Args:
            win_probability: Point estimate of probability (0-1).
            n_samples: Number of samples/observations.
            confidence: Confidence level (e.g., 0.95 for 95% CI).

        Returns:
            Tuple of (lower_bound, upper_bound, margin_of_error).

        Raises:
            ValueError: If n_samples <= 0 or confidence not in (0, 1).
        """
        if n_samples <= 0:
            raise ValueError(f"n_samples {n_samples} must be positive")
        if not 0.0 < confidence < 1.0:
            raise ValueError(f"Confidence level {confidence} must be between 0 and 1")

        alpha = 1.0 - confidence
        z_val = float(stats.norm.ppf(1.0 - alpha / 2))

        z_squared = z_val * z_val
        n = float(n_samples)

        denominator = 1.0 + z_squared / n
        center = win_probability + z_squared / (2 * n)
        margin = z_val * (
            (win_probability * (1.0 - win_probability) / n + z_squared / (4 * n**2)) ** 0.5
        )

        lower = (center - margin) / denominator
        upper = (center + margin) / denominator

        lower = max(0.0, min(1.0, lower))
        upper = max(0.0, min(1.0, upper))

        margin_of_error = (upper - lower) / 2.0

        logger.debug(
            "CI: p=%.3f, n=%d, conf=%.1f%%, CI=[%.3f, %.3f]",
            win_probability,
            n_samples,
            confidence * 100,
            lower,
            upper,
        )

        return float(lower), float(upper), float(margin_of_error)

    def is_significant_edge(
        self,
        win_probability: float,
        odds: float,
        n_samples: int,
        confidence: float = 0.95,
    ) -> bool:
        """Check if edge is statistically significant.

        Args:
            win_probability: Estimated probability of winning (0-1).
            odds: Decimal odds from bookmaker.
            n_samples: Number of samples/observations.
            confidence: Confidence level for statistical test.

        Returns:
            True if edge is statistically significant.
        """
        edge = self.compute_edge(win_probability, odds)

        if edge <= 0:
            return False

        implied_prob = 1.0 / odds

        lower, _, _ = self.confidence_interval(win_probability, n_samples, confidence)

        is_significant = lower > implied_prob

        logger.debug(
            "Significance test: edge=%.2f%%, CI_lower=%.1f%% > implied=%.1f%%? %s",
            edge * 100,
            lower * 100,
            implied_prob * 100,
            is_significant,
        )

        return is_significant

    def kelly_equivalent_edge(
        self,
        win_probability: float,
        odds: float,
        kelly_fraction: float = 1.0,
    ) -> float:
        """Calculate the Kelly-equivalent edge.

        This is the effective edge after applying Kelly fraction,
        useful for comparing bets with different Kelly sizing.

        Args:
            win_probability: Estimated probability of winning (0-1).
            odds: Decimal odds from bookmaker.
            kelly_fraction: Fraction of Kelly to apply (default 1.0).

        Returns:
            Kelly-equivalent edge as decimal.
        """
        edge = self.compute_edge(win_probability, odds)
        return edge * kelly_fraction

    def roi_break_even(self, odds: float, kelly_fraction: float = 1.0) -> float:
        """Calculate break-even win rate adjusted for Kelly sizing.

        Args:
            odds: Decimal odds.
            kelly_fraction: Fraction of Kelly to apply.

        Returns:
            Break-even win rate as probability (0-1).
        """
        if odds <= 1.0:
            raise ValueError(f"Odds {odds} must be greater than 1.0")

        break_even_prob = 1.0 / odds

        if kelly_fraction < 1.0:
            adjusted_break_even = 1.0 - kelly_fraction * (1.0 - break_even_prob)
        else:
            adjusted_break_even = break_even_prob

        return adjusted_break_even
