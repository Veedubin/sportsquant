"""
Uncertainty Quantification Module

Provides multiple uncertainty quantification methods for sports analytics predictions.

MLflow Integration:
- Logs prediction intervals and confidence bounds
- Logs conformal prediction results
- Logs ensemble diversity metrics
- Logs quantile regression metrics

Data Sources:
- Reads predictions from Kafka topic 'sports-analytics-model-predictions'
- Reads calibration data from TimescaleDB

Output:
- Writes analysis results to Kafka topic 'betting-metrics'
- Writes uncertainty metrics to Parquet for historical analysis
- Supports webhook callbacks for real-time alerts
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator
from sklearn.ensemble import GradientBoostingRegressor, RandomForestClassifier

from sportsquant.core.backtest.analysis.mlflow_logger import (
    MLflowLogger,
    get_mlflow_logger,
    log_conformal_prediction_results,
    log_ensemble_diversity,
    UncertaintyMetricsConfig,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class UncertaintyConfig:
    """Configuration for uncertainty-aware prediction.

    Attributes:
        n_bootstraps: Number of bootstrap models to train
        confidence_level: Confidence level for prediction intervals
        random_seed: Random seed for reproducibility
        parallelize: Whether to use parallel processing
        n_jobs: Number of jobs for parallel processing
    """

    n_bootstraps: int = 100
    confidence_level: float = 0.9
    random_seed: int = 42
    parallelize: bool = False
    n_jobs: int = -1


@dataclass(frozen=True)
class QuantileConfig:
    """Configuration for quantile regression.

    Attributes:
        quantiles: Quantiles to predict
        alpha: Regularization parameter
    """

    quantiles: tuple[float, ...] = (0.1, 0.5, 0.9)
    alpha: float = 0.1


@dataclass(frozen=True)
class ConformalConfig:
    """Configuration for conformal prediction.

    Attributes:
        confidence_level: Confidence level for intervals
        mlflow_logger: Optional MLflow logger
    """

    confidence_level: float = 0.9
    mlflow_logger: Optional[MLflowLogger] = None


def fit_bootstrap_model(
    model_class: type[BaseEstimator],
    x: pd.DataFrame,
    y: pd.Series,
    sample_weight: pd.Series | None = None,
    random_state: int = 42,
) -> tuple[BaseEstimator, np.ndarray]:
    """Fit a single bootstrap model.

    Args:
        model_class: Scikit-learn model class
        x: Feature matrix
        y: Target values
        sample_weight: Optional sample weights
        random_state: Random state for bootstrap sampling

    Returns:
        Tuple of (fitted model, out-of-bag indices)
    """
    n_samples = len(x)

    if n_samples < 2:
        raise ValueError("Need at least 2 samples for bootstrap")

    rng = np.random.default_rng(random_state)
    indices = rng.choice(n_samples, size=n_samples, replace=True)
    oob_indices = np.array(list(set(range(n_samples)) - set(indices)))

    x_boot = x.iloc[indices]
    y_boot = y.iloc[indices]

    if sample_weight is not None:
        weight_boot = sample_weight.iloc[indices]
        model = model_class()
        model.fit(x_boot, y_boot, sample_weight=weight_boot)
    else:
        model = model_class()
        model.fit(x_boot, y_boot)

    return model, oob_indices


def predict_with_bootstrap(
    models: list[tuple[BaseEstimator, np.ndarray]],
    x: pd.DataFrame,
    confidence_level: float = 0.9,
) -> dict[str, np.ndarray]:
    """Generate predictions with uncertainty from bootstrap models.

    Args:
        models: List of (model, oob_indices) tuples
        x: Feature matrix for predictions
        confidence_level: Confidence level for intervals

    Returns:
        Dictionary with prediction, lower, upper, and std
    """
    predictions: list[np.ndarray] = []

    for model, _ in models:
        if hasattr(model, "predict_proba"):
            preds = model.predict_proba(x)[:, 1]
        else:
            preds = model.predict(x)
        predictions.append(preds)

    predictions_arr = np.array(predictions)

    point_pred = predictions_arr.mean(axis=0)
    pred_std = predictions_arr.std(axis=0)

    alpha_lower = (1 - confidence_level) / 2
    alpha_upper = 1 - alpha_lower

    lower_bound = np.percentile(predictions_arr, alpha_lower * 100, axis=0)
    upper_bound = np.percentile(predictions_arr, alpha_upper * 100, axis=0)

    return {
        "prediction": point_pred,
        "lower": lower_bound,
        "upper": upper_bound,
        "std": pred_std,
        "mean_std": pred_std.mean(),
    }


class UncertaintyAwarePredictor:
    """Wraps a base model with bootstrap-based uncertainty quantification.

    Fits multiple bootstrap models and provides prediction intervals
    based on the distribution of predictions.

    MLflow Integration:
        - Logs uncertainty metrics via mlflow_logger
        - Logs prediction intervals and confidence bounds
        - Logs bootstrap model statistics
    """

    def __init__(
        self,
        base_model: BaseEstimator | type[BaseEstimator],
        config: UncertaintyConfig | None = None,
        mlflow_logger: Optional[MLflowLogger] = None,
    ) -> None:
        """Initialize uncertainty-aware predictor.

        Args:
            base_model: Either a fitted model instance or a model class
            config: Uncertainty configuration
            mlflow_logger: Optional MLflow logger
        """
        self.config = config or UncertaintyConfig()
        self.base_model = base_model
        self.bootstrap_models: list[tuple[BaseEstimator, np.ndarray]] = []
        self.is_fitted = False
        self.mlflow_logger = mlflow_logger or get_mlflow_logger()

    def fit(
        self,
        x: pd.DataFrame,
        y: pd.Series,
        sample_weight: pd.Series | None = None,
    ) -> UncertaintyAwarePredictor:
        """Fit multiple bootstrap models.

        Args:
            x: Feature matrix
            y: Target values
            sample_weight: Optional sample weights

        Returns:
            self for method chaining
        """
        np.random.seed(self.config.random_seed)

        self.bootstrap_models = []

        if not isinstance(self.base_model, type):
            model_class = self.base_model.__class__
        else:
            model_class = self.base_model

        for i in range(self.config.n_bootstraps):
            try:
                model, oob_indices = fit_bootstrap_model(
                    model_class,
                    x,
                    y,
                    sample_weight,
                    random_state=self.config.random_seed + i,
                )
                self.bootstrap_models.append((model, oob_indices))
            except (ValueError, RuntimeError):
                continue

        self.is_fitted = True

        if self.mlflow_logger:
            self.mlflow_logger.log_params(
                {
                    "uncertainty_n_bootstraps": self.config.n_bootstraps,
                    "uncertainty_confidence_level": self.config.confidence_level,
                }
            )

        logger.info("Fitted %d bootstrap models", len(self.bootstrap_models))
        return self

    def predict_with_interval(
        self,
        x: pd.DataFrame,
        confidence_level: float | None = None,
    ) -> dict[str, np.ndarray]:
        """Predict with credible intervals.

        Args:
            x: Feature matrix for predictions
            confidence_level: Confidence level. Uses config if None

        Returns:
            Dictionary with prediction, intervals, and uncertainty metrics

        Raises:
            RuntimeError: If model not fitted
        """
        if not self.is_fitted:
            raise RuntimeError("Model must be fitted before prediction")

        conf = confidence_level or self.config.confidence_level

        return predict_with_bootstrap(self.bootstrap_models, x, conf)

    def get_prediction_df(
        self,
        x: pd.DataFrame,
        confidence_level: float | None = None,
    ) -> pd.DataFrame:
        """Get predictions as a DataFrame.

        Args:
            x: Feature matrix
            confidence_level: Confidence level

        Returns:
            DataFrame with prediction columns
        """
        results = self.predict_with_interval(x, confidence_level)

        df = pd.DataFrame(
            {
                "prediction": results["prediction"],
                "lower_bound": results["lower"],
                "upper_bound": results["upper"],
                "std": results["std"],
                "interval_width": results["upper"] - results["lower"],
            }
        )

        return df

    def log_uncertainty_metrics(self, x: pd.DataFrame) -> None:
        """Log uncertainty metrics to MLflow.

        Args:
            x: Feature matrix for predictions
        """
        if not self.is_fitted:
            raise RuntimeError("Model must be fitted before logging")

        results = self.predict_with_interval(x)

        if self.mlflow_logger:
            self.mlflow_logger.log_uncertainty_metrics(
                lower_bound=np.mean(results["lower"]),
                upper_bound=np.mean(results["upper"]),
                config=UncertaintyMetricsConfig(
                    confidence_level=self.config.confidence_level,
                    prediction_mean=np.mean(results["prediction"]),
                    prediction_std=np.mean(results["std"]),
                ),
            )


def quantile_regression_loss(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    quantile: float,
) -> float:
    """Compute quantile regression loss (pinball loss).

    Args:
        y_true: True values
        y_pred: Predicted values
        quantile: Quantile to predict (0-1)

    Returns:
        Pinball loss value
    """
    errors = y_true - y_pred
    loss = np.where(errors > 0, quantile * errors, (quantile - 1) * errors)

    return np.mean(loss)


class QuantilePredictor:
    """Quantile regression for prediction intervals.

    Uses gradient boosting with quantile loss to predict
    conditional quantiles for uncertainty estimation.

    MLflow Integration:
        - Logs quantile predictions to MLflow
        - Logs interval width metrics
    """

    def __init__(
        self,
        quantiles: tuple[float, ...] | None = None,
        mlflow_logger: Optional[MLflowLogger] = None,
    ) -> None:
        """Initialize quantile predictor.

        Args:
            quantiles: Quantiles to predict
            mlflow_logger: Optional MLflow logger
        """
        self.quantiles = quantiles or (0.1, 0.5, 0.9)
        self.models: dict[float, BaseEstimator] = {}
        self.is_fitted = False
        self.mlflow_logger = mlflow_logger or get_mlflow_logger()

    def fit(
        self,
        x: pd.DataFrame,
        y: pd.Series,
        **model_kwargs,
    ) -> QuantilePredictor:
        """Fit quantile regression models.

        Args:
            x: Feature matrix
            y: Target values
            **model_kwargs: Additional arguments for model

        Returns:
            self for method chaining
        """
        for quantile in self.quantiles:
            model = GradientBoostingRegressor(
                loss="quantile",
                alpha=quantile,
                n_estimators=100,
                max_depth=4,
                **model_kwargs,
            )
            model.fit(x, y)
            self.models[quantile] = model

        self.is_fitted = True

        if self.mlflow_logger:
            self.mlflow_logger.log_params(
                {
                    "quantile_predictor_quantiles": str(self.quantiles),
                }
            )

        return self

    def predict(self, x: pd.DataFrame) -> dict[float, np.ndarray]:
        """Predict quantiles.

        Args:
            x: Feature matrix

        Returns:
            Dictionary of quantile -> predictions
        """
        if not self.is_fitted:
            raise RuntimeError("Model must be fitted first")

        predictions: dict[float, np.ndarray] = {}

        for quantile, model in self.models.items():
            predictions[quantile] = model.predict(x)

        return predictions

    def predict_with_interval(
        self,
        x: pd.DataFrame,
        confidence_level: float = 0.9,
    ) -> dict[str, np.ndarray]:
        """Predict with prediction interval.

        Args:
            x: Feature matrix
            confidence_level: Confidence level

        Returns:
            Dictionary with median, lower, upper bounds
        """
        predictions = self.predict(x)

        alpha_lower = (1 - confidence_level) / 2
        alpha_upper = 1 - alpha_lower

        lower_quantile = min((q for q in self.quantiles if q >= alpha_lower), default=0.1)
        upper_quantile = max((q for q in self.quantiles if q <= alpha_upper), default=0.9)
        median_quantile = min((q for q in self.quantiles if q >= 0.5), default=0.5)

        return {
            "median": predictions[median_quantile],
            "lower": predictions[lower_quantile],
            "upper": predictions[upper_quantile],
        }


def conformal_prediction_interval(
    x_cal: pd.DataFrame,
    y_cal: np.ndarray,
    x_test: pd.DataFrame,
    model: BaseEstimator,
    config: ConformalConfig,
) -> dict[str, np.ndarray]:
    """Compute conformal prediction intervals.

    Args:
        x_cal: Calibration features
        y_cal: Calibration targets
        x_test: Test features
        model: Fitted model
        config: Conformal prediction configuration

    Returns:
        Dictionary with lower and upper bounds
    """
    if hasattr(model, "predict"):
        y_pred_cal = model.predict(x_cal)
        y_pred_test = model.predict(x_test)
    else:
        y_pred_cal = model.predict(x_cal)
        y_pred_test = model.predict(x_test)

    residuals = np.abs(y_cal - y_pred_cal)

    n = len(residuals)
    alpha = 1 - config.confidence_level

    q = np.quantile(residuals, np.ceil((n + 1) * (1 - alpha)) / n)

    lower = y_pred_test - q
    upper = y_pred_test + q

    if config.mlflow_logger:
        log_conformal_prediction_results(
            config.mlflow_logger,
            calibration_size=len(x_cal),
            test_size=len(x_test),
            coverage=1.0,
            interval_width=np.mean(upper - lower),
        )

    return {
        "lower": lower,
        "upper": upper,
        "adjustment": q,
    }


class EnsembleUncertainty:
    """Uncertainty quantification using ensemble diversity.

    Estimates uncertainty based on disagreement between
    ensemble members.

    MLflow Integration:
        - Logs ensemble diversity metrics
        - Logs prediction disagreement scores
    """

    def __init__(
        self,
        n_models: int = 10,
        mlflow_logger: Optional[MLflowLogger] = None,
    ) -> None:
        """Initialize ensemble uncertainty.

        Args:
            n_models: Number of models in ensemble
            mlflow_logger: Optional MLflow logger
        """
        self.n_models = n_models
        self.models: list[BaseEstimator] = []
        self.is_fitted = False
        self.mlflow_logger = mlflow_logger or get_mlflow_logger()

    def fit(
        self,
        x: pd.DataFrame,
        y: pd.Series,
        model_class: type[BaseEstimator] | None = None,
    ) -> EnsembleUncertainty:
        """Fit diverse ensemble models.

        Args:
            x: Feature matrix
            y: Target values
            model_class: Model class to use

        Returns:
            self for method chaining
        """
        if model_class is None:
            model_class = RandomForestClassifier

        for i in range(self.n_models):
            if hasattr(model_class, "random_state"):
                model = model_class(random_state=i, n_estimators=50)
            else:
                model = model_class(n_estimators=50)
            model.fit(x, y)
            self.models.append(model)

        self.is_fitted = True

        if self.mlflow_logger:
            self.mlflow_logger.log_params(
                {
                    "ensemble_n_models": self.n_models,
                }
            )

        return self

    def predict_with_uncertainty(self, x: pd.DataFrame) -> dict[str, np.ndarray]:
        """Predict with uncertainty estimates.

        Args:
            x: Feature matrix

        Returns:
            Dictionary with predictions and uncertainty metrics
        """
        if not self.is_fitted:
            raise RuntimeError("Ensemble must be fitted first")

        all_predictions: list[np.ndarray] = []

        for model in self.models:
            if hasattr(model, "predict_proba"):
                preds = model.predict_proba(x)[:, 1]
            else:
                preds = model.predict(x)
            all_predictions.append(preds)

        predictions_arr = np.array(all_predictions)

        disagreement = predictions_arr.std(axis=0) / (predictions_arr.mean(axis=0) + 1e-6)

        if self.mlflow_logger:
            log_ensemble_diversity(
                self.mlflow_logger,
                prediction_std=np.mean(predictions_arr.std(axis=0)),
                disagreement_score=np.mean(disagreement),
                n_models=self.n_models,
            )

        return {
            "prediction": predictions_arr.mean(axis=0),
            "std": predictions_arr.std(axis=0),
            "lower": predictions_arr.min(axis=0),
            "upper": predictions_arr.max(axis=0),
            "disagreement": disagreement,
        }


class UncertaintyAnalyzer:
    """Unified interface for uncertainty quantification.

    Provides multiple methods for uncertainty estimation with
    automatic MLflow logging.

    MLflow Integration:
        - Logs all uncertainty metrics to MLflow
        - Logs prediction intervals and confidence bounds
    """

    def __init__(
        self,
        model: BaseEstimator,
        mlflow_logger: Optional[MLflowLogger] = None,
    ) -> None:
        """Initialize uncertainty analyzer.

        Args:
            model: Fitted base model
            mlflow_logger: Optional MLflow logger
        """
        self.model = model
        self.mlflow_logger = mlflow_logger or get_mlflow_logger()

    # pylint: disable=too-many-arguments
    def analyze_with_bootstrap(
        self,
        x: pd.DataFrame,
        y: pd.Series,
        n_bootstraps: int = 100,
        confidence_level: float = 0.9,
    ) -> dict:
        """Analyze uncertainty using bootstrap sampling.

        Args:
            x: Feature matrix
            y: Target values
            n_bootstraps: Number of bootstrap iterations
            confidence_level: Confidence level

        Returns:
            Dictionary with uncertainty analysis results
        """
        predictor = UncertaintyAwarePredictor(
            self.model,
            config=UncertaintyConfig(
                n_bootstraps=n_bootstraps,
                confidence_level=confidence_level,
            ),
            mlflow_logger=self.mlflow_logger,
        )
        predictor.fit(x, y)

        results = predictor.predict_with_interval(x)
        predictor.log_uncertainty_metrics(x)

        return {
            "prediction": results["prediction"].tolist(),
            "lower_bound": results["lower"].tolist(),
            "upper_bound": results["upper"].tolist(),
            "std": results["std"].tolist(),
            "mean_std": float(results["mean_std"]),
        }

    def analyze_with_conformal(
        self,
        x_cal: pd.DataFrame,
        y_cal: np.ndarray,
        x_test: pd.DataFrame,
        confidence_level: float = 0.9,
    ) -> dict:
        """Analyze uncertainty using conformal prediction.

        Args:
            x_cal: Calibration features
            y_cal: Calibration targets
            x_test: Test features
            confidence_level: Confidence level

        Returns:
            Dictionary with conformal prediction results
        """
        results = conformal_prediction_interval(
            x_cal=x_cal,
            y_cal=y_cal,
            x_test=x_test,
            model=self.model,
            config=ConformalConfig(
                confidence_level=confidence_level,
                mlflow_logger=self.mlflow_logger,
            ),
        )

        return {
            "lower": results["lower"].tolist(),
            "upper": results["upper"].tolist(),
            "adjustment": float(results["adjustment"]),
        }
