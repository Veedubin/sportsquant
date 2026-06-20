from __future__ import annotations

# pylint: disable=too-many-arguments,too-many-locals,invalid-name

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import numpy as np
import numpy.typing as npt
import pandas as pd
import xgboost as xgb  # pyright: ignore[reportMissingImports]  # pylint: disable=import-error

from quantitative_sports.util.nba_logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class ModelConfig:  # pylint: disable=too-many-instance-attributes
    n_estimators: int = 400
    learning_rate: float = 0.05
    max_depth: int = 4
    subsample: float = 0.9
    colsample_bytree: float = 0.9
    random_state: int = 42
    use_gpu: bool = False
    gpu_id: int = 0


def train_regressor(
    X: pd.DataFrame, y: pd.Series, *, cfg: ModelConfig | None = None
) -> xgb.XGBRegressor:
    cfg = cfg or ModelConfig()
    device = f"cuda:{cfg.gpu_id}" if cfg.use_gpu else "cpu"
    model = xgb.XGBRegressor(
        objective="reg:squarederror",
        n_estimators=cfg.n_estimators,
        learning_rate=cfg.learning_rate,
        max_depth=cfg.max_depth,
        subsample=cfg.subsample,
        colsample_bytree=cfg.colsample_bytree,
        random_state=cfg.random_state,
        n_jobs=-1,
        tree_method="gpu_hist" if cfg.use_gpu else "hist",
        device=device,
    )
    model.fit(X, y)
    return model


def evaluate_holdout_rmse(
    X: pd.DataFrame,
    y: pd.Series,
    *,
    holdout_frac: float = 0.2,
    cfg: ModelConfig | None = None,
) -> float:
    # Small sample sizes are not meaningful; return NaN rather than a noisy metric.
    if len(X) < 10:
        return float("nan")

    n = len(X)
    split = max(1, int(n * (1.0 - holdout_frac)))

    # Pandas stubs often type .iloc as Any; cast to keep Pyright strict happy.
    X_train: pd.DataFrame = cast(pd.DataFrame, X.iloc[:split])
    X_test: pd.DataFrame = cast(pd.DataFrame, X.iloc[split:])
    y_train: pd.Series = cast(pd.Series, y.iloc[:split])
    y_test: pd.Series = cast(pd.Series, y.iloc[split:])

    model = train_regressor(X_train, y_train, cfg=cfg)

    preds = cast(npt.NDArray[np.floating[Any]], model.predict(X_test))
    # Avoid Series.to_numpy typing issues in strict Pyright; use NumPy conversion directly.
    y_test_arr = cast(npt.NDArray[np.floating[Any]], np.asarray(y_test, dtype=float))

    diff = preds - y_test_arr
    rmse = float(np.sqrt(np.mean(diff**2)))
    return rmse


def evaluate_holdout_with_baselines(
    X: pd.DataFrame,
    y: pd.Series,
    *,
    holdout_frac: float = 0.2,
    cfg: ModelConfig | None = None,
) -> dict[str, float]:
    """Evaluate a naive time split and compare against simple baselines.

    Baselines:
      - season_avg: constant mean of the training portion.
      - last10: rolling mean of the last 10 games (lagged to avoid leakage).

    Returns a dict with rmse values; small samples (<10 rows) return NaNs.
    """

    if len(X) < 10:
        nan = float("nan")
        return {
            "rmse_model": nan,
            "rmse_season_avg": nan,
            "rmse_last10": nan,
        }

    n = len(X)
    split = max(1, int(n * (1.0 - holdout_frac)))

    X_train: pd.DataFrame = cast(pd.DataFrame, X.iloc[:split])
    X_test: pd.DataFrame = cast(pd.DataFrame, X.iloc[split:])
    y_train: pd.Series = cast(pd.Series, y.iloc[:split])
    y_test: pd.Series = cast(pd.Series, y.iloc[split:])

    model = train_regressor(X_train, y_train, cfg=cfg)
    preds = cast(npt.NDArray[np.floating[Any]], model.predict(X_test))
    y_test_arr = cast(npt.NDArray[np.floating[Any]], np.asarray(y_test, dtype=float))

    diff = preds - y_test_arr
    rmse_model = float(np.sqrt(np.mean(diff**2)))

    # Baseline 1: season average (training mean)
    mean_train = float(np.mean(np.asarray(y_train, dtype=float)))
    season_avg_preds = np.full(shape=y_test_arr.shape, fill_value=mean_train, dtype=float)
    rmse_season_avg = float(np.sqrt(np.mean((season_avg_preds - y_test_arr) ** 2)))

    # Baseline 2: last-10 average (lagged).
    # Prefer an already-leakage-safe feature if present.
    if "PTS_ROLL10" in X_test.columns:
        last10 = cast(npt.NDArray[np.floating[Any]], np.asarray(X_test["PTS_ROLL10"], dtype=float))
    else:
        # Compute from y directly: rolling mean of y.shift(1) with window=10
        y_lag = np.asarray(y, dtype=float)
        # Build rolling for entire series then slice test segment
        roll: list[float] = []
        for i in range(len(y_lag)):
            start = max(0, i - 10)
            window = y_lag[start:i]
            if len(window) == 0:
                roll.append(float("nan"))
            else:
                roll.append(float(np.nanmean(window)))
        last10 = np.asarray(roll[split:], dtype=float)
        last10 = np.nan_to_num(last10, nan=mean_train)

    rmse_last10 = float(np.sqrt(np.mean((last10 - y_test_arr) ** 2)))

    return {
        "rmse_model": rmse_model,
        "rmse_season_avg": rmse_season_avg,
        "rmse_last10": rmse_last10,
    }


