"""Underdog Fantasy-specific prop evaluation.

This module provides Underdog-specific evaluation for Higher/Lower props.
Underdog is unique because it includes sportsbook odds in their projections!
"""

from dataclasses import dataclass
from typing import Optional

from quantitative_sports.models.analysis.engine import BaseEvaluator, EvaluationResult
from quantitative_sports.models.analysis.rules.underdog import (
    PICKEM_PAYOUTS,
    DEFAULT_PICKEM_RULES,
    PickemRules,
    calculate_payout,
    calculate_flex_payout,
)


@dataclass
class UnderdogLeg:
    """A leg for Underdog pick building."""

    player_name: str
    team: str
    opponent: str
    stat_type: str
    line: float
    probability: float
    edge: float
    side: str  # "Higher" or "Lower"
    sportsbook_odds: Optional[dict] = None  # May be included in projection!
    start_local: str = ""


@dataclass
class UnderdogEntry:
    """A complete Underdog entry recommendation."""

    entry_type: str  # e.g., "PICKEM_5", "FLEX_8"
    format_type: str  # "pickem" or "flex"
    n_picks: int
    legs: list[UnderdogLeg]
    ev: float
    avg_probability: float
    payout_multiplier: float
    confidence: float
    rank: int = 0

    def legs_description(self) -> str:
        """Human-readable leg descriptions."""
        return " | ".join(
            [
                f"{leg.player_name} {leg.stat_type} {leg.side} {leg.line:g} (p={leg.probability:.3f})"
                for leg in self.legs
            ]
        )


