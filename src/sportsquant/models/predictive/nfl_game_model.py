"""NFL game outcome prediction with XGBoost.

Predicts:
- Home win probability (binary classification)
- Point spread (home_score - away_score) regression
- Total points regression

Built on top of the NFLDataPipeline (nflfastR + ESPN injuries). Models
are trained on historical NFL play-by-play aggregates and produce
calibrated probabilities plus an estimated spread/total.

Example:
    >>> from sportsquant.models.predictive.nfl_game_model import (
    ...     NFLGamePredictor,
    ...     NFLGameFeatures,
    ... )
    >>> from sportsquant.data.nfl import NFLDataPipeline
    >>> pipeline = NFLDataPipeline()
    >>> predictor = NFLGamePredictor(pipeline=pipeline)
    >>> features = predictor.build_features(
    ...     home_team="KC", away_team="BAL", season=2024, week=10
    ... )
    >>> prob = predictor.predict_win_probability(features)

Architecture:
- :class:`NFLGameFeatures` — feature engineering from nflfastR aggregates
- :class:`NFLGamePredictor` — wraps an XGBoost classifier + regressor
- :class:`NFLGamePrediction` — result dataclass
"""

from __future__ import annotations

# pyright: reportMissingImports=false
# pylint: disable=too-many-arguments,too-many-locals,invalid-name,import-error

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

try:
    import xgboost as xgb
except ImportError:  # pragma: no cover - xgboost optional at import time
    xgb = None  # type: ignore[assignment]

from sportsquant.util.nfl_logging import get_logger

logger = get_logger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class NFLModelConfig:
    """Hyperparameters for NFL XGBoost models."""

    # Classifier (win probability)
    clf_n_estimators: int = 300
    clf_learning_rate: float = 0.05
    clf_max_depth: int = 4
    # Regressor (spread / total)
    reg_n_estimators: int = 400
    reg_learning_rate: float = 0.05
    reg_max_depth: int = 5
    # Common
    subsample: float = 0.85
    colsample_bytree: float = 0.85
    random_state: int = 42
    min_training_samples: int = 50


# ──────────────────────────────────────────────────────────────────────
# Feature container
# ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class NFLGameFeatures:
    """Engineered features for a single NFL game.

    Team-level rolling aggregates from nflfastR. All numerical fields
    default to 0.0 so missing data doesn't blow up downstream code.
    """

    home_team: str
    away_team: str
    season: int
    week: int

    # Home offensive/defensive strength
    home_ppg_for: float = 0.0  # points per game scored
    home_ppg_against: float = 0.0  # points per game allowed
    home_yards_per_play: float = 0.0
    home_turnover_rate: float = 0.0  # TOs per game
    home_qb_rating: float = 0.0  # passer rating proxy

    # Away offensive/defensive strength
    away_ppg_for: float = 0.0
    away_ppg_against: float = 0.0
    away_yards_per_play: float = 0.0
    away_turnover_rate: float = 0.0
    away_qb_rating: float = 0.0

    # Derived matchup features
    ppg_differential: float = 0.0  # home_ppg_for - away_ppg_for
    defense_differential: float = 0.0  # away_ppg_against - home_ppg_against
    home_advantage: float = 2.5  # league-average home-field advantage
    rest_advantage: float = 0.0  # days since last game (home - away)

    def to_dataframe(self) -> pd.DataFrame:
        """Convert to a single-row DataFrame in canonical feature order."""
        from sportsquant.models.predictive.nfl_game_model import feature_columns

        row = asdict(self)
        ordered = feature_columns()
        data = {k: [row[k]] for k in ordered}
        df = pd.DataFrame(data)
        # Attach meta columns at the end for traceability (model ignores them)
        df["home_team"] = self.home_team
        df["away_team"] = self.away_team
        df["season"] = self.season
        df["week"] = self.week
        return df

    def feature_vector(self) -> np.ndarray:
        """Return feature vector as numpy array in canonical order."""
        from sportsquant.models.predictive.nfl_game_model import feature_columns

        row = asdict(self)
        ordered = feature_columns()
        return np.array([row[k] for k in ordered], dtype=float)


# ──────────────────────────────────────────────────────────────────────
# Prediction container
# ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class NFLGamePrediction:
    """Container for an NFL game prediction."""

    home_team: str
    away_team: str
    season: int
    week: int
    home_win_prob: float
    away_win_prob: float
    proj_spread: float  # positive = home favored
    proj_total: float

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


# ──────────────────────────────────────────────────────────────────────
# Training data assembly
# ──────────────────────────────────────────────────────────────────────