def evaluate_time_series_cv_with_baselines(
    X: pd.DataFrame,
    y: pd.Series,
    *,
    n_splits: int = 3,
    min_train_size: int = 20,
    test_size: int = 10,
    cfg: ModelConfig | None = None,
) -> dict[str, float]:
    """Time-series CV (expanding window) with baseline comparisons.

    This avoids leakage and provides a more stable estimate than a single split,
    especially when adding richer feature sets.

    Returns mean RMSE across folds. If there is insufficient history, returns NaNs.
    """

    if len(X) < max(10, min_train_size + test_size):
        nan = float("nan")
        return {
            "rmse_model": nan,
            "rmse_season_avg": nan,
            "rmse_last10": nan,
        }

    n = len(X)
    # Build fold boundaries from the end, but keep expanding train windows.
    # Example: test windows are contiguous blocks of length test_size.
    max_folds = (n - min_train_size) // test_size
    folds = min(int(n_splits), int(max_folds))
    if folds <= 0:
        nan = float("nan")
        return {
            "rmse_model": nan,
            "rmse_season_avg": nan,
            "rmse_last10": nan,
        }

    rmses_model: list[float] = []
    rmses_season_avg: list[float] = []
    rmses_last10: list[float] = []

    for k in range(folds):
        train_end = min_train_size + k * test_size
        test_start = train_end
        test_end = min(n, test_start + test_size)
        if test_end <= test_start:
            continue

        X_train: pd.DataFrame = cast(pd.DataFrame, X.iloc[:train_end])
        y_train: pd.Series = cast(pd.Series, y.iloc[:train_end])
        X_test: pd.DataFrame = cast(pd.DataFrame, X.iloc[test_start:test_end])
        y_test: pd.Series = cast(pd.Series, y.iloc[test_start:test_end])

        model = train_regressor(X_train, y_train, cfg=cfg)
        preds = cast(npt.NDArray[np.floating[Any]], model.predict(X_test))
        y_test_arr = cast(npt.NDArray[np.floating[Any]], np.asarray(y_test, dtype=float))

        diff = preds - y_test_arr
        rmses_model.append(float(np.sqrt(np.mean(diff**2))))

        mean_train = float(np.mean(np.asarray(y_train, dtype=float)))
        season_avg_preds = np.full(shape=y_test_arr.shape, fill_value=mean_train, dtype=float)
        rmses_season_avg.append(float(np.sqrt(np.mean((season_avg_preds - y_test_arr) ** 2))))

        # Baseline: last10 average. Prefer feature if present (leakage-safe).
        if "PTS_ROLL10" in X_test.columns:
            last10 = cast(
                npt.NDArray[np.floating[Any]], np.asarray(X_test["PTS_ROLL10"], dtype=float)
            )
        else:
            y_lag = np.asarray(y, dtype=float)
            roll: list[float] = []
            for i in range(len(y_lag)):
                start = max(0, i - 10)
                window = y_lag[start:i]
                if len(window) == 0:
                    roll.append(float("nan"))
                else:
                    roll.append(float(np.nanmean(window)))
            last10 = np.asarray(roll[test_start:test_end], dtype=float)
            last10 = np.nan_to_num(last10, nan=mean_train)
        rmses_last10.append(float(np.sqrt(np.mean((last10 - y_test_arr) ** 2))))

    def _safe_mean(vals: list[float]) -> float:
        arr = np.asarray(vals, dtype=float)
        if arr.size == 0:
            return float("nan")
        return float(np.nanmean(arr))

    return {
        "rmse_model": _safe_mean(rmses_model),
        "rmse_season_avg": _safe_mean(rmses_season_avg),
        "rmse_last10": _safe_mean(rmses_last10),
    }


def _xgb_save_model(model: xgb.XGBRegressor, path: Path) -> None:
    # Some XGBoost builds do not set `_estimator_type` until a Scikit mixin is applied.
    if not hasattr(model, "_estimator_type"):
        # Avoid direct protected-member access (pylint W0212) while still providing
        # compatibility with older XGBoost builds.
        setattr(model, "_estimator_type", "regressor")
    # XGBoost's type stubs may include PathLike[Unknown], which triggers Pyright strict warnings.
    cast(Any, model).save_model(str(path))


def _xgb_load_model(model: xgb.XGBRegressor, path: Path) -> None:
    if not hasattr(model, "_estimator_type"):
        setattr(model, "_estimator_type", "regressor")
    # XGBoost's type stubs may include PathLike[Unknown], which triggers Pyright strict warnings.
    cast(Any, model).load_model(str(path))


def save_artifact(model_out: Path, model: xgb.XGBRegressor, meta: dict[str, Any]) -> None:
    model_out.parent.mkdir(parents=True, exist_ok=True)
    model_path = model_out.with_suffix(".json")
    meta_path = model_out.with_suffix(".meta.json")

    _xgb_save_model(model, model_path)
    with meta_path.open("w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, sort_keys=True)

    logger.info("saved model: %s", model_path)
    logger.info("saved meta:  %s", meta_path)


def load_artifact(model_in: Path) -> tuple[xgb.XGBRegressor, dict[str, Any]]:
    model_path = model_in.with_suffix(".json")
    meta_path = model_in.with_suffix(".meta.json")

    if not model_path.exists():
        raise FileNotFoundError(str(model_path))
    if not meta_path.exists():
        raise FileNotFoundError(str(meta_path))

    model = xgb.XGBRegressor()
    _xgb_load_model(model, model_path)

    meta = cast(dict[str, Any], json.loads(meta_path.read_text(encoding="utf-8")))
    return model, meta
