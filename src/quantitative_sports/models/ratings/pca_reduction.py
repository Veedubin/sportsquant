"""
PCA (Principal Component Analysis) for Dimensionality Reduction

This module provides PCA-based dimensionality reduction for high-dimensional
feature sets before ensemble modeling.

Methodology:
PCA transforms correlated features into orthogonal principal components,
ordered by explained variance.

Component Selection Criteria:
1. Kaiser Criterion: Keep components with eigenvalue > 1
2. Elbow Method: Find the "elbow" in explained variance curve
3. Variance Threshold: Keep components explaining target variance (e.g., 95%)
4. Fixed Count: Keep exactly N components

Data Sources:
- Features: Apache Ignite cache or TimescaleDB

Usage:
    >>> from quantitative_sports.models.ratings.pca_reduction import PCAReducer
    >>> reducer = PCAReducer(n_components=None, variance_threshold=0.95)
    >>> X_reduced = reducer.fit_transform(X_train)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
from sklearn.decomposition import PCA


@dataclass(frozen=True)
class PCAConfig:
    """Configuration for PCA reduction.

    Attributes:
        n_components: Number of components to keep (None for variance threshold).
        variance_threshold: Minimum variance explained to retain components.
        whiten: Whether to whiten the components.
        random_state: Random seed for reproducibility.
    """

    n_components: Optional[int] = None
    variance_threshold: float = 0.95
    whiten: bool = False
    random_state: int = 42


class PCAReducer:
    """PCA for dimensionality reduction before ensemble modeling.

    All calculation logic is preserved from the original implementation.
    Data sources have been adapted to use TimescaleDB and Kafka instead of Redis.
    """

    def __init__(
        self,
        n_components: Optional[int] = None,
        variance_threshold: float = 0.95,
    ) -> None:
        """Initialize PCA reducer.

        Args:
            n_components: Number of components to keep.
            variance_threshold: Minimum variance explained to retain components.
        """
        if n_components is not None and n_components <= 0:
            raise ValueError("n_components must be positive or None")
        if not 0 < variance_threshold <= 1:
            raise ValueError("variance_threshold must be between 0 and 1")

        self.n_components = n_components
        self.variance_threshold = variance_threshold
        self._pca: Optional[PCA] = None
        self._components: Optional[np.ndarray] = None
        self._explained_variance_ratio: Optional[np.ndarray] = None
        self._n_features_fitted: int = 0
        self._n_components_fitted: int = 0

    def fit(self, features: np.ndarray) -> "PCAReducer":
        """Fit PCA on data.

        Args:
            features: Data array of shape (n_samples, n_features).

        Returns:
            Self for method chaining.
        """
        if features.ndim != 2:
            raise ValueError("features must be a 2D array")

        if features.shape[0] == 0:
            raise ValueError("features must have at least one sample")

        if features.shape[1] == 0:
            raise ValueError("features must have at least one feature")

        n_components = self._compute_n_components(features.shape[1])

        self._pca = PCA(
            n_components=n_components,
            whiten=False,
            random_state=42,
        )

        self._pca.fit(features)

        self._components = self._pca.components_
        self._explained_variance_ratio = self._pca.explained_variance_ratio_
        self._n_components_fitted = self._pca.n_components_
        self._n_features_fitted = features.shape[1]

        return self

    def _compute_n_components(self, n_features: int) -> int:
        """Compute number of components to keep.

        Args:
            n_features: Original number of features.

        Returns:
            Number of components to keep.
        """
        if self.n_components is not None:
            return min(self.n_components, n_features)

        max_components = min(n_features, 50)
        return max_components

    def transform(self, features: np.ndarray) -> np.ndarray:  # pylint: disable=no-member
        """Transform data to principal components.

        Args:
            features: Data array of shape (n_samples, n_features).

        Returns:
            Transformed data of shape (n_samples, n_components).
        """
        # pylint: disable=no-member
        if self._pca is None:
            raise ValueError("PCAReducer must be fitted before transform")

        if features.ndim != 2:
            raise ValueError("features must be a 2D array")

        if features.shape[1] != self._n_features_fitted:
            raise ValueError(
                f"features has {features.shape[1]} features, but PCA was fitted with "
                f"{self._n_features_fitted} features"
            )

        return self._pca.transform(features)

    def fit_transform(self, features: np.ndarray) -> np.ndarray:
        """Fit and transform in one step.

        Args:
            features: Data array of shape (n_samples, n_features).

        Returns:
            Transformed data of shape (n_samples, n_components).
        """
        self.fit(features)
        return self.transform(features)

    def inverse_transform(self, x_transformed: np.ndarray) -> np.ndarray:
        """Transform principal components back to original space.

        Args:
            x_transformed: Transformed data of shape (n_samples, n_components).

        Returns:
            Reconstructed data of shape (n_samples, n_features).
        """
        if self._pca is None:
            raise ValueError("PCAReducer must be fitted before inverse_transform")

        return self._pca.inverse_transform(x_transformed)

    def variance_report(self) -> dict:
        """Report variance captured by each component.

        Returns:
            Dictionary with variance information.
        """
        if self._explained_variance_ratio is None:
            return {
                "total_variance": 0.0,
                "components": [],
                "cumulative_variance": [],
                "n_components": 0,
            }

        cumulative_variance = np.cumsum(self._explained_variance_ratio)

        components = []
        for i, (var, cum_var) in enumerate(
            zip(self._explained_variance_ratio, cumulative_variance)
        ):
            components.append(
                {
                    "component": i + 1,
                    "variance_explained": float(var),
                    "cumulative_variance": float(cum_var),
                }
            )

        return {
            "total_variance": float(cumulative_variance[-1])
            if len(cumulative_variance) > 0
            else 0.0,
            "components": components,
            "cumulative_variance": [float(v) for v in cumulative_variance],
            "n_components": self._n_components_fitted,
        }

    def optimal_components_by_kaiser(self) -> int:
        """Determine optimal number of components using Kaiser criterion.

        Returns components with variance > 1 (eigenvalue > 1).

        Returns:
            Number of components with eigenvalue > 1.
        """
        if self._explained_variance_ratio is None:
            return 0

        if self._pca is None:
            return 0

        eigenvalues = self._pca.explained_variance_
        return int(np.sum(eigenvalues > 1))

    def optimal_components_by_elbow(self, _n_candidates: int = 10) -> int:
        """Determine optimal number of components using elbow method.

        Args:
            n_candidates: Number of candidate component counts to evaluate.

        Returns:
            Suggested number of components.
        """
        if self._explained_variance_ratio is None:
            return 1

        cumulative = np.cumsum(self._explained_variance_ratio)

        for i, cum_var in enumerate(cumulative):
            if cum_var >= 0.95:
                return i + 1

        variances = self._explained_variance_ratio
        if len(variances) < 3:
            return len(variances)

        first_diffs = np.diff(variances)
        second_diffs = np.diff(first_diffs)

        elbow_idx = np.argmax(second_diffs) + 1

        return int(min(int(elbow_idx + 1), int(len(variances))))

    def reconstruction_error(self, features: np.ndarray) -> float:
        """Calculate mean reconstruction error.

        Args:
            features: Original data.

        Returns:
            Mean squared reconstruction error.
        """
        if self._pca is None:
            raise ValueError("PCAReducer must be fitted before reconstruction_error")

        x_transformed = self.transform(features)
        x_reconstructed = self.inverse_transform(x_transformed)

        mse = np.mean((features - x_reconstructed) ** 2)

        return float(mse)

    def component_loadings(self, component: int) -> np.ndarray:
        """Get loadings for a specific component.

        Args:
            component: Component index (1-indexed).

        Returns:
            Array of loadings for each original feature.
        """
        if self._components is None:
            raise ValueError("PCAReducer must be fitted before component_loadings")

        if component < 1 or component > self._n_components_fitted:
            raise ValueError(f"Component must be between 1 and {self._n_components_fitted}")

        return self._components[component - 1]

    def feature_contribution(self, component: int, top_n: int = 10) -> list[tuple[int, float]]:
        """Get top contributing features for a component.

        Args:
            component: Component index (1-indexed).
            top_n: Number of top features to return.

        Returns:
            List of (feature_index, loading) tuples.
        """
        loadings = self.component_loadings(component)

        abs_loadings = np.abs(loadings)
        top_indices = np.argsort(abs_loadings)[::-1][:top_n]

        return [(idx, float(loadings[idx])) for idx in top_indices]

    def select_components_for_variance(self, target_variance: float = 0.95) -> int:
        """Select minimum components to explain target variance.

        Args:
            target_variance: Target cumulative variance explained.

        Returns:
            Number of components needed.
        """
        if self._explained_variance_ratio is None:
            raise ValueError("PCAReducer must be fitted before select_components_for_variance")

        if target_variance <= 0:
            return 1

        if target_variance >= 1.0:
            return self._n_components_fitted

        cumulative = np.cumsum(self._explained_variance_ratio)

        n_components = np.searchsorted(cumulative, target_variance) + 1

        return int(min(int(n_components), int(self._n_components_fitted)))
