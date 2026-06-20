"""Base evaluation engine for all DFS sites.

This module provides the foundational EV calculation and confidence scoring
that all site-specific evaluators inherit from.
"""

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


def clamp(x: float, lo: float, hi: float) -> float:
    """Clamp value to range [lo, hi]."""
    return max(lo, min(hi, x))


@dataclass
class EvaluationResult:
    """Result of evaluating a single prop."""

    player_name: str
    stat_type: str
    line: float

    # Probabilities
    model_prob: float
    market_prob: float  # Can be None if no market data available
    fair_prob: float
    final_prob: float

    # Recommendations
    recommended_side: str  # "Over" or "Under" for PrizePicks, "Higher" or "Lower" for Underdog
    alternative_side: str

    # Metrics
    edge: float
    ev: float
    confidence: float
    hit_probability: float

    # Kelly
    kelly_fraction: float
    suggested_stake: float

    # Risk
    risk_score: float
    variance: float

    # Metadata
    site: str
    payout_multiplier: float = 1.0
    breakeven_prob: float = 0.5  # 1/payout - for fixed payout games

    def is_plus_ev(self, threshold: float = 0.0) -> bool:
        """Check if this is a +EV play."""
        return self.ev > threshold

    def confidence_level(self) -> str:
        """Return human-readable confidence."""
        if self.confidence >= 80:
            return "HIGH"
        elif self.confidence >= 60:
            return "MEDIUM"
        elif self.confidence >= 40:
            return "LOW"
        return "VERY LOW"


