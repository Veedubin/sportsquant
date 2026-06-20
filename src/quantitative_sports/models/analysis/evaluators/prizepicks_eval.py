"""PrizePicks-specific prop evaluation.

This module provides PrizePicks-specific evaluation using the
base engine and PrizePicks rules.
"""

from dataclasses import dataclass
from typing import Optional

from quantitative_sports.models.analysis.engine import BaseEvaluator, EvaluationResult
from quantitative_sports.models.analysis.rules import (
    STANDARD_PAYOUT_POWER,
    STANDARD_PAYOUT_FLEX,
)
from quantitative_sports.models.analysis.ev_calculator import EVCalculator
from quantitative_sports.models.analysis.slip_optimizer import SlipOptimizer, Leg

# Actual PrizePicks tier payouts (fixed, not market-based)
# Standard: 3x, Goblin: 5x, Demon: 10x
TIER_PAYOUTS = {
    "Standard": 3.0,
    "Goblin": 5.0,
    "Demon": 10.0,
}


@dataclass
class PrizePicksLeg:
    """A leg for PrizePicks slip building."""

    player_name: str
    team: str
    opponent: str
    stat_type: str
    line: float
    probability: float
    edge: float
    tier: str = "Standard"
    side: str = "Over"
    start_local: str = ""

    @property
    def game_key(self) -> str:
        """Game key for correlation."""
        start = self.start_local[:10] if self.start_local else ""
        return f"{self.team}@{self.opponent}|{start}"


@dataclass
class PrizePicksSlip:
    """A complete PrizePicks slip recommendation."""

    slip_type: str  # e.g., "POWER_3", "FLEX_5"
    format_type: str  # "power" or "flex"
    n_legs: int
    legs: list[PrizePicksLeg]
    ev: float
    avg_probability: float
    payout_multiplier: float
    confidence: float
    rank: int = 0

    def legs_description(self) -> str:
        """Human-readable leg descriptions."""
        return " | ".join(
            [
                f"{leg.player_name} {leg.stat_type} {leg.side} {leg.line:g} "
                f"(p={leg.probability:.3f}, edge={leg.edge:+.3f})"
                for leg in self.legs
            ]
        )