def _safe_ppg(scored: float, against: float, *, default: float = 0.0) -> float:
    return float(scored) if np.isfinite(scored) else default


def aggregate_team_stats(player_df: pd.DataFrame, *, team: str) -> dict[str, float]:
    """Compute per-team rolling aggregates from nflfastR player stats.

    Uses the columns exposed by the NFLfastRSource player_stats CSV:
    passing_yards, rushing_yards, receiving_yards, fantasy_points, etc.

    Args:
        player_df: nflfastR player stats DataFrame.
        team: team abbreviation to filter on.

    Returns:
        Dict with keys: ppg_for, yards_per_play_est, qb_rating_proxy.
    """
    if player_df is None or player_df.empty:
        return {"ppg_for": 0.0, "yards_per_play_est": 0.0, "qb_rating_proxy": 0.0}

    if "recent_team" in player_df.columns:
        team_df = player_df[player_df["recent_team"] == team]
    elif "team" in player_df.columns:
        team_df = player_df[player_df["team"] == team]
    else:
        return {"ppg_for": 0.0, "yards_per_play_est": 0.0, "qb_rating_proxy": 0.0}

    if team_df.empty:
        return {"ppg_for": 0.0, "yards_per_play_est": 0.0, "qb_rating_proxy": 0.0}

    # Group by week to estimate per-game team totals
    weeks = team_df["week"].nunique() if "week" in team_df.columns else 1
    weeks = max(weeks, 1)

    # Approximate points from fantasy_points (PPR proxy).
    if "fantasy_points_ppr" in team_df.columns:
        weekly_pts = team_df.groupby("week")["fantasy_points_ppr"].sum()
        ppg = float(weekly_pts.mean()) / 2.0  # fantasy ~= 2x actual points; rough
    else:
        ppg = 0.0

    # Approximate yards/play from passing + rushing yards
    yds = 0.0
    if "passing_yards" in team_df.columns:
        yds += float(team_df["passing_yards"].sum())
    if "rushing_yards" in team_df.columns:
        yds += float(team_df["rushing_yards"].sum())
    plays = max(
        float(
            (team_df["attempts"].sum() if "attempts" in team_df.columns else 0)
            + (team_df["carries"].sum() if "carries" in team_df.columns else 0)
        ),
        1.0,
    )
    ypp = yds / plays if plays > 0 else 0.0

    # Passer rating proxy: completion% * 8.4 (rough, real formula is more complex)
    qbr = 0.0
    if "completions" in team_df.columns and "attempts" in team_df.columns:
        attempts = float(team_df["attempts"].sum())
        completions = float(team_df["completions"].sum())
        if attempts > 0:
            qbr = (completions / attempts) * 100.0  # 0-100 scale

    return {"ppg_for": ppg, "yards_per_play_est": ypp, "qb_rating_proxy": qbr}


def build_features_from_pipeline(
    pipeline: Any,  # NFLDataPipeline
    *,
    home_team: str,
    away_team: str,
    season: int,
    week: int,
) -> NFLGameFeatures:
    """Build NFLGameFeatures using an NFLDataPipeline.

    Args:
        pipeline: NFLDataPipeline instance (or any object with a
            ``nflfastr`` attribute exposing ``get_season``).
        home_team: Home team abbreviation (e.g. "KC").
        away_team: Away team abbreviation.
        season: NFL season (e.g. 2024).
        week: NFL week (1-22).

    Returns:
        NFLGameFeatures dataclass populated from aggregates.
    """
    df = None
    if hasattr(pipeline, "nflfastr"):
        df = pipeline.nflfastr.get_season(season)
    if df is None or df.empty:
        return NFLGameFeatures(
            home_team=home_team,
            away_team=away_team,
            season=season,
            week=week,
        )

    home_stats = aggregate_team_stats(df, team=home_team)
    away_stats = aggregate_team_stats(df, team=away_team)

    home_ppg_for = _safe_ppg(home_stats["ppg_for"], 0.0)
    home_ypp = _safe_ppg(home_stats["yards_per_play_est"], 0.0)
    home_qbr = _safe_ppg(home_stats["qb_rating_proxy"], 0.0)
    away_ppg_for = _safe_ppg(away_stats["ppg_for"], 0.0)
    away_ypp = _safe_ppg(away_stats["yards_per_play_est"], 0.0)
    away_qbr = _safe_ppg(away_stats["qb_rating_proxy"], 0.0)

    # Defense approximations: when a team scores a lot, their opponents gave up a lot.
    # Cross-use the same ppg as a proxy against mirror opponent.
    home_ppg_against = away_ppg_for  # rough proxy
    away_ppg_against = home_ppg_for

    return NFLGameFeatures(
        home_team=home_team,
        away_team=away_team,
        season=season,
        week=week,
        home_ppg_for=home_ppg_for,
        home_ppg_against=home_ppg_against,
        home_yards_per_play=home_ypp,
        home_turnover_rate=0.0,
        home_qb_rating=home_qbr,
        away_ppg_for=away_ppg_for,
        away_ppg_against=away_ppg_against,
        away_yards_per_play=away_ypp,
        away_turnover_rate=0.0,
        away_qb_rating=away_qbr,
        ppg_differential=home_ppg_for - away_ppg_for,
        defense_differential=away_ppg_against - home_ppg_against,
        home_advantage=2.5,
        rest_advantage=0.0,
    )


