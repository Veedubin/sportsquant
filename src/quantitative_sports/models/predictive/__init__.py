"""Predictive models for NBA sports analytics.

This package provides XGBoost-based predictive models for NBA player
props and game outcomes, including PRA simulation, component models,
game-level betting models, and baseline evaluation.
"""

from quantitative_sports.models.predictive.artifact import (
    ModelConfig,
    evaluate_holdout_rmse,
    evaluate_holdout_with_baselines,
    evaluate_time_series_cv_with_baselines,
    load_artifact,
    save_artifact,
    train_regressor,
)

from quantitative_sports.models.predictive.baselines import (
    NormalBaseline,
    add_baseline_probabilities,
    baseline_from_feature_row,
    baseline_last_n_mean,
    baseline_minutes_x_rate,
    baseline_season_mean_to_date,
    estimate_sigma,
    normal_p_over,
)

from quantitative_sports.models.predictive.game_models import (
    GameOutcomePredictor,
    GamePrediction,
    MoneylineModel,
    SpreadModel,
    TeamTotalModel,
    predict_games_from_features,
)

from quantitative_sports.models.predictive.io import load_pra_features

from quantitative_sports.models.predictive.pra_components import (
    ComponentModelPaths,
    PraComponentTrainConfig,
    train_pra_component_models,
)

from quantitative_sports.models.predictive.simulate import (
    PraSimConfig,
    simulate_pra_distribution_for_rows,
    simulate_pra_for_lines_csv,
)

from quantitative_sports.models.predictive.single_stat_simulate import (
    SingleStatSimResult,
    StatType,
    add_betting_columns_single_stat,
    simulate_combo_stat,
    simulate_single_stat,
    simulate_single_stat_for_rows,
)

__all__ = [
    # artifact
    "ModelConfig",
    "evaluate_holdout_rmse",
    "evaluate_holdout_with_baselines",
    "evaluate_time_series_cv_with_baselines",
    "load_artifact",
    "save_artifact",
    "train_regressor",
    # baselines
    "NormalBaseline",
    "add_baseline_probabilities",
    "baseline_from_feature_row",
    "baseline_last_n_mean",
    "baseline_minutes_x_rate",
    "baseline_season_mean_to_date",
    "estimate_sigma",
    "normal_p_over",
    # game_models
    "GameOutcomePredictor",
    "GamePrediction",
    "MoneylineModel",
    "SpreadModel",
    "TeamTotalModel",
    "predict_games_from_features",
    # io
    "load_pra_features",
    # pra_components
    "ComponentModelPaths",
    "PraComponentTrainConfig",
    "train_pra_component_models",
    # simulate
    "PraSimConfig",
    "simulate_pra_distribution_for_rows",
    "simulate_pra_for_lines_csv",
    # single_stat_simulate
    "SingleStatSimResult",
    "StatType",
    "add_betting_columns_single_stat",
    "simulate_combo_stat",
    "simulate_single_stat",
    "simulate_single_stat_for_rows",
]
