"""Alternate line evaluation for props like "10+ Points", "25+ Points".

This module evaluates alternate lines (also called alternate props or alt lines)
where the payout is based on whether a player's stat exceeds a threshold.

Example: "Will Stephen Curry score 25+ points?" at +150 odds
- Calculate P(Steph >= 25 points) from historical data
- Compare to breakeven probability from odds
- Calculate expected value and edge
"""

from dataclasses import dataclass
from typing import Optional

import numpy as np

from .distribution_models import DistributionSelector


def clamp(x: float, lo: float, hi: float) -> float:
    """Clamp value to range [lo, hi]."""
    return max(lo, min(hi, x))


def american_to_decimal(odds: float) -> float:
    """Convert American odds to decimal odds (including stake).

    Args:
        odds: American odds (e.g., -120, +150)

    Returns:
        Decimal odds (e.g., 1.83, 2.50)
    """
    odds = float(odds)
    if odds < 0:
        return abs(odds) / abs(odds) + 100.0 / abs(odds)
    return odds / 100.0 + 1.0


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


@dataclass
class AlternateLineResult:
    """Result of evaluating an alternate line prop."""

    player_name: str
    stat_type: str
    threshold: float

    # Probabilities
    model_probability: float
    breakeven_probability: float

    # EV calculations
    ev_percent: float
    edge: float

    # Confidence and quality
    confidence: float
    recommended: bool
    distribution_type: str
    sample_size: int
    historical_hit_rate: float

    # Additional metadata
    payout_multiplier: float = 1.0
    odds: float = 0.0
    fit_quality: float = 0.0


