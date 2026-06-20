"""
Advanced Rating and Feature Engineering Modules for Quant-Sports

This package contains advanced rating models and feature engineering modules
adapted from the original NBA-Suite/Sports-Platform implementation.

Modules:
- raptor_box: RAPTOR box score component features
- raptor_composite: RAPTOR composite score combining all components
- raptor_onoff: RAPTOR on-court vs off-court features
- raptor_priors: RAPTOR predictive prior features
- bayesian_priors: Bayesian player prior calculations
- bayesian_shrinkage: Bayesian feature shrinkage methods
- massey_ratings: Massey rating system for team strength
- pagerank_ratings: PageRank-style transitive opponent strength
- pca_reduction: PCA dimensionality reduction
- court_zones: Court zone-based shooting features
- trends: Trend, momentum, and volatility features
- auto_features: Automated feature engineering with DFS
- feature_registry: Feature discovery and dependency management
- data_access: Unified data access layer (TimescaleDB, Ignite, Kafka)

Usage:
    >>> from quantitative_sports.models.ratings import RaptorCompositeFeatures
    >>> from quantitative_sports.models.ratings import TrendFeatures
"""

from __future__ import annotations

from quantitative_sports.models.ratings.auto_features import (
    DFSConfig,
    DeepFeatureSynthesis,
    EntityConfig,
    compute_feature_importance_dfs,
    generate_dfs_features,
    select_features_by_importance,
)
from quantitative_sports.models.ratings.bayesian_priors import (
    BayesianPlayerPrior,
    ExperiencePriorGenerator,
    MatchupPriorGenerator,
    PlayerPosteriorRequest,
    PlayerPriorConfig,
    PlayerPriorRequest,
    PositionPriorConfig,
    PositionPriorGenerator,
    StatType,
)
from quantitative_sports.models.ratings.bayesian_shrinkage import (
    BayesianFeatureShrinkage,
    BayesianShrinkageConfig,
    FeatureImportanceConfig,
)
from quantitative_sports.models.ratings.court_zones import (
    CourtZoneConfig,
    CourtZoneFeatures,
    ShotZoneConfig,
)
from quantitative_sports.models.ratings.data_access import (
    DataAccess,
    DataAccessConfig,
    IgniteCache,
    KafkaConsumer,
    TimescaleDBClient,
)
from quantitative_sports.models.ratings.massey_ratings import (
    MasseyRatings,
    MasseyRatingsConfig,
)
from quantitative_sports.models.ratings.pagerank_ratings import (
    PageRankRatings,
)
from quantitative_sports.models.ratings.pca_reduction import (
    PCAConfig,
    PCAReducer,
)
from quantitative_sports.models.ratings.raptor_box import (
    RaptorBoxConfig,
    RaptorBoxFeatures,
)
from quantitative_sports.models.ratings.raptor_composite import (
    RaptorCompositeConfig,
    RaptorCompositeFeatures,
)
from quantitative_sports.models.ratings.raptor_onoff import (
    RaptorOnOffConfig,
    RaptorOnOffFeatures,
)
from quantitative_sports.models.ratings.raptor_priors import (
    RaptorPriorsConfig,
    RaptorPriorsFeatures,
)
from quantitative_sports.models.ratings.trends import (
    RollingTrendConfig,
    TrendConfig,
    TrendFeatures,
)

__all__ = [
    # Data Access
    "DataAccess",
    "DataAccessConfig",
    "IgniteCache",
    "KafkaConsumer",
    "TimescaleDBClient",
    # RAPTOR
    "RaptorBoxConfig",
    "RaptorBoxFeatures",
    "RaptorCompositeConfig",
    "RaptorCompositeFeatures",
    "RaptorOnOffConfig",
    "RaptorOnOffFeatures",
    "RaptorPriorsConfig",
    "RaptorPriorsFeatures",
    # Bayesian
    "BayesianFeatureShrinkage",
    "BayesianShrinkageConfig",
    "BayesianPlayerPrior",
    "PlayerPriorConfig",
    "PlayerPriorRequest",
    "PlayerPosteriorRequest",
    "PositionPriorConfig",
    "PositionPriorGenerator",
    "ExperiencePriorGenerator",
    "MatchupPriorGenerator",
    "StatType",
    "FeatureImportanceConfig",
    # Trends
    "TrendConfig",
    "TrendFeatures",
    "RollingTrendConfig",
    # Ratings
    "MasseyRatings",
    "MasseyRatingsConfig",
    "PageRankRatings",
    # PCA
    "PCAConfig",
    "PCAReducer",
    # Court Zones
    "CourtZoneConfig",
    "CourtZoneFeatures",
    "ShotZoneConfig",
    # Auto Features
    "DFSConfig",
    "EntityConfig",
    "DeepFeatureSynthesis",
    "generate_dfs_features",
    "compute_feature_importance_dfs",
    "select_features_by_importance",
]
