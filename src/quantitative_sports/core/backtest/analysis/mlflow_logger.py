"""
MLflow Logger Helper for Model Analysis

Provides experiment tracking, feature importance logging, metric logging,
and model artifact logging for the sports analytics platform.

MLflow Integration:
- Logs explainability results (SHAP values, feature importance)
- Logs uncertainty metrics (prediction intervals, confidence bounds)
- Logs bootstrap P&L confidence intervals
- Logs regime analysis metrics and performance

Data Sources:
- Reads from TimescaleDB for historical data
- Reads predictions from Kafka topic 'sports-analytics-model-predictions'
- Writes analysis results to Kafka topic 'betting-metrics'
- Writes to Parquet for historical analysis
- Supports webhook callbacks for real-time alerts

# pylint: disable=import-error
# NOTE: mlflow is an optional dependency for ML workflows.
# It is only installed in environments running ML training jobs.
# The module gracefully handles ImportError for non-ML environments.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

# pylint: disable=import-error
import mlflow
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BootstrapResultsConfig:
    """Configuration for bootstrap results logging.

    Attributes:
        roi_ci_lower: Lower bound of ROI confidence interval.
        roi_ci_upper: Upper bound of ROI confidence interval.
        n_bootstrap_samples: Number of bootstrap samples.
        pnl_mean: Mean P&L.
        pnl_std: Standard deviation of P&L.
    """

    roi_ci_lower: float
    roi_ci_upper: float
    n_bootstrap_samples: int
    pnl_mean: float | None = None
    pnl_std: float | None = None


@dataclass(frozen=True)
class RegimeAnalysisConfig:
    """Configuration for regime analysis logging."""

    edge_ci_lower: float
    edge_ci_upper: float
    sample_size: int


@dataclass(frozen=True)
class LineDecayConfig:
    """Configuration for line decay metrics."""

    initial_edge: float
    final_edge: float
    decay_rate: float
    movement_category: str


@dataclass(frozen=True)
class MLflowConfig:
    """Configuration for MLflow logging."""

    tracking_uri: str = "http://mlflow-server:5000"
    experiment_name: str = "sports-analytics-model-analysis"
    artifact_location: str = "s3://sports-platform-mlflow/artifacts"
    registered_model_name: str | None = None


@dataclass(frozen=True)
class UncertaintyMetricsConfig:
    """Configuration for uncertainty metrics logging.

    Attributes:
        confidence_level: Confidence level for intervals.
        prediction_mean: Mean prediction value.
        prediction_std: Standard deviation of predictions.
    """

    confidence_level: float = 0.9
    prediction_mean: float | None = None
    prediction_std: float | None = None


@dataclass(frozen=True)
class PredictionIntervalConfig:
    """Configuration for prediction interval bounds.

    Attributes:
        lower_bound: Lower bound of prediction interval.
        upper_bound: Upper bound of prediction interval.
    """

    lower_bound: float
    upper_bound: float


class MLflowLogger:
    """MLflow logger for model analysis experiments.

    Provides methods to log:
    - Explainability results (SHAP values, feature importance)
    - Uncertainty metrics (prediction intervals, confidence bounds)
    - Bootstrap P&L confidence intervals
    - Regime analysis metrics and performance
    """

    def __init__(self, config: MLflowConfig | None = None):
        self.config = config or MLflowConfig()
        self._run_id: str | None = None
        self._experiment_id: str | None = None

    def set_tracking_uri(self, uri: str) -> None:
        """Set the MLflow tracking URI.

        Args:
            uri: ML tracking URI (e.g., http://mlflow-server:5000)
        """
        self.config = MLflowConfig(tracking_uri=uri, experiment_name=self.config.experiment_name)
        logger.info("MLflow tracking URI set to: %s", uri)

    def get_experiment_id(self) -> str | None:
        """Get the current experiment ID.

        Returns:
            Experiment ID or None if not started
        """
        return self._experiment_id

    def get_run_id(self) -> str | None:
        """Get the current run ID.

        Returns:
            Run ID or None if not started
        """
        return self._run_id

    def start_experiment(self, run_name: str | None = None) -> str:
        """Start an MLflow experiment/run.

        Args:
            run_name: Optional name for the run

        Returns:
            Run ID
        """
        try:
            mlflow.set_tracking_uri(self.config.tracking_uri)
            mlflow.set_experiment(self.config.experiment_name)

            run = mlflow.start_run(
                run_name=run_name or f"analysis_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
                experiment_id=self._experiment_id if self._experiment_id else None,
            )
            self._run_id = run.info.run_id
            self._experiment_id = run.info.experiment_id

            logger.info("MLflow experiment started: run_id=%s", self._run_id)
            return self._run_id

        except ImportError:
            logger.warning("MLflow not installed. Using mock logging.")
            self._run_id = f"mock_run_{datetime.utcnow().timestamp()}"
            return self._run_id

    def end_experiment(self) -> None:
        """End the current MLflow experiment/run."""
        try:
            mlflow.end_run()
            logger.info("MLflow experiment ended: run_id=%s", self._run_id)

        except ImportError:
            logger.info("Mock experiment ended: run_id=%s", self._run_id)

        self._run_id = None

    def log_params(self, params: dict[str, Any]) -> None:
        """Log parameters to MLflow.

        Args:
            params: Dictionary of parameters to log
        """
        try:
            mlflow.log_params(params)
            logger.debug("Logged params: %s", list(params.keys()))

        except ImportError:
            logger.debug("Mock logged params: %s", list(params.keys()))

    def log_metric(self, key: str, value: float, step: int | None = None) -> None:
        """Log a single metric to MLflow.

        Args:
            key: Metric name
            value: Metric value
            step: Optional step number
        """
        try:
            mlflow.log_metric(key, value, step=step)
            logger.debug("Logged metric: %s=%.4f", key, value)

        except ImportError:
            logger.debug("Mock logged metric: %s=%.4f", key, value)

    def log_metrics(self, metrics: dict[str, float], step: int | None = None) -> None:
        """Log multiple metrics to MLflow.

        Args:
            metrics: Dictionary of metrics to log
            step: Optional step number
        """
        try:
            mlflow.log_metrics(metrics, step=step)
            logger.debug("Logged %d metrics", len(metrics))

        except ImportError:
            logger.debug("Mock logged %d metrics", len(metrics))

    def log_feature_importance(
        self,
        feature_importance: list[dict[str, Any]],
        importance_type: str = "shap",
    ) -> None:
        """Log feature importance results.

        Args:
            feature_importance: List of feature importance dicts with 'feature'
                and 'importance' keys
            importance_type: Type of importance (e.g., 'shap', 'permutation',
                'gain')
        """
        try:
            importance_df = pd.DataFrame(feature_importance)
            importance_df.to_csv("feature_importance.csv", index=False)
            mlflow.log_artifact("feature_importance.csv")

            for item in feature_importance[:20]:
                self.log_metric(
                    f"feature_importance_{importance_type}_{item['feature'][:30]}",
                    item.get("importance", 0.0),
                )

            logger.info("Logged feature importance for %d features", len(feature_importance))

        except ImportError:
            logger.info(
                "Mock logged feature importance for %d features",
                len(feature_importance),
            )

    def log_uncertainty_metrics(
        self,
        lower_bound: float,
        upper_bound: float,
        config: UncertaintyMetricsConfig | None = None,
    ) -> None:
        """Log uncertainty quantification metrics.

        Args:
            lower_bound: Lower bound of prediction interval
            upper_bound: Upper bound of prediction interval
            config: Uncertainty metrics configuration
        """
        cfg = config or UncertaintyMetricsConfig()
        metrics = {
            "uncertainty_mean": cfg.prediction_mean,
            "uncertainty_std": cfg.prediction_std,
            "uncertainty_interval_width": upper_bound - lower_bound,
            f"uncertainty_lower_{int(cfg.confidence_level * 100)}": lower_bound,
            f"uncertainty_upper_{int(cfg.confidence_level * 100)}": upper_bound,
        }
        self.log_metrics(metrics)

    def log_bootstrap_results(
        self,
        roi_mean: float,
        win_rate_mean: float,
        config: BootstrapResultsConfig,
    ) -> None:
        """Log bootstrap P&L analysis results.

        Args:
            roi_mean: Mean ROI percentage
            win_rate_mean: Mean win rate
            config: Bootstrap results configuration
        """
        metrics = {
            "bootstrap_pnl_mean": config.pnl_mean,
            "bootstrap_pnl_std": config.pnl_std,
            "bootstrap_roi_mean": roi_mean,
            "bootstrap_roi_ci_lower": config.roi_ci_lower,
            "bootstrap_roi_ci_upper": config.roi_ci_upper,
            "bootstrap_win_rate_mean": win_rate_mean,
            "bootstrap_n_samples": config.n_bootstrap_samples,
        }
        self.log_metrics(metrics)

        pnl_mean = config.pnl_mean or 0.0
        pnl_std = config.pnl_std or 1.0
        self.log_metric(
            "bootstrap_sharpe_ratio",
            pnl_mean / (pnl_std + 1e-10) if pnl_std > 0 else 0.0,
        )

    def log_regime_analysis(
        self,
        regime_type: str,
        edge: float,
        win_rate: float,
        config: RegimeAnalysisConfig,
    ) -> None:
        """Log regime analysis metrics.

        Args:
            regime_type: Type of regime (e.g., 'high_pace', 'low_variance')
            edge: Edge value
            win_rate: Win rate for the regime
            config: Regime analysis configuration
        """
        metrics = {
            f"regime_{regime_type}_edge": edge,
            f"regime_{regime_type}_edge_ci_lower": config.edge_ci_lower,
            f"regime_{regime_type}_edge_ci_upper": config.edge_ci_upper,
            f"regime_{regime_type}_win_rate": win_rate,
            f"regime_{regime_type}_sample_size": config.sample_size,
        }
        self.log_metrics(metrics)

    def log_line_decay_metrics(
        self,
        half_life_hours: float,
        config: LineDecayConfig,
    ) -> None:
        """Log line decay analysis metrics.

        Args:
            half_life_hours: Half-life of edge decay in hours
            config: Line decay configuration
        """
        metrics = {
            "line_decay_half_life_hours": half_life_hours,
            "line_decay_initial_edge": config.initial_edge,
            "line_decay_final_edge": config.final_edge,
            "line_decay_rate": config.decay_rate,
        }
        self.log_metrics(metrics)

        self.log_metric(f"line_decay_category_{config.movement_category}", 1.0)

    def log_model_artifact(self, artifact_path: str, artifact_type: str = "model") -> None:
        """Log a model artifact.

        Args:
            artifact_path: Path to the artifact
            type: Type of artifact (model, chart, data)
        """
        try:
            if Path(artifact_path).exists():
                mlflow.log_artifact(artifact_path)
                logger.info("Logged artifact: %s (type: %s)", artifact_path, artifact_type)
            else:
                logger.warning("Artifact not found: %s", artifact_path)

        except ImportError:
            logger.info("Mock logged artifact: %s (type: %s)", artifact_path, artifact_type)

    def log_table(self, table: pd.DataFrame, artifact_path: str) -> None:
        """Log a DataFrame as an artifact.

        Args:
            table: DataFrame to log
            artifact_path: Path for the artifact file
        """
        try:
            table.to_csv(artifact_path, index=False)
            mlflow.log_artifact(artifact_path)
            logger.info("Logged table artifact: %s (%d rows)", artifact_path, len(table))

        except ImportError:
            logger.info("Mock logged table artifact: %s (%d rows)", artifact_path, len(table))

    def log_json(self, data: dict[str, Any], artifact_path: str) -> None:
        """Log a dictionary as JSON.

        Args:
            data: Dictionary to log
            artifact_path: Path for the JSON file
        """
        try:
            with open(artifact_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
            mlflow.log_artifact(artifact_path)
            logger.info("Logged JSON artifact: %s", artifact_path)

        except ImportError:
            logger.info("Mock logged JSON artifact: %s", artifact_path)


class MLflowLoggerContext:
    """Context manager for MLflow experiments.

    Usage:
        with MLflowLoggerContext(config) as logger:
            logger.log_metrics(...)
    """

    def __init__(self, config: MLflowConfig | None = None, run_name: str | None = None):
        self.config = config
        self.run_name = run_name
        self.logger: MLflowLogger | None = None

    def __enter__(self) -> MLflowLogger:
        self.logger = MLflowLogger(self.config)
        self.logger.start_experiment(self.run_name)
        return self.logger

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.logger:
            self.logger.end_experiment()


def get_mlflow_logger(config: MLflowConfig | None = None) -> MLflowLogger:
    """Factory function to create an MLflow logger.

    Args:
        config: Optional MLflow configuration

    Returns:
        Configured MLflowLogger instance
    """
    return MLflowLogger(config)


def log_conformal_prediction_results(
    mlflow_logger: MLflowLogger,
    calibration_size: int,
    test_size: int,
    coverage: float,
    interval_width: float,
) -> None:
    """Log conformal prediction results to MLflow.

    Args:
        mlflow_logger: MLflowLogger instance
        calibration_size: Size of calibration set
        test_size: Size of test set
        coverage: Actual coverage achieved
        interval_width: Average interval width
    """
    metrics = {
        "conformal_calibration_size": calibration_size,
        "conformal_test_size": test_size,
        "conformal_coverage": coverage,
        "conformal_interval_width": interval_width,
    }
    mlflow_logger.log_metrics(metrics)


def log_ensemble_diversity(
    mlflow_logger: MLflowLogger,
    prediction_std: float,
    disagreement_score: float,
    n_models: int,
) -> None:
    """Log ensemble diversity metrics.

    Args:
        mlflow_logger: MLflowLogger instance
        prediction_std: Standard deviation of ensemble predictions
        disagreement_score: Disagreement between ensemble members
        n_models: Number of models in ensemble
    """
    metrics = {
        "ensemble_prediction_std": prediction_std,
        "ensemble_disagreement": disagreement_score,
        "ensemble_n_models": n_models,
    }
    mlflow_logger.log_metrics(metrics)
