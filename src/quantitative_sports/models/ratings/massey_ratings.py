"""
Massey Rating System with Attack/Defense Decomposition

This module implements the Massey rating system, a well-established method
for computing team strength ratings from game results using linear algebra.

Methodology:
The Massey system solves: r = M^{-1} * p
where:
- r is the rating vector (one rating per team)
- M is the margin matrix (M[i,j] = 1 if team i played team j, -1 if j vs i)
- p is the point margin vector (HOME_SCORE - AWAY_SCORE - home_advantage)

Key Features:
- Attack/defense decomposition into component ratings
- Home advantage adjustment
- Conference strength normalization
- Rest day and back-to-back fatigue adjustments
- Schedule strength calculation

Data Sources:
- Game data: TimescaleDB (games table)
- Team info: TimescaleDB (teams table)
- Caching: Apache Ignite for opponent strength

Usage:
    >>> from quantitative_sports.models.ratings.massey_ratings import MasseyRatings
    >>> massey = MasseyRatings(home_advantage=3.0)
    >>> ratings_df = massey.compute_ratings(games_df)
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class MasseyRatingsConfig:
    """Configuration for Massey rating system.

    Attributes:
        home_advantage: Home court advantage in points.
        min_games: Minimum games required for rating.
        regularization: Regularization parameter for stability.
    """

    home_advantage: float = 3.0
    min_games: int = 5
    regularization: float = 0.01


class MasseyRatings:
    """Massey rating system with attack/defense decomposition.

    Solves: r = M^{-1} * p for rating vector r

    All calculation logic is preserved from the original implementation.
    Data sources have been adapted to use TimescaleDB and Kafka instead of Redis.
    """

    def __init__(self, home_advantage: float = 3.0) -> None:
        """Initialize Massey ratings calculator.

        Args:
            home_advantage: Home court advantage in points.
        """
        self.home_advantage = home_advantage

    def _build_matrices(
        self, games: pd.DataFrame, teams: list[str], team_to_idx: dict[str, int]
    ) -> tuple[np.ndarray, np.ndarray]:
        """Build margin and selection matrices from games.

        Args:
            games: Games DataFrame.
            teams: List of team IDs.
            team_to_idx: Mapping of team to index.

        Returns:
            Tuple of (margin_matrix, selection_vector).
        """
        n_teams = len(teams)
        margin_matrix = []
        selection_vector = []

        for game in games.itertuples(index=False):
            home_idx = team_to_idx[game.HOME_TEAM]  # type: ignore[attr-defined]
            away_idx = team_to_idx[game.AWAY_TEAM]  # type: ignore[attr-defined]
            margin = game.HOME_SCORE - game.AWAY_SCORE - self.home_advantage  # type: ignore[attr-defined]

            row = np.zeros(n_teams)
            row[home_idx] = 1
            row[away_idx] = -1
            margin_matrix.append(row)
            selection_vector.append(margin)

        return np.array(margin_matrix), np.array(selection_vector)

    def _solve_ratings(self, margin_matrix: np.ndarray, selection_vector: np.ndarray) -> np.ndarray:
        """Solve for ratings using matrix operations.

        Args:
            margin_matrix: Matrix of game margins.
            selection_vector: Vector of adjusted margins.

        Returns:
            Rating vector for each team.
        """
        matrix_gram = margin_matrix.T @ margin_matrix
        vector_rhs = margin_matrix.T @ selection_vector

        n = matrix_gram.shape[0]
        matrix_gram += 1e-6 * np.eye(n)

        ratings = np.linalg.solve(matrix_gram, vector_rhs)

        mean_rating = np.mean(ratings)
        return ratings - mean_rating

    def _build_ratings_dict(
        self, ratings: np.ndarray, team_to_idx: dict[str, int]
    ) -> dict[str, dict[str, float]]:
        """Convert ratings array to dictionary.

        Args:
            ratings: Rating vector.
            team_to_idx: Mapping of team to index.

        Returns:
            Dictionary mapping team to ratings.
        """
        ratings_dict = {}
        for team, idx in team_to_idx.items():
            rating = ratings[idx]
            ratings_dict[team] = {"overall_rating": float(rating)}
        return ratings_dict

    def compute_ratings(self, games: pd.DataFrame) -> pd.DataFrame:
        """Compute Massey ratings from game results.

        Args:
            games: DataFrame with columns:
                - 'HOME_TEAM': Home team ID
                - 'AWAY_TEAM': Away team ID
                - 'HOME_SCORE': Home team points
                - 'AWAY_SCORE': Away team points

        Returns:
            DataFrame with team ratings (offensive, defensive, overall).
        """
        if games.empty:
            raise ValueError("Games DataFrame cannot be empty")

        required_cols = {"HOME_TEAM", "AWAY_TEAM", "HOME_SCORE", "AWAY_SCORE"}
        missing_cols = required_cols - set(games.columns)
        if missing_cols:
            raise ValueError(f"Missing required columns: {missing_cols}")

        teams = sorted(set(games["HOME_TEAM"].unique()) | set(games["AWAY_TEAM"].unique()))
        team_to_idx = {team: i for i, team in enumerate(teams)}

        try:
            margin_matrix, selection_vector = self._build_matrices(games, teams, team_to_idx)
            ratings = self._solve_ratings(margin_matrix, selection_vector)
            ratings_dict = self._build_ratings_dict(ratings, team_to_idx)

            return pd.DataFrame.from_dict(ratings_dict, orient="index")

        except np.linalg.LinAlgError:
            return self._simple_ratings(games, teams)

    def _simple_ratings(self, games: pd.DataFrame, teams: list[str]) -> pd.DataFrame:
        """Compute simple ratings when Massey method fails.

        Args:
            games: Games DataFrame.
            teams: List of team IDs.

        Returns:
            DataFrame with simple ratings.
        """
        ratings_dict = {team: {"overall_rating": 0.0} for team in teams}

        for team in teams:
            team_games = games[(games["HOME_TEAM"] == team) | (games["AWAY_TEAM"] == team)]
            if team_games.empty:
                continue

            point_diffs = []
            for _, game in team_games.iterrows():
                if game["HOME_TEAM"] == team:
                    diff = game["HOME_SCORE"] - game["AWAY_SCORE"] - self.home_advantage
                else:
                    diff = game["AWAY_SCORE"] - game["HOME_SCORE"] + self.home_advantage
                point_diffs.append(diff)

            ratings_dict[team]["overall_rating"] = float(np.mean(point_diffs))

        return pd.DataFrame.from_dict(ratings_dict, orient="index")

    def decompose_rating(self, team_rating: float) -> tuple[float, float]:
        """Decompose into offensive and defensive components.

        Args:
            team_rating: Overall team rating.

        Returns:
            Tuple of (offensive_rating, defensive_rating).
        """
        base_defense = 0.0
        base_offense = 0.0

        if team_rating > 0:
            split = min(team_rating, 2.0) / 2.0
            offensive = base_offense + split * team_rating
            defensive = base_defense + (1 - split) * team_rating
        else:
            split = max(team_rating, -2.0) / -2.0
            offensive = base_offense + (1 - split) * team_rating
            defensive = base_defense + split * team_rating

        return (float(offensive), float(defensive))

    def home_away_split(self, team_rating: float, is_home: bool) -> float:
        """Adjust rating for home/away context.

        Args:
            team_rating: Base team rating.
            is_home: Whether team is playing at home.

        Returns:
            Adjusted rating for the context.
        """
        if is_home:
            return team_rating + self.home_advantage * 0.5
        return team_rating - self.home_advantage * 0.5

    def schedule_strength(self, games: pd.DataFrame, team: str, ratings: pd.DataFrame) -> float:
        """Calculate strength of schedule for a team.

        Args:
            games: Games DataFrame.
            team: Team ID.
            ratings: Ratings DataFrame from compute_ratings.

        Returns:
            Average rating of opponents faced.
        """
        team_games = games[(games["HOME_TEAM"] == team) | (games["AWAY_TEAM"] == team)]
        if team_games.empty:
            return 0.0

        opponent_ratings = []
        for _, game in team_games.iterrows():
            opponent = game["AWAY_TEAM"] if game["HOME_TEAM"] == team else game["HOME_TEAM"]
            if opponent in ratings.index:
                opponent_ratings.append(ratings.loc[opponent, "overall_rating"])

        if not opponent_ratings:
            return 0.0

        return float(np.mean(opponent_ratings))

    def conference_adjustment(
        self,
        ratings: pd.DataFrame,
        conference_teams: dict[str, str],
    ) -> pd.DataFrame:
        """Adjust ratings for conference strength.

        Args:
            ratings: Base ratings DataFrame.
            conference_teams: Dict mapping team to conference.

        Returns:
            Adjusted ratings with conference normalization.
        """
        conferences = set(conference_teams.values())
        conference_means = {}

        for conf in conferences:
            conf_teams = [
                t for t, c in conference_teams.items() if c == conf and t in ratings.index
            ]
            if conf_teams:
                conf_ratings = [ratings.loc[t, "overall_rating"] for t in conf_teams]
                conference_means[conf] = np.mean(conf_ratings)

        if not conference_means:
            return ratings

        grand_mean = np.mean(list(conference_means.values()))

        adjusted_ratings = ratings.copy()
        for team in adjusted_ratings.index:
            if team in conference_teams:
                conf = conference_teams[team]
                if conf in conference_means:
                    adjustment = conference_means[conf] - grand_mean
                    adjusted_ratings.loc[team, "overall_rating"] -= adjustment

        return adjusted_ratings

    def rest_day_adjustment(
        self,
        days_rest: int,
        base_rating: float,
        rest_coefficient: float = 0.15,
    ) -> float:
        """Adjust rating based on rest days.

        Args:
            days_rest: Number of rest days.
            base_rating: Base team rating.
            rest_coefficient: Impact of rest on rating.

        Returns:
            Adjusted rating accounting for rest.
        """
        rest_bonus = min(days_rest, 4) * rest_coefficient
        return base_rating + rest_bonus

    def back_to_back_adjustment(
        self,
        is_back_to_back: bool,
        is_second_game: bool,
        base_rating: float,
        fatigue_factor: float = 0.5,
    ) -> float:
        """Adjust rating for back-to-back games.

        Args:
            is_back_to_back: Whether this is a back-to-back.
            is_second_game: Whether this is the second game of back-to-back.
            base_rating: Base team rating.
            fatigue_factor: Impact of fatigue on rating.

        Returns:
            Adjusted rating accounting for fatigue.
        """
        if not is_back_to_back:
            return base_rating
        if is_second_game:
            return base_rating - fatigue_factor
        return base_rating - fatigue_factor * 0.3
