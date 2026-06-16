"""
Bayesian Player Priors

Implements Bayesian prior calculations for player projections based on:
1. Position-specific statistical baselines
2. Experience and reliability adjustments
3. Matchup context and opponent strength

Data Sources:
- Player info: TimescaleDB (player_info table)
- Game data: Kafka topic 'sports-analytics-player-stats'
- Opponent strength: Apache Ignite cache
- Schedule: Kafka topic 'sports-schedules'

Usage:
    >>> from sportsquant.models.ratings.bayesian_priors import BayesianPlayerPrior
    >>> prior = BayesianPlayerPrior()
    >>> posterior = prior.compute_full_posterior(request)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


StatType = Literal["pts", "reb", "ast", "pra", "stl", "blk", "to", "fg_pct", "3pt_pct", "ft_pct"]


@dataclass(frozen=True)
class PlayerPriorConfig:
    """Configuration for Bayesian player priors.

    This configuration controls how much weight to apply to different
    prior sources when computing Bayesian player projections.

    Data Sources:
    - Player info: TimescaleDB (player_info table)
    - Game data: Kafka topic 'sports-analytics-player-stats'
    - Opponent strength: Apache Ignite cache
    """

    position_prior_weight: float = 0.3
    experience_prior_weight: float = 0.2
    matchup_prior_weight: float = 0.15
    league_avg_baseline: float = 0.5
    min_games_for_likelihood: int = 10
    shrinkage_lambda: float = 0.3


@dataclass(frozen=True)
class PlayerPriorRequest:
    """Request for computing player prior probability.

    Contains all the context needed to compute a Bayesian prior for a
    player's expected performance in an upcoming game.

    Attributes:
        position: Player position (PG, SG, SF, PF, C).
        years_experience: Number of years of NBA experience.
        stat_type: Type of statistic to compute prior for.
        career_avg: Player's career average for this stat.
        opponent_team: Opponent team abbreviation, if applicable.
        historical_vs_opponent: Historical average vs this opponent.
    """

    position: str
    years_experience: int
    stat_type: StatType
    career_avg: float
    opponent_team: str | None = None
    historical_vs_opponent: float | None = None


@dataclass(frozen=True)
class PlayerPosteriorRequest:
    """Request for computing full player posterior.

    Extends a prior request with recent performance data to compute
    a posterior estimate using Bayesian updating.

    Attributes:
        prior_request: The prior request with player context.
        recent_avg: Player's average over recent games.
        n_recent_games: Number of recent games in the average.
    """

    prior_request: PlayerPriorRequest
    recent_avg: float
    n_recent_games: int


@dataclass(frozen=True)
class PositionPriorConfig:
    """Position-specific statistics baseline storing stat weights."""

    stats: dict[StatType, float]

    def get(self, stat_type: StatType, default: float = 0.5) -> float:
        """Fetch stored baseline for a stat with a safe default."""
        return self.stats.get(stat_type, default)


class PositionPriorGenerator:
    """Generate priors based on player position.

    Uses position-specific statistical baselines to inform
    prior probabilities for player performance projections.

    All calculation logic is preserved from the original implementation.
    """

    _POSITION_STATS: dict[str, PositionPriorConfig] = {
        "PG": PositionPriorConfig(
            stats={
                "pts": 0.4,
                "reb": 0.35,
                "ast": 0.75,
                "pra": 0.55,
                "stl": 0.5,
                "blk": 0.25,
                "to": 0.55,
                "fg_pct": 0.45,
                "3pt_pct": 0.45,
                "ft_pct": 0.75,
            }
        ),
        "SG": PositionPriorConfig(
            stats={
                "pts": 0.55,
                "reb": 0.4,
                "ast": 0.5,
                "pra": 0.5,
                "stl": 0.45,
                "blk": 0.3,
                "to": 0.5,
                "fg_pct": 0.48,
                "3pt_pct": 0.45,
                "ft_pct": 0.75,
            }
        ),
        "SF": PositionPriorConfig(
            stats={
                "pts": 0.5,
                "reb": 0.5,
                "ast": 0.45,
                "pra": 0.5,
                "stl": 0.45,
                "blk": 0.4,
                "to": 0.45,
                "fg_pct": 0.48,
                "3pt_pct": 0.45,
                "ft_pct": 0.75,
            }
        ),
        "PF": PositionPriorConfig(
            stats={
                "pts": 0.5,
                "reb": 0.65,
                "ast": 0.35,
                "pra": 0.55,
                "stl": 0.4,
                "blk": 0.55,
                "to": 0.4,
                "fg_pct": 0.5,
                "3pt_pct": 0.45,
                "ft_pct": 0.75,
            }
        ),
        "C": PositionPriorConfig(
            stats={
                "pts": 0.55,
                "reb": 0.75,
                "ast": 0.3,
                "pra": 0.55,
                "stl": 0.35,
                "blk": 0.7,
                "to": 0.35,
                "fg_pct": 0.55,
                "3pt_pct": 0.45,
                "ft_pct": 0.75,
            }
        ),
    }

    def __init__(self, position_stats: dict[str, float] | None = None) -> None:
        """Initialize position prior generator.

        Args:
            position_stats: Optional custom position statistics mapping.
        """
        self._custom_position_stats = position_stats

    def get_position_prior(self, position: str, stat_type: StatType) -> float:
        """Get prior for player at position for specific stat.

        Args:
            position: Player position (PG, SG, SF, PF, C).
            stat_type: Type of statistic to get prior for.

        Returns:
            Prior probability value between 0 and 1.
        """
        if position not in self._POSITION_STATS:
            available = ", ".join(sorted(self._POSITION_STATS.keys()))
            raise ValueError(f"Unknown position '{position}'. Available: {available}")

        pos_config = self._POSITION_STATS[position]
        return pos_config.get(stat_type)

    def get_default_positions(self) -> list[str]:
        """Get list of supported positions."""
        return list(self._POSITION_STATS.keys())


class ExperiencePriorGenerator:
    """Generate priors based on years of experience.

    Veterans are generally more reliable and have less variance
    in their performance, while rookies need more prior shrinkage
    toward league averages.
    """

    # pylint: disable=too-few-public-methods

    _EXPERIENCE_CURVE: dict[int, float] = {
        0: 0.6,
        1: 0.7,
        2: 0.8,
        3: 0.85,
        4: 0.9,
        5: 0.92,
        6: 0.94,
        7: 0.95,
        8: 0.96,
        9: 0.97,
        10: 0.98,
    }

    def get_experience_prior(
        self,
        years_experience: int,
        stat_type: StatType,
        career_avg: float,
    ) -> float:
        """Calculate prior based on experience and career average.

        Args:
            years_experience: Number of years in NBA.
            stat_type: Type of statistic.
            career_avg: Player's career average for this stat.

        Returns:
            Experience-adjusted prior value.
        """
        if years_experience < 0:
            raise ValueError(f"Years of experience {years_experience} cannot be negative")

        reliability = self._get_reliability_factor(years_experience)

        stat_volatility_map: dict[StatType, float] = {
            "pts": 1.0,
            "reb": 0.9,
            "ast": 1.1,
            "pra": 1.0,
            "stl": 1.3,
            "blk": 1.2,
            "to": 1.1,
            "fg_pct": 0.8,
            "3pt_pct": 0.9,
            "ft_pct": 0.7,
        }

        volatility_adjustment = stat_volatility_map.get(stat_type, 1.0)

        reliability_adjusted = reliability**volatility_adjustment

        prior = reliability_adjusted * career_avg + (1 - reliability_adjusted) * 0.5

        return max(0.0, min(1.0, prior))

    def _get_reliability_factor(self, years_experience: int) -> float:
        """Get reliability factor based on experience.

        Args:
            years_experience: Number of years in NBA.

        Returns:
            Reliability factor between 0 and 1.
        """
        if years_experience >= 10:
            return self._EXPERIENCE_CURVE[10]

        if years_experience in self._EXPERIENCE_CURVE:
            return self._EXPERIENCE_CURVE[years_experience]

        for exp in sorted(self._EXPERIENCE_CURVE.keys(), reverse=True):
            if years_experience >= exp:
                return self._EXPERIENCE_CURVE[exp]

        return self._EXPERIENCE_CURVE[0]


class MatchupPriorGenerator:
    """Generate priors based on matchup context.

    Adjusts prior probabilities based on opponent defensive ratings
    and historical performance against specific opponents.
    """

    # pylint: disable=too-few-public-methods

    def __init__(
        self,
        opponent_ratings: dict[str, float] | None = None,
        league_avg_def_rating: float = 112.0,
    ) -> None:
        """Initialize matchup prior generator.

        Args:
            opponent_ratings: Dictionary of opponent defensive ratings.
            league_avg_def_rating: League average defensive rating.
        """
        self._opponent_ratings = opponent_ratings if opponent_ratings is not None else {}
        self._league_avg_def_rating = league_avg_def_rating

    def get_matchup_prior(
        self,
        _player_team: str,
        opponent_team: str,
        stat_type: StatType,
        historical_avg: float,
    ) -> float:
        """Calculate prior based on matchup context.

        Args:
            _player_team: Player's team abbreviation (unused, for API compatibility).
            opponent_team: Opponent's team abbreviation.
            stat_type: Type of statistic.
            historical_avg: Player's historical average for this stat.

        Returns:
            Matchup-adjusted prior value.
        """
        if not 0.0 <= historical_avg <= 1.0:
            raise ValueError(f"Historical average {historical_avg} must be between 0 and 1")

        def_rating = self._get_opponent_def_rating(opponent_team)
        def_adjustment = self._calculate_def_adjustment(def_rating, stat_type)

        prior = historical_avg * def_adjustment

        return max(0.0, min(1.0, prior))

    def _get_opponent_def_rating(self, opponent_team: str) -> float:
        """Get opponent defensive rating.

        Args:
            opponent_team: Team abbreviation.

        Returns:
            Defensive rating or league average if unknown.
        """
        return self._opponent_ratings.get(opponent_team, self._league_avg_def_rating)

    def _calculate_def_adjustment(self, def_rating: float, stat_type: StatType) -> float:
        """Calculate adjustment factor based on defensive rating.

        Args:
            def_rating: Opponent defensive rating.
            stat_type: Type of statistic.

        Returns:
            Adjustment factor between 0.5 and 1.5.
        """
        rating_diff = def_rating - self._league_avg_def_rating
        rating_factor = 1.0 + (rating_diff / self._league_avg_def_rating)

        stat_sensitivity_map: dict[StatType, float] = {
            "pts": 1.0,
            "reb": 0.7,
            "ast": 0.6,
            "pra": 0.85,
            "stl": 0.5,
            "blk": 0.6,
            "to": 0.8,
            "fg_pct": 0.9,
            "3pt_pct": 0.85,
            "ft_pct": 0.7,
        }

        sensitivity = stat_sensitivity_map.get(stat_type, 1.0)

        adjustment = rating_factor**sensitivity

        return max(0.5, min(1.5, adjustment))


class BayesianPlayerPrior:
    """Main Bayesian prior calculator for player projections.

    Combines multiple prior sources (position, experience, matchup)
    with likelihood from observed data to compute posterior estimates.

    All calculation logic is preserved from the original implementation.
    Data sources have been adapted to use TimescaleDB and Kafka instead of Redis.
    """

    def __init__(self, config: PlayerPriorConfig | None = None) -> None:
        """Initialize Bayesian player prior calculator.

        Args:
            config: Optional configuration for prior calculations.
        """
        self.config = config if config is not None else PlayerPriorConfig()

        self._position_generator = PositionPriorGenerator()
        self._experience_generator = ExperiencePriorGenerator()
        self._matchup_generator = MatchupPriorGenerator()

    def compute_prior(self, request: PlayerPriorRequest) -> float:
        """Compute combined prior from all sources.

        Args:
            request: Prior request describing player context.

        Returns:
            Combined prior probability.
        """
        position_prior = self._position_generator.get_position_prior(
            request.position, request.stat_type
        )

        experience_prior = self._experience_generator.get_experience_prior(
            request.years_experience, request.stat_type, request.career_avg
        )

        weights = [
            self.config.position_prior_weight,
            self.config.experience_prior_weight,
        ]
        priors = [position_prior, experience_prior]

        if request.opponent_team is not None and request.historical_vs_opponent is not None:
            matchup_prior = self._matchup_generator.get_matchup_prior(
                "TEAM",
                request.opponent_team,
                request.stat_type,
                request.historical_vs_opponent,
            )
            weights.append(self.config.matchup_prior_weight)
            priors.append(matchup_prior)

        return self.combine_priors(*priors, weights=weights)

    def compute_posterior(
        self,
        prior: float,
        likelihood: float,
        n_observations: int,
    ) -> float:
        """Compute posterior using Bayesian update.

        Args:
            prior: Prior probability.
            likelihood: Likelihood from observed data.
            n_observations: Number of observations supporting likelihood.

        Returns:
            Posterior probability.
        """
        if n_observations < 0:
            raise ValueError(f"n_observations {n_observations} cannot be negative")

        if n_observations == 0:
            return prior

        if n_observations < self.config.min_games_for_likelihood:
            shrinkage = self.shrinkage_factor(n_observations)
            posterior = shrinkage * prior + (1 - shrinkage) * likelihood
        else:
            evidence_weight = min(n_observations / 50.0, 1.0)
            posterior = evidence_weight * likelihood + (1 - evidence_weight) * prior

        return max(0.0, min(1.0, posterior))

    def shrinkage_factor(self, n_observations: int) -> float:
        """Calculate shrinkage factor toward prior based on sample size.

        Args:
            n_observations: Number of observations.

        Returns:
            Shrinkage factor between 0 and 1.
        """
        if n_observations <= 0:
            return 1.0

        return 1.0 / (1.0 + self.config.shrinkage_lambda * n_observations)

    def combine_priors(self, *priors: float, weights: list[float]) -> float:
        """Combine multiple prior sources with weights.

        Args:
            priors: Prior values to combine.
            weights: Weights for each prior.

        Returns:
            Weighted combination of priors.
        """
        if len(priors) != len(weights):
            raise ValueError(
                f"Number of priors ({len(priors)}) != number of weights ({len(weights)})"
            )

        if len(priors) == 0:
            return self.config.league_avg_baseline

        total_weight = sum(weights)

        if total_weight == 0:
            return self.config.league_avg_baseline

        combined = sum(p * w for p, w in zip(priors, weights)) / total_weight

        return max(0.0, min(1.0, combined))

    def compute_full_posterior(self, request: PlayerPosteriorRequest) -> float:
        """Compute full posterior combining all sources.

        Args:
            request: Posterior request describing player and recent data.

        Returns:
            Final posterior probability.
        """
        prior = self.compute_prior(request.prior_request)

        likelihood = request.recent_avg

        return self.compute_posterior(prior, likelihood, request.n_recent_games)