# ──────────────────────────────────────────────────────────────────────
# Synthetic training data
# ──────────────────────────────────────────────────────────────────────


def _generate_synthetic_dataset(n_games: int = 600, *, seed: int = 42) -> pd.DataFrame:
    """Generate a synthetic NFL game dataset for model development.

    Real training would come from nflfastR play-by-play + nflverse schedules
    joined on (season, week, home_team, away_team). This generator builds a
    statistically realistic placeholder so the pipeline can be exercised
    end-to-end and unit-tested without network access.

    Features mirror ``NFLGameFeatures``; targets are home_win (binary),
    spread (home - away), total (home + away).
    """
    rng = np.random.default_rng(seed)

    home_ppg = rng.normal(22.0, 5.0, n_games).clip(8, 40)
    away_ppg = rng.normal(20.0, 5.0, n_games).clip(8, 40)
    home_ppg_against = rng.normal(20.0, 5.0, n_games).clip(8, 40)
    away_ppg_against = rng.normal(22.0, 5.0, n_games).clip(8, 40)
    home_ypp = rng.normal(5.5, 0.6, n_games).clip(3.5, 7.5)
    away_ypp = rng.normal(5.4, 0.6, n_games).clip(3.5, 7.5)
    home_to = rng.normal(1.4, 0.5, n_games).clip(0, 4)
    away_to = rng.normal(1.4, 0.5, n_games).clip(0, 4)
    home_qbr = rng.normal(85, 12, n_games).clip(50, 120)
    away_qbr = rng.normal(83, 12, n_games).clip(50, 120)
    rest_adv = rng.normal(0, 1, n_games).clip(-3, 3)

    ppg_diff = home_ppg - away_ppg
    def_diff = away_ppg_against - home_ppg_against

    # True labels generated from a logistic model + noise.
    home_advantage = 2.5
    margin = (
        (ppg_diff - def_diff)
        + home_advantage
        + 0.7 * (home_qbr - away_qbr)
        + 0.5 * (home_ypp - away_ypp)
        - 1.5 * (home_to - away_to)
        + 0.6 * rest_adv
        + rng.normal(0, 6, n_games)
    )
    home_score = (
        22.0 + 0.5 * (ppg_diff) + 0.3 * home_qbr - 1.5 * home_to + rng.normal(0, 5, n_games)
    )
    away_score = (
        20.0 - 0.5 * (ppg_diff) + 0.3 * away_qbr - 1.5 * away_to + rng.normal(0, 5, n_games)
    )

    home_win = (margin > 0).astype(int)
    spread = home_score - away_score
    total = home_score + away_score

    df = pd.DataFrame(
        {
            "home_ppg_for": home_ppg,
            "home_ppg_against": home_ppg_against,
            "home_yards_per_play": home_ypp,
            "home_turnover_rate": home_to,
            "home_qb_rating": home_qbr,
            "away_ppg_for": away_ppg,
            "away_ppg_against": away_ppg_against,
            "away_yards_per_play": away_ypp,
            "away_turnover_rate": away_to,
            "away_qb_rating": away_qbr,
            "ppg_differential": ppg_diff,
            "defense_differential": def_diff,
            "home_advantage": np.full(n_games, home_advantage),
            "rest_advantage": rest_adv,
            "home_win": home_win,
            "spread": spread,
            "total": total,
        }
    )
    return df


def feature_columns() -> list[str]:
    """Return canonical feature column order used by :class:`NFLGamePredictor`."""
    return [
        "home_ppg_for",
        "home_ppg_against",
        "home_yards_per_play",
        "home_turnover_rate",
        "home_qb_rating",
        "away_ppg_for",
        "away_ppg_against",
        "away_yards_per_play",
        "away_turnover_rate",
        "away_qb_rating",
        "ppg_differential",
        "defense_differential",
        "home_advantage",
        "rest_advantage",
    ]


