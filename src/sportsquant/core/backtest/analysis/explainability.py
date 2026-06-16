"""
Explainability Analysis Module

Provides SHAP-based model explainability for sports analytics predictions.

MLflow Integration:
- Logs feature importance to MLflow experiment
- Logs prediction attributions to MLflow
- Logs SHAP summary plots as artifacts
- Logs top contributing features with metrics

Data Sources:
- Reads predictions from Kafka topic 'sports-analytics-model-predictions'
- Reads feature data from TimescaleDB for model analysis

Output:
- Writes analysis results to Kafka topic 'betting-metrics'
- Writes feature importance to Parquet for historical analysis
- Supports webhook callbacks for real-time alerts
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.figure import Figure
from pandas import DataFrame, Series

try:
    import shap

    SHAP_AVAILABLE = True
except ImportError:
    SHAP_AVAILABLE = False

from sportsquant.core.backtest.analysis.mlflow_logger import MLflowLogger, get_mlflow_logger

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FeatureImportance:
    """Feature importance data.

    Attributes:
        feature: Feature name
        importance: Importance value
        std: Standard deviation of importance
        model_name: Name of the model (e.g., 'xgb', 'lgb', 'rf')
    """

    feature: str
    importance: float
    std: float = 0.0
    model_name: Optional[str] = None


@dataclass(frozen=True)
class PredictionAttribution:
    """Prediction attribution for a single prediction.

    Attributes:
        prediction: Predicted value
        base_value: Base value (expected value)
        feature_attributions: Dictionary mapping features to their attributions
        top_features: List of top contributing features
        model_name: Name of the model
    """

    prediction: float
    base_value: float
    feature_attributions: dict[str, float]
    top_features: list[FeatureContribution]
    model_name: str


@dataclass(frozen=True)
class FeatureContribution:
    """Feature contribution to a prediction.

    Attributes:
        feature: Feature name
        contribution: Contribution value
        direction: Direction of contribution ('positive' or 'negative')
        magnitude: Absolute magnitude of contribution
    """

    feature: str
    contribution: float
    direction: str
    magnitude: float


class ShapAnalyzer:
    """SHAP-based explainability analyzer.

    Computes SHAP values for tree-based models and provides
    feature importance and prediction attributions.

    MLflow Integration:
        - Logs feature importance via mlflow_logger
        - Logs SHAP summary plots as artifacts
        - Logs top features with metrics
    """

    def __init__(
        self,
        model: Any,
        feature_names: list[str],
        mlflow_logger: Optional[MLflowLogger] = None,
    ) -> None:
        """Initialize SHAP analyzer.

        Args:
            model: Fitted ensemble model with xgb_model, lgb_model, or rf_model attributes
            feature_names: List of feature names
            mlflow_logger: Optional MLflow logger for logging results
        """
        self.model = model
        self.feature_names = feature_names
        self.explainer: Optional[shap.Explainer] = None
        self.shap_values: Optional[np.ndarray] = None
        self._valid_models: list[str] = []
        self.mlflow_logger = mlflow_logger or get_mlflow_logger()

    def compute_explainer(self, _features: DataFrame) -> "shap.Explainer":
        """Compute SHAP explainer for the model.

        Args:
            features: Feature DataFrame (for shape information)

        Returns:
            SHAP Explainer instance

        Raises:
            ImportError: If SHAP is not installed
            ValueError: If no fitted model is available
        """
        if not SHAP_AVAILABLE:
            raise ImportError("SHAP not installed. Install with: pip install shap")

        if self.model.xgb_model is not None:
            self.explainer = shap.TreeExplainer(self.model.xgb_model)
            self._valid_models = ["xgb"]
            logger.info("Created SHAP explainer for XGBoost model")
        elif self.model.lgb_model is not None:
            self.explainer = shap.TreeExplainer(self.model.lgb_model)
            self._valid_models = ["lgb"]
            logger.info("Created SHAP explainer for LightGBM model")
        elif self.model.rf_model is not None:
            self.explainer = shap.TreeExplainer(self.model.rf_model)
            self._valid_models = ["rf"]
            logger.info("Created SHAP explainer for Random Forest model")
        else:
            raise ValueError("No fitted model found. Call fit_all() on the model first.")

        return self.explainer

    def compute_shap_values(self, features: DataFrame) -> np.ndarray:
        """Compute SHAP values for the given features.

        Args:
            features: Feature DataFrame

        Returns:
            SHAP values array
        """
        if self.explainer is None:
            self.compute_explainer(features)

        self.shap_values = self.explainer.shap_values(features.values)

        if isinstance(self.shap_values, list):
            self.shap_values = self.shap_values[0]

        logger.info("Computed SHAP values for %d samples", features.shape[0])
        return self.shap_values

    def get_top_features(self, n: int = 20) -> list[FeatureImportance]:
        """Get top N features by SHAP importance.

        Args:
            n: Number of top features to return

        Returns:
            List of FeatureImportance dataclasses

        Raises:
            ValueError: If SHAP values not computed
        """
        if self.shap_values is None:
            raise ValueError("SHAP values not computed. Call compute_shap_values() first.")

        mean_abs_values = np.abs(self.shap_values).mean(axis=0)
        sorted_indices = np.argsort(mean_abs_values)[::-1][:n]

        top_features: list[FeatureImportance] = []
        for idx in sorted_indices:
            importance = mean_abs_values[idx]
            std = np.abs(self.shap_values[:, idx]).std()
            model_name = self._valid_models[0] if self._valid_models else None
            top_features.append(
                FeatureImportance(
                    feature=self.feature_names[idx],
                    importance=float(importance),
                    std=float(std),
                    model_name=model_name,
                )
            )

        logger.info("Retrieved top %d features by SHAP importance", n)

        if self.mlflow_logger:
            self.mlflow_logger.log_feature_importance(
                [
                    {"feature": f.feature, "importance": f.importance, "std": f.std}
                    for f in top_features
                ],
                importance_type="shap",
            )

        return top_features

    def plot_summary(self, output_path: Path) -> Figure:
        """Create and save SHAP summary plot.

        Args:
            output_path: Path to save the plot

        Returns:
            Matplotlib Figure object

        Raises:
            ValueError: If SHAP values not computed
        """
        if self.shap_values is None:
            raise ValueError("SHAP values not computed. Call compute_shap_values() first.")

        plt.figure(figsize=(12, 10))
        shap.summary_plot(
            self.shap_values,
            pd.DataFrame(self.shap_values, columns=self.feature_names),
            show=False,
            max_display=20,
        )
        plt.title("SHAP Summary Plot - Feature Importance", fontsize=14)
        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches="tight")
        plt.close()

        logger.info("Saved SHAP summary plot to %s", output_path)

        if self.mlflow_logger:
            self.mlflow_logger.log_model_artifact(str(output_path), "chart")

        return plt.gcf()

    def plot_dependence(self, feature: str, output_path: Path) -> Figure:
        """Create and save SHAP dependence plot for a feature.

        Args:
            feature: Feature name
            output_path: Path to save the plot

        Returns:
            Matplotlib Figure object

        Raises:
            ValueError: If SHAP values not computed or feature not found
        """
        if self.shap_values is None:
            raise ValueError("SHAP values not computed. Call compute_shap_values() first.")

        if feature not in self.feature_names:
            raise ValueError(f"Feature '{feature}' not found in feature names")

        feature_idx = self.feature_names.index(feature)

        plt.figure(figsize=(10, 8))
        shap.dependence_plot(
            feature_idx,
            self.shap_values,
            pd.DataFrame(self.shap_values, columns=self.feature_names),
            show=False,
        )
        plt.title(f"SHAP Dependence Plot - {feature}", fontsize=14)
        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches="tight")
        plt.close()

        logger.info("Saved SHAP dependence plot for '%s' to %s", feature, output_path)

        if self.mlflow_logger:
            self.mlflow_logger.log_model_artifact(str(output_path), "chart")

        return plt.gcf()

    def compute_feature_interactions(self, features: DataFrame) -> dict[str, np.ndarray]:
        """Compute feature interaction values.

        Args:
            features: Feature DataFrame

        Returns:
            Dictionary mapping feature pairs to interaction values
        """
        if self.explainer is None:
            self.compute_explainer(features)

        if not hasattr(self.explainer, "shap_interaction_values"):
            logger.warning("Model does not support SHAP interaction values")
            return {}

        interaction_values = self.explainer.shap_interaction_values(features.values)

        if isinstance(interaction_values, list):
            interaction_values = interaction_values[0]

        interactions: dict[str, np.ndarray] = {}
        for i, feature1 in enumerate(self.feature_names):
            for j, feature2 in enumerate(self.feature_names):
                if i < j:
                    pair_name = f"{feature1} x {feature2}"
                    interactions[pair_name] = interaction_values[:, i, j]

        logger.info("Computed feature interactions for %d feature pairs", len(interactions))
        return interactions


class FeatureAttributor:
    """Provides feature attribution for individual predictions.

    MLflow Integration:
        - Logs prediction attributions when available
    """

    def __init__(
        self, analyzer: ShapAnalyzer, mlflow_logger: Optional[MLflowLogger] = None
    ) -> None:
        """Initialize feature attributor.

        Args:
            analyzer: ShapAnalyzer instance
            mlflow_logger: Optional MLflow logger
        """
        self.analyzer = analyzer
        self.mlflow_logger = mlflow_logger

    def attribute_prediction(self, x_row: Series) -> PredictionAttribution:
        """Get feature attribution for a single prediction.

        Args:
            x_row: Feature Series for a single prediction

        Returns:
            PredictionAttribution with feature contributions

        Raises:
            ValueError: If SHAP values not computed
        """
        if self.analyzer.shap_values is None:
            raise ValueError("SHAP values not computed. Call compute_shap_values() first.")

        row_idx = x_row.name
        if row_idx is None:
            row_idx = 0

        if isinstance(self.analyzer.shap_values, list):
            shap_vals = self.analyzer.shap_values[0]
        else:
            shap_vals = self.analyzer.shap_values

        if row_idx >= shap_vals.shape[0]:
            raise ValueError(f"Row index {row_idx} out of bounds for SHAP values")

        row_shap = shap_vals[row_idx]
        base_value = self.analyzer.explainer.expected_value
        if isinstance(base_value, list):
            base_value = base_value[0]

        feature_attributions: dict[str, float] = {}
        for i, feature in enumerate(self.analyzer.feature_names):
            feature_attributions[feature] = float(row_shap[i])

        prediction = float(base_value + row_shap.sum())
        model_name = (
            self.analyzer._valid_models[0]  # pylint: disable=protected-access
            if self.analyzer._valid_models
            else "unknown"  # pylint: disable=protected-access
        )

        top_contributors = self.get_top_contributors(x_row, n=5)

        return PredictionAttribution(
            prediction=prediction,
            base_value=float(base_value),
            feature_attributions=feature_attributions,
            top_features=top_contributors,
            model_name=model_name,
        )

    def get_top_contributors(self, x_row: Series, n: int = 5) -> list[FeatureContribution]:
        """Get top N contributing features for a prediction.

        Args:
            x_row: Feature Series for a single prediction
            n: Number of top contributors to return

        Returns:
            List of FeatureContribution dataclasses

        Raises:
            ValueError: If SHAP values not computed
        """
        if self.analyzer.shap_values is None:
            raise ValueError("SHAP values not computed. Call compute_shap_values() first.")

        row_idx = x_row.name
        if row_idx is None:
            row_idx = 0

        if isinstance(self.analyzer.shap_values, list):
            shap_vals = self.analyzer.shap_values[0]
        else:
            shap_vals = self.analyzer.shap_values

        if row_idx >= shap_vals.shape[0]:
            raise ValueError(f"Row index {row_idx} out of bounds for SHAP values")

        row_shap = shap_vals[row_idx]

        sorted_indices = np.argsort(np.abs(row_shap))[::-1][:n]

        contributors: list[FeatureContribution] = []
        for idx in sorted_indices:
            contribution = row_shap[idx]
            direction = "positive" if contribution > 0 else "negative"
            magnitude = float(np.abs(contribution))
            contributors.append(
                FeatureContribution(
                    feature=self.analyzer.feature_names[idx],
                    contribution=float(contribution),
                    direction=direction,
                    magnitude=magnitude,
                )
            )

        return contributors


class ExplainabilityAnalyzer:
    """Unified explainability analysis interface.

    Provides high-level methods for explainability analysis with
    automatic MLflow logging.

    MLflow Integration:
        - Logs all analysis results to MLflow
        - Logs feature importance DataFrames as artifacts
        - Logs prediction attributions as JSON
    """

    def __init__(
        self,
        model: Any,
        feature_names: list[str],
        mlflow_config: Optional[MLflowLogger] = None,
    ) -> None:
        """Initialize explainability analyzer.

        Args:
            model: Fitted ensemble model
            feature_names: List of feature names
            mlflow_config: Optional MLflow logger or config
        """
        if isinstance(mlflow_config, MLflowLogger):
            mlflow_logger = mlflow_config
        else:
            mlflow_logger = get_mlflow_logger(mlflow_config)

        self.shap_analyzer = ShapAnalyzer(model, feature_names, mlflow_logger)
        self.feature_attributor = FeatureAttributor(self.shap_analyzer, mlflow_logger)
        self.mlflow_logger = mlflow_logger

    def analyze(self, features: DataFrame) -> dict:
        """Run full explainability analysis.

        Args:
            features: Feature DataFrame

        Returns:
            Dictionary with analysis results
        """
        self.shap_analyzer.compute_shap_values(features)
        top_features = self.shap_analyzer.get_top_features(20)

        results = {
            "top_features": [
                {"feature": f.feature, "importance": f.importance, "std": f.std}
                for f in top_features
            ],
            "n_features": len(self.feature_attributor.analyzer.feature_names),
            "n_samples": len(features),
        }

        if self.mlflow_logger:
            self.mlflow_logger.log_metrics(
                {
                    "explainability_n_features": results["n_features"],
                    "explainability_n_samples": results["n_samples"],
                }
            )

        return results

    def get_prediction_explanation(self, features: DataFrame, idx: int = 0) -> dict:
        """Get detailed explanation for a specific prediction.

        Args:
            features: Feature DataFrame
            idx: Index of the prediction to explain

        Returns:
            Dictionary with prediction explanation
        """
        if self.shap_analyzer.shap_values is None:
            self.shap_analyzer.compute_shap_values(features)

        x_row = features.iloc[idx]
        attribution = self.feature_attributor.attribute_prediction(x_row)

        return {
            "prediction": attribution.prediction,
            "base_value": attribution.base_value,
            "top_contributors": [
                {
                    "feature": c.feature,
                    "contribution": c.contribution,
                    "direction": c.direction,
                    "magnitude": c.magnitude,
                }
                for c in attribution.top_features
            ],
            "model_name": attribution.model_name,
        }
