from __future__ import annotations

# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
# pylint: disable=too-many-arguments,too-many-locals

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, cast, Literal

import numpy as np
import pandas as pd
from pandas import DataFrame, Index, Series


from quantitative_sports.data.sources.curated.io import (
    CuratedPaths,
    resolve_paths_from_config,
    resolve_snapshot_id,
)
from quantitative_sports.models.predictive.baselines import add_baseline_probabilities
from quantitative_sports.util.logging import get_logger

logger = get_logger(__name__)


def _to_numeric_series(
    values: pd.Series, *, errors: Literal["ignore", "raise", "coerce"] = "coerce"
) -> pd.Series:
    """Coerce a Series into numeric values (NaN on parse failures).

    Notes:
      pandas' stubs intentionally widen return types for `pd.to_numeric`.
      We normalize back to a Series for the rest of this module.
    """
    out: pd.Series = cast(pd.Series, pd.to_numeric(values, errors=errors))  # pyright: ignore[reportUnknownMemberType]
    return out


def _brier_score(y_true: np.ndarray, p: np.ndarray) -> float:
    p = np.clip(p, 1e-9, 1.0 - 1e-9)
    return float(np.mean((p - y_true) ** 2))


def _log_loss(y_true: np.ndarray, p: np.ndarray) -> float:
    p = np.clip(p, 1e-9, 1.0 - 1e-9)
    return float(-np.mean(y_true * np.log(p) + (1.0 - y_true) * np.log(1.0 - p)))


def _ensure_required(df: DataFrame, cols: list[str], *, what: str) -> None:
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise ValueError(f"{what} missing required columns: {missing}")


def _col(df: DataFrame, col: str) -> pd.Series:
    """Return a DataFrame column as a Series.

    pandas' type stubs are intentionally conservative and sometimes widen `df[col]` to
    `Series | DataFrame | Unknown`. In this codepath we only access scalar columns,
    which are Series at runtime.
    """
    return cast(pd.Series, df[col])


def _astype_series(
    s: pd.Series,
    dtype: Any,
    *,
    errors: Literal["ignore", "raise"] = "raise",
) -> pd.Series:
    """Typed wrapper around Series.astype.

    pandas' `astype` stubs can be partially unknown depending on dtype.
    We normalize to a plain Series for downstream typing.
    """
    return s.astype(dtype, errors=errors)  # pyright: ignore[reportUnknownMemberType]


def _date_key(values: pd.Series) -> pd.Series:
    """Normalize date-like values to a YYYY-MM-DD string key for joins."""
    dt = pd.to_datetime(values, errors="coerce")  # pyright: ignore[reportUnknownMemberType]
    fmt_fn: Any = getattr(getattr(dt, "dt"), "strftime")
    formatted = cast(Series, fmt_fn("%Y-%m-%d"))
    mask = dt.notna()
    idx = cast(Index, values.index)
    normalized: list[str | Any] = []
    formatted_arr = formatted.to_numpy(dtype=object)
    mask_arr = mask.to_numpy(dtype=bool)
    for fmt_val, mask_flag in zip(formatted_arr, mask_arr):
        if mask_flag:
            normalized.append(str(fmt_val))
        else:
            normalized.append(pd.NA)
    result = pd.Series(normalized, index=idx, dtype="string")
    result.name = values.name
    return _astype_series(result, "string")


def _read_parquet(path: Path) -> DataFrame:
    """Typed wrapper for pd.read_parquet (pandas stubs are partially unknown)."""
    return pd.read_parquet(path)  # pyright: ignore[reportUnknownMemberType]


def _read_csv(path: Path) -> DataFrame:
    """Typed wrapper for pd.read_csv (pandas stubs are partially unknown)."""
    return pd.read_csv(path)  # pyright: ignore[reportUnknownMemberType]