class UnderdogEvaluator(BaseEvaluator):
    """Evaluate Underdog props and recommend Higher/Lower.

    Underdog uses "Higher" and "Lower" terminology.
    Unique feature: sportsbook odds are included in projections!

    This allows direct EV calculation using Underdog's own odds
    without needing external market data.
    """

    def __init__(
        self,
        model_weight: float = 0.30,
        min_confidence: float = 45.0,
        min_edge: float = 0.03,
        base_kelly: float = 0.25,
        rules: Optional[PickemRules] = None,
    ):
        """Initialize Underdog evaluator.

        Args:
            model_weight: Weight given to model probability (0-1)
            min_confidence: Minimum confidence to recommend
            min_edge: Minimum edge to recommend
            base_kelly: Base Kelly fraction
            rules: PickemRules instance
        """
        super().__init__(
            model_weight=model_weight,
            min_confidence=min_confidence,
            min_edge=min_edge,
            base_kelly=base_kelly,
        )
        self.rules = rules or DEFAULT_PICKEM_RULES

    def evaluate_projection(
        self,
        projection,
        sportsbook_odds: Optional[dict] = None,
        model_prob: Optional[float] = None,
        side_override: Optional[str] = None,
    ) -> EvaluationResult:
        """Evaluate a single Underdog projection.

        Args:
            projection: Underdog Projection object with higher_option and lower_option
            sportsbook_odds: Sportsbook odds dict with 'over' and 'under' keys
            model_prob: Model probability override
            side_override: Force a specific side ("Higher" or "Lower")

        Returns:
            EvaluationResult with recommendation
        """
        # Extract data from projection
        player_name = projection.player_name or "Unknown"
        stat_type = projection.stat_display_name or projection.stat_type or "Unknown"
        line = projection.line_score or 0.0

        # Extract sportsbook odds from projection if available
        if projection.sportsbook_odds_higher and not sportsbook_odds:
            sportsbook_odds = {
                "higher": projection.sportsbook_odds_higher,
                "lower": projection.sportsbook_odds_lower,
            }

        # Calculate model probability if not provided
        if model_prob is None:
            model_prob = 0.52  # Default assumption

        # Underdog 5-pick standard payout is 12x (breakeven = 1/12 ≈ 0.083)
        # Most Underdog entries are 5-pick, so use that as default
        payout = 12.0
        breakeven_prob = 1.0 / payout

        # Get market odds or calculate fair probability
        # When no sportsbook data, use 0.50 as neutral anchor (not breakeven)
        if sportsbook_odds:
            higher_odds = self._extract_american_odds(sportsbook_odds.get("higher"))
            lower_odds = self._extract_american_odds(sportsbook_odds.get("lower"))
            if higher_odds:
                market_prob_higher = self.american_to_prob(higher_odds)
            else:
                market_prob_higher = breakeven_prob
            if lower_odds:
                market_prob_lower = self.american_to_prob(lower_odds)
            else:
                market_prob_lower = breakeven_prob
            blend_anchor = market_prob_higher
        else:
            # No market data - use 0.50 as neutral anchor
            market_prob_higher = 0.50
            market_prob_lower = 0.50
            blend_anchor = 0.50

        # Blend probabilities using neutral anchor
        final_prob = self.logit_blend(model_prob, blend_anchor)

        # Calculate EV for both "Higher" and "Lower"
        # P(Higher hits) = final_prob (model thinks player exceeds line)
        # P(Lower hits) = 1 - final_prob (model thinks player stays under line)
        ev_higher = final_prob * payout - 1.0
        ev_lower = (1 - final_prob) * payout - 1.0

        # Determine side by comparing EVs for both sides
        # Underdog has fixed payout for both Higher and Lower
        if side_override:
            recommended_side = side_override
        else:
            # Recommend side with higher EV
            if ev_higher >= ev_lower:
                recommended_side = "Higher"
            else:
                recommended_side = "Lower"

        alternative_side = "Lower" if recommended_side == "Higher" else "Higher"

        # Use the EV of the recommended side
        ev = ev_higher if recommended_side == "Higher" else ev_lower

        # Calculate edge vs market for the recommended side
        if recommended_side == "Higher":
            market_prob = market_prob_higher
        else:
            market_prob = market_prob_lower
        edge = final_prob - market_prob

        # Calculate confidence
        confidence = self.calculate_confidence(
            final_prob,
            market_prob,
            sample_size=5,
            edge=edge,
        )

        # Calculate Kelly
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
            fair_prob=breakeven_prob,
            final_prob=final_prob,
            breakeven_prob=breakeven_prob,
            recommended_side=recommended_side,
            alternative_side=alternative_side,
            edge=edge,
            ev=ev,
            confidence=confidence,
            hit_probability=final_prob,
            kelly_fraction=kelly_frac,
            suggested_stake=kelly_frac,
            risk_score=risk,
            variance=0.0,
            site="underdog",
            payout_multiplier=payout,
        )

    def _get_sportsbook_prob(self, odds_data: Optional[dict]) -> Optional[float]:
        """Extract probability from sportsbook odds data.

        Args:
            odds_data: Sportsbook odds dict

        Returns:
            Implied probability or None
        """
        if not odds_data:
            return None

        # Try different fields
        american = odds_data.get("american")
        if american:
            return self.american_to_prob(float(american))

        decimal = odds_data.get("decimal")
        if decimal:
            try:
                return 1.0 / float(decimal)
            except (ValueError, ZeroDivisionError):
                pass

        return None

    def _extract_american_odds(self, odds_data: Optional[dict]) -> Optional[float]:
        """Extract American odds from sportsbook odds data.

        Args:
            odds_data: Sportsbook odds dict

        Returns:
            American odds or None
        """
        if not odds_data:
            return None

        american = odds_data.get("american")
        if american:
            return float(american)

        return None

    def build_optimal_entries(
        self,
        projections: list,
        sportsbook_data: Optional[dict] = None,
        model_probs: Optional[dict] = None,
        n_picks: int = 5,
        use_flex: bool = False,
        top_k: int = 10,
        min_probability: float = 0.58,
    ) -> list[UnderdogEntry]:
        """Build optimal pick'em entries.

        Args:
            projections: List of Underdog Projection objects
            sportsbook_data: Dict mapping projection_id to sportsbook odds
            model_probs: Dict mapping projection_id to model probability
            n_picks: Number of picks per entry (2-8)
            use_flex: Whether to use FLEX format
            top_k: Number of top entries to return
            min_probability: Minimum probability threshold

        Returns:
            List of UnderdogEntry recommendations
        """
        if not self.rules.is_valid_pick_count(n_picks):
            return []

        # Evaluate projections
        evaluated = []
        for proj in projections:
            sportsbook_odds = sportsbook_data.get(proj.id) if sportsbook_data else None
            model_prob = model_probs.get(proj.id) if model_probs else None

            result = self.evaluate_projection(
                proj,
                sportsbook_odds=sportsbook_odds,
                model_prob=model_prob,
            )

            leg = UnderdogLeg(
                player_name=result.player_name,
                team=getattr(proj, "team_abbreviation", "") or "",
                opponent="",
                stat_type=result.stat_type,
                line=result.line,
                probability=result.final_prob,
                edge=result.edge,
                side=result.recommended_side,
                sportsbook_odds=sportsbook_odds,
                start_local=str(getattr(proj, "scheduled_at", "") or ""),
            )
            evaluated.append((leg, result))

        # Sort by probability (descending)
        evaluated = sorted(evaluated, key=lambda x: x[1].final_prob, reverse=True)

        # Filter by minimum probability
        candidates = [
            (leg, result) for leg, result in evaluated if result.final_prob >= min_probability
        ]

        if len(candidates) < n_picks:
            return []

        # Generate combinations
        from itertools import combinations

        entries = []
        all_combos = list(combinations(candidates, n_picks))

        for combo in all_combos:
            legs = [c[0] for c in combo]
            results = [c[1] for c in combo]

            # Check same team restriction
            teams = [leg.team for leg in legs if leg.team]
            if len(set(teams)) < 2:
                continue

            # Calculate entry EV using Monte Carlo
            ev = self._simulate_entry_ev(legs, use_flex=use_flex)
            avg_prob = sum(r.final_prob for r in results) / len(results)

            # Get payout multiplier
            if use_flex:
                payout_mult = 0.0  # Will be calculated on hits
            else:
                payout_mult = PICKEM_PAYOUTS.get(n_picks, {}).get((n_picks, n_picks), 1.0)

            entry = UnderdogEntry(
                entry_type=f"{'FLEX' if use_flex else 'PICKEM'}_{n_picks}",
                format_type="flex" if use_flex else "pickem",
                n_picks=n_picks,
                legs=legs,
                ev=ev,
                avg_probability=avg_prob,
                payout_multiplier=payout_mult,
                confidence=avg_prob * 100,
            )
            entries.append(entry)

        # Sort by EV and return top k
        entries = sorted(entries, key=lambda x: x.ev, reverse=True)[:top_k]

        for i, entry in enumerate(entries):
            entry.rank = i + 1

        return entries

    def _simulate_entry_ev(
        self,
        legs: list[UnderdogLeg],
        n_sims: int = 100000,
        use_flex: bool = False,
    ) -> float:
        """Simulate entry EV using Monte Carlo.

        Args:
            legs: List of UnderdogLeg objects
            n_sims: Number of simulations
            use_flex: Whether using FLEX format

        Returns:
            Expected value
        """
        import numpy as np

        n = len(legs)
        probs = np.array([leg.probability for leg in legs])

        # Sample hits
        rng = np.random.default_rng(42)
        hits = rng.random(n_sims) < probs  # shape: (n_sims, n)
        k = hits.sum(axis=1)  # hits per simulation

        # Calculate payouts
        payouts = np.zeros(n_sims)
        for i in range(n_sims):
            n_hits = k[i]
            if use_flex:
                payouts[i] = calculate_flex_payout(n, n_hits)
            else:
                payouts[i] = calculate_payout(n, n_hits, flex=False)

        # EV = mean payout - 1 (stake)
        return float(payouts.mean() - 1.0)

    def rank_projections(
        self,
        projections: list,
        sportsbook_data: Optional[dict] = None,
        model_probs: Optional[dict] = None,
    ) -> list[EvaluationResult]:
        """Rank projections by expected value.

        Args:
            projections: List of Underdog Projection objects
            sportsbook_data: Dict mapping projection_id to sportsbook odds
            model_probs: Dict mapping projection_id to model probability

        Returns:
            Sorted list of EvaluationResult
        """
        results = []
        for proj in projections:
            sportsbook_odds = sportsbook_data.get(proj.id) if sportsbook_data else None
            model_prob = model_probs.get(proj.id) if model_probs else None

            result = self.evaluate_projection(
                proj,
                sportsbook_odds=sportsbook_odds,
                model_prob=model_prob,
            )
            results.append(result)

        # Sort by EV descending
        return sorted(results, key=lambda x: x.ev, reverse=True)

    def get_best_single_picks(
        self,
        projections: list,
        sportsbook_data: Optional[dict] = None,
        model_probs: Optional[dict] = None,
        min_ev: float = 0.05,
        min_confidence: float = 50.0,
    ) -> list[EvaluationResult]:
        """Get the best single-pick recommendations.

        Args:
            projections: List of Underdog Projection objects
            sportsbook_data: Sportsbook odds
            model_probs: Model probabilities
            min_ev: Minimum EV threshold
            min_confidence: Minimum confidence threshold

        Returns:
            Filtered and sorted list of EvaluationResult
        """
        ranked = self.rank_projections(projections, sportsbook_data, model_probs)

        return [r for r in ranked if r.ev >= min_ev and r.confidence >= min_confidence]
