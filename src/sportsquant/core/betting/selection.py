"""
Model Selection and Complexity Analysis

Adapted from sports_analytics.model.selection
Changes: Replaced sports_analytics.util.logging with standard logging

This module provides model selection and complexity analysis capabilities
for betting model optimization.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.figure import Figure
from sklearn.base import RegressorMixin
from sklearn.model_selection import cross_val_score

matplotlib.use("Agg")

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ComparisonResult:  # pylint: disable=R0902
    """Result of comparing multiple models.

    Contains all metrics computed during model comparison including
    cross-validation scores, information criteria, and complexity.

    Attributes:
        model_names: Names of the compared models.
        cv_scores_mean: Mean cross-validation scores.
        cv_scores_std: Std dev of CV scores.
        r2_scores: R² scores for each model.
        adjusted_r2_scores: Adjusted R² scores.
        aic_scores: AIC scores (lower is better).
        bic_scores: BIC scores (lower is better).
        complexity_scores: Number of parameters for each model.
        metadata: Additional information about the comparison.
    """

    model_names: list[str]
    cv_scores_mean: list[float]
    cv_scores_std: list[float]
    r2_scores: list[float]
    adjusted_r2_scores: list[float]
    aic_scores: list[float]
    bic_scores: list[float]
    complexity_scores: list[int]
    metadata: dict[str, Any]


@dataclass(frozen=True)
class ModelRecommendation:
    """Recommendation result from model selection.

    Attributes:
        best_model_name: Name of the recommended model.
        best_model: The recommended model instance.
        criterion: Criterion used for selection.
        criterion_value: Value of the criterion for the best model.
        alternative_models: List of alternative model names.
        reasoning: Explanation for the recommendation.
    """

    best_model_name: str
    criterion: str
    criterion_value: float
    alternative_models: list[str]
    reasoning: str
    best_model: RegressorMixin | None = None


@dataclass(frozen=True)
class ModelSelectorConfig:
    """Configuration for model selection."""

    cv_folds: int = 5


@dataclass(frozen=True)
class ReasoningParams:
    """Parameters for building reasoning."""

    best_model_name: str
    best_value: float
    criterion: str
    scores: list[float]
    sorted_indices: np.ndarray
    comparison: ComparisonResult
    best_idx: int


class ModelSelector:
    """Model selection using cross-validation and information criteria.

    Provides methods to compare multiple models and select the best
    based on various criteria such as adjusted R², AIC, BIC, or
    cross-validation scores.
    """

    def __init__(self, features: Any, y: Any, config: ModelSelectorConfig | None = None) -> None:
        self.features = features
        self.y = y
        self.config = config or ModelSelectorConfig()
        self.n_samples = len(y)
        self.n_features = features.shape[1] if hasattr(features, "shape") else len(features.columns)

    def _compute_cv_scores(self, model: RegressorMixin, name: str) -> tuple[float, float]:
        """Compute cross-validation scores for a model.

        Args:
            model: Model to evaluate.
            name: Model name for logging.

        Returns:
            Tuple of (cv_mean, cv_std).
        """
        try:
            cv_scores = cross_val_score(
                model,
                self.features,
                self.y,
                cv=self.config.cv_folds,
                scoring="neg_mean_squared_error",
            )
            return float(-cv_scores.mean()), float(cv_scores.std())
        except (ValueError, TypeError) as e:
            logger.warning("CV scoring failed for %s: %s", name, e)
            return np.inf, np.inf

    def _compute_fit_metrics(
        self, model: RegressorMixin, name: str
    ) -> tuple[float, float, float, float, int]:
        """Compute in-sample fit metrics for a model.

        Args:
            model: Fitted model.
            name: Model name for logging.

        Returns:
            Tuple of (r2, adjusted_r2, aic, bic, n_params).
        """
        try:
            model.fit(self.features, self.y)  # type: ignore[attr-defined]
            y_pred = model.predict(self.features)  # type: ignore[attr-defined]
            ss_res = np.sum((self.y - y_pred) ** 2)
            ss_tot = np.sum((self.y - np.mean(self.y)) ** 2)
            r2 = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0.0

            n = self.n_samples
            p = self.n_features
            adj_r2 = 1 - (1 - r2) * (n - 1) / (n - p - 1) if n > p + 1 else 0.0

            mse = ss_res / n
            aic = n * np.log(mse) + 2 * p
            bic = n * np.log(mse) + p * np.log(n)

            n_params = self._count_model_params(model)

            return float(r2), float(adj_r2), float(aic), float(bic), n_params
        except (ValueError, TypeError) as e:
            logger.warning("Model fitting failed for %s: %s", name, e)
            return 0.0, 0.0, np.inf, np.inf, 0

    def _collect_model_metrics(self, model: RegressorMixin, name: str) -> dict[str, Any]:
        """Collect all metrics for a single model.

        Args:
            model: The model to evaluate.
            name: Name of the model.

        Returns:
            Dictionary with all computed metrics.
        """
        cv_mean, cv_std = self._compute_cv_scores(model, name)
        r2, adj_r2, aic, bic, n_params = self._compute_fit_metrics(model, name)
        return {
            "cv_mean": cv_mean,
            "cv_std": cv_std,
            "r2": r2,
            "adj_r2": adj_r2,
            "aic": aic,
            "bic": bic,
            "n_params": n_params,
        }

    def compare_models(self, models: dict[str, RegressorMixin]) -> ComparisonResult:
        """Compare multiple models and compute selection metrics.

        Args:
            models: Dictionary mapping model names to fitted model instances.

        Returns:
            ComparisonResult containing all computed metrics.
        """
        model_names: list[str] = []
        cv_scores_mean: list[float] = []
        cv_scores_std: list[float] = []
        r2_scores: list[float] = []
        adjusted_r2_scores: list[float] = []
        aic_scores: list[float] = []
        bic_scores: list[float] = []
        complexity_scores: list[int] = []

        for name, model in models.items():
            model_names.append(name)

            metrics = self._collect_model_metrics(model, name)
            cv_scores_mean.append(metrics["cv_mean"])
            cv_scores_std.append(metrics["cv_std"])
            r2_scores.append(metrics["r2"])
            adjusted_r2_scores.append(metrics["adj_r2"])
            aic_scores.append(metrics["aic"])
            bic_scores.append(metrics["bic"])
            complexity_scores.append(metrics["n_params"])

        metadata = {"n_samples": self.n_samples, "n_features": self.n_features}

        return ComparisonResult(
            model_names=model_names,
            cv_scores_mean=cv_scores_mean,
            cv_scores_std=cv_scores_std,
            r2_scores=r2_scores,
            adjusted_r2_scores=adjusted_r2_scores,
            aic_scores=aic_scores,
            bic_scores=bic_scores,
            complexity_scores=complexity_scores,
            metadata=metadata,
        )

    def compute_ic_penalty(self, model: RegressorMixin, n_features: int) -> float:
        """Compute information criterion penalty for a model.

        Args:
            model: Fitted model to evaluate.
            n_features: Number of features in the model.

        Returns:
            AIC penalty value (lower is better).
        """
        try:
            model.fit(self.features, self.y)  # type: ignore[attr-defined]
            y_pred = model.predict(self.features)  # type: ignore[attr-defined]
            ss_res = np.sum((self.y - y_pred) ** 2)
            n = self.n_samples
            mse = ss_res / n
            aic = n * np.log(mse) + 2 * n_features
            return float(aic)
        except (ValueError, TypeError) as e:
            logger.warning("IC penalty calculation failed: %s", e)
            return np.inf

    def _get_criterion_info(
        self, comparison: ComparisonResult, criterion: str
    ) -> tuple[list[float], bool, int]:
        """Get scores and metadata for the specified criterion.

        Args:
            comparison: ComparisonResult with all model scores.
            criterion: Selection criterion name.

        Returns:
            Tuple of (scores, higher_better, best_index).
        """
        if criterion == "adjusted_r2":
            return (
                comparison.adjusted_r2_scores,
                True,
                int(np.argmax(comparison.adjusted_r2_scores)),
            )
        if criterion == "aic":
            return comparison.aic_scores, False, int(np.argmin(comparison.aic_scores))
        if criterion == "bic":
            return comparison.bic_scores, False, int(np.argmin(comparison.bic_scores))
        if criterion == "cv":
            return (
                comparison.cv_scores_mean,
                False,
                int(np.argmin(comparison.cv_scores_mean)),
            )

        raise ValueError(f"Unknown criterion: {criterion}")

    def _build_reasoning(
        self,
        params: ReasoningParams,
    ) -> str:
        """Build reasoning string for model selection.

        Args:
            params: Parameters for reasoning.

        Returns:
            Formatted reasoning string.
        """
        reasoning_parts = []
        reasoning_parts.append(
            f"Selected '{params.best_model_name}' based on "
            f"{params.criterion} = {params.best_value:.4f}"
        )

        if len(params.comparison.model_names) > 1:
            runner_up_idx = params.sorted_indices[1]
            runner_up_name = params.comparison.model_names[runner_up_idx]
            runner_up_value = params.scores[runner_up_idx]
            reasoning_parts.append(
                f"Runner-up: '{runner_up_name}' with {params.criterion} = {runner_up_value:.4f}"
            )

        if params.criterion == "adjusted_r2":
            complexity = params.comparison.complexity_scores[params.best_idx]
            reasoning_parts.append(
                f"Model uses {complexity} parameters and balances fit vs complexity"
            )
        elif params.criterion in ("aic", "bic"):
            reasoning_parts.append(
                f"Lower {params.criterion.upper()} indicates better model with "
                f"penalty for complexity"
            )

        return ". ".join(reasoning_parts)

    def select_best_model(
        self, comparison: ComparisonResult, criterion: str = "adjusted_r2"
    ) -> ModelRecommendation:
        """Select the best model based on the specified criterion.

        Args:
            comparison: ComparisonResult from compare_models.
            criterion: Selection criterion ('adjusted_r2', 'aic', 'bic', 'cv').

        Returns:
            ModelRecommendation with the best model and reasoning.
        """
        scores, higher_better, best_idx = self._get_criterion_info(comparison, criterion)

        best_model_name = comparison.model_names[best_idx]
        best_value = scores[best_idx]

        alternative_models = [
            name for i, name in enumerate(comparison.model_names) if i != best_idx
        ]

        if higher_better:
            sorted_indices = np.argsort(scores)[::-1]
        else:
            sorted_indices = np.argsort(scores)

        reasoning = self._build_reasoning(
            ReasoningParams(
                best_model_name=best_model_name,
                best_value=best_value,
                criterion=criterion,
                scores=scores,
                sorted_indices=sorted_indices,
                comparison=comparison,
                best_idx=best_idx,
            )
        )

        return ModelRecommendation(
            best_model_name=best_model_name,
            best_model=None,
            criterion=criterion,
            criterion_value=best_value,
            alternative_models=alternative_models,
            reasoning=reasoning,
        )

    def _count_model_params(self, model: RegressorMixin) -> int:
        try:
            if hasattr(model, "coef_"):
                return len(model.coef_)  # type: ignore[attr-defined]
            if hasattr(model, "n_estimators"):
                return model.n_estimators  # type: ignore[attr-defined]
            if hasattr(model, "n_features_in_"):
                return model.n_features_in_  # type: ignore[attr-defined]
            return self.n_features
        except (TypeError, AttributeError):
            return self.n_features


@dataclass(frozen=True)
class ComplexityAnalyzerConfig:
    """Configuration for complexity analysis."""

    cv_splits: int = 5


class ComplexityAnalyzer:
    """Analyze model complexity vs performance trade-offs.

    Provides methods to sweep complexity parameters and find
    the optimal complexity using elbow detection.
    """

    def __init__(
        self, features: Any, y: Any, config: ComplexityAnalyzerConfig | None = None
    ) -> None:
        self.features = features
        self.y = y
        self.config = config or ComplexityAnalyzerConfig()

    def _create_model_instance(self, model_class: type, param_value: int | float) -> RegressorMixin:
        """Create a model instance with the appropriate parameter."""
        if hasattr(model_class, "__init__"):
            init_params = model_class.__init__.__code__.co_varnames
            if "n_estimators" in init_params:
                return model_class(n_estimators=int(param_value))
            if "max_depth" in init_params:
                return model_class(max_depth=int(param_value))
            if "n_neighbors" in init_params:
                return model_class(n_neighbors=int(param_value))
        return model_class()

    def _compute_scores_for_param(
        self, model_class: type, param_value: int | float
    ) -> tuple[float, float]:
        """Compute train and validation scores for a parameter value."""
        try:
            model = self._create_model_instance(model_class, param_value)

            train_score = float(
                model.fit(self.features, self.y).score(self.features, self.y)  # type: ignore[attr-defined]
            )

            val_cv = cross_val_score(model, self.features, self.y, cv=self.config.cv_splits)
            val_score = float(val_cv.mean())

            return train_score, val_score
        except (ValueError, TypeError) as e:
            logger.warning("Complexity sweep failed for %s: %s", param_value, e)
            return np.nan, np.nan

    def plot_complexity_curve(
        self, model_class: type, param_range: list, output_path: Path
    ) -> Figure:
        """Plot complexity vs performance curve.

        Args:
            model_class: Model class to evaluate.
            param_range: Range of complexity parameter values to test.
            output_path: Path to save the plot.

        Returns:
            Matplotlib Figure object.
        """
        train_scores: list[float] = []
        val_scores: list[float] = []

        for param_value in param_range:
            train_score, val_score = self._compute_scores_for_param(model_class, param_value)
            train_scores.append(train_score)
            val_scores.append(val_score)

        fig, ax = plt.subplots(figsize=(10, 6))
        ax.plot(param_range, train_scores, "b-o", label="Train Score", linewidth=2)
        ax.plot(param_range, val_scores, "r-s", label="Validation Score", linewidth=2)
        ax.set_xlabel("Complexity Parameter")
        ax.set_ylabel("Score (R²)")
        ax.set_title("Model Complexity vs Performance")
        ax.legend()
        ax.grid(True, alpha=0.3)

        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            fig.savefig(output_path, dpi=150, bbox_inches="tight")

        return fig

    def _compute_point_distances(self, x_norm: np.ndarray, y_norm: np.ndarray) -> list[float]:
        """Compute distances for elbow detection.

        Args:
            x_norm: Normalized complexity values.
            y_norm: Normalized performance scores.

        Returns:
            List of distance values for each point.
        """
        distances: list[float] = []
        n = len(x_norm)

        for i in range(n):
            if i in (0, n - 1):
                distances.append(0.0)
                continue

            p1 = np.array([x_norm[i - 1], y_norm[i - 1]])
            p2 = np.array([x_norm[i + 1], y_norm[i + 1]])
            p = np.array([x_norm[i], y_norm[i]])

            line_vec = p2 - p1
            point_vec = p - p1
            line_len = np.linalg.norm(line_vec)
            if line_len < 1e-10:
                distances.append(0.0)
                continue
            t = np.dot(point_vec, line_vec) / (line_len**2)
            t = np.clip(t, 0, 1)
            nearest = p1 + t * line_vec
            dist = np.linalg.norm(p - nearest)
            distances.append(float(dist))

        return distances

    def find_elbow(self, complexity_scores: list[float], performance_scores: list[float]) -> int:
        """Find optimal complexity using elbow method.

        Args:
            complexity_scores: List of complexity parameter values.
            performance_scores: List of corresponding performance scores.

        Returns:
            Index of the elbow point in the scores lists.
        """
        if len(complexity_scores) < 3 or len(performance_scores) < 3:
            return 0

        x = np.array(complexity_scores)
        y = np.array(performance_scores)

        x_min, x_max = x.min(), x.max()
        y_min, y_max = y.min(), y.max()

        x_norm = (x - x_min) / (x_max - x_min + 1e-10)
        y_norm = (y - y_min) / (y_max - y_min + 1e-10)

        distances = self._compute_point_distances(x_norm, y_norm)

        elbow_idx = int(np.argmax(distances))
        return elbow_idx


__all__ = [
    "ModelSelectorConfig",
    "ModelSelector",
    "ComplexityAnalyzerConfig",
    "ComplexityAnalyzer",
    "ComparisonResult",
    "ModelRecommendation",
]
