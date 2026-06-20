"""
Bayesian Feature Shrinkage

Implements Bayesian feature shrinkage for small-sample estimation.
Shrinks feature estimates toward league averages to reduce overfitting.

Key components:
1. Empirical Bayes prior computation
2. Hierarchical shrinkage by group
3. Feature importance with uncertainty
4. Adaptive shrinkage based on feature reliability

Data Sources:
- Player stats: TimescaleDB (player_stats table)
- Game data: Kafka topic 'sports-analytics-player-stats'
- Caching: Apache Ignite for feature storage and retrieval

Usage:
    >>> from quantitative_sports.models.ratings.bayesian_shrinkage import BayesianFeatureShrinkage
    >>> shrinkage = BayesianFeatureShrinkage()
    >>> shrunk = shrinkage.compute_shrunk_features(X, y)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler


@dataclass(frozen=True)
class BayesianShrinkageConfig:
    """Configuration for Bayesian feature shrinkage.

    Attributes:
        shrinkage_factor: Default shrinkage intensity (0-1).
            Higher values = more shrinkage toward prior.
        prior_mean: Prior mean for feature values (usually 0).
        prior_variance: Prior variance for feature values.
        sample_size_threshold: Minimum samples for no shrinkage.
        feature_variance_floor: Minimum variance to avoid division by zero.
    """

    shrinkage_factor: float = 0.3
    prior_mean: float = 0.0
    prior_variance: float = 1.0
    sample_size_threshold: int = 30
    feature_variance_floor: float = 1e-6


@dataclass(frozen=True)
class FeatureImportanceConfig:
    """Configuration for feature importance with uncertainty.

    Attributes:
        n_bootstrap: Number of bootstrap samples for confidence intervals.
        confidence_level: Confidence level for intervals (0.9 = 90%).
        min_feature_count: Minimum occurrences for importance calculation.
    """

    n_bootstrap: int = 100
    confidence_level: float = 0.9
    min_feature_count: int = 10


def compute_empirical_prior(
    x: pd.DataFrame,
    y: pd.Series,
    target_col: str,
    shrinkage_factor: float = 0.3,
) -> dict[str, float]:
    """Compute empirical prior from data and apply shrinkage.

    Uses empirical Bayes approach to estimate feature priors
    from the data itself, then shrinks estimates toward the prior.

    Args:
        x: Feature DataFrame.
        y: Target series.
        target_col: Name of target column to exclude from features.
        shrinkage_factor: Intensity of shrinkage.

    Returns:
        Dictionary of shrunk feature values.
    """
    feature_cols = [c for c in x.columns if c != target_col]

    if not feature_cols:
        return {}

    if len(y) < 2:
        return dict.fromkeys(feature_cols, 0.0)

    priors: dict[str, float] = {}

    for col in feature_cols:
        if col not in x.columns:
            continue

        mask = x[col].notna() & y.notna()
        if mask.sum() < 2:
            priors[col] = 0.0
            continue

        feature_values = x.loc[mask, col]
        target_values = y[mask]

        if feature_values.std() < 1e-6:
            priors[col] = 0.0
            continue

        try:
            correlation = np.corrcoef(feature_values, target_values)[0, 1]
            if np.isnan(correlation):
                correlation = 0.0
        except ValueError:
            correlation = 0.0

        sample_size = mask.sum()
        shrinkage_weight = shrinkage_factor * min(1.0, sample_size / 30)

        shrunk_value = (1 - shrinkage_weight) * correlation + shrinkage_weight * 0.0
        priors[col] = shrunk_value

    return priors


def compute_shrunk_features(
    x: pd.DataFrame,
    _y: pd.Series,
    shrinkage_factor: float = 0.3,
    prior_mean: float = 0.0,
) -> pd.DataFrame:
    """Apply Bayesian shrinkage to feature values.

    Shrinks individual feature values toward the prior mean
    based on sample size uncertainty.

    Args:
        x: Feature DataFrame.
        y: Target series.
        shrinkage_factor: Intensity of shrinkage.
        prior_mean: Prior mean to shrink toward.

    Returns:
        DataFrame with shrunk feature values.
    """
    if x.empty:
        return x

    shrunk = x.copy()

    for col in x.columns:
        if x[col].dtype in [object, "category"]:
            continue

        mask = x[col].notna()
        sample_size = mask.sum()

        if sample_size < 2:
            continue

        col_std = x.loc[mask, col].std()
        if col_std < 1e-6:
            shrunk[col] = prior_mean
            continue

        shrinkage_weight = shrinkage_factor * min(1.0, sample_size / 30)

        original_values = np.asarray(x[col].values, dtype=np.float64)
        shrunk_values = (1 - shrinkage_weight) * original_values + shrinkage_weight * prior_mean

        shrunk[col] = shrunk_values

    return shrunk


def compute_posterior_variance(
    prior_variance: float,
    sample_variance: float,
    sample_size: int,
    shrinkage_factor: float = 0.3,
) -> float:
    """Compute posterior variance under Bayesian shrinkage model.

    Args:
        prior_variance: Prior variance.
        sample_variance: Sample variance from data.
        sample_size: Number of samples.
        shrinkage_factor: Shrinkage intensity.

    Returns:
        Posterior variance estimate.
    """
    if sample_size < 2:
        return prior_variance

    precision_weight = sample_size / (sample_variance + 1e-6)
    prior_precision = 1.0 / (prior_variance + 1e-6)

    effective_precision = prior_precision + shrinkage_factor * precision_weight

    if effective_precision < 1e-6:
        return prior_variance

    posterior_variance = 1.0 / effective_precision

    return posterior_variance


def compute_feature_importance_with_uncertainty(
    x: pd.DataFrame,
    y: pd.Series,
    n_bootstrap: int = 100,
    confidence_level: float = 0.9,
) -> pd.DataFrame:
    """Compute feature importance with credible intervals via bootstrap.

    Args:
        X: Feature DataFrame.
        y: Target series.
        n_bootstrap: Number of bootstrap iterations.
        confidence_level: Confidence level for intervals.

    Returns:
        DataFrame with importance, lower/upper bounds.
    """
    # pylint: disable=R0914
    feature_cols = x.select_dtypes(include=[np.number]).columns.tolist()

    if not feature_cols:
        return pd.DataFrame()

    x_clean = x[feature_cols].fillna(0)
    y_clean = y.fillna(0)

    scaler = StandardScaler()
    x_scaled = scaler.fit_transform(x_clean)

    bootstrap_importances: list[dict[str, float]] = []

    rng = np.random.default_rng()
    for _ in range(n_bootstrap):
        indices = rng.choice(len(x_scaled), size=len(x_scaled), replace=True)

        if len(np.unique(y_clean.iloc[indices])) < 2:
            continue

        try:
            model = RandomForestClassifier(n_estimators=50, random_state=_, max_depth=5)
            model.fit(x_scaled[indices], y_clean.iloc[indices])

            importances = dict(zip(feature_cols, model.feature_importances_.astype(float)))
            bootstrap_importances.append(importances)
        except ValueError:
            continue

    if not bootstrap_importances:
        return pd.DataFrame()

    importance_data: dict[str, list[float]] = {col: [] for col in feature_cols}

    for imp in bootstrap_importances:
        for col in feature_cols:
            importance_data[col].append(imp.get(col, 0.0))

    results: dict[str, Any] = {"feature": [], "importance": [], "std": []}

    alpha_lower = (1 - confidence_level) / 2
    alpha_upper = 1 - alpha_lower

    for col in feature_cols:
        values = importance_data[col]
        if not values:
            continue

        results["feature"].append(col)
        results["importance"].append(np.mean(values))
        results["std"].append(np.std(values))
        results[f"lower_{int(confidence_level * 100)}"].append(
            np.percentile(values, alpha_lower * 100)
        )
        results[f"upper_{int(confidence_level * 100)}"].append(
            np.percentile(values, alpha_upper * 100)
        )

    return pd.DataFrame(results).set_index("feature")


def compute_hierarchical_shrinkage(
    x: pd.DataFrame,
    y: pd.Series,
    group_col: str | None = None,
    shrinkage_factor: float = 0.3,
) -> pd.DataFrame:
    """Apply hierarchical shrinkage accounting for group structure.

    Shrinks more for small groups, less for large groups.

    Args:
        x: Feature DataFrame.
        y: Target series.
        group_col: Column identifying groups (e.g., player_id).
        shrinkage_factor: Maximum shrinkage intensity.

    Returns:
        DataFrame with hierarchically shrunk features.
    """
    if group_col is None or group_col not in x.columns:
        return compute_shrunk_features(x, y, shrinkage_factor)

    result = x.copy()

    for _, group_data in x.groupby(group_col):
        if len(group_data) < 2:
            group_shrinkage = shrinkage_factor
        else:
            group_shrinkage = shrinkage_factor * min(1.0, 30 / len(group_data))

        shrunk_group = compute_shrunk_features(group_data, y, group_shrinkage)

        for col in x.columns:
            if col != group_col and col in result.columns:
                result.loc[group_data.index, col] = shrunk_group[col]

    return result


class BayesianFeatureShrinkage:
    """Implements Bayesian feature shrinkage for small-sample estimation.

    Provides methods for shrinking feature estimates toward league
    averages to reduce overfitting with limited data.

    All feature calculation logic is preserved from the original implementation.
    Data sources have been adapted to use TimescaleDB and Kafka instead of Redis.
    """

    def __init__(self, config: BayesianShrinkageConfig | None = None) -> None:
        """Initialize Bayesian shrinkage processor.

        Args:
            config: Shrinkage configuration.
        """
        self.config = config or BayesianShrinkageConfig()

    def compute_shrunk_features(self, x: pd.DataFrame, y: pd.Series) -> pd.DataFrame:
        """Shrink features toward prior mean.

        Args:
            x: Feature DataFrame.
            y: Target series.

        Returns:
            DataFrame with shrunk features.
        """
        return compute_shrunk_features(
            x,
            y,
            shrinkage_factor=self.config.shrinkage_factor,
            prior_mean=self.config.prior_mean,
        )

    def compute_empirical_prior(
        self, x: pd.DataFrame, y: pd.Series, target_col: str
    ) -> dict[str, float]:
        """Compute empirical prior from data.

        Args:
            x: Feature DataFrame.
            y: Target series.
            target_col: Target column name.

        Returns:
            Dictionary of prior values.
        """
        return compute_empirical_prior(x, y, target_col, self.config.shrinkage_factor)

    def compute_importance_with_uncertainty(self, x: pd.DataFrame, y: pd.Series) -> pd.DataFrame:
        """Compute feature importance with credible intervals.

        Args:
            x: Feature DataFrame.
            y: Target series.

        Returns:
            DataFrame with importance and confidence intervals.
        """
        return compute_feature_importance_with_uncertainty(
            x, y, n_bootstrap=100, confidence_level=0.9
        )

    def compute_hierarchical_shrinkage(
        self, x: pd.DataFrame, y: pd.Series, group_col: str | None = None
    ) -> pd.DataFrame:
        """Apply hierarchical shrinkage.

        Args:
            x: Feature DataFrame.
            y: Target series.
            group_col: Grouping column.

        Returns:
            DataFrame with hierarchically shrunk features.
        """
        return compute_hierarchical_shrinkage(x, y, group_col, self.config.shrinkage_factor)


def compute_beta_prior(
    sample_mean: float,
    sample_size: int,
    prior_alpha: float = 1.0,
    prior_beta: float = 1.0,
    shrinkage_factor: float = 0.3,
) -> float:
    """Compute posterior mean under Beta-Binomial model.

    Useful for shrinking probability estimates.

    Args:
        sample_mean: Empirical probability.
        sample_size: Number of observations.
        prior_alpha: Prior alpha parameter.
        prior_beta: Prior beta parameter.
        shrinkage_factor: Additional shrinkage intensity.

    Returns:
        Posterior mean estimate.
    """
    posterior_alpha = prior_alpha + shrinkage_factor * sample_size * sample_mean
    posterior_beta = prior_beta + shrinkage_factor * sample_size * (1 - sample_mean)

    if posterior_alpha + posterior_beta < 1e-6:
        return sample_mean

    return posterior_alpha / (posterior_alpha + posterior_beta)


@dataclass(frozen=True)
class NormalPriorConfig:
    """Configuration for normal prior computation.

    Attributes:
        prior_mean: Prior mean.
        prior_std: Prior standard deviation.
        shrinkage_factor: Shrinkage intensity.
    """

    prior_mean: float = 0.0
    prior_std: float = 1.0
    shrinkage_factor: float = 0.3


def compute_normal_prior(
    sample_mean: float,
    sample_std: float,
    sample_size: int,
    config: NormalPriorConfig,
) -> float:
    """Compute posterior mean under Normal-Normal model.

    Args:
        sample_mean: Sample mean.
        sample_std: Sample standard deviation.
        sample_size: Number of observations.
        config: Normal prior configuration.

    Returns:
        Posterior mean estimate.
    """
    if sample_size < 2 or sample_std < 1e-6:
        return config.prior_mean

    prior_precision = 1.0 / (config.prior_std**2 + 1e-6)
    sample_precision = sample_size / (sample_std**2 + 1e-6)

    effective_precision = prior_precision + config.shrinkage_factor * sample_precision
    effective_precision = max(effective_precision, 1e-6)

    posterior_mean = (
        config.prior_mean * prior_precision
        + config.shrinkage_factor * sample_mean * sample_precision
    ) / effective_precision

    return posterior_mean


def adaptive_shrinkage(
    x: pd.DataFrame,
    _y: pd.Series,
    config: BayesianShrinkageConfig | None = None,
) -> pd.DataFrame:
    """Apply adaptive shrinkage based on feature reliability.

    Features with more data are shrunk less than features with less data.

    Args:
        x: Feature DataFrame.
        y: Target series.
        config: Shrinkage configuration.

    Returns:
        DataFrame with adaptively shrunk features.
    """
    if config is None:
        config = BayesianShrinkageConfig()

    result = x.copy()

    for col in x.columns:
        if x[col].dtype in [object, "category"]:
            continue

        valid_count = x[col].notna().sum()

        shrinkage = (
            min(config.shrinkage_factor, 1.0)
            if valid_count < config.sample_size_threshold
            else config.shrinkage_factor * config.sample_size_threshold / valid_count
        )

        shrinkage = min(shrinkage, 1.0)

        result[col] = (1 - shrinkage) * x[col] + shrinkage * config.prior_mean

    return result
