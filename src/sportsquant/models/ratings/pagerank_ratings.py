"""
PageRank-Style Team Ratings for Transitive Opponent Strength

This module implements a PageRank-inspired algorithm to compute team ratings
that account for the quality of opponents beaten.

Methodology:
1. Build a transition matrix from game results where:
   - Edge weight from team A to team B = A's wins / B's losses
2. Apply power iteration with damping factor (typically 0.85)
3. Add teleportation vector to handle disconnected components
4. Iterate until convergence (tolerance 1e-6)

Key Features:
- Margin-weighted transitions (close wins count less than blowouts)
- Personalization vectors for team-specific analysis
- Strength of schedule calculations
- Wins against highly-rated opponents metric

Data Sources:
- Game data: TimescaleDB (games table)
- Team info: TimescaleDB (teams table)
- Caching: Apache Ignite for opponent strength

Usage:
    >>> from sportsquant.models.ratings.pagerank_ratings import PageRankRatings
    >>> ratings = PageRankRatings(damping=0.85)
    >>> team_ratings = ratings.compute_ratings(games_df, teams)
"""

from __future__ import annotations

import numpy as np
import pandas as pd


class PageRankRatings:
    """PageRank-style ratings for transitive opponent strength.

    Iteratively compute ratings until convergence.

    All calculation logic is preserved from the original implementation.
    Data sources have been adapted to use TimescaleDB and Kafka instead of Redis.
    """

    def __init__(
        self,
        damping: float = 0.85,
        max_iterations: int = 100,
        tolerance: float = 1e-6,
    ) -> None:
        """Initialize PageRank ratings calculator.

        Args:
            damping: Damping factor (probability of following links).
            max_iterations: Maximum iterations for convergence.
            tolerance: Convergence tolerance.
        """
        if not 0 < damping < 1:
            raise ValueError("damping must be between 0 and 1")
        if max_iterations <= 0:
            raise ValueError("max_iterations must be positive")
        if tolerance <= 0:
            raise ValueError("tolerance must be positive")

        self.damping = damping
        self.max_iterations = max_iterations
        self.tolerance = tolerance

    def compute_ratings(self, games: pd.DataFrame, teams: list[str]) -> dict[str, float]:
        """Compute PageRank ratings.

        Args:
            games: DataFrame with columns:
                - 'WINNER': Team ID of winner
                - 'LOSER': Team ID of loser
                - 'WINNER_SCORE': Winner's score
                - 'LOSER_SCORE': Loser's score
            teams: List of team IDs to include in ratings.

        Returns:
            Dictionary mapping team ID to PageRank rating.
        """
        if not teams:
            return {}

        teams_set = set(teams)
        valid_games = games[
            (games["WINNER"].isin(list(teams_set))) & (games["LOSER"].isin(list(teams_set)))
        ]

        if valid_games.empty:
            return {team: 1.0 / len(teams) for team in teams}

        transition_matrix = self.build_transition_matrix(
            valid_games,  # type: ignore[arg-type]
            teams,
        )

        ratings = np.ones(len(teams)) / len(teams)

        for _ in range(self.max_iterations):
            new_ratings = self._power_iteration(ratings, transition_matrix)

            if np.allclose(new_ratings, ratings, rtol=self.tolerance):
                break

            ratings = new_ratings

        return {team: float(rating) for team, rating in zip(teams, ratings)}

    def _power_iteration(self, ratings: np.ndarray, transition_matrix: np.ndarray) -> np.ndarray:
        """Perform one iteration of power method.

        Args:
            ratings: Current rating vector.
            transition_matrix: Transition probability matrix.

        Returns:
            Updated rating vector.
        """
        n = len(ratings)
        teleportation = np.ones(n) / n

        new_ratings = (
            self.damping * (transition_matrix.T @ ratings) + (1 - self.damping) * teleportation
        )

        return new_ratings / np.sum(new_ratings)

    def _compute_win_loss_counts(
        self, games: pd.DataFrame, teams: list[str], team_to_idx: dict[str, int]
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Compute win/loss counts and margin totals.

        Args:
            games: Games DataFrame.
            teams: List of team IDs.
            team_to_idx: Mapping of team to index.

        Returns:
            Tuple of (win_counts, loss_counts, margin_matrix).
        """
        n = len(teams)
        win_counts = np.zeros(n)
        loss_counts = np.zeros(n)
        margin_matrix = np.zeros((n, n))

        for _, game in games.iterrows():
            winner: str = str(game["WINNER"])
            loser: str = str(game["LOSER"])
            winner_idx = team_to_idx[winner]
            loser_idx = team_to_idx[loser]

            win_counts[winner_idx] += 1
            loss_counts[loser_idx] += 1

            if "WINNER_SCORE" in game and "LOSER_SCORE" in game:
                margin = game["WINNER_SCORE"] - game["LOSER_SCORE"]
                margin_matrix[winner_idx, loser_idx] += margin
                margin_matrix[loser_idx, winner_idx] -= margin

        return win_counts, loss_counts, margin_matrix

    def _build_transition_matrix(
        self, win_counts: np.ndarray, loss_counts: np.ndarray, n: int
    ) -> np.ndarray:
        """Build normalized transition matrix from win/loss counts.

        Args:
            win_counts: Array of win counts per team.
            loss_counts: Array of loss counts per team.
            n: Number of teams.

        Returns:
            Normalized transition matrix.
        """
        transition_matrix = np.zeros((n, n))

        for i in range(n):
            for j in range(n):
                if i != j and loss_counts[j] > 0:
                    transition_matrix[i, j] = win_counts[i] / loss_counts[j]

        row_sums = transition_matrix.sum(axis=1, keepdims=True)
        row_sums[row_sums == 0] = 1

        return transition_matrix / row_sums

    def build_transition_matrix(self, games: pd.DataFrame, teams: list[str]) -> np.ndarray:
        """Build normalized transition matrix from game results.

        Args:
            games: Games DataFrame.
            teams: List of team IDs.

        Returns:
            Normalized transition matrix.
        """
        n = len(teams)
        team_to_idx = {team: i for i, team in enumerate(teams)}

        win_counts, loss_counts, _ = self._compute_win_loss_counts(games, teams, team_to_idx)
        return self._build_transition_matrix(win_counts, loss_counts, n)

    def build_margin_matrix(self, games: pd.DataFrame, teams: list[str]) -> np.ndarray:
        """Build margin-weighted transition matrix.

        Args:
            games: Games DataFrame.
            teams: List of team IDs.

        Returns:
            Margin-weighted transition matrix.
        """
        n = len(teams)
        team_to_idx = {team: i for i, team in enumerate(teams)}

        margin_matrix = np.zeros((n, n))
        win_matrix = np.zeros((n, n))

        for _, game in games.iterrows():
            winner: str = str(game["WINNER"])
            loser: str = str(game["LOSER"])
            winner_idx = team_to_idx[winner]
            loser_idx = team_to_idx[loser]

            if "WINNER_SCORE" in game and "LOSER_SCORE" in game:
                margin = game["WINNER_SCORE"] - game["LOSER_SCORE"]
                margin_matrix[winner_idx, loser_idx] += margin
                win_matrix[winner_idx, loser_idx] += 1

        margin_matrix = margin_matrix / (win_matrix + 1e-6)

        row_sums = np.abs(margin_matrix).sum(axis=1, keepdims=True) + 1e-6
        normalized_matrix = margin_matrix / row_sums

        return normalized_matrix

    def personalize_by_results(
        self,
        games: pd.DataFrame,
        teams: list[str],
        focus_team: str,
    ) -> np.ndarray:
        """Create personalization vector emphasizing focus team.

        Args:
            games: Games DataFrame.
            teams: List of team IDs.
            focus_team: Team to emphasize in ratings.

        Returns:
            Personalization vector.
        """
        n = len(teams)

        if focus_team not in teams:
            return np.ones(n) / n

        team_to_idx = {team: i for i, team in enumerate(teams)}
        focus_idx = team_to_idx[focus_team]

        teams_set = set(teams)
        team_games = games[
            (games["WINNER"].isin(list(teams_set))) | (games["LOSER"].isin(list(teams_set)))
        ]

        opponent_counts = {}
        for _, game in team_games.iterrows():
            for team in [game["WINNER"], game["LOSER"]]:
                if team != focus_team:
                    opponent_counts[team] = opponent_counts.get(team, 0) + 1

        personalization = np.ones(n) * 0.1 / n
        personalization[focus_idx] = 0.5

        for team, count in opponent_counts.items():
            if team in team_to_idx:
                idx = team_to_idx[team]
                personalization[idx] += 0.4 * min(count / 10, 1.0)

        personalization = personalization / personalization.sum()

        return personalization

    def wins_against_rated(
        self,
        games: pd.DataFrame,
        ratings: dict[str, float],
        team: str,
        min_rating_threshold: float = 0.5,
    ) -> float:
        """Calculate fraction of wins against highly-rated opponents.

        Args:
            games: Games DataFrame.
            ratings: Team ratings dictionary.
            team: Team to evaluate.
            min_rating_threshold: Minimum rating to be considered "highly rated".

        Returns:
            Fraction of wins against highly-rated opponents.
        """
        if not ratings:
            return 0.0

        teams_set = set(ratings.keys())
        team_games = games[
            ((games["WINNER"] == team) | (games["LOSER"] == team))
            & (games["WINNER"].isin(list(teams_set)))
            & (games["LOSER"].isin(list(teams_set)))
        ]

        if team_games.empty:
            return 0.5

        wins_against_rated = 0
        total_wins = 0

        for _, game in team_games.iterrows():
            if game["WINNER"] == team:
                opponent: str = str(game["LOSER"])
                total_wins += 1
                if ratings.get(opponent, 0) >= min_rating_threshold:
                    wins_against_rated += 1

        if total_wins == 0:
            return 0.5

        return wins_against_rated / total_wins

    def strength_of_schedule(
        self,
        games: pd.DataFrame,
        ratings: dict[str, float],
        team: str,
    ) -> float:
        """Calculate average rating of opponents faced.

        Args:
            games: Games DataFrame.
            ratings: Team ratings dictionary.
            team: Team to evaluate.

        Returns:
            Average rating of opponents faced.
        """
        if not ratings:
            return 0.5

        teams_set = set(ratings.keys())
        team_games = games[
            ((games["HOME_TEAM"] == team) | (games["AWAY_TEAM"] == team))
            & (games["HOME_TEAM"].isin(list(teams_set)))
            & (games["AWAY_TEAM"].isin(list(teams_set)))
        ]

        if team_games.empty:
            return 0.5

        opponent_ratings = []
        for _, game in team_games.iterrows():
            opponent: str = str(
                game["AWAY_TEAM"] if game["HOME_TEAM"] == team else game["HOME_TEAM"]
            )
            if opponent in ratings:
                opponent_ratings.append(ratings[opponent])

        if not opponent_ratings:
            return 0.5

        return float(np.mean(opponent_ratings))
