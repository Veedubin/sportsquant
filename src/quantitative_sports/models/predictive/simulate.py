from __future__ import annotations

# pylint: disable=too-many-instance-attributes,too-many-arguments,too-many-locals,too-many-branches,too-many-statements,invalid-name

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, cast

import numpy as np
import pandas as pd
import xgboost as xgb  # pyright: ignore[reportMissingImports]  # pylint: disable=import-error
from pandas import DataFrame

from quantitative_sports.models.predictive.io import load_pra_features
from quantitative_sports.models.predictive.artifact import load_artifact
from quantitative_sports.models.predictive.pra_components import ComponentModelPaths
from quantitative_sports.util.nba_logging import get_logger

logger = get_logger(__name__)


def _infer_feature_columns(feats: DataFrame) -> list[str]:
    """Infer feature columns from a PRA features dataframe.

    Drops obvious identifiers / labels and keeps remaining columns. This is a fallback only;
    preferred path is loading `feature_cols` from model metadata.
    """
    drop = {
        "player_id",
        "game_id",
        "game_date",
        "team_id",
        "team_abbrev",
        "opponent_abbrev",
        "line",
        "pra_mu",
        "pra_sigma",
        "p_over",
    }
    cols: list[str] = []
    # Iterating `Index` yields `Unknown` under strict pyright with pandas-stubs.
    # Convert to `str` up-front to keep the loop variable typed.
    for c_str in map(str, feats.columns):
        if c_str in drop:
            continue
        if c_str.startswith("_"):
            continue
        cols.append(c_str)
    return cols


def _fillna_frame_mean(frame: DataFrame) -> DataFrame:
    """Fill NaNs using per-column mean.

    pandas-stubs include `Unknown` in various DataFrame method signatures. We call
    through `Any` to keep strict pyright clean while maintaining a typed return.
    """

    frame_any = cast(Any, frame)
    return cast(DataFrame, frame_any.fillna(frame_any.mean(numeric_only=True)))


def _to_numeric_series(values: object) -> pd.Series:
    """Convert values to numeric Series (coerce errors)."""

    return cast(pd.Series, cast(Any, pd).to_numeric(values, errors="coerce"))


def _astype_series(values: pd.Series, dtype: str) -> pd.Series:
    """Series.astype wrapper to avoid pandas-stubs `Unknown` signatures."""

    return cast(pd.Series, cast(Any, values).astype(dtype))


@dataclass(frozen=True)
class PraSimConfig:
    league: str
    season: str
    cache_root: Path
    snapshot_id: Optional[str] = None
    n_sims: int = 5000
    random_state: int = 1337
    # Floors to keep distributions reasonable when sample sizes are small.
    min_sigma_minutes: float = 2.5
    min_sigma_rate: float = 0.02


def _predict(model: xgb.XGBRegressor, X: DataFrame) -> np.ndarray:
    # XGBoost accepts ndarray. Using NumPy conversion avoids pandas-stubs typing
    # ambiguity around DataFrame.to_numpy's `dtype` parameter under strict pyright.
    arr = np.asarray(X, dtype=float)
    out = cast(np.ndarray, model.predict(arr))
    return out.astype(np.float64, copy=False)


