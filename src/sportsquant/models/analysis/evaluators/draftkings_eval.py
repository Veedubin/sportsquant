"""DraftKings-specific prop evaluation.

This module provides DraftKings-specific evaluation using the
base engine and DraftKings sportsbook rules.
"""

from typing import Optional

from sportsquant.models.analysis.engine import BaseEvaluator, EvaluationResult


# DraftKings market key to stat type mapping
DK_STAT_TO_NBA_STAT = {
    "player_points": "Points",
    "player_rebounds": "Rebounds",
    "player_assists": "Assists",
    "player_threes": "3-PT Made",
    "player_blocks": "Blocks",
    "player_steals": "Steals",
}


class DraftKingsEvaluator(BaseEvaluator):
    """Evaluate DraftKings player props.

    DraftKings uses standard Over/Under lines with American odds.
    """

    def __init__(
        self,
        model_weight: float = 0.30,
        min_confidence: float = 45.0,
        min_edge: float = 0.03,
        base_kelly: float = 0.25,
    ):
        """Initialize DraftKings evaluator.

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

    def evaluate_projection(
        self,
        projection,
        market_odds: Optional[dict] = None,
        model_prob: Optional[float] = None,
    ) -> EvaluationResult:
        """Evaluate a single DraftKings projection.

        Args:
            projection: DraftKings projection dict with keys:
                - player_name: str
                - stat_type: str (market_key like "player_points")
                - line: float
                - odds_american: int (American odds)
                - odds_decimal: float (decimal odds)
                - outcome_type: str ("over" or "under")
            market_odds: Optional dict with 'over' and 'under' American odds
            model_prob: Model probability override

        Returns:
            EvaluationResult with recommendation
        """
        # Extract data from projection
        player_name = projection.get("player_name", "Unknown")
        market_key = projection.get("stat_type", "") or projection.get("market_key", "")
        line = projection.get("line", 0.0)

        # Get odds
        odds_american = projection.get("odds_american")
        odds_decimal = projection.get("odds_decimal")

        # Convert string odds if needed (DraftKings quirk with Unicode minus sign)
        if isinstance(odds_american, str):
            # Unicode minus sign (U+2212) to ASCII hyphen-minus
            odds_american = int(odds_american.replace("−", "-"))
        if isinstance(odds_decimal, str):
            odds_decimal = float(odds_decimal)

        # Determine recommended side from outcome_type
        outcome_type = projection.get("outcome_type", "") or ""
        is_over = "over" in outcome_type.lower()
        recommended_side = "Over" if is_over else "Under"
        alternative_side = "Under" if is_over else "Over"

        # Calculate market probability from American odds
        if odds_american is not None:
            market_prob = self.american_to_prob(odds_american)
            payout_mult = self.american_to_decimal(odds_american)
        elif odds_decimal is not None:
            payout_mult = odds_decimal
            market_prob = 1.0 / payout_mult
        else:
            # Default -110 equivalent
            payout_mult = 1.91
            market_prob = self.american_to_prob(-110)

        # Breakeven probability
        breakeven_prob = 1.0 / payout_mult if payout_mult > 1 else 0.5

        # Model probability
        if model_prob is None:
            model_prob = projection.get("model_prob", 0.52)

        # Blend model and market in logit space
        final_prob = self.logit_blend(model_prob, market_prob)

        # Calculate edge vs market
        edge = final_prob - market_prob

        # Calculate EV: E[profit] = P(hit) * payout - stake
        # EV = probability * decimal_odds - 1
        ev = final_prob * payout_mult - 1.0

        # Confidence
        confidence = self.calculate_confidence(
            final_prob,
            market_prob,
            sample_size=5,
            edge=edge,
        )

        # Kelly
        kelly_frac = self.kelly_criterion(
            final_prob,
            payout_mult,
            self.base_kelly,
        )

        # Risk
        risk = self.risk_score(final_prob, payout_mult)

        # Map market_key to stat type for display
        stat_type = DK_STAT_TO_NBA_STAT.get(market_key, market_key.replace("player_", "").title())

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
            site="draftkings",
            payout_multiplier=payout_mult,
        )
