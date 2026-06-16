"""
Advanced Rating and Feature Engineering Modules for SportsQuant

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
    >>> from sportsquant.models.ratings import RaptorCompositeFeatures
    >>> from sportsquant.models.ratings import TrendFeatures
"""

from __future__ import annotations

from sportsquant.models.ratings.auto_features import (
    DFSConfig,
    DeepFeatureSynthesis,
    EntityConfig,
    compute_feature_importance_dfs,
    generate_dfs_features,
    select_features_by_importance,
)
from sportsquant.models.ratings.bayesian_priors import (
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
from sportsquant.models.ratings.bayesian_shrinkage import (
    BayesianFeatureShrinkage,
    BayesianShrinkageConfig,
    FeatureImportanceConfig,
)
from sportsquant.models.ratings.court_zones import (
    CourtZoneConfig,
    CourtZoneFeatures,
    ShotZoneConfig,
)
from sportsquant.models.ratings.data_access import (
    DataAccess,
    DataAccessConfig,
    IgniteCache,
    KafkaConsumer,
    TimescaleDBClient,
)
from sportsquant.models.ratings.massey_ratings import (
    MasseyRatings,
    MasseyRatingsConfig,
)
from sportsquant.models.ratings.pagerank_ratings import (
    PageRankRatings,
)
from sportsquant.models.ratings.pca_reduction import (
    PCAConfig,
    PCAReducer,
)
from sportsquant.models.ratings.raptor_box import (
    RaptorBoxConfig,
    RaptorBoxFeatures,
)
from sportsquant.models.ratings.raptor_composite import (
    RaptorCompositeConfig,
    RaptorCompositeFeatures,
)
from sportsquant.models.ratings.raptor_onoff import (
    RaptorOnOffConfig,
    RaptorOnOffFeatures,
)
from sportsquant.models.ratings.raptor_priors import (
    RaptorPriorsConfig,
    RaptorPriorsFeatures,
)
from sportsquant.models.ratings.trends import (
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
