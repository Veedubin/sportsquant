"""FanDuel DFS-specific evaluation.

This module provides FanDuel-specific evaluation for DFS lineups
and Picks format recommendations.
"""

from dataclasses import dataclass
from typing import Optional

from quantitative_sports.models.analysis.engine import BaseEvaluator, EvaluationResult
from quantitative_sports.models.analysis.rules.fanduel import (
    calculate_fanduel_points,
    get_salary_cap,
    validate_picks,
    PICKS_FORMAT,
)


@dataclass
class FanDuelPlayer:
    """A player for lineup building."""

    name: str
    position: str
    salary: int
    projected_points: float
    team: str = ""
    opponent: str = ""
    injury_status: str = ""


@dataclass
class FanDuelLineup:
    """A complete FanDuel lineup recommendation."""

    players: list[FanDuelPlayer]
    total_salary: int
    projected_points: float
    projected_ownership: float = 0.0
    entry_type: str = "tournament"
    confidence: float = 0.0
    rank: int = 0

    def is_valid(self, sport: str = "NBA") -> bool:
        """Check if lineup is valid."""
        cap = get_salary_cap(sport)
        return self.total_salary <= cap


@dataclass
class FanDuelPick:
    """A single pick in FanDuel Picks format."""

    player_name: str
    team: str
    stat_type: str
    line: float
    side: str  # "Yes" or "No" for Picks format
    confidence: float
    projected_odds: Optional[float] = None