def _write_csv(df: DataFrame, path: Path) -> None:
    """Typed wrapper for DataFrame.to_csv (pandas stubs are partially unknown)."""
    df.to_csv(path, index=False)  # pyright: ignore[reportUnknownMemberType]


@dataclass(frozen=True)
class EvaluateLinesConfig:
    league: str
    season: str
    cache_root: Path
    snapshot_id: Optional[str] = None


def export_lines_template_from_features(
    *,
    cfg: EvaluateLinesConfig,
    out_csv: Path,
    n_rows: int = 250,
    include_game_id: bool = True,
    line_source: str = "pra_last_10_mean",
) -> Path:
    """Export a *synthetic* lines.csv template from the features table.

    This is a smoke-test aid so you can validate the join + metrics pipeline
    without real betting data.

    Output columns:
      - player_id
      - game_date
      - line
      - game_id (optional)

    line_source:
      - 'pra_last_10_mean' (default)
      - 'y_pra' (actual)
      - 'pra_mu' (if already computed elsewhere)
    """

    league = str(cfg.league).lower().strip()
    season = str(cfg.season).strip()

    sid = resolve_snapshot_id(
        cfg.cache_root, league=league, season=season, snapshot_id=cfg.snapshot_id
    )
    if sid is None:
        raise FileNotFoundError(
            f"No snapshot found under {cfg.cache_root}/{league}/seasons/{season} (missing current.json)"
        )

    paths = CuratedPaths(cache_root=cfg.cache_root, league=league, season=season, snapshot_id=sid)
    feat_path = paths.pra_features_path()
    if not feat_path.exists():
        raise FileNotFoundError(f"missing features table: {feat_path}")

    feats: DataFrame = _read_parquet(feat_path)
    if feats.empty:
        raise RuntimeError("features table is empty")

    # Keep the most recent rows; they are most likely to reflect current schema.
    feats = feats.copy()
    feats["_game_date"] = _date_key(_col(feats, "game_date"))
    feats = feats.dropna(subset=["player_id", "_game_date"]).reset_index(drop=True)

    # Prefer later games in the season for realistic rolling windows.
    feats = feats.sort_values(["_game_date", "player_id"], ascending=[False, True])

    if line_source not in feats.columns:
        # Fallback to y_pra if desired source isn't present.
        line_col = "y_pra" if "y_pra" in feats.columns else None
    else:
        line_col = line_source

    if line_col is None:
        raise ValueError(
            f"line_source='{line_source}' not present in features and no fallback 'y_pra' column exists"
        )

    out = DataFrame(
        {
            "player_id": _astype_series(_col(feats, "player_id"), "int64", errors="ignore"),
            "game_date": _col(feats, "_game_date"),
            "line": _to_numeric_series(_col(feats, line_col)),
        }
    )
    if include_game_id and "game_id" in feats.columns:
        out["game_id"] = _astype_series(_col(feats, "game_id"), "string")

    out = out.head(int(max(1, n_rows))).reset_index(drop=True)

    out_csv = Path(out_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    _write_csv(out, out_csv)
    logger.info("wrote lines template: %s (rows=%d)", out_csv, len(out))
    return out_csv


def _load_eval_features(
    cfg: EvaluateLinesConfig,
) -> tuple[str, str, str, CuratedPaths, Path, DataFrame]:
    league, season, paths = resolve_paths_from_config(cfg)
    sid = paths.snapshot_id
    feat_path = paths.pra_features_path()
    if not feat_path.exists():
        raise FileNotFoundError(f"missing features table: {feat_path}")

    feats: DataFrame = _read_parquet(feat_path)
    return league, season, sid, paths, feat_path, feats


def _normalize_lines_for_eval(
    lines: DataFrame,
    *,
    col_player_id: str,
    col_game_date: str,
    col_line: str,
) -> DataFrame:
    lines = lines.copy()
    lines["_player_id"] = _astype_series(_to_numeric_series(_col(lines, col_player_id)), "Int64")
    lines["_game_date"] = _date_key(_col(lines, col_game_date))
    lines["line"] = _to_numeric_series(_col(lines, col_line))
    lines = lines.dropna(subset=["_player_id", "_game_date", "line"]).reset_index(drop=True)
    lines["_line_row"] = np.arange(len(lines))
    return lines


def _normalize_features_for_eval(feats: DataFrame) -> DataFrame:
    feats = feats.copy()
    feats["_player_id"] = _astype_series(_to_numeric_series(_col(feats, "player_id")), "Int64")
    feats["_game_date"] = _date_key(_col(feats, "game_date"))
    return feats


def _join_lines_to_features(
    *,
    lines: DataFrame,
    feats: DataFrame,
    col_game_id: Optional[str],
) -> tuple[DataFrame, str, DataFrame]:
    join_l = ["_player_id", "_game_date"]
    join_f = ["_player_id", "_game_date"]
    used_game_id = False

    if col_game_id and col_game_id in lines.columns and "game_id" in feats.columns:
        lines["_game_id"] = _astype_series(_col(lines, col_game_id), "string")
        feats["_game_id"] = _astype_series(_col(feats, "game_id"), "string")
        join_l.append("_game_id")
        join_f.append("_game_id")
        used_game_id = True

    matches: list[DataFrame] = []
    notes: list[str] = []
    remaining: DataFrame = lines

    merged = remaining.merge(feats, left_on=join_l, right_on=join_f, how="inner")
    if not merged.empty:
        matches.append(
            merged.assign(_join_note="player_id+game_date" + ("+game_id" if used_game_id else ""))
        )
        matched_rows = _col(merged, "_line_row").tolist()
        remaining = cast(DataFrame, remaining[~_col(remaining, "_line_row").isin(matched_rows)])
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
            matched_rows = _col(merged, "_line_row").tolist()
            remaining = cast(DataFrame, remaining[~_col(remaining, "_line_row").isin(matched_rows)])
            notes.append("player_id+game_date (fallback)")

    if not remaining.empty:
        latest_feats = (
            feats.sort_values("_game_date")
            .groupby("_player_id", as_index=False, sort=False)
            .tail(1)
        )
        merged = remaining.merge(latest_feats, on="_player_id", how="inner", suffixes=("_x", "_y"))
        if not merged.empty:
            if "game_date_y" in merged.columns and "game_date_x" in merged.columns:
                merged["game_date_y"] = merged["game_date_x"]
            if "_game_date_y" in merged.columns and "_game_date_x" in merged.columns:
                merged["_game_date_y"] = merged["_game_date_x"]
            if "game_id_y" not in merged.columns and "game_id_x" in merged.columns:
                merged["game_id_y"] = merged["game_id_x"]
            merged["_join_note"] = "player_id (latest features fallback)"
            matches.append(merged)
            matched_rows = _col(merged, "_line_row").tolist()
            remaining = cast(DataFrame, remaining[~_col(remaining, "_line_row").isin(matched_rows)])
            notes.append("player_id (latest fallback)")

    if not matches:
        return DataFrame(), "no join matches (player_id+date)", remaining

    joined = pd.concat(matches, ignore_index=True)
    note = "; ".join(dict.fromkeys(notes))
    return joined, note, remaining


def _finalize_joined_lines(joined: DataFrame) -> DataFrame:
    if "player_id_y" in joined.columns:
        joined["player_id"] = joined["player_id_y"]
    if "game_date_y" in joined.columns:
        joined["game_date"] = joined["game_date_y"]
    if "game_id_y" in joined.columns and "game_id" not in joined.columns:
        joined["game_id"] = joined["game_id_y"]

    rename_map = {}
    for col in list(joined.columns):
        if col.endswith("_y"):
            base = col[:-2]
            if base not in joined.columns:
                rename_map[col] = base
    if rename_map:
        joined = joined.rename(columns=rename_map)
    if "line" not in joined.columns:
        if "line_x" in joined.columns:
            joined["line"] = joined["line_x"]
        elif "line_y" in joined.columns:
            joined["line"] = joined["line_y"]
    return joined.drop(columns=[c for c in ["_line_row", "_join_note"] if c in joined.columns])


def _build_eval_summary(
    joined: DataFrame,
    *,
    lines: DataFrame,
    note: str,
    sid: str,
    feat_path: Path,
    col_game_date: str,
) -> dict[str, Any]:
    y_pra = _to_numeric_series(_col(joined, "y_pra"))
    line_ser = _to_numeric_series(_col(joined, "line"))
    y_over = (np.asarray(y_pra, dtype=float) > np.asarray(line_ser, dtype=float)).astype(float)

    p_over = _to_numeric_series(_col(joined, "baseline_p_over"))
    p_arr = np.asarray(p_over, dtype=float)

    summary: dict[str, Any] = {
        "n": int(len(joined)),
        "snapshot_id": sid,
        "artifact_features": str(feat_path),
        "brier": _brier_score(y_over, p_arr),
        "log_loss": _log_loss(y_over, p_arr),
        "note": note,
    }
    if col_game_date in lines.columns:
        summary["requested_dates"] = sorted({str(d) for d in _col(lines, col_game_date).unique()})
    if "game_date" in joined.columns:
        summary["evaluated_dates"] = sorted({str(d) for d in _col(joined, "game_date").unique()})
    return summary


def evaluate_baselines_vs_lines(
    *,
    cfg: EvaluateLinesConfig,
    lines_csv: Path,
    col_player_id: str = "player_id",
    col_game_date: str = "game_date",
    col_line: str = "line",
    col_game_id: Optional[str] = "game_id",
) -> tuple[DataFrame, dict[str, Any]]:
    """Join a user-provided lines.csv against features and evaluate baseline probabilities.

    Expected lines.csv columns:
      - player_id (required)
      - game_date (required; YYYY-MM-DD)
      - line (required; numeric)
      - game_id (optional but recommended if you have duplicate dates)

    Outputs:
      - features/baseline_lines_eval_<season>.parquet under the season snapshot
      - returns (joined_df, summary_metrics)
    """

    _league, season, sid, paths, feat_path, feats = _load_eval_features(cfg)
    if feats.empty:
        return DataFrame(), {"n": 0, "note": "empty features"}

    lines: DataFrame = _read_csv(Path(lines_csv))
    _ensure_required(lines, [col_player_id, col_game_date, col_line], what="lines.csv")

    # Normalize join keys
    lines = _normalize_lines_for_eval(
        lines,
        col_player_id=col_player_id,
        col_game_date=col_game_date,
        col_line=col_line,
    )
    if lines.empty:
        return DataFrame(), {"n": 0, "note": "no valid lines rows"}

    feats = _normalize_features_for_eval(feats)

    joined, note, remaining = _join_lines_to_features(
        lines=lines,
        feats=feats,
        col_game_id=col_game_id,
    )
    if joined.empty:
        return DataFrame(), {"n": 0, "note": note}
    if not remaining.empty:
        note = f"{note}; unmatched_lines={len(remaining)}"

    # Preserve canonical columns and drop helpers.
    joined = _finalize_joined_lines(joined)

    # Add baseline probability columns
    joined = add_baseline_probabilities(joined, line_col="line", out_prob_col="baseline_p_over")
    summary = _build_eval_summary(
        joined,
        lines=lines,
        note=note,
        sid=sid,
        feat_path=feat_path,
        col_game_date=col_game_date,
    )

    try:
        out_path = paths.features_dir() / f"baseline_lines_eval_{season}.parquet"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        cast(Any, joined).to_parquet(out_path, index=False)
        summary["artifact"] = str(out_path)
    except (OSError, ValueError, TypeError):
        logger.exception("failed writing baseline lines eval artifact")

    return joined, summary
