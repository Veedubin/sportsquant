"""Game-level betting models for spreads, totals, and moneyline.

Phase 5: Aggregates player projections to predict game outcomes.
"""

from __future__ import annotations

# pylint: disable=too-many-instance-attributes,too-many-arguments,too-many-locals,too-many-positional-arguments,too-few-public-methods

from dataclasses import dataclass
from typing import Any, Optional, cast

import numpy as np
import pandas as pd
from pandas import DataFrame, Series
from scipy import stats  # pyright: ignore[reportMissingImports]  # pylint: disable=import-error

from quantitative_sports.util.nba_logging import get_logger

logger = get_logger(__name__)


def _coerce_numeric(df: DataFrame, col: str) -> Series:
    """Coerce column to numeric."""
    if col not in df.columns:
        return pd.Series(np.nan, index=df.index, dtype="float64")
    return cast(Series, cast(Any, pd).to_numeric(df[col], errors="coerce"))


@dataclass(frozen=True)
class GamePrediction:
    """Container for game-level predictions."""

    home_team: str
    away_team: str
    game_date: str

    # Team totals
    home_proj_total: float
    away_proj_total: float
    home_total_std: float
    away_total_std: float

    # Spread (home perspective: positive means home favored)
    proj_spread: float  # Home score - Away score
    spread_std: float

    # Total points
    proj_total_points: float
    total_points_std: float

    # Moneyline (home win probability)
    home_win_prob: float
    away_win_prob: float

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "home_team": self.home_team,
            "away_team": self.away_team,
            "game_date": self.game_date,
            "home_proj_total": self.home_proj_total,
            "away_proj_total": self.away_proj_total,
            "home_total_std": self.home_total_std,
            "away_total_std": self.away_total_std,
            "proj_spread": self.proj_spread,
            "spread_std": self.spread_std,
            "proj_total_points": self.proj_total_points,
            "total_points_std": self.total_points_std,
            "home_win_prob": self.home_win_prob,
            "away_win_prob": self.away_win_prob,
        }


class TeamTotalModel:
    """Predict team total points using aggregated player projections.

    Simple approach: Sum player minutes × rates with variance propagation.
    """

    def __init__(
        self,
        *,
        name: str = "TeamTotal",
        baseline_std_per_player: float = 3.0,
        min_std: float = 8.0,
    ):
        """Initialize team total model.

        Args:
            name: Model name
            baseline_std_per_player: Baseline standard deviation per player
            min_std: Minimum standard deviation for team total
        """
        self.name = name
        self.baseline_std_per_player = baseline_std_per_player
        self.min_std = min_std

    def predict_team_total(
        self,
        team_proj_points: float,
        team_rotation_size: int = 10,
    ) -> tuple[float, float]:
        """Predict team total points with uncertainty.

        Args:
            team_proj_points: Aggregated player projections
            team_rotation_size: Number of players in rotation (for variance)

        Returns:
            Tuple of (mean_points, std_points)
        """
        # Mean is simply the aggregated projection
        mean_points = float(team_proj_points)

        # Uncertainty scales with sqrt(N) players (central limit theorem)
        std_points = self.baseline_std_per_player * np.sqrt(team_rotation_size)
        std_points = max(std_points, self.min_std)

        return mean_points, std_points


class SpreadModel:
    """Predict point spread (home - away) using team projections.

    Spread = Home Total - Away Total
    Variance = Var(Home) + Var(Away)  # Independent teams
    """

    def __init__(
        self,
        *,
        name: str = "Spread",
        home_court_advantage: float = 3.0,  # Points
    ):
        """Initialize spread model.

        Args:
            name: Model name
            home_court_advantage: Points advantage for home team
        """
        self.name = name
        self.home_court_advantage = home_court_advantage

    def predict_spread(
        self,
        home_proj: float,
        away_proj: float,
        home_std: float,
        away_std: float,
    ) -> tuple[float, float]:
        """Predict point spread (home perspective).

        Args:
            home_proj: Home team projected points
            away_proj: Away team projected points
            home_std: Home team standard deviation
            away_std: Away team standard deviation

        Returns:
            Tuple of (spread_mean, spread_std)
            Positive spread = home favored
        """
        # Spread = Home - Away + Home Court Advantage
        spread_mean = home_proj - away_proj + self.home_court_advantage

        # Variance propagation (independent teams)
        spread_var = home_std**2 + away_std**2
        spread_std = np.sqrt(spread_var)

        return float(spread_mean), float(spread_std)

    def prob_home_covers(self, spread_line: float, spread_mean: float, spread_std: float) -> float:
        """Probability that home team covers the spread.

        Args:
            spread_line: Betting line (home perspective, e.g., -5.5)
            spread_mean: Predicted spread
            spread_std: Spread uncertainty

        Returns:
            Probability home covers (0-1)
        """
        # P(Home covers) = P(Home - Away > spread_line)
        z_score = (spread_mean - spread_line) / spread_std if spread_std > 0 else 0.0
        prob = float(stats.norm.cdf(z_score))
        return np.clip(prob, 0.0, 1.0)