class FanDuelEvaluator(BaseEvaluator):
    """Evaluate FanDuel DFS picks and lineup recommendations.

    FanDuel has two main formats:
    1. DFS Lineups - salary cap based, roster players
    2. Picks - pick correct outcomes (similar to parlay)
    """

    def __init__(
        self,
        model_weight: float = 0.30,
        min_confidence: float = 45.0,
        min_edge: float = 0.03,
        base_kelly: float = 0.25,
        sport: str = "NBA",
    ):
        """Initialize FanDuel evaluator.

        Args:
            model_weight: Weight given to model probability (0-1)
            min_confidence: Minimum confidence to recommend
            min_edge: Minimum edge to recommend
            base_kelly: Base Kelly fraction
            sport: Sport being evaluated
        """
        super().__init__(
            model_weight=model_weight,
            min_confidence=min_confidence,
            min_edge=min_edge,
            base_kelly=base_kelly,
        )
        self.sport = sport

    def evaluate_projection(self, projection, **kwargs) -> EvaluationResult:
        """Evaluate a projection (abstract method implementation).

        Args:
            projection: FanDuel projection data (dict-like)
            **kwargs: Additional arguments including model_prob and market_odds

        Returns:
            EvaluationResult with recommendation
        """
        # Delegate to evaluate_player_prop with kwargs
        return self.evaluate_player_prop(
            projection,
            market_odds=kwargs.get("market_odds"),
            model_prob=kwargs.get("model_prob"),
        )

    def evaluate_player_prop(
        self,
        player_data: dict,
        market_odds: Optional[dict] = None,
        model_prob: Optional[float] = None,
    ) -> EvaluationResult:
        """Evaluate a player prop on FanDuel.

        Args:
            player_data: Dict with player info
            market_odds: Market odds dict
            model_prob: Model probability override

        Returns:
            EvaluationResult with recommendation
        """
        player_name = player_data.get("name", "Unknown")
        stat_type = player_data.get("stat_type", "Points")
        line = player_data.get("line", 0.0)

        # FanDuel market-based payout (from sportsbook odds)
        # If no market odds, use -110 equivalent (1.91)
        if market_odds:
            over_odds = market_odds.get("over", -110)
            under_odds = market_odds.get("under", -110)
            implied_over = self.american_to_prob(over_odds)
            implied_under = self.american_to_prob(under_odds)
            market_prob = self.remove_vig(implied_over, implied_under)
            payout_mult = self.american_to_decimal(over_odds)
        else:
            market_prob = None  # No market data
            payout_mult = 1.91  # Default -110 equivalent
            implied_over = self.american_to_prob(-110)
            implied_under = self.american_to_prob(-110)
            market_prob_ref = self.remove_vig(implied_over, implied_under)

        # Breakeven for market payout
        breakeven_prob = 1.0 / payout_mult

        # Model probability
        if model_prob is None:
            model_prob = player_data.get("projected_prob", 0.52)

        # Blend
        if market_prob is not None:
            final_prob = self.logit_blend(model_prob, market_prob)
        else:
            final_prob = self.logit_blend(model_prob, 0.5)

        # Determine side
        recommended_side = "Over" if final_prob > 0.5 else "Under"
        alternative_side = "Under" if recommended_side == "Over" else "Over"

        # Edge and EV
        if market_prob is not None:
            edge = final_prob - market_prob
        else:
            edge = final_prob - breakeven_prob

        ev = final_prob * payout_mult - 1.0

        # Confidence
        confidence = self.calculate_confidence(
            final_prob,
            market_prob if market_prob is not None else breakeven_prob,
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

        return EvaluationResult(
            player_name=player_name,
            stat_type=stat_type,
            line=line,
            model_prob=model_prob,
            market_prob=market_prob if market_prob is not None else market_prob_ref,
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
            site="fanduel",
            payout_multiplier=payout_mult,
        )

    def build_optimal_lineup(
        self,
        pool: list[FanDuelPlayer],
        salary_cap: Optional[int] = None,
        positions_required: Optional[dict] = None,
        entry_type: str = "tournament",
    ) -> FanDuelLineup:
        """Build optimal DFS lineup within salary cap.

        Uses a greedy algorithm with projected points per salary.

        Args:
            pool: List of FanDuelPlayer objects
            salary_cap: Salary cap (uses sport default if None)
            positions_required: Dict of position -> count
            entry_type: Type of contest

        Returns:
            FanDuelLineup recommendation
        """
        if not pool:
            return FanDuelLineup([], 0, 0.0)

        sport_cap = salary_cap or get_salary_cap(self.sport)

        # Sort by value (projected points / salary)
        sorted_pool = sorted(
            pool,
            key=lambda p: p.projected_points / max(p.salary, 1),
            reverse=True,
        )

        lineup = []
        total_salary = 0
        projected_points = 0.0

        for player in sorted_pool:
            if total_salary + player.salary <= sport_cap:
                lineup.append(player)
                total_salary += player.salary
                projected_points += player.projected_points

        return FanDuelLineup(
            players=lineup,
            total_salary=total_salary,
            projected_points=projected_points,
            entry_type=entry_type,
            confidence=projected_points / 300.0
            if self.sport == "NBA"
            else projected_points / 200.0,
        )

    def evaluate_picks(
        self,
        picks: list[FanDuelPick],
        market_odds: Optional[dict] = None,
        model_probs: Optional[dict] = None,
    ) -> dict:
        """Evaluate FanDuel Picks format.

        FanDuel Picks is a pick-based format similar to parlays.

        Args:
            picks: List of FanDuelPick objects
            market_odds: Dict mapping pick index to odds
            model_probs: Dict mapping pick index to model probability

        Returns:
            Dict with evaluation results
        """
        n_picks = len(picks)

        # Validate picks
        is_valid, error = validate_picks(picks, sport=self.sport)
        if not is_valid:
            return {
                "is_valid": False,
                "error": error,
                "ev": 0.0,
                "confidence": 0.0,
            }

        # Calculate individual probabilities
        probs = []
        for i, pick in enumerate(picks):
            model_prob = model_probs.get(i) if model_probs else None
            if model_prob is None:
                model_prob = 0.52

            market_prob = 0.5
            if market_odds:
                odds = market_odds.get(i, -110)
                market_prob = self.american_to_prob(odds)

            final_prob = self.logit_blend(model_prob, market_prob)
            probs.append(final_prob)

        # Calculate combined EV using Monte Carlo
        import numpy as np

        n_sims = 100000
        rng = np.random.default_rng(42)

        all_hits = rng.random((n_sims, n_picks)) < np.array(probs)
        n_hits = all_hits.sum(axis=1)

        # Calculate payouts
        payouts = np.zeros(n_sims)
        structure = PICKS_FORMAT.get(self.sport, PICKS_FORMAT["NBA"])
        payout_table = structure.get("payout_structure", {}).get(n_picks, {})

        for i in range(n_sims):
            nh = n_hits[i]
            payouts[i] = payout_table.get(nh, 0.0)

        ev = float(payouts.mean() - 1.0)
        avg_prob = sum(probs) / len(probs)
        confidence = avg_prob * 100

        # Determine if recommended
        recommended = ev > 0.05 and confidence > 50

        return {
            "is_valid": True,
            "error": "",
            "n_picks": n_picks,
            "probabilities": probs,
            "avg_probability": avg_prob,
            "projected_hits": sum(probs),
            "ev": ev,
            "confidence": confidence,
            "recommended": recommended,
            "payout_structure": payout_table,
        }

    def calculate_projections_from_stats(
        self,
        stats: dict,
        sport: Optional[str] = None,
    ) -> float:
        """Calculate FanDuel projected points from raw stats.

        Args:
            stats: Dict of stat -> value
            sport: Sport (uses self.sport if None)

        Returns:
            Projected FanDuel points
        """
        sport = sport or self.sport
        return calculate_fanduel_points(stats, sport)

    def get_salary_efficiency(
        self,
        player: FanDuelPlayer,
        ceiling: Optional[float] = None,
    ) -> float:
        """Calculate salary efficiency metric.

        Args:
            player: FanDuelPlayer
            ceiling: Optional ceiling projection

        Returns:
            Points per $1000 salary
        """
        base_points = player.projected_points
        if ceiling:
            # Blend ceiling with base
            projected = 0.7 * base_points + 0.3 * ceiling
        else:
            projected = base_points

        return projected / (player.salary / 1000.0)

    def get_ownership_boost(
        self,
        projected_ownership: float,
        field_size: int = 10000,
    ) -> float:
        """Calculate ownership boost factor.

        In GPPs, lower ownership can significantly boost value.

        Args:
            projected_ownership: Expected ownership %
            field_size: Number of entries in contest

        Returns:
            Multiplier for EV calculation
        """
        # Lower ownership = higher boost
        base = 1.0
        if projected_ownership < 0.05:
            return base * 1.2
        elif projected_ownership < 0.10:
            return base * 1.1
        elif projected_ownership < 0.20:
            return base
        elif projected_ownership < 0.30:
            return base * 0.95
        else:
            return base * 0.85
