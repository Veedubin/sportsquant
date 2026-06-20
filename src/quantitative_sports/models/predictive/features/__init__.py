"""Feature engineering for NBA predictive models.

Provides PRA feature building, game-level feature aggregation,
and general player game log feature construction.
"""

from quantitative_sports.models.predictive.features.build import (
    FeatureBuildConfig,
    build_next_game_features,
    build_training_frame,
    clean_player_gamelog,
)

from quantitative_sports.models.predictive.features.game_features import (
    aggregate_player_projections_to_team,
    build_game_features_from_snapshot,
    build_game_matchup_features,
)

from quantitative_sports.models.predictive.features.pra import (
    PRAFeatureConfig,
    build_pra_features,
    merge_team_context_data,
)

__all__ = [
    # build
    "FeatureBuildConfig",
    "build_next_game_features",
    "build_training_frame",
    "clean_player_gamelog",
    # game_features
    "aggregate_player_projections_to_team",
    "build_game_features_from_snapshot",
    "build_game_matchup_features",
    # pra
    "PRAFeatureConfig",
    "build_pra_features",
    "merge_team_context_data",
]
