from __future__ import annotations

# pylint: disable=too-many-instance-attributes,too-many-arguments,too-many-locals,invalid-name

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional, cast

import numpy as np
import pandas as pd
import xgboost as xgb  # pyright: ignore[reportMissingImports]  # pylint: disable=import-error
from pandas import DataFrame

from sportsquant.models.predictive.io import load_pra_features
from sportsquant.models.predictive.artifact import ModelConfig, save_artifact, train_regressor
from sportsquant.util.nba_logging import get_logger

logger = get_logger(__name__)


def _is_numeric(series_or_dtype: Any) -> bool:
    # `pandas.api.types.is_numeric_dtype` is typed as accepting `Unknown` in
    # pandas-stubs, which trips strict pyright diagnostics.
    return bool(cast(Any, pd.api.types).is_numeric_dtype(series_or_dtype))


def _fillna_frame_mean(frame: DataFrame) -> DataFrame:
    # pandas-stubs contain `Unknown` in these method signatures; call through
    # `Any` to avoid `reportUnknownMemberType` while keeping a typed return.
    frame_any = cast(Any, frame)
    return cast(DataFrame, frame_any.fillna(frame_any.mean(numeric_only=True)))


def _to_numeric_series(values: object) -> pd.Series:
    # `pd.to_numeric` is partially unknown in pandas-stubs; call through `Any`.
    return cast(pd.Series, cast(Any, pd).to_numeric(values, errors="coerce"))


def _fillna_series_mean(series: pd.Series) -> pd.Series:
    series_any = cast(Any, series)
    return cast(pd.Series, series_any.fillna(series_any.mean()))


@dataclass(frozen=True)
class ComponentModelPaths:
    """Canonical storage locations for PRA component models within a season snapshot."""

    cache_root: Path
    league: str
    season: str
    snapshot_id: str

    def base_dir(self) -> Path:
        return (
            Path(self.cache_root)
            / self.league
            / "seasons"
            / self.season
            / self.snapshot_id
            / "models"
        )

    def minutes_prefix(self) -> Path:
        return self.base_dir() / f"minutes_{self.season}"

    def ppm_prefix(self) -> Path:
        return self.base_dir() / f"ppm_{self.season}"

    def rpm_prefix(self) -> Path:
        return self.base_dir() / f"rpm_{self.season}"

    def apm_prefix(self) -> Path:
        return self.base_dir() / f"apm_{self.season}"


@dataclass(frozen=True)
class PraComponentTrainConfig:
    league: str
    season: str
    cache_root: Path
    snapshot_id: Optional[str] = None
    cfg_minutes: Optional[ModelConfig] = None
    cfg_rates: Optional[ModelConfig] = None
    min_rows: int = 250
    random_state: int = 42
    # "Regression gate" controls.
    gate_enabled: bool = True
    gate_max_rmse_ratio_vs_baseline: float = (
        1.05  # 1.0 requires beating the baseline; >1.0 allows small slack
    )


def _select_feature_columns(df: DataFrame) -> list[str]:
    """Select numeric feature columns for model training.

    This is intentionally conservative: it excludes identifiers and targets and uses
    only numeric columns.
    """

    exclude_prefixes = ("y_",)
    exclude_cols = {
        "season",
        "game_id",
        "game_date",
        "player_id",
        "player_name",
        "team_abbr",
        "opp_team_abbr",
        "is_home",
    }

    cols: list[str] = []
    for c in map(str, df.columns):
        if c in exclude_cols:
            continue
        if any(c.startswith(p) for p in exclude_prefixes):
            continue
        col_value = cast(Any, df[c])
        if _is_numeric(col_value):
            cols.append(c)
    return cols


def _baseline_rmse_mean_predictor(y: np.ndarray) -> float:
    if y.size == 0:
        return float("nan")
    mu = float(np.nanmean(y))
    return float(np.sqrt(np.nanmean((y - mu) ** 2)))


def _holdout_rmse(model: xgb.XGBRegressor, X: np.ndarray, y: np.ndarray, split: int) -> float:
    if split >= len(y):
        return float("nan")
    preds = cast(np.ndarray, model.predict(X[split:]))
    diff = preds.astype(float) - y[split:].astype(float)
    return float(np.sqrt(np.nanmean(diff**2)))