def simulate_pra_distribution_for_rows(
    feats: DataFrame,
    *,
    cache_root: Path,
    league: str,
    season: str,
    snapshot_id: str,
    n_sims: int,
    random_state: int,
    min_sigma_minutes: float,
    min_sigma_rate: float,
) -> DataFrame:
    """Simulate PRA distributions for a set of feature rows.

    Expects a dataframe shaped like the PRA features table (one row per player-game).
    Returns the input rows with appended distribution summary statistics:
      - pra_mu, pra_sigma
      - p_over (requires `line` column on the input)
    """

    required = {"player_id", "game_date"}
    missing = required - set(feats.columns)
    if missing:
        raise ValueError(f"missing required feature columns: {sorted(missing)}")

    model_paths = ComponentModelPaths(
        cache_root=cache_root, league=league, season=season, snapshot_id=snapshot_id
    )
    minutes_model, minutes_meta = load_artifact(model_paths.minutes_prefix())
    ppm_model, ppm_meta = load_artifact(model_paths.ppm_prefix())
    rpm_model, rpm_meta = load_artifact(model_paths.rpm_prefix())
    apm_model, apm_meta = load_artifact(model_paths.apm_prefix())

    # Determine feature columns from stored meta if available; fallback to inference.
    feature_cols_meta = minutes_meta.get("feature_cols")
    fcols = (
        cast(list[str], feature_cols_meta)
        if isinstance(feature_cols_meta, list)
        else _infer_feature_columns(feats)
    )
    if not fcols:
        raise RuntimeError("no feature columns for simulation")

    # Avoid DataFrame.__getitem__ typing ambiguity under strict pyright by calling via `Any`.
    feats_any = cast(Any, feats)
    x_df = cast(DataFrame, feats_any.reindex(columns=fcols).copy())
    x_df = x_df.replace([np.inf, -np.inf], np.nan)
    x_df = _fillna_frame_mean(x_df)

    min_mu = _predict(minutes_model, x_df)
    ppm_mu = _predict(ppm_model, x_df)
    rpm_mu = _predict(rpm_model, x_df)
    apm_mu = _predict(apm_model, x_df)

    # Use training-time holdout residual scales if present; otherwise use global std floors.
    # The per-row distribution is not perfectly calibrated; this is a pragmatic Phase-1 approximation.
    min_sig = float(min_sigma_minutes)
    rate_sig = float(min_sigma_rate)
    for meta in (minutes_meta, ppm_meta, rpm_meta, apm_meta):
        v = meta.get("rmse_holdout")
        if isinstance(v, (int, float)) and math.isfinite(float(v)):
            if meta.get("target") == "y_minutes":
                min_sig = max(min_sig, float(v))
            else:
                rate_sig = max(rate_sig, float(v))

    rng = np.random.default_rng(int(random_state))

    n_rows = int(len(feats))
    if n_rows == 0:
        return feats.copy()

    n_sims_i = int(n_sims)

    # Broadcast sims: (n_rows, n_sims)
    mins = rng.normal(loc=min_mu.reshape(-1, 1), scale=min_sig, size=(n_rows, n_sims_i))
    mins = np.clip(mins, 0.0, None)

    ppm = rng.normal(loc=ppm_mu.reshape(-1, 1), scale=rate_sig, size=(n_rows, n_sims_i))
    rpm = rng.normal(loc=rpm_mu.reshape(-1, 1), scale=rate_sig, size=(n_rows, n_sims_i))
    apm = rng.normal(loc=apm_mu.reshape(-1, 1), scale=rate_sig, size=(n_rows, n_sims_i))

    pra = mins * (ppm + rpm + apm)

    out = feats.copy()
    out["pra_mu"] = np.mean(pra, axis=1)
    out["pra_sigma"] = np.std(pra, axis=1)

    if "line" in out.columns:
        line_ser = _to_numeric_series(cast(pd.Series, out["line"]))
        line_arr = np.asarray(line_ser, dtype=np.float64)
        out["p_over"] = np.mean(pra > line_arr.reshape(-1, 1), axis=1)

    return out