class MoneylineModel:
    """Predict win probability from spread distribution.

    P(Home wins) = P(Home - Away > 0)
    """

    def __init__(self, *, name: str = "Moneyline"):
        """Initialize moneyline model.

        Args:
            name: Model name
        """
        self.name = name

    def predict_win_prob(self, spread_mean: float, spread_std: float) -> tuple[float, float]:
        """Predict home and away win probabilities.

        Args:
            spread_mean: Predicted spread (home - away)
            spread_std: Spread uncertainty

        Returns:
            Tuple of (home_win_prob, away_win_prob)
        """
        # P(Home wins) = P(Home - Away > 0) = P(Spread > 0)
        if spread_std > 0:
            z_score = spread_mean / spread_std
            home_prob = float(stats.norm.cdf(z_score))
        else:
            # Deterministic case
            home_prob = 1.0 if spread_mean > 0 else 0.0

        home_prob = np.clip(home_prob, 0.01, 0.99)  # Avoid extreme probabilities
        away_prob = 1.0 - home_prob

        return float(home_prob), float(away_prob)


class GameOutcomePredictor:
    """Unified predictor for all game-level markets.

    Combines TeamTotalModel, SpreadModel, and MoneylineModel.
    """

    def __init__(
        self,
        *,
        team_total_model: Optional[TeamTotalModel] = None,
        spread_model: Optional[SpreadModel] = None,
        moneyline_model: Optional[MoneylineModel] = None,
    ):
        """Initialize game outcome predictor.

        Args:
            team_total_model: Team total prediction model
            spread_model: Spread prediction model
            moneyline_model: Moneyline prediction model
        """
        self.team_total_model = team_total_model or TeamTotalModel()
        self.spread_model = spread_model or SpreadModel()
        self.moneyline_model = moneyline_model or MoneylineModel()

    def predict_game(
        self,
        home_team: str,
        away_team: str,
        game_date: str,
        home_proj_points: float,
        away_proj_points: float,
        home_rotation_size: int = 10,
        away_rotation_size: int = 10,
    ) -> GamePrediction:
        """Predict all game outcomes (totals, spread, moneyline).

        Args:
            home_team: Home team abbreviation
            away_team: Away team abbreviation
            game_date: Game date string
            home_proj_points: Home team projected points
            away_proj_points: Away team projected points
            home_rotation_size: Number of home players in rotation
            away_rotation_size: Number of away players in rotation

        Returns:
            GamePrediction with all market predictions
        """
        # Team totals
        home_total, home_std = self.team_total_model.predict_team_total(
            home_proj_points, home_rotation_size
        )
        away_total, away_std = self.team_total_model.predict_team_total(
            away_proj_points, away_rotation_size
        )

        # Spread
        spread_mean, spread_std = self.spread_model.predict_spread(
            home_total, away_total, home_std, away_std
        )

        # Total points
        total_mean = home_total + away_total
        total_std = np.sqrt(home_std**2 + away_std**2)

        # Moneyline
        home_win_prob, away_win_prob = self.moneyline_model.predict_win_prob(
            spread_mean, spread_std
        )

        return GamePrediction(
            home_team=home_team,
            away_team=away_team,
            game_date=game_date,
            home_proj_total=home_total,
            away_proj_total=away_total,
            home_total_std=home_std,
            away_total_std=away_std,
            proj_spread=spread_mean,
            spread_std=spread_std,
            proj_total_points=total_mean,
            total_points_std=total_std,
            home_win_prob=home_win_prob,
            away_win_prob=away_win_prob,
        )


def predict_games_from_features(
    game_features: DataFrame,
    *,
    predictor: Optional[GameOutcomePredictor] = None,
) -> DataFrame:
    """Predict game outcomes from game features DataFrame.

    Args:
        game_features: Game matchup features (from game_features.py)
        predictor: Game outcome predictor (uses defaults if None)

    Returns:
        DataFrame with predictions for each game
    """
    if game_features.empty:
        return DataFrame()

    predictor = predictor or GameOutcomePredictor()

    predictions: list[dict[str, Any]] = []

    for _, row in cast(Any, game_features).iterrows():
        home_team = str(row.get("home_team", ""))
        away_team = str(row.get("away_team", ""))
        game_date = str(row.get("game_date", ""))

        home_proj = float(row.get("team_proj_points_home", 100.0))
        away_proj = float(row.get("team_proj_points_away", 100.0))

        # Estimate rotation size from projected minutes
        home_minutes = float(row.get("team_proj_minutes_home", 240.0))
        away_minutes = float(row.get("team_proj_minutes_away", 240.0))
        home_rotation = max(int(home_minutes / 24.0), 8)  # Assume 24 min/player
        away_rotation = max(int(away_minutes / 24.0), 8)

        pred = predictor.predict_game(
            home_team=home_team,
            away_team=away_team,
            game_date=game_date,
            home_proj_points=home_proj,
            away_proj_points=away_proj,
            home_rotation_size=home_rotation,
            away_rotation_size=away_rotation,
        )

        predictions.append(pred.to_dict())

    return DataFrame(predictions)
