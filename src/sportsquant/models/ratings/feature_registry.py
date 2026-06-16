"""
Feature Registry for Sports Platform

Provides feature discovery, registration, and dependency management for all
advanced feature engineering modules.

Features:
- Automatic feature discovery
- Feature dependency tracking
- Feature category organization
- Metadata management

Usage:
    >>> from sportsquant.models.ratings.feature_registry import FeatureRegistry
    >>> registry = FeatureRegistry()
    >>> registry.discover_features()
    >>> raptor_features = registry.get_features_by_category("raptor")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sportsquant.models.ratings.auto_features import DFSConfig, DeepFeatureSynthesis
from sportsquant.models.ratings.bayesian_priors import (
    BayesianPlayerPrior,
    PlayerPriorConfig,
)
from sportsquant.models.ratings.bayesian_shrinkage import (
    BayesianFeatureShrinkage,
    BayesianShrinkageConfig,
)
from sportsquant.models.ratings.court_zones import CourtZoneConfig, CourtZoneFeatures
from sportsquant.models.ratings.massey_ratings import MasseyRatings, MasseyRatingsConfig
from sportsquant.models.ratings.pagerank_ratings import PageRankRatings
from sportsquant.models.ratings.pca_reduction import PCAConfig, PCAReducer
from sportsquant.models.ratings.raptor_box import RaptorBoxConfig, RaptorBoxFeatures
from sportsquant.models.ratings.raptor_composite import (
    RaptorCompositeConfig,
    RaptorCompositeFeatures,
)
from sportsquant.models.ratings.raptor_onoff import RaptorOnOffConfig, RaptorOnOffFeatures
from sportsquant.models.ratings.raptor_priors import RaptorPriorsConfig, RaptorPriorsFeatures
from sportsquant.models.ratings.trends import TrendConfig, TrendFeatures


@dataclass
class FeatureMetadata:
    """Metadata for a feature.

    Attributes:
        name: Feature name.
        category: Feature category (e.g., 'raptor', 'bayesian', 'trends').
        description: Human-readable description.
        dependencies: List of other features this depends on.
        data_sources: Data sources required (e.g., 'timescaledb', 'kafka', 'ignite').
        compute_fn: Function to compute the feature.
        config_class: Configuration class for the feature.
    """

    name: str
    category: str
    description: str
    dependencies: list[str] = field(default_factory=list)
    data_sources: list[str] = field(default_factory=list)
    compute_fn: Any = None
    config_class: Any = None


@dataclass
class FeatureCategory:
    """Category grouping for features.

    Attributes:
        name: Category name.
        description: Category description.
        features: List of feature names in this category.
    """

    name: str
    description: str
    features: list[str] = field(default_factory=list)


class FeatureRegistry:
    """Registry for all available features in the sports platform.

    Provides:
    - Feature discovery and registration
    - Dependency resolution
    - Feature metadata management
    - Category-based organization

    Data Sources:
    - TimescaleDB: Player statistics, game data
    - Kafka: Real-time player stats, schedules
    - Apache Ignite: Distributed caching
    """

    def __init__(self) -> None:
        """Initialize feature registry."""
        self._features: dict[str, FeatureMetadata] = {}
        self._categories: dict[str, FeatureCategory] = {}
        self._initialized = False

    def register_feature(self, feature: FeatureMetadata) -> None:
        """Register a feature with the registry.

        Args:
            feature: Feature metadata to register.
        """
        self._features[feature.name] = feature

        if feature.category not in self._categories:
            self._categories[feature.category] = FeatureCategory(
                name=feature.category,
                description=f"Features related to {feature.category}",
            )
        self._categories[feature.category].features.append(feature.name)

    def get_feature(self, name: str) -> FeatureMetadata | None:
        """Get feature metadata by name.

        Args:
            name: Feature name.

        Returns:
            Feature metadata or None if not found.
        """
        return self._features.get(name)

    def get_features_by_category(self, category: str) -> list[FeatureMetadata]:
        """Get all features in a category.

        Args:
            category: Category name.

        Returns:
            List of feature metadata.
        """
        cat = self._categories.get(category)
        if cat is None:
            return []
        return [self._features[f] for f in cat.features if f in self._features]

    def get_all_features(self) -> list[FeatureMetadata]:
        """Get all registered features.

        Returns:
            List of all feature metadata.
        """
        return list(self._features.values())

    def get_feature_names(self) -> list[str]:
        """Get all feature names.

        Returns:
            List of feature names.
        """
        return list(self._features.keys())

    def get_categories(self) -> list[str]:
        """Get all category names.

        Returns:
            List of category names.
        """
        return list(self._categories.keys())

    def resolve_dependencies(self, feature_names: list[str]) -> list[str]:
        """Resolve feature dependencies in order.

        Args:
            feature_names: List of feature names to resolve.

        Returns:
            List of feature names in dependency order.
        """
        resolved: list[str] = []
        seen: set[str] = set()

        def resolve(name: str) -> None:
            if name in seen:
                return
            seen.add(name)

            feature = self._features.get(name)
            if feature:
                for dep in feature.dependencies:
                    resolve(dep)
                if name not in resolved:
                    resolved.append(name)

        for name in feature_names:
            resolve(name)

        return resolved

    def discover_features(self) -> None:
        """Automatically discover and register all features."""
        if self._initialized:
            return

        self._register_raptor_features()
        self._register_bayesian_features()
        self._register_trend_features()
        self._register_rating_features()
        self._register_reduction_features()
        self._register_zone_features()
        self._register_auto_features()

        self._initialized = True

    def _register_raptor_features(self) -> None:
        """Register RAPTOR-related features."""
        raptor_features = [
            FeatureMetadata(
                name="raptor_box",
                category="raptor",
                description=(
                    "RAPTOR box score component features "
                    "(scoring, playmaking, rebounding, defense, pacing)"
                ),
                dependencies=[],
                data_sources=["timescaledb", "kafka"],
                compute_fn=RaptorBoxFeatures,
                config_class=RaptorBoxConfig,
            ),
            FeatureMetadata(
                name="raptor_onoff",
                category="raptor",
                description="RAPTOR on-court vs off-court performance differentials",
                dependencies=["raptor_box"],
                data_sources=["timescaledb", "kafka", "ignite"],
                compute_fn=RaptorOnOffFeatures,
                config_class=RaptorOnOffConfig,
            ),
            FeatureMetadata(
                name="raptor_priors",
                category="raptor",
                description=(
                    "RAPTOR predictive priors (age, height, draft, contract, injury, schedule)"
                ),
                dependencies=[],
                data_sources=["timescaledb", "kafka"],
                compute_fn=RaptorPriorsFeatures,
                config_class=RaptorPriorsConfig,
            ),
            FeatureMetadata(
                name="raptor_composite",
                category="raptor",
                description="RAPTOR composite score combining box, on-off, and priors components",
                dependencies=["raptor_box", "raptor_onoff", "raptor_priors"],
                data_sources=["timescaledb", "kafka", "ignite"],
                compute_fn=RaptorCompositeFeatures,
                config_class=RaptorCompositeConfig,
            ),
        ]

        for feature in raptor_features:
            self.register_feature(feature)

    def _register_bayesian_features(self) -> None:
        """Register Bayesian-related features."""
        bayesian_features = [
            FeatureMetadata(
                name="bayesian_shrinkage",
                category="bayesian",
                description="Bayesian feature shrinkage for small-sample estimation",
                dependencies=[],
                data_sources=["timescaledb", "ignite"],
                compute_fn=BayesianFeatureShrinkage,
                config_class=BayesianShrinkageConfig,
            ),
            FeatureMetadata(
                name="bayesian_priors",
                category="bayesian",
                description="Bayesian player priors (position, experience, matchup)",
                dependencies=[],
                data_sources=["timescaledb", "ignite"],
                compute_fn=BayesianPlayerPrior,
                config_class=PlayerPriorConfig,
            ),
        ]

        for feature in bayesian_features:
            self.register_feature(feature)

    def _register_trend_features(self) -> None:
        """Register trend-related features."""
        trend_features = [
            FeatureMetadata(
                name="trends",
                category="trends",
                description="Trend, momentum, and volatility features for time series analysis",
                dependencies=[],
                data_sources=["timescaledb", "kafka"],
                compute_fn=TrendFeatures,
                config_class=TrendConfig,
            ),
        ]

        for feature in trend_features:
            self.register_feature(feature)

    def _register_rating_features(self) -> None:
        """Register rating-related features."""
        rating_features = [
            FeatureMetadata(
                name="massey_ratings",
                category="ratings",
                description="Massey rating system for team strength (attack/defense decomposition)",
                dependencies=[],
                data_sources=["timescaledb", "ignite"],
                compute_fn=MasseyRatings,
                config_class=MasseyRatingsConfig,
            ),
            FeatureMetadata(
                name="pagerank_ratings",
                category="ratings",
                description="PageRank-style transitive opponent strength ratings",
                dependencies=[],
                data_sources=["timescaledb", "ignite"],
                compute_fn=PageRankRatings,
                config_class=None,
            ),
        ]

        for feature in rating_features:
            self.register_feature(feature)

    def _register_reduction_features(self) -> None:
        """Register dimensionality reduction features."""
        reduction_features = [
            FeatureMetadata(
                name="pca_reduction",
                category="reduction",
                description="PCA-based dimensionality reduction for feature compression",
                dependencies=[],
                data_sources=["ignite"],
                compute_fn=PCAReducer,
                config_class=PCAConfig,
            ),
        ]

        for feature in reduction_features:
            self.register_feature(feature)

    def _register_zone_features(self) -> None:
        """Register court zone features."""
        zone_features = [
            FeatureMetadata(
                name="court_zones",
                category="zones",
                description="Court zone-based shooting efficiency and tendency features",
                dependencies=[],
                data_sources=["timescaledb", "kafka", "ignite"],
                compute_fn=CourtZoneFeatures,
                config_class=CourtZoneConfig,
            ),
        ]

        for feature in zone_features:
            self.register_feature(feature)

    def _register_auto_features(self) -> None:
        """Register automated feature engineering features."""
        auto_features = [
            FeatureMetadata(
                name="auto_features",
                category="automation",
                description="Deep Feature Synthesis for automated feature generation",
                dependencies=[],
                data_sources=["timescaledb", "kafka"],
                compute_fn=DeepFeatureSynthesis,
                config_class=DFSConfig,
            ),
        ]

        for feature in auto_features:
            self.register_feature(feature)

    def get_feature_info(self, name: str) -> dict[str, Any]:
        """Get comprehensive information about a feature.

        Args:
            name: Feature name.

        Returns:
            Dictionary with feature information.
        """
        feature = self._features.get(name)
        if feature is None:
            return {}

        return {
            "name": feature.name,
            "category": feature.category,
            "description": feature.description,
            "dependencies": feature.dependencies,
            "data_sources": feature.data_sources,
            "has_config": feature.config_class is not None,
        }

    def list_features_by_source(self, source: str) -> list[str]:
        """List features that require a specific data source.

        Args:
            source: Data source name (e.g., 'timescaledb', 'kafka', 'ignite').

        Returns:
            List of feature names.
        """
        return [name for name, feature in self._features.items() if source in feature.data_sources]

    def validate_dependencies(self, feature_names: list[str]) -> tuple[bool, list[str]]:
        """Validate that all dependencies exist for specified features.

        Args:
            feature_names: List of feature names to validate.

        Returns:
            Tuple of (is_valid, list of missing dependencies).
        """
        all_deps: set[str] = set()
        for name in feature_names:
            feature = self._features.get(name)
            if feature:
                all_deps.update(feature.dependencies)

        missing = [dep for dep in all_deps if dep not in self._features]
        return len(missing) == 0, missing
