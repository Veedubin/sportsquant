"""
Custom exception hierarchy for quantitative_sports.

Provides specific exception types for better error handling and debugging.
"""

from pathlib import Path
from typing import Any


class NBAXGBError(Exception):
    """Base exception for all quantitative_sports errors."""

    def __init__(self, message: str, context: dict[str, Any] | None = None):
        self.message = message
        self.context = context or {}
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        ctx_str = ", ".join(f"{k}={v}" for k, v in self.context.items()) if self.context else ""
        return f"{self.message}" + (f" [{ctx_str}]" if ctx_str else "")


class CacheError(NBAXGBError):
    """Base exception for cache-related errors."""


class CacheBuildError(CacheError):
    """Raised when cache build fails for a specific season."""

    def __init__(self, season: str, player_id: int | None = None, reason: str = "Unknown"):
        context: dict[str, Any] = {"season": season}
        if player_id is not None:
            context["player_id"] = player_id
        super().__init__(f"Cache build failed for season {season}", context)
        self.season = season
        self.player_id = player_id
        self.reason = reason


class CacheSnapshotError(CacheError):
    """Raised when snapshot operations fail."""

    def __init__(self, season: str, snapshot_id: str | None, reason: str):
        context: dict[str, Any] = {"season": season}
        if snapshot_id is not None:
            context["snapshot_id"] = snapshot_id
        super().__init__(f"Snapshot error for {season}/{snapshot_id}: {reason}", context)


class CacheNotFoundError(CacheError):
    """Raised when required cache data is not found."""

    def __init__(self, cache_path: Path, expected_for: str | None = None):
        context: dict[str, Any] = {"path": str(cache_path)}
        if expected_for:
            context["expected_for"] = expected_for
        super().__init__(f"Cache not found: {cache_path}", context)


class ModelError(NBAXGBError):
    """Base exception for model-related errors."""


class ModelTrainingError(ModelError):
    """Raised when model training fails."""

    def __init__(self, model_name: str, reason: str, metrics: dict[str, float] | None = None):
        context: dict[str, Any] = {"model": model_name, "reason": reason}
        if metrics:
            context["metrics"] = metrics
        super().__init__(f"Model training failed for {model_name}: {reason}", context)


class ModelPredictionError(ModelError):
    """Raised when model prediction fails."""

    def __init__(self, model_name: str, reason: str, input_shape: tuple[int, ...] | None = None):
        context: dict[str, Any] = {"model": model_name, "reason": reason}
        if input_shape:
            context["input_shape"] = input_shape
        super().__init__(f"Prediction failed for {model_name}: {reason}", context)


class ModelArtifactError(ModelError):
    """Raised when model artifact operations fail."""

    def __init__(self, artifact_path: Path, operation: str, reason: str):
        super().__init__(
            f"Artifact operation '{operation}' failed for {artifact_path}: {reason}",
            {"path": str(artifact_path), "operation": operation},
        )


class DataError(NBAXGBError):
    """Base exception for data-related errors."""


class DataValidationError(DataError):
    """Raised when data validation fails."""

    def __init__(self, column: str | None, expected: str, actual: str | None = None):
        context: dict[str, Any] = {"expected": expected}
        if column:
            context["column"] = column
        if actual:
            context["actual"] = actual
        super().__init__("Data validation failed", context)


class LinesCSVError(DataError):
    """Raised when lines.csv processing fails."""

    def __init__(self, file_path: Path, issue: str, row: int | None = None):
        context: dict[str, Any] = {"file": str(file_path), "issue": issue}
        if row is not None:
            context["row"] = row
        super().__init__(f"Lines CSV error in {file_path}: {issue}", context)


class FeatureEngineeringError(DataError):
    """Raised when feature engineering fails."""

    def __init__(self, feature_name: str, reason: str):
        super().__init__(
            f"Feature engineering failed for {feature_name}: {reason}",
            {"feature": feature_name},
        )


class BacktestError(NBAXGBError):
    """Base exception for backtest-related errors."""


class BacktestConfigurationError(BacktestError):
    """Raised when backtest configuration is invalid."""

    def __init__(self, config_param: str, reason: str, value: Any | None = None):
        context: dict[str, Any] = {"parameter": config_param, "reason": reason}
        if value is not None:
            context["value"] = str(value)
        super().__init__(f"Backtest configuration error: {config_param}", context)


class BacktestExecutionError(BacktestError):
    """Raised when backtest execution fails."""

    def __init__(self, market: str, season: str, reason: str):
        super().__init__(
            f"Backtest execution failed for {market}/{season}: {reason}",
            {"market": market, "season": season},
        )


class OddsAPIError(NBAXGBError):
    """Base exception for Odds API errors."""

    def __init__(
        self,
        api_endpoint: str,
        status_code: int | None = None,
        response: str | None = None,
    ):
        context: dict[str, Any] = {"endpoint": api_endpoint}
        if status_code:
            context["status_code"] = status_code
        if response:
            context["response"] = response
        super().__init__(f"Odds API error at {api_endpoint}", context)


class OddsAPIAuthError(OddsAPIError):
    """Raised when Odds API authentication fails."""

    def __init__(self, reason: str = "Invalid or missing API key"):
        super().__init__("authentication", response=reason)


class OddsAPIQuotaError(OddsAPIError):
    """Raised when Odds API quota is exceeded."""

    def __init__(self, remaining: int):
        super().__init__("quota_check", response=f"remaining={remaining}")


class StrategyError(NBAXGBError):
    """Base exception for strategy-related errors."""


class StrategyConfigurationError(StrategyError):
    """Raised when strategy configuration is invalid."""

    def __init__(self, strategy_name: str, param: str, reason: str):
        super().__init__(
            f"Strategy configuration error for {strategy_name}: {param} ({reason})",
            {"strategy": strategy_name, "parameter": param, "reason": reason},
        )


class StrategyExecutionError(StrategyError):
    """Raised when strategy execution fails."""

    def __init__(self, strategy_name: str, reason: str):
        super().__init__(
            f"Strategy execution failed for {strategy_name}: {reason}",
            {"strategy": strategy_name},
        )


class CLIError(NBAXGBError):
    """Base exception for CLI errors."""


class CLIOptionError(CLIError):
    """Raised when CLI options are invalid."""

    def __init__(self, option: str, reason: str, suggestion: str | None = None):
        context: dict[str, Any] = {"option": option, "reason": reason}
        if suggestion:
            context["suggestion"] = suggestion
        super().__init__(f"CLI option error: {option}", context)


class CLIDependencyError(CLIError):
    """Raised when required CLI dependency is missing."""

    def __init__(self, dependency: str, install_hint: str):
        super().__init__(
            f"Missing dependency: {dependency}",
            {"dependency": dependency, "install_hint": install_hint},
        )