def _train_one(
    df: DataFrame,
    *,
    target_col: str,
    feature_cols: list[str],
    cfg: Optional[ModelConfig],
    gate_enabled: bool,
    gate_ratio: float,
    meta_extra: dict[str, Any],
    model_out: Path,
) -> dict[str, Any]:
    if target_col not in df.columns:
        raise ValueError(f"features table missing required target column: {target_col}")

    # Call through `Any` because pandas-stubs can report unknown member types under strict pyright.
    work = cast(DataFrame, cast(Any, df).dropna(subset=[target_col]))
    work = work.copy()
    if len(work) < 10:
        raise RuntimeError(f"insufficient rows for target={target_col}: {len(work)}")

    feature_frame = cast(DataFrame, cast(Any, work).loc[:, feature_cols])
    x_df: DataFrame = feature_frame.copy()
    x_df = x_df.replace([np.inf, -np.inf], np.nan)
    x_df = _fillna_frame_mean(x_df)

    y_raw = cast(Any, work[target_col])
    y_s = _to_numeric_series(y_raw)
    y_s = y_s.replace([np.inf, -np.inf], np.nan)
    y_s = _fillna_series_mean(y_s)

    # Time-based holdout: last 20%.
    n = len(work)
    split = max(1, int(n * 0.8))
    X_train = cast(DataFrame, x_df.iloc[:split])
    y_train = cast(pd.Series, y_s.iloc[:split])
    y_test = cast(pd.Series, y_s.iloc[split:])

    model = train_regressor(X_train, y_train, cfg=cfg)

    # Regression gate: compare holdout RMSE to mean-predictor RMSE.
    y_test_arr = np.asarray(y_test, dtype=float)
    rmse_base = _baseline_rmse_mean_predictor(y_test_arr)
    rmse_model = _holdout_rmse(
        model, np.asarray(x_df, dtype=float), np.asarray(y_s, dtype=float), split
    )
    if not np.isfinite(rmse_base) or rmse_base == 0.0:
        rmse_ratio = float("nan")
    else:
        rmse_ratio = float(rmse_model / rmse_base)

    if gate_enabled and np.isfinite(rmse_base) and np.isfinite(rmse_model):
        if rmse_model > (rmse_base * gate_ratio):
            raise RuntimeError(
                f"regression gate failed for {target_col}: rmse_model={rmse_model:.4f} rmse_baseline={rmse_base:.4f} "
                f"ratio={(rmse_model / rmse_base):.3f} gate={gate_ratio:.3f}"
            )

    meta: dict[str, Any] = {
        "target": target_col,
        "feature_cols": feature_cols,
        "n_rows": int(n),
        "split": int(split),
        "rmse_holdout": float(rmse_model),
        "rmse_baseline_mean": float(rmse_base),
        "rmse_ratio_vs_baseline": float(rmse_ratio),
        "cfg": asdict(cfg or ModelConfig()),
        **meta_extra,
    }

    save_artifact(model_out, model, meta)
    return meta


def train_pra_component_models(cfg: PraComponentTrainConfig) -> dict[str, Any]:
    """Train PRA component models (minutes + points/reb/ast per minute).

    Input: features/pra_features_<season>.parquet (built via `pra-build`).
    Output: model artifacts written under the season snapshot `models/` directory.
    """

    league, season, paths, feat_path, feats = load_pra_features(
        cfg,
        min_rows=int(cfg.min_rows),
    )
    sid = paths.snapshot_id

    feature_cols = _select_feature_columns(feats)
    if not feature_cols:
        raise RuntimeError("no numeric feature columns available for training")

    out_paths = ComponentModelPaths(
        cache_root=Path(cfg.cache_root), league=league, season=season, snapshot_id=sid
    )
    out_paths.base_dir().mkdir(parents=True, exist_ok=True)

    meta_common = {
        "league": league,
        "season": season,
        "snapshot_id": sid,
        "features_path": str(feat_path),
    }

    results: dict[str, Any] = {"models": {}, "paths": {"base_dir": str(out_paths.base_dir())}}

    logger.info(
        "training PRA component models: season=%s rows=%d features=%d",
        season,
        len(feats),
        len(feature_cols),
    )

    results["models"]["minutes"] = _train_one(
        feats,
        target_col="y_minutes",
        feature_cols=feature_cols,
        cfg=cfg.cfg_minutes,
        gate_enabled=cfg.gate_enabled,
        gate_ratio=cfg.gate_max_rmse_ratio_vs_baseline,
        meta_extra={**meta_common, "component": "minutes"},
        model_out=out_paths.minutes_prefix(),
    )

    for comp, target, outp in (
        ("ppm", "y_ppm", out_paths.ppm_prefix()),
        ("rpm", "y_rpm", out_paths.rpm_prefix()),
        ("apm", "y_apm", out_paths.apm_prefix()),
    ):
        results["models"][comp] = _train_one(
            feats,
            target_col=target,
            feature_cols=feature_cols,
            cfg=cfg.cfg_rates,
            gate_enabled=cfg.gate_enabled,
            gate_ratio=cfg.gate_max_rmse_ratio_vs_baseline,
            meta_extra={**meta_common, "component": comp},
            model_out=outp,
        )

    # Write a convenience manifest for tooling.
    try:
        manifest = out_paths.base_dir() / f"pra_component_manifest_{season}.json"
        manifest.write_text(json.dumps(results, indent=2, sort_keys=True), encoding="utf-8")
        results["paths"]["manifest"] = str(manifest)
    except (OSError, TypeError, ValueError):
        logger.exception("failed writing PRA component manifest")

    return results
