"""Tests for NFL XGBoost game outcome model."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from quantitative_sports.models.predictive.nfl_game_model import (
    NFLGameFeatures,
    NFLGamePrediction,
    NFLGamePredictor,
    NFLModelConfig,
    _generate_synthetic_dataset,
    aggregate_team_stats,
    build_features_from_pipeline,
    feature_columns,
    train_default_model,
)


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────


@pytest.fixture
def synthetic_df() -> pd.DataFrame:
    return _generate_synthetic_dataset(n_games=400, seed=42)


@pytest.fixture
def trained_predictor(synthetic_df: pd.DataFrame) -> NFLGamePredictor:
    p = NFLGamePredictor()
    p.train(synthetic_df, verbose=False)
    return p


# ──────────────────────────────────────────────────────────────────────
# Features
# ──────────────────────────────────────────────────────────────────────


def test_nfl_game_features_to_dataframe_includes_meta() -> None:
    feats = NFLGameFeatures(home_team="KC", away_team="BAL", season=2024, week=10)
    df = feats.to_dataframe()
    assert df.loc[0, "home_team"] == "KC"
    assert df.loc[0, "away_team"] == "BAL"
    assert df.loc[0, "season"] == 2024
    assert df.loc[0, "week"] == 10
    # Has all feature columns plus meta
    assert all(col in df.columns for col in feature_columns())


def test_nfl_game_features_feature_vector_matches_columns() -> None:
    feats = NFLGameFeatures(home_team="KC", away_team="BAL", season=2024, week=10)
    cols = feature_columns()
    vec = feats.feature_vector()
    assert vec.shape == (len(cols),)


def test_aggregate_team_stats_empty_df() -> None:
    out = aggregate_team_stats(pd.DataFrame(), team="KC")
    assert out == {"ppg_for": 0.0, "yards_per_play_est": 0.0, "qb_rating_proxy": 0.0}


def test_aggregate_team_stats_no_team_match() -> None:
    df = pd.DataFrame({"recent_team": ["BAL", "BAL"], "passing_yards": [200, 250]})
    out = aggregate_team_stats(df, team="KC")
    assert out["ppg_for"] == 0.0


def test_aggregate_team_stats_computes_aggregates() -> None:
    df = pd.DataFrame(
        {
            "recent_team": ["KC", "KC", "KC"],
            "week": [1, 2, 3],
            "passing_yards": [250, 280, 300],
            "rushing_yards": [80, 90, 100],
            "carries": [20, 22, 24],
            "attempts": [30, 32, 35],
            "completions": [20, 22, 25],
            "fantasy_points_ppr": [40.0, 45.0, 50.0],
        }
    )
    out = aggregate_team_stats(df, team="KC")
    assert out["ppg_for"] > 0
    assert out["yards_per_play_est"] > 0
    assert 0 <= out["qb_rating_proxy"] <= 100


def test_build_features_from_pipeline_no_data() -> None:
    class FakeNflfastr:
        def get_season(self, season):  # noqa: ARG002
            return pd.DataFrame()

    class FakePipeline:
        nflfastr = FakeNflfastr()

    feats = build_features_from_pipeline(
        FakePipeline(), home_team="KC", away_team="BAL", season=2024, week=10
    )
    assert feats.home_team == "KC"
    assert feats.home_ppg_for == 0.0


def test_build_features_from_pipeline_with_data() -> None:
    class FakeNflfastr:
        def get_season(self, season):  # noqa: ARG002
            return pd.DataFrame(
                {
                    "recent_team": ["KC", "KC", "BAL", "BAL"],
                    "week": [1, 2, 1, 2],
                    "passing_yards": [250, 280, 240, 270],
                    "rushing_yards": [80, 90, 70, 85],
                    "carries": [20, 22, 18, 20],
                    "attempts": [30, 32, 28, 30],
                    "completions": [20, 22, 18, 20],
                    "fantasy_points_ppr": [40.0, 45.0, 38.0, 42.0],
                }
            )

    class FakePipeline:
        nflfastr = FakeNflfastr()

    feats = build_features_from_pipeline(
        FakePipeline(), home_team="KC", away_team="BAL", season=2024, week=10
    )
    assert feats.home_ppg_for > 0
    assert feats.away_ppg_for > 0
    # Cross-defense proxy
    assert feats.home_ppg_against == feats.away_ppg_for


# ──────────────────────────────────────────────────────────────────────
# Synthetic data
# ──────────────────────────────────────────────────────────────────────


def test_generate_synthetic_dataset_columns_and_size() -> None:
    df = _generate_synthetic_dataset(n_games=300)
    assert len(df) == 300
    assert set(feature_columns()).issubset(df.columns)
    assert {"home_win", "spread", "total"}.issubset(df.columns)
    assert df["home_win"].isin([0, 1]).all()


def test_generate_synthetic_dataset_deterministic_with_seed() -> None:
    a = _generate_synthetic_dataset(n_games=100, seed=7)
    b = _generate_synthetic_dataset(n_games=100, seed=7)
    assert a.equals(b)


# ──────────────────────────────────────────────────────────────────────
# Training
# ──────────────────────────────────────────────────────────────────────


def test_train_default_model_produces_trained_predictor() -> None:
    p = train_default_model(n_games=200, verbose=False)
    assert p.is_trained()


def test_train_rejects_missing_features() -> None:
    p = NFLGamePredictor()
    bad = pd.DataFrame({"home_win": [1, 0], "spread": [3.0, -2.0], "total": [45.0, 50.0]})
    with pytest.raises(ValueError, match="missing features"):
        p.train(bad)


def test_train_rejects_missing_targets() -> None:
    p = NFLGamePredictor()
    df = _generate_synthetic_dataset(n_games=200).drop(columns=["home_win"])
    with pytest.raises(ValueError, match="missing target"):
        p.train(df)


def test_train_rejects_too_few_samples(synthetic_df: pd.DataFrame) -> None:
    p = NFLGamePredictor(cfg=NFLModelConfig(min_training_samples=10000))
    with pytest.raises(ValueError, match="at least"):
        p.train(synthetic_df)


def test_train_returns_holdout_metrics(synthetic_df: pd.DataFrame) -> None:
    p = NFLGamePredictor()
    metrics = p.train(synthetic_df)
    assert "holdout_acc" in metrics
    assert "holdout_spread_rmse" in metrics
    assert "holdout_total_rmse" in metrics
    # Synthetic data has signal — accuracy should beat coin flip
    assert metrics["holdout_acc"] > 0.55


def test_train_populates_feature_importances(trained_predictor: NFLGamePredictor) -> None:
    assert trained_predictor.feature_importances
    assert set(trained_predictor.feature_importances) == set(feature_columns())


# ──────────────────────────────────────────────────────────────────────
# Prediction
# ──────────────────────────────────────────────────────────────────────


def test_predict_requires_training() -> None:
    p = NFLGamePredictor()
    with pytest.raises(RuntimeError, match="not trained"):
        p.predict(NFLGameFeatures(home_team="KC", away_team="BAL", season=2024, week=10))


def test_predict_returns_nfl_game_prediction(trained_predictor: NFLGamePredictor) -> None:
    feats = NFLGameFeatures(
        home_team="KC",
        away_team="BAL",
        season=2024,
        week=10,
        home_ppg_for=28.0,
        away_ppg_for=22.0,
        home_yards_per_play=6.2,
        away_yards_per_play=5.5,
        home_qb_rating=100.0,
        away_qb_rating=85.0,
        home_ppg_against=20.0,
        away_ppg_against=24.0,
    )
    pred = trained_predictor.predict(feats)
    assert isinstance(pred, NFLGamePrediction)
    assert pred.home_team == "KC"
    assert pred.away_team == "BAL"
    assert 0.0 <= pred.home_win_prob <= 1.0
    assert 0.0 <= pred.away_win_prob <= 1.0
    assert abs((pred.home_win_prob + pred.away_win_prob) - 1.0) < 1e-6


def test_predict_win_probability_convenience(
    trained_predictor: NFLGamePredictor,
) -> None:
    feats = NFLGameFeatures(home_team="KC", away_team="BAL", season=2024, week=10)
    prob = trained_predictor.predict_win_probability(feats)
    assert 0.0 <= prob <= 1.0


def test_stronger_home_team_gets_higher_win_prob(
    trained_predictor: NFLGamePredictor,
) -> None:
    # Use values consistent with the synthetic data distribution:
    # ppg ~ N(22, 5), qb_rating ~ N(85, 12).
    strong = NFLGameFeatures(
        home_team="KC",
        away_team="BAL",
        season=2024,
        week=10,
        home_ppg_for=30.0,
        away_ppg_for=15.0,
        home_qb_rating=110.0,
        away_qb_rating=70.0,
        home_ppg_against=18.0,
        away_ppg_against=28.0,
    )
    weak = NFLGameFeatures(
        home_team="CAR",
        away_team="KC",
        season=2024,
        week=10,
        home_ppg_for=15.0,
        away_ppg_for=30.0,
        home_qb_rating=70.0,
        away_qb_rating=110.0,
        home_ppg_against=28.0,
        away_ppg_against=18.0,
    )
    p_strong = trained_predictor.predict(strong).home_win_prob
    p_weak = trained_predictor.predict(weak).home_win_prob
    assert p_strong > p_weak, f"strong={p_strong}, weak={p_weak}"


# ──────────────────────────────────────────────────────────────────────
# Persistence
# ──────────────────────────────────────────────────────────────────────


def test_save_load_roundtrip(trained_predictor: NFLGamePredictor, tmp_path: Path) -> None:
    trained_predictor.save(tmp_path)

    # Files exist
    assert (tmp_path / "classifier.json").exists()
    assert (tmp_path / "spread.json").exists()
    assert (tmp_path / "total.json").exists()
    assert (tmp_path / "meta.json").exists()

    # Round-trip
    loaded = NFLGamePredictor.load(tmp_path)
    assert loaded.is_trained()

    feats = NFLGameFeatures(home_team="KC", away_team="BAL", season=2024, week=10)
    p_orig = trained_predictor.predict(feats)
    p_loaded = loaded.predict(feats)
    assert abs(p_orig.home_win_prob - p_loaded.home_win_prob) < 1e-6
    assert abs(p_orig.proj_spread - p_loaded.proj_spread) < 1e-6


def test_save_untrained_raises() -> None:
    p = NFLGamePredictor()
    with pytest.raises(RuntimeError, match="untrained"):
        p.save(Path("/tmp/should_not_exist"))


def test_meta_json_has_feature_columns(trained_predictor: NFLGamePredictor, tmp_path: Path) -> None:
    trained_predictor.save(tmp_path)
    meta = json.loads((tmp_path / "meta.json").read_text())
    assert meta["feature_columns"] == feature_columns()
    assert "cfg" in meta
    assert "feature_importances" in meta


# ──────────────────────────────────────────────────────────────────────
# Dataclass to_dict
# ──────────────────────────────────────────────────────────────────────


def test_nfl_game_prediction_to_dict() -> None:
    pred = NFLGamePrediction(
        home_team="KC",
        away_team="BAL",
        season=2024,
        week=10,
        home_win_prob=0.65,
        away_win_prob=0.35,
        proj_spread=3.5,
        proj_total=47.5,
    )
    d = pred.to_dict()
    assert d["home_team"] == "KC"
    assert d["home_win_prob"] == 0.65
    assert d["proj_spread"] == 3.5


def test_nfl_game_features_default_zeros() -> None:
    feats = NFLGameFeatures(home_team="KC", away_team="BAL", season=2024, week=10)
    # All numeric fields default to 0 except home_advantage (2.5 baseline)
    for field_name in feature_columns():
        if field_name == "home_advantage":
            assert getattr(feats, field_name) == 2.5
        else:
            assert getattr(feats, field_name) == 0.0