class AlternateLineEvaluator:
    """Evaluate alternate lines like "10+ Points", "25+ Points".

    An alternate line prop asks "Will player achieve X or more of stat Y?"
    at given odds. For example, "Will Jayson Tatum score 30+ points?" at +200.

    The evaluator:
    1. Models the probability distribution of the player's stat
    2. Calculates P(stat >= threshold) from the distribution
    3. Compares to breakeven probability from odds
    4. Calculates expected value and edge
    5. Scores confidence based on multiple factors
    """

    def __init__(
        self,
        player_history: list[dict],
        stat_type: str,
        player_name: str = "Unknown Player",
    ):
        """Initialize alternate line evaluator.

        Args:
            player_history: List of game log dicts with stat values.
                           Each dict should have the stat as a key with numeric value.
                           Example: [{"points": 28}, {"points": 35}, ...]
                           or [{"player_points": 28}, ...]
            stat_type: Canonical stat key (e.g., "player_points", "rebounds")
                      The stat_type will be used to find the stat value in each dict.
            player_name: Name of the player for display purposes
        """
        self.player_name = player_name
        self.stat_type = stat_type
        self.player_history = player_history
        self.observations: list[float] = []
        self._distribution: Optional[DistributionSelector] = None

        # Extract observations from game logs
        self._extract_observations()

        # Fit distribution if we have data
        if self.observations:
            # Try to find stat key variations
            self._distribution = DistributionSelector(self.observations, stat_type=stat_type)

    def _extract_observations(self) -> None:
        """Extract stat values from game logs into observations list."""
        if not self.player_history:
            return

        # Try different stat key formats
        stat_keys_to_try = [
            self.stat_type,
            self.stat_type.replace("_", ""),
            self.stat_type.replace("player_", ""),
            self.stat_type.replace("player", "").lower(),
        ]

        # Add common variations
        stat_lower = self.stat_type.lower()
        if "points" in stat_lower or "pts" in stat_lower:
            stat_keys_to_try.extend(["points", "pts", "Points", "PTS", "player_points"])
        if "rebounds" in stat_lower or "reb" in stat_lower:
            stat_keys_to_try.extend(["rebounds", "reb", "Rebounds", "REB"])
        if "assists" in stat_lower or "ast" in stat_lower:
            stat_keys_to_try.extend(["assists", "ast", "Assists", "AST"])
        if "steals" in stat_lower or "stl" in stat_lower:
            stat_keys_to_try.extend(["steals", "stl", "Steals", "STL"])
        if "blocks" in stat_lower or "blk" in stat_lower:
            stat_keys_to_try.extend(["blocks", "blk", "Blocks", "BLK"])

        # Deduplicate
        stat_keys_to_try = list(dict.fromkeys(stat_keys_to_try))

        for game_log in self.player_history:
            value = None

            # Handle plain int/float format: [10, 15, 20, ...]
            if isinstance(game_log, (int, float)):
                try:
                    value = float(game_log)
                    self.observations.append(value)
                    continue
                except (ValueError, TypeError):
                    continue

            # Handle dict format: [{"PTS": 10}, {"PTS": 15}, ...]
            if not isinstance(game_log, dict):
                continue

            # Try each key format
            for key in stat_keys_to_try:
                if key in game_log:
                    try:
                        value = float(game_log[key])
                        break
                    except (ValueError, TypeError):
                        continue

            # If still no value, try case-insensitive search
            if value is None:
                for key, val in game_log.items():
                    if isinstance(val, (int, float)) and any(
                        sk in key.lower() for sk in ["points", "pts", "reb", "ast"]
                    ):
                        try:
                            value = float(val)
                            break
                        except (ValueError, TypeError):
                            continue

            if value is not None:
                self.observations.append(value)

    @property
    def sample_size(self) -> int:
        """Return number of observations."""
        return len(self.observations)

    @property
    def has_data(self) -> bool:
        """Return whether we have sufficient data."""
        return self.sample_size >= 3

    def evaluate(
        self,
        threshold: float,
        odds: float,
        vig_adjustment: bool = False,
    ) -> Optional[AlternateLineResult]:
        """Evaluate an alternate line prop.

        Args:
            threshold: The line (e.g., 10.0 for "10+ points")
            odds: American odds (e.g., -120, +150)
            vig_adjustment: Whether to remove vig from odds (default False)

        Returns:
            AlternateLineResult with all calculations, or None if insufficient data
        """
        if not self.has_data:
            return None

        if self._distribution is None:
            return None

        # Handle edge cases for threshold
        if threshold <= 0:
            return AlternateLineResult(
                player_name=self.player_name,
                stat_type=self.stat_type,
                threshold=threshold,
                model_probability=1.0,
                breakeven_probability=american_to_prob(odds),
                ev_percent=100.0,
                edge=1.0 - american_to_prob(odds),
                confidence=100.0,
                recommended=True,
                distribution_type="edge_case",
                sample_size=self.sample_size,
                historical_hit_rate=1.0,
                payout_multiplier=american_to_decimal(odds),
                odds=odds,
            )

        # Check if threshold is beyond all observed data
        all_above = all(obs >= threshold for obs in self.observations)
        all_below = all(obs < threshold for obs in self.observations)

        # Calculate model probability
        model_prob = self._distribution.probability(threshold)

        # Calculate breakeven probability
        decimal_odds = american_to_decimal(odds)
        breakeven = 1.0 / decimal_odds

        # Calculate EV
        # payout = decimal_odds - 1 (profit per unit staked)
        payout = decimal_odds - 1.0
        ev = (model_prob * payout) - (1.0 - model_prob)
        ev_percent = ev * 100.0

        # Calculate edge
        edge = model_prob - breakeven

        # Calculate confidence score
        confidence = self._calculate_confidence(
            model_prob=model_prob,
            threshold=threshold,
            all_above=all_above,
            all_below=all_below,
        )

        # Historical hit rate
        hist_hit_rate = self._distribution.historical_hit_rate(threshold)

        # Get distribution type
        dist_type = self._distribution.get_selected_type()

        # Recommended if positive EV and confidence above minimum threshold
        recommended = ev > 0 and confidence >= 0.30

        # If all observations are at extreme relative to threshold,
        # deprecate confidence
        if all_above or all_below:
            confidence *= 0.7

        return AlternateLineResult(
            player_name=self.player_name,
            stat_type=self.stat_type,
            threshold=threshold,
            model_probability=model_prob,
            breakeven_probability=breakeven,
            ev_percent=ev_percent,
            edge=edge,
            confidence=confidence,
            recommended=recommended,
            distribution_type=dist_type,
            sample_size=self.sample_size,
            historical_hit_rate=hist_hit_rate,
            payout_multiplier=decimal_odds,
            odds=odds,
            fit_quality=self._distribution.get_fit_quality(),
        )

    def _calculate_confidence(
        self,
        model_prob: float,
        threshold: float,
        all_above: bool,
        all_below: bool,
    ) -> float:
        """Calculate confidence score (0-1) for the evaluation.

        Confidence scoring components:
        - sample_size_weight (30%): More games = higher confidence
        - variance_weight (20%): Lower CV = higher confidence
        - threshold_frequency_weight (20%): More hits at this threshold = higher confidence
        - distribution_fit_weight (30%): Better KS test = higher confidence

        Args:
            model_prob: Model probability P(X >= threshold)
            threshold: The threshold value
            all_above: Whether all observations are above threshold
            all_below: Whether all observations are below threshold

        Returns:
            Confidence score (0-1)
        """
        if not self._distribution:
            return 0.0

        # 1. Sample size weight (30% of confidence)
        # Scale from 0 (3 games) to 0.3 (30+ games)
        n = self.sample_size
        sample_score = clamp((n - 3) / 27, 0.0, 1.0) * 0.30

        # 2. Variance weight (20% of confidence)
        # Lower coefficient of variation = higher confidence
        cv = self._distribution.coefficient_of_variation()
        # CV typically ranges from 0.1 to 2.0
        # Lower CV = more consistent performance = higher confidence
        variance_score = clamp((2.0 - cv) / 1.9, 0.0, 1.0) * 0.20

        # 3. Threshold frequency weight (20% of confidence)
        # How often does this player hit this threshold historically?
        hist_hit = self._distribution.historical_hit_rate(threshold)
        # Not too extreme (0% or 100%), not around 50%
        # Best: 20-80% range indicates signal
        frequency_score = clamp(min(hist_hit, 1.0 - hist_hit) * 5, 0.0, 1.0) * 0.20

        # 4. Distribution fit weight (30% of confidence)
        fit_score = self._distribution.get_fit_quality() * 0.30

        total_confidence = sample_score + variance_score + frequency_score + fit_score

        return round(clamp(total_confidence, 0.0, 1.0), 3)

    def evaluate_multiple_thresholds(
        self,
        thresholds: list[float],
        odds_map: dict[float, float],
    ) -> list[AlternateLineResult]:
        """Evaluate multiple alternate lines for the same player/stat.

        Args:
            thresholds: List of thresholds to evaluate
            odds_map: Dict mapping threshold to American odds
                     e.g., {10.0: -120, 15.0: +150, 20.0: +300}

        Returns:
            List of AlternateLineResult sorted by EV descending
        """
        results = []
        for threshold in thresholds:
            odds = odds_map.get(threshold)
            if odds is None:
                continue

            result = self.evaluate(threshold, odds)
            if result is not None:
                results.append(result)

        # Sort by EV descending
        results.sort(key=lambda r: r.ev_percent, reverse=True)
        return results

    def get_probability_at_threshold(self, threshold: float) -> float:
        """Get probability that player exceeds threshold.

        Args:
            threshold: The threshold value

        Returns:
            Probability P(X >= threshold)
        """
        if not self._distribution:
            return 0.5
        return self._distribution.probability(threshold)

    def get_distribution_summary(self) -> dict:
        """Get summary statistics about the fitted distribution.

        Returns:
            Dict with distribution statistics
        """
        if not self._distribution:
            return {"error": "No distribution fitted"}

        obs = np.array(self.observations)

        return {
            "distribution_type": self._distribution.get_selected_type(),
            "sample_size": self.sample_size,
            "mean": float(obs.mean()),
            "std": float(obs.std()),
            "min": float(obs.min()),
            "max": float(obs.max()),
            "cv": float(self._distribution.coefficient_of_variation()),
            "fit_quality": float(self._distribution.get_fit_quality()),
        }


# Convenience function for quick evaluation
def quick_evaluate(
    observations: list[float],
    threshold: float,
    odds: float,
    stat_type: str = "stat",
    player_name: str = "Player",
) -> Optional[AlternateLineResult]:
    """Quickly evaluate an alternate line from a list of observations.

    Args:
        observations: List of historical stat values
        threshold: The line (e.g., 10.0 for "10+")
        odds: American odds (e.g., -120, +150)
        stat_type: Stat type for distribution selection
        player_name: Player name for display

    Returns:
        AlternateLineResult or None
    """
    # Convert to game log format
    game_logs = [{stat_type: obs} for obs in observations]

    evaluator = AlternateLineEvaluator(
        player_history=game_logs,
        stat_type=stat_type,
        player_name=player_name,
    )

    return evaluator.evaluate(threshold, odds)