class BaseEvaluator(ABC):
    """Base evaluation engine for all DFS sites.

    Provides common functionality for EV calculation, confidence scoring,
    and probability blending that site-specific evaluators inherit from.
    """

    def __init__(
        self,
        model_weight: float = 0.30,
        min_confidence: float = 40.0,
        min_edge: float = 0.02,
        base_kelly: float = 0.25,
    ):
        """Initialize base evaluator.

        Args:
            model_weight: Weight given to model probability (0-1)
            min_confidence: Minimum confidence to recommend
            min_edge: Minimum edge to recommend
            base_kelly: Base Kelly fraction to use (fraction of bankroll)
        """
        self.model_weight = model_weight
        self.min_confidence = min_confidence
        self.min_edge = min_edge
        self.base_kelly = base_kelly

    @staticmethod
    def logit(p: float) -> float:
        """Convert probability to logit.

        Args:
            p: Probability (0-1)

        Returns:
            Logit value (-inf to +inf)
        """
        eps = 1e-6
        p = clamp(p, eps, 1 - eps)
        return math.log(p / (1 - p))

    @staticmethod
    def sigmoid(x: float) -> float:
        """Convert logit back to probability.

        Args:
            x: Logit value

        Returns:
            Probability (0-1)
        """
        return 1.0 / (1.0 + math.exp(-x))

    def logit_blend(
        self,
        p_model: float,
        p_market: float,
        weight: Optional[float] = None,
    ) -> float:
        """Blend probabilities in logit space.

        This is the key algorithm for combining model and market probabilities.
        It preserves the odds-ratio structure better than linear blending.

        Formula:
            blended_logit = weight * logit(p_model) + (1-weight) * logit(p_market)
            blended_prob = sigmoid(blended_logit)

        Args:
            p_model: Model probability (0 to 1)
            p_market: Market probability (0 to 1)
            weight: Model weight override (uses self.model_weight if None)

        Returns:
            Blended probability in (0, 1)
        """
        w = weight if weight is not None else self.model_weight
        ww = clamp(w, 0.0, 1.0)

        logit_model = self.logit(p_model)
        logit_market = self.logit(p_market)

        blended_logit = ww * logit_model + (1 - ww) * logit_market
        return self.sigmoid(blended_logit)

    def calculate_ev(
        self,
        line: float,
        over_odds: float,
        under_odds: float,
        model_prob: float,
        payout_multiplier: float = 1.0,
    ) -> dict:
        """Calculate expected value for a prop.

        Args:
            line: The prop line
            over_odds: American odds for Over
            under_odds: American odds for Under
            model_prob: Probability from statistical model
            payout_multiplier: Payout multiplier (including stake)

        Returns:
            Dict with EV calculation results
        """
        # Convert American odds to implied probabilities
        implied_over = self.american_to_prob(over_odds)
        implied_under = self.american_to_prob(under_odds)

        # Remove vig to get fair probabilities
        fair_over = self.remove_vig(implied_over, implied_under)
        fair_under = 1.0 - fair_over

        # Blend model and market
        final_over = self.logit_blend(model_prob, fair_over)
        final_under = self.logit_blend(1.0 - model_prob, fair_under)

        # Determine recommended side
        if final_over >= final_under:
            recommended_side = "Over"
            final_side = final_over
            market_side = fair_over
        else:
            recommended_side = "Under"
            final_side = final_under
            market_side = fair_under

        # Calculate edge
        edge = final_side - market_side

        # Calculate EV: E[profit] = P(hit) * payout - stake
        # Assuming stake = 1, EV = P(hit) * payout_multiplier - 1
        ev = final_side * payout_multiplier - 1.0

        return {
            "implied_over": implied_over,
            "implied_under": implied_under,
            "fair_over": fair_over,
            "fair_under": fair_under,
            "final_over": final_over,
            "final_under": final_under,
            "recommended_side": recommended_side,
            "final_side": final_side,
            "market_side": market_side,
            "edge": edge,
            "ev": ev,
        }

    def calculate_confidence(
        self,
        model_prob: float,
        market_prob: float,
        sample_size: int = 5,
        edge: float = 0.0,
    ) -> float:
        """Calculate confidence score (0-100).

        Combines:
        - Base: scaled deviation from 50%
        - Edge bonus: larger edge = higher confidence
        - Market depth bonus: more books = higher confidence

        Args:
            model_prob: Final blended probability
            market_prob: Market probability
            sample_size: Number of data sources/books
            edge: Edge vs market

        Returns:
            Confidence score 0-100
        """
        # Base: scaled deviation from 50%
        deviation = abs(model_prob - 0.5) / 0.5
        base = 100.0 * deviation

        # Edge bonus (capped)
        edge_bonus = 20.0 * min(edge / 0.1, 1.0)

        # Market depth bonus (logarithmic)
        depth_bonus = 10.0 * (1.0 - math.exp(-sample_size / 5.0))

        confidence = clamp(base + edge_bonus + depth_bonus, 0.0, 100.0)
        return round(confidence, 1)

    def expected_hit_rate(
        self,
        projections: list,
        base_rate: float = 0.55,
        correlation: float = 0.1,
    ) -> float:
        """Predict hit rate for a set of projections.

        Uses a simplified model accounting for correlation between legs.

        Args:
            projections: List of projection dicts with 'probability' key
            base_rate: Base hit rate if all legs were independent
            correlation: Correlation coefficient between legs

        Returns:
            Expected hit rate for all legs hitting
        """
        if not projections:
            return 0.0

        probs = [p.get("probability", 0.5) for p in projections]
        n = len(probs)

        if n <= 1:
            return probs[0] if probs else 0.0

        # Simple approximation: reduce expected hit rate based on correlation
        # Higher correlation = lower expected multi-leg hit rate
        expected_independent = math.prod(probs)

        # Adjust for correlation (simplified model)
        avg_prob = sum(probs) / n
        adjustment = 1.0 + correlation * (n - 1) * (1.0 - avg_prob)

        return clamp(expected_independent * adjustment, 0.0, 1.0)

    def correlate_legs(
        self,
        leg1: dict,
        leg2: dict,
        same_game: bool = True,
        same_player: bool = False,
    ) -> float:
        """Calculate correlation between legs.

        Uses heuristics based on game/player relationships.

        Args:
            leg1: First leg dict with 'stat_type', 'player', etc.
            leg2: Second leg dict
            same_game: Whether legs are from same game
            same_player: Whether legs are for same player

        Returns:
            Correlation coefficient (0 to ~0.35)
        """
        if same_player:
            # Same player correlations
            stat1 = leg1.get("stat_type", "").upper()
            stat2 = leg2.get("stat_type", "").upper()

            # PRA combos have highest correlation
            if "PRA" in [stat1, stat2] or {"PTS", "REB", "AST"} <= {stat1, stat2}:
                return 0.35
            if {"PTS", "3PM"} <= {stat1, stat2}:
                return 0.20
            if {"PTS", "AST"} <= {stat1, stat2}:
                return 0.18
            if {"PTS", "REB"} <= {stat1, stat2}:
                return 0.12
            return 0.22

        if same_game:
            return 0.06

        return 0.02  # Different games

    def kelly_criterion(
        self,
        probability: float,
        odds: float,
        kelly_fraction: float = 0.25,
    ) -> float:
        """Calculate Kelly Criterion bet size.

        Args:
            probability: Win probability
            odds: Decimal odds (payout including stake)
            kelly_fraction: Fraction of Kelly to use (risk management)

        Returns:
            Kelly fraction for this bet (0-1)
        """
        if odds <= 1.0:
            return 0.0

        # Kelly formula: f* = (bp - q) / b
        # where b = decimal odds - 1, p = probability, q = 1 - p
        b = odds - 1.0
        p = probability
        q = 1.0 - p

        kelly = (b * p - q) / b

        if kelly <= 0:
            return 0.0

        # Apply fractional Kelly (reduce variance)
        return clamp(kelly * kelly_fraction, 0.0, 1.0)

    def risk_score(
        self,
        probability: float,
        payout_multiplier: float,
        variance: float = 0.0,
    ) -> float:
        """Calculate risk score for a prop.

        Higher risk = higher variance in outcomes.

        Args:
            probability: Hit probability
            payout_multiplier: Payout multiplier
            variance: Additional variance component

        Returns:
            Risk score (0-100, higher = riskier)
        """
        # Base risk from probability (extreme probabilities = higher risk)
        prob_risk = 50.0 * abs(probability - 0.5) / 0.5

        # Payout risk (high payouts = higher risk usually)
        payout_risk = min(30.0, (payout_multiplier - 1.0) * 10.0)

        return clamp(prob_risk + payout_risk + variance, 0.0, 100.0)

    @staticmethod
    def american_to_prob(odds: float) -> float:
        """Convert American odds to implied probability.

        Args:
            odds: American odds (e.g., -110, +150)

        Returns:
            Implied probability (0-1)
        """
        odds = float(odds)
        if odds < 0:
            return abs(odds) / (abs(odds) + 100.0)
        return 100.0 / (odds + 100.0)

    @staticmethod
    def prob_to_american(prob: float) -> float:
        """Convert probability to American odds.

        Args:
            prob: Probability (0-1)

        Returns:
            American odds
        """
        if prob >= 1.0:
            return float("inf")
        if prob <= 0.0:
            return float("-inf")
        if prob >= 0.5:
            return -100.0 * prob / (1.0 - prob)
        return 100.0 * (1.0 - prob) / prob

    @staticmethod
    def american_to_decimal(odds: float) -> float:
        """Convert American odds to decimal odds.

        Args:
            odds: American odds

        Returns:
            Decimal odds (including stake)
        """
        odds = float(odds)
        if odds < 0:
            return abs(odds) / abs(odds) + 100.0 / abs(odds)
        return odds / 100.0 + 1.0

    @staticmethod
    def remove_vig(p_over: float, p_under: float) -> float:
        """Remove vig from two-way market.

        Uses additive method: scales probabilities to sum to 1.0.

        Args:
            p_over: Raw over probability
            p_under: Raw under probability

        Returns:
            Devigged over probability
        """
        total = p_over + p_under
        if total <= 0:
            return 0.5
        return p_over / total

    @abstractmethod
    def evaluate_projection(self, projection, **kwargs) -> EvaluationResult:
        """Evaluate a single projection.

        Must be implemented by subclass.

        Args:
            projection: Site-specific projection object
            **kwargs: Additional site-specific arguments

        Returns:
            EvaluationResult with recommendation
        """
        pass
