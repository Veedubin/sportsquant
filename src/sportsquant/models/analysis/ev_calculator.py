"""+EV (positive expected value) calculation.

This module calculates expected value by blending statistical model
probabilities with market probabilities using logit space blending.

Key insight: Simple linear blending underestimates the impact of
small probability differences near 0 or 1. Logit blending preserves
the odds-ratio structure and produces more accurate edge estimates.

Math:
  logit(p) = log(p / (1 - p))
  logit_blend = w * logit(p_model) + (1-w) * logit(p_market)
  blended_prob = sigmoid(logit_blend)

The logit transformation maps probabilities from [0,1] to (-inf, +inf),
making linear combination more meaningful for probability estimation.
"""

import math
from .rules import TIER_SCORING_POINTS, NBA_FANTASY_SCORE_WEIGHTS


def clamp(x: float, lo: float, hi: float) -> float:
    """Clamp value to range [lo, hi]."""
    return max(lo, min(hi, x))


def calculate_nba_fantasy_score(stats: dict) -> float:
    """Calculate NBA Fantasy Score from stat dict.

    NBA Fantasy Score = PTS*1 + REB*1.2 + AST*1.5 + BLK*3 + STL*3 - TOV*1

    Args:
        stats: Dict with keys like PTS, REB, AST, BLK, STL, TOV

    Returns:
        Fantasy score as float
    """
    return sum(stats.get(k, 0) * v for k, v in NBA_FANTASY_SCORE_WEIGHTS.items())


class EVCalculator:
    """Calculates expected value using logit blending of model and market probabilities.

    This class identifies +EV plays by:
    1. Blending model and market probabilities in logit space
    2. Computing edge as difference between blended and market
    3. Determining recommended side (Over/Under) based on final probability
    4. Calculating confidence score based on edge and market depth
    """

    def __init__(self, base_blend: float = 0.30):
        """Initialize EV calculator.

        Args:
            base_blend: Base model weight (0.30 = 30% model, 70% market)
        """
        self.base_blend = base_blend

    @staticmethod
    def logit_blend(p_model: float, p_market: float, weight: float) -> float:
        """Blend probabilities in logit space.

        This is the key algorithm for combining model and market probabilities.
        It preserves the odds-ratio structure better than linear blending.

        Formula:
          blended_logit = weight * logit(p_model) + (1-weight) * logit(p_market)
          blended_prob = sigmoid(blended_logit)

        Args:
            p_model: Model probability (0 to 1)
            p_market: Market probability (0 to 1)
            weight: Model weight (0 to 1)

        Returns:
            Blended probability in (0, 1)
        """
        eps = 1e-6
        pm = clamp(float(p_model), eps, 1 - eps)
        pk = clamp(float(p_market), eps, 1 - eps)
        ww = clamp(float(weight), 0.0, 1.0)

        # Transform to logit space
        logit_model = math.log(pm / (1 - pm))
        logit_market = math.log(pk / (1 - pk))

        # Linear blend in logit space
        blended_logit = ww * logit_model + (1 - ww) * logit_market

        # Transform back to probability space
        return 1.0 / (1.0 + math.exp(-blended_logit))

    def calculate_ev(
        self,
        model_prob: float,
        market_prob: float,
        payout_multiplier: float,
        blend_weight: float,
        over_only_tiers: set[str] | None = None,
        tier: str = "Standard",
    ) -> dict:
        """Calculate expected value for a play.

        Args:
            model_prob: Probability from statistical model
            market_prob: Probability from market odds
            payout_multiplier: Payout multiplier (e.g., 2.0 = even odds)
            blend_weight: Model weight for logit blending
            over_only_tiers: Set of tiers where only Over is allowed
            tier: PrizePicks tier (Standard, Goblin, Demon)

        Returns:
            Dict with:
              - final_prob: Blended probability
              - final_prob_over: Probability of Over
              - final_prob_under: Probability of Under
              - recommended_side: "Over" or "Under"
              - edge: Edge vs market (final_prob - market_side_prob)
              - ev: Expected value (final_prob * payout - 1)
              - confidence: Confidence score (0-100)
        """
        over_only_tiers = over_only_tiers or {"Goblin", "Demon"}

        model_under = 1.0 - model_prob
        market_under = 1.0 - market_prob

        # Logit blend
        final_over = self.logit_blend(model_prob, market_prob, blend_weight)
        final_under = self.logit_blend(model_under, market_under, blend_weight)

        # Determine recommended side
        if tier in over_only_tiers:
            recommended_side = "Over"
            final_side = final_over
            market_side = market_prob
        else:
            if final_over >= final_under:
                recommended_side = "Over"
                final_side = final_over
                market_side = market_prob
            else:
                recommended_side = "Under"
                final_side = final_under
                market_side = market_under

        # Edge calculation
        edge = final_side - market_side

        # EV calculation: E[profit] = P(hit) * payout - stake
        # Assuming stake = 1, EV = P(hit) * payout_multiplier - 1
        ev = final_side * payout_multiplier - 1.0

        # Confidence score: combines edge strength and market depth
        # Base: scaled deviation from 50%
        # Bonus: more books = higher confidence (more market validation)
        books_count = 5  # Default if not provided
        base = 100.0 * clamp((final_side - 0.5) / 0.5, 0.0, 1.0)
        conf = clamp(base + 6.0 * (1.0 - math.exp(-books_count / 5.0)), 0.0, 100.0)

        return {
            "final_prob": float(final_side),
            "final_prob_over": float(final_over),
            "final_prob_under": float(final_under),
            "recommended_side": recommended_side,
            "edge": float(edge),
            "ev": float(ev),
            "confidence": round(float(conf), 1),
            "model_prob": float(model_prob),
            "market_prob": float(market_prob),
            "blend_weight": float(blend_weight),
        }

    @staticmethod
    def american_odds_to_payout(odds: float) -> float:
        """Convert American odds to payout multiplier.

        Args:
            odds: American odds (e.g., -110, +150)

        Returns:
            Payout multiplier (including stake)
        """
        odds = float(odds)
        if odds < 0:
            return abs(odds) / abs(odds) + 100.0 / abs(odds)
        else:
            return odds / 100.0 + 1.0

    @staticmethod
    def adjust_probability_for_tier(
        probability: float,
        tier: str,
        tier_scoring_points: dict = None,
    ) -> float:
        """Adjust probability based on tier scoring modifiers.

        Different tiers have different effective probabilities due to
        group competition scoring adjustments.

        Args:
            probability: Base probability
            tier: PrizePicks tier (Standard, Goblin, Demon)
            tier_scoring_points: Override scoring points dict

        Returns:
            Adjusted probability
        """
        tier_scoring_points = tier_scoring_points or TIER_SCORING_POINTS
        modifier = tier_scoring_points.get(tier, 1.0)

        # Goblins are "easier" so effective probability is higher
        # Demons are "harder" so effective probability is lower
        # The modifier directly scales the line, not the probability
        # We need to invert to get probability adjustment
        if modifier != 1.0:
            # Approximate adjustment: higher modifier = harder = lower prob
            adjustment = 1.0 / modifier
            probability = probability * adjustment

        return clamp(probability, 0.01, 0.99)