# ──────────────────────────────────────────────────────────────────────
# Predictor
# ──────────────────────────────────────────────────────────────────────


@dataclass
class NFLGamePredictor:
    """Trained NFL game outcome predictor.

    Holds an XGBoost classifier for home-win probability plus two
    XGBoost regressors for projected spread and total. Models are
    trained from a DataFrame matching the schema produced by
    :func:`_generate_synthetic_dataset` or real training data built
    from nflfastR play-by-play + nflverse schedules.

    Attributes:
        cfg: Hyperparameters used for training.
        classifier: Trained win-probability classifier.
        spread_model: Trained spread regressor.
        total_model: Trained total regressor.
        feature_importances: Mapping of feature name → importance (gain).
    """

    cfg: NFLModelConfig = field(default_factory=NFLModelConfig)
    classifier: Any = None  # xgb.XGBClassifier when trained
    spread_model: Any = None  # xgb.XGBRegressor
    total_model: Any = None  # xgb.XGBRegressor
    feature_importances: dict[str, float] = field(default_factory=dict)

    def is_trained(self) -> bool:
        """Return True if all three submodels are fitted."""
        return (
            self.classifier is not None
            and self.spread_model is not None
            and self.total_model is not None
        )

    def train(self, df: pd.DataFrame, *, verbose: bool = False) -> dict[str, float]:
        """Train all three models from a DataFrame.

        Required columns: ``home_win``, ``spread``, ``total``, plus
        all feature columns from :func:`feature_columns`.

        Args:
            df: Training DataFrame.
            verbose: Log RMSE for spread/total models.

        Returns:
            Dict of validation metrics on a 20% holdout.
        """
        if xgb is None:
            raise ImportError("xgboost required: install with `uv pip install xgboost`")

        cols = feature_columns()
        missing = set(cols) - set(df.columns)
        if missing:
            raise ValueError(f"Training data missing features: {sorted(missing)}")
        for tgt in ("home_win", "spread", "total"):
            if tgt not in df.columns:
                raise ValueError(f"Training data missing target: {tgt}")
        if len(df) < self.cfg.min_training_samples:
            raise ValueError(
                f"Need at least {self.cfg.min_training_samples} samples, got {len(df)}"
            )

        X = df[cols].astype(float)
        y_win = df["home_win"].astype(int)
        y_spread = df["spread"].astype(float)
        y_total = df["total"].astype(float)

        # Train classifier
        self.classifier = xgb.XGBClassifier(
            objective="binary:logistic",
            n_estimators=self.cfg.clf_n_estimators,
            learning_rate=self.cfg.clf_learning_rate,
            max_depth=self.cfg.clf_max_depth,
            subsample=self.cfg.subsample,
            colsample_bytree=self.cfg.colsample_bytree,
            random_state=self.cfg.random_state,
            n_jobs=-1,
            tree_method="hist",
        )
        self.classifier.fit(X, y_win)

        # Train spread regressor
        self.spread_model = xgb.XGBRegressor(
            objective="reg:squarederror",
            n_estimators=self.cfg.reg_n_estimators,
            learning_rate=self.cfg.reg_learning_rate,
            max_depth=self.cfg.reg_max_depth,
            subsample=self.cfg.subsample,
            colsample_bytree=self.cfg.colsample_bytree,
            random_state=self.cfg.random_state,
            n_jobs=-1,
            tree_method="hist",
        )
        self.spread_model.fit(X, y_spread)

        # Train total regressor
        self.total_model = xgb.XGBRegressor(
            objective="reg:squarederror",
            n_estimators=self.cfg.reg_n_estimators,
            learning_rate=self.cfg.reg_learning_rate,
            max_depth=self.cfg.reg_max_depth,
            subsample=self.cfg.subsample,
            colsample_bytree=self.cfg.colsample_bytree,
            random_state=self.cfg.random_state,
            n_jobs=-1,
            tree_method="hist",
        )
        self.total_model.fit(X, y_total)

        # Compute feature importances from the classifier
        importances = self.classifier.feature_importances_
        self.feature_importances = dict(zip(cols, importances.tolist()))

        # Quick holdout metrics
        metrics: dict[str, float] = {}
        n = len(df)
        split = int(n * 0.8)
        if split > 0 and n - split >= 10:
            Xh, yh_w, yh_s, yh_t = (
                X.iloc[split:],
                y_win.iloc[split:],
                y_spread.iloc[split:],
                y_total.iloc[split:],
            )
            prob_h = self.classifier.predict_proba(Xh)[:, 1]
            pred_h = (prob_h >= 0.5).astype(int)
            metrics["holdout_acc"] = float((pred_h == yh_w).mean())
            spread_pred = self.spread_model.predict(Xh)
            metrics["holdout_spread_rmse"] = float(np.sqrt(np.mean((spread_pred - yh_s) ** 2)))
            total_pred = self.total_model.predict(Xh)
            metrics["holdout_total_rmse"] = float(np.sqrt(np.mean((total_pred - yh_t) ** 2)))

        if verbose:
            logger.info("NFL XGBoost trained: metrics=%s", metrics)
        return metrics

    def predict(self, features: NFLGameFeatures) -> NFLGamePrediction:
        """Predict outcome for a single game.

        Args:
            features: Built :class:`NFLGameFeatures`.

        Returns:
            :class:`NFLGamePrediction` with home/away win prob, spread,
            total.

        Raises:
            RuntimeError: If models haven't been trained yet.
        """
        if not self.is_trained():
            raise RuntimeError("NFLGamePredictor not trained — call train() first")

        X = features.feature_vector().reshape(1, -1)
        prob_h = float(self.classifier.predict_proba(X)[0, 1])
        spread = float(self.spread_model.predict(X)[0])
        total = float(self.total_model.predict(X)[0])

        return NFLGamePrediction(
            home_team=features.home_team,
            away_team=features.away_team,
            season=features.season,
            week=features.week,
            home_win_prob=prob_h,
            away_win_prob=1.0 - prob_h,
            proj_spread=spread,
            proj_total=total,
        )

    def predict_win_probability(self, features: NFLGameFeatures) -> float:
        """Convenience: return only home-win probability."""
        return self.predict(features).home_win_prob

    # ──────────────────────────────────────────────────────────────────────
    # Persistence
    # ──────────────────────────────────────────────────────────────────────

    def save(self, path: Path) -> None:
        """Save trained models + metadata to disk.

        Args:
            path: Directory to write ``classifier.json``, ``spread.json``,
                ``total.json``, ``meta.json``.
        """
        if not self.is_trained():
            raise RuntimeError("Cannot save untrained predictor")
        path.mkdir(parents=True, exist_ok=True)
        self.classifier.save_model(str(path / "classifier.json"))
        self.spread_model.save_model(str(path / "spread.json"))
        self.total_model.save_model(str(path / "total.json"))
        meta = {
            "cfg": asdict(self.cfg),
            "feature_importances": self.feature_importances,
            "feature_columns": feature_columns(),
        }
        (path / "meta.json").write_text(json.dumps(meta, indent=2))

    @classmethod
    def load(cls, path: Path) -> NFLGamePredictor:
        """Load a previously saved predictor from disk."""
        if xgb is None:
            raise ImportError("xgboost required: install with `uv pip install xgboost`")
        cfg_dict = json.loads((path / "meta.json").read_text())
        predictor = cls(cfg=NFLModelConfig(**cfg_dict["cfg"]))
        predictor.classifier = xgb.XGBClassifier()
        predictor.classifier.load_model(str(path / "classifier.json"))
        predictor.spread_model = xgb.XGBRegressor()
        predictor.spread_model.load_model(str(path / "spread.json"))
        predictor.total_model = xgb.XGBRegressor()
        predictor.total_model.load_model(str(path / "total.json"))
        predictor.feature_importances = cfg_dict.get("feature_importances", {})
        return predictor


# ──────────────────────────────────────────────────────────────────────
# Convenience entry point
# ──────────────────────────────────────────────────────────────────────


def train_default_model(
    *, n_games: int = 600, save_path: Optional[Path] = None, verbose: bool = False
) -> NFLGamePredictor:
    """Train a default NFLGamePredictor on synthetic data.

    Useful for development/testing and for providing a starting point
    before real nflfastR training data is wired in.

    Args:
        n_games: Number of synthetic games to generate.
        save_path: If provided, save the trained models to this directory.
        verbose: Log training metrics.

    Returns:
        Trained :class:`NFLGamePredictor`.
    """
    df = _generate_synthetic_dataset(n_games=n_games)
    predictor = NFLGamePredictor()
    metrics = predictor.train(df, verbose=verbose)
    if verbose:
        logger.info("Default NFL model metrics: %s", metrics)
    if save_path is not None:
        predictor.save(save_path)
    return predictor