class PrizePicksEvaluator(BaseEvaluator):
    """Evaluate PrizePicks props and recommend More/Less.

    PrizePicks uses "More" (Over) and "Less" (Under) terminology.
    Supports POWER and FLEX formats with different payout structures.
    """

    def __init__(
        self,
        model_weight: float = 0.30,
        min_confidence: float = 45.0,
        min_edge: float = 0.03,
        base_kelly: float = 0.25,
    ):
        """Initialize PrizePicks evaluator.

        Args:
            model_weight: Weight given to model probability (0-1)
            min_confidence: Minimum confidence to recommend
            min_edge: Minimum edge to recommend
            base_kelly: Base Kelly fraction
        """
        super().__init__(
            model_weight=model_weight,
            min_confidence=min_confidence,
            min_edge=min_edge,
            base_kelly=base_kelly,
        )
        self.ev_calculator = EVCalculator(base_blend=model_weight)

    def evaluate_projection(
        self,
        projection,
        market_odds: Optional[dict] = None,
        model_prob: Optional[float] = None,
        side_override: Optional[str] = None,
    ) -> EvaluationResult:
        """Evaluate a single PrizePicks projection.

        Args:
            projection: PrizePicks Projection object
            market_odds: Market odds dict with 'over' and 'under' American odds
            model_prob: Model probability override
            side_override: Force a specific side ("More" or "Less")

        Returns:
            EvaluationResult with recommendation
        """
        # Extract data from projection
        player_name = projection.player_name or "Unknown"
        stat_type = projection.stat_display_name or projection.stat_type or "Unknown"
        line = projection.line_score
        tier = projection.tier or "Standard"

        # Calculate model probability if not provided
        if model_prob is None:
            model_prob = 0.52  # Default assumption

        # Get actual PrizePicks payout for this tier
        payout = TIER_PAYOUTS.get(tier, 3.0)
        breakeven_prob = 1.0 / payout

        # Get market odds or calculate fair probability
        market_odds_available = bool(market_odds)
        if market_odds:
            over_odds = market_odds.get("over", -110)
            under_odds = market_odds.get("under", -110)
            implied_over = self.american_to_prob(over_odds)
            implied_under = self.american_to_prob(under_odds)
            fair_prob = self.remove_vig(implied_over, implied_under)
            # Use the market prob corresponding to the side we'll recommend
            market_prob_over = implied_over
            market_prob_under = implied_under
        else:
            # No market data available
            # Use model_prob directly, mark market_prob as None
            fair_prob = model_prob
            market_prob_over = None
            market_prob_under = None

        # Blend probabilities (use model_prob vs market or fair_prob as anchor)
        if market_odds_available and market_prob_over is not None:
            final_prob = self.logit_blend(model_prob, market_prob_over)
        else:
            # No market - use model_prob as final with slight regression toward 50%
            final_prob = self.logit_blend(model_prob, 0.50)

        # Calculate EV for both "More" (Over) and "Less" (Under)
        # P(More hits) = final_prob (model thinks player exceeds line)
        # P(Less hits) = 1 - final_prob (model thinks player stays under line)
        ev_more = final_prob * payout - 1.0
        ev_less = (1 - final_prob) * payout - 1.0

        # Determine side by comparing EVs for both sides
        # PrizePicks has fixed payout for both Over and Under
        if side_override:
            recommended_side = side_override
        else:
            # Recommend side with higher EV
            if ev_more >= ev_less:
                recommended_side = "More"
            else:
                recommended_side = "Less"

        alternative_side = "Less" if recommended_side == "More" else "More"

        # Use the EV of the recommended side
        ev = ev_more if recommended_side == "More" else ev_less

        # Calculate edge
        # If market available: edge = final_prob - market_prob for that side
        # If no market: edge = final_prob - breakeven_prob (advantage over break-even)
        market_prob = None
        if market_prob_over is not None:
            market_prob = market_prob_over if recommended_side == "More" else market_prob_under
            edge = final_prob - market_prob
        else:
            edge = final_prob - breakeven_prob

        # Calculate confidence
        confidence = self.calculate_confidence(
            final_prob,
            market_prob if market_prob is not None else breakeven_prob,
            sample_size=5,
            edge=edge,
        )

        # Calculate Kelly using actual payout
        kelly_frac = self.kelly_criterion(
            final_prob,
            payout,
            self.base_kelly,
        )

        # Risk score
        risk = self.risk_score(final_prob, payout)

        return EvaluationResult(
            player_name=player_name,
            stat_type=stat_type,
            line=line,
            model_prob=model_prob,
            market_prob=market_prob,
            fair_prob=fair_prob,
            final_prob=final_prob,
            recommended_side=recommended_side,
            alternative_side=alternative_side,
            edge=edge,
            ev=ev,
            confidence=confidence,
            hit_probability=final_prob,
            kelly_fraction=kelly_frac,
            suggested_stake=kelly_frac,  # Fraction of bankroll
            risk_score=risk,
            variance=0.0,
            site="prizepicks",
            payout_multiplier=payout,  # Actual PrizePicks tier payout
            breakeven_prob=breakeven_prob,
        )

    def build_optimal_slips(
        self,
        projections: list,
        market_data: Optional[dict] = None,
        model_probs: Optional[dict] = None,
        format_type: str = "power",
        n_legs: int = 3,
        top_k: int = 10,
        min_probability: float = 0.58,
    ) -> list[PrizePicksSlip]:
        """Build optimal slips for the given projections.

        Args:
            projections: List of PrizePicks Projection objects
            market_data: Dict mapping projection_id to market odds
            model_probs: Dict mapping projection_id to model probability
            format_type: "power" or "flex"
            n_legs: Number of legs per slip
            top_k: Number of top slips to return
            min_probability: Minimum probability threshold

        Returns:
            List of PrizePicksSlip recommendations
        """
        # Convert projections to legs
        legs = []
        for proj in projections:
            # Get market odds if available
            market_odds = market_data.get(proj.id) if market_data else None

            # Get model probability if available
            model_prob = model_probs.get(proj.id) if model_probs else None

            # Evaluate projection
            result = self.evaluate_projection(
                proj,
                market_odds=market_odds,
                model_prob=model_prob,
            )

            # Convert to PrizePicksLeg
            leg = PrizePicksLeg(
                player_name=result.player_name,
                team=getattr(proj, "team_abbreviation", "") or "",
                opponent="",
                stat_type=result.stat_type,
                line=result.line,
                probability=result.final_prob,
                edge=result.edge,
                tier=proj.tier or "Standard",
                side=result.recommended_side,
                start_local=getattr(proj, "start_time", "") or "",
            )
            legs.append(leg)

        # Use SlipOptimizer for multi-leg combinations
        optimizer = SlipOptimizer(n_sims=50000)

        # Convert to slip_optimizer Leg format
        optimizer_legs = [
            Leg(
                player_name=leg.player_name,
                stat_type=leg.stat_type,
                line=leg.line,
                probability=leg.probability,
                edge=leg.edge,
                tier=leg.tier,
                side=leg.side,
                start_local=leg.start_local,
            )
            for leg in legs
        ]

        # Optimize
        payout = STANDARD_PAYOUT_POWER if format_type.lower() == "power" else STANDARD_PAYOUT_FLEX

        results = optimizer.optimize_slips(
            legs_pool=optimizer_legs,
            format_type=format_type,
            n_legs=n_legs,
            min_p=min_probability,
            top_k=top_k,
            payout=payout,
        )

        # Convert to PrizePicksSlip
        slips = []
        for i, result in enumerate(results):
            slip_type = f"{format_type.upper()}_{result.n_legs}"
            payout_mult = payout.get((result.n_legs, result.n_legs), 1.0)

            pp_legs = [
                PrizePicksLeg(
                    player_name=leg.player,
                    team=leg.team,
                    opponent=leg.opponent,
                    stat_type=leg.stat_type,
                    line=leg.line,
                    probability=leg.probability,
                    edge=leg.edge,
                    tier=leg.tier,
                    side=leg.side,
                    start_local=leg.start_local,
                )
                for leg in result.legs
            ]

            slip = PrizePicksSlip(
                slip_type=slip_type,
                format_type=format_type,
                n_legs=result.n_legs,
                legs=pp_legs,
                ev=result.ev,
                avg_probability=result.avg_probability,
                payout_multiplier=payout_mult,
                confidence=result.ev * 50 + 50,  # Rough approximation
                rank=i + 1,
            )
            slips.append(slip)

        return slips

    def rank_projections(
        self,
        projections: list,
        market_data: Optional[dict] = None,
        model_probs: Optional[dict] = None,
    ) -> list[EvaluationResult]:
        """Rank projections by expected value.

        Args:
            projections: List of PrizePicks Projection objects
            market_data: Dict mapping projection_id to market odds
            model_probs: Dict mapping projection_id to model probability

        Returns:
            Sorted list of EvaluationResult
        """
        results = []
        for proj in projections:
            result = self.evaluate_projection(
                proj,
                market_odds=market_data.get(proj.id) if market_data else None,
                model_prob=model_probs.get(proj.id) if model_probs else None,
            )
            results.append(result)

        # Sort by EV descending
        return sorted(results, key=lambda x: x.ev, reverse=True)

    def get_best_single_picks(
        self,
        projections: list,
        market_data: Optional[dict] = None,
        model_probs: Optional[dict] = None,
        min_ev: float = 0.05,
        min_confidence: float = 50.0,
    ) -> list[EvaluationResult]:
        """Get the best single-pick recommendations.

        Args:
            projections: List of PrizePicks Projection objects
            market_data: Market odds
            model_probs: Model probabilities
            min_ev: Minimum EV threshold
            min_confidence: Minimum confidence threshold

        Returns:
            Filtered and sorted list of EvaluationResult
        """
        ranked = self.rank_projections(projections, market_data, model_probs)

        return [r for r in ranked if r.ev >= min_ev and r.confidence >= min_confidence]