def simulate_pra_for_lines_csv(
    *,
    cfg: PraSimConfig,
    lines_csv: Path,
    col_player_id: str = "player_id",
    col_game_date: str = "game_date",
    col_line: str = "line",
    col_game_id: Optional[str] = "game_id",
) -> tuple[DataFrame, dict[str, Any]]:
    """Join lines CSV to features and compute simulation-based probabilities."""

    league, season, paths, feat_path, feats = load_pra_features(
        cfg,
        allow_empty=True,
    )
    sid = paths.snapshot_id
    if feats.empty:
        return DataFrame(), {"n": 0, "note": "empty features"}

    lines = cast(DataFrame, cast(Any, pd).read_csv(Path(lines_csv)))
    for c in (col_player_id, col_game_date, col_line):
        if c not in lines.columns:
            raise ValueError(f"lines CSV missing required column: {c}")

    lines = lines.copy()
    lines["_player_id"] = _astype_series(
        _to_numeric_series(cast(pd.Series, lines[col_player_id])), "Int64"
    )
    lines["_game_date"] = cast(Any, pd).to_datetime(lines[col_game_date], errors="coerce")
    lines["line"] = _to_numeric_series(cast(pd.Series, lines[col_line]))
    lines = lines.dropna(subset=["_player_id", "_game_date", "line"]).reset_index(drop=True)
    lines["_line_row"] = np.arange(len(lines))
    if lines.empty:
        return DataFrame(), {"n": 0, "note": "no valid lines rows"}

    feats = feats.copy()
    feats["_player_id"] = _astype_series(
        _to_numeric_series(cast(pd.Series, feats["player_id"])), "Int64"
    )
    feats["_game_date"] = cast(Any, pd).to_datetime(feats["game_date"], errors="coerce")

    join_l = ["_player_id", "_game_date"]
    join_f = ["_player_id", "_game_date"]
    used_game_id = False
    if col_game_id and col_game_id in lines.columns and "game_id" in feats.columns:
        lines["_game_id"] = _astype_series(cast(pd.Series, lines[col_game_id]), "string")
        feats["_game_id"] = _astype_series(cast(pd.Series, feats["game_id"]), "string")
        join_l.append("_game_id")
        join_f.append("_game_id")
        used_game_id = True
    # Build up matches in stages to allow fallbacks.
    matches: list[DataFrame] = []
    notes: list[str] = []
    remaining: DataFrame = lines

    merged = remaining.merge(feats, left_on=join_l, right_on=join_f, how="inner")
    if not merged.empty:
        matches.append(
            merged.assign(_join_note="player_id+game_date" + ("+game_id" if used_game_id else ""))
        )
        matched_rows = cast(pd.Series, merged["_line_row"]).tolist()
        remaining = cast(
            DataFrame, remaining[~cast(pd.Series, remaining["_line_row"]).isin(matched_rows)]
        )
        notes.append("player_id+game_date" + ("+game_id" if used_game_id else ""))

    if used_game_id and not remaining.empty:
        merged = remaining.merge(
            feats,
            left_on=["_player_id", "_game_date"],
            right_on=["_player_id", "_game_date"],
            how="inner",
        )
        if not merged.empty:
            matches.append(
                merged.assign(_join_note="player_id+game_date (fallback, game_id mismatch)")
            )
            matched_rows = cast(pd.Series, merged["_line_row"]).tolist()
            remaining = cast(
                DataFrame, remaining[~cast(pd.Series, remaining["_line_row"]).isin(matched_rows)]
            )
            notes.append("player_id+game_date (fallback)")

    if not remaining.empty:
        latest_feats = (
            feats.sort_values("_game_date")
            .groupby("_player_id", as_index=False, sort=False)
            .tail(1)
        )
        merged = remaining.merge(latest_feats, on="_player_id", how="inner", suffixes=("_x", "_y"))
        if not merged.empty:
            # Preserve the lines' game date/game id on the feature side to avoid confusing downstream consumers.
            if "game_date_y" in merged.columns and "game_date_x" in merged.columns:
                merged["game_date_y"] = merged["game_date_x"]
            if "_game_date_y" in merged.columns and "_game_date_x" in merged.columns:
                merged["_game_date_y"] = merged["_game_date_x"]
            if "game_id_y" not in merged.columns and "game_id_x" in merged.columns:
                merged["game_id_y"] = merged["game_id_x"]
            merged["_join_note"] = "player_id (latest features fallback)"
            matches.append(merged)
            matched_rows = cast(pd.Series, merged["_line_row"]).tolist()
            remaining = cast(
                DataFrame, remaining[~cast(pd.Series, remaining["_line_row"]).isin(matched_rows)]
            )
            notes.append("player_id (latest fallback)")

    if not matches:
        return DataFrame(), {"n": 0, "note": "no join matches (player_id+date)"}

    merged = pd.concat(matches, ignore_index=True)
    note = "; ".join(dict.fromkeys(notes))  # preserve order, remove duplicates
    if not remaining.empty:
        note = f"{note}; unmatched_lines={len(remaining)}"

    # After merge, columns from features have _y suffix, from lines have _x suffix
    # The simulation function expects the feature columns without suffix
    # Rename key columns from features (_y) to remove suffix
    if "player_id_y" in merged.columns:
        merged["player_id"] = merged["player_id_y"]
    if "game_date_y" in merged.columns:
        merged["game_date"] = merged["game_date_y"]

    # Drop helper columns used for join bookkeeping.
    merged = merged.drop(columns=[c for c in ["_line_row", "_join_note"] if c in merged.columns])

    sim = simulate_pra_distribution_for_rows(
        merged,
        cache_root=Path(cfg.cache_root),
        league=league,
        season=season,
        snapshot_id=sid,
        n_sims=int(cfg.n_sims),
        random_state=int(cfg.random_state),
        min_sigma_minutes=float(cfg.min_sigma_minutes),
        min_sigma_rate=float(cfg.min_sigma_rate),
    )

    summary: dict[str, Any] = {
        "n": int(len(sim)),
        "artifact_features": str(feat_path),
        "snapshot_id": sid,
        "n_sims": int(cfg.n_sims),
        "note": note,
    }
    if "game_date" in lines.columns:
        summary["requested_dates"] = sorted({str(d) for d in lines[col_game_date].unique()})
    if "game_date" in sim.columns:
        summary["simulated_dates"] = sorted({str(d) for d in sim["game_date"].unique()})
    if "p_over" in sim.columns:
        p_over_ser = _to_numeric_series(cast(pd.Series, sim["p_over"]))
        p_over_arr = np.asarray(p_over_ser, dtype=np.float64)
        summary["p_over_mean"] = float(np.nanmean(p_over_arr))
    else:
        summary["p_over_mean"] = None

    # Write artifact next to features.
    try:
        out_path = paths.features_dir() / f"pra_sim_lines_{season}.parquet"
        out_path.parent.mkdir(parents=True, exist_ok=True)

        # Normalize date columns to consistent format for parquet compatibility
        date_cols = [c for c in sim.columns if "date" in c.lower()]
        for col in date_cols:
            sim[col] = pd.to_datetime(sim[col], errors="coerce").dt.strftime("%Y-%m-%d")

        cast(Any, sim).to_parquet(out_path, index=False)
        summary["artifact"] = str(out_path)
    except (OSError, ValueError, TypeError):
        logger.exception("failed writing PRA simulation lines artifact")

    return sim, summary
