from __future__ import annotations

# pylint: disable=too-many-instance-attributes,too-many-arguments,too-many-locals,too-many-branches,too-many-statements

from dataclasses import dataclass
from typing import Any, Callable, cast

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class FeatureBuildConfig:
    rolling_windows: tuple[int, ...] = (5, 10)
    include_opponent: bool = True
    # If True and opponent-strength stats are provided, include season-to-date opponent
    # defensive/pace proxy features (computed from the league cache).
    include_opp_strength: bool = False
    # If True, include simple availability / minutes stability indicators.
    include_availability: bool = True
    # If True, include lifetime (expanding) averages of lagged stats.
    include_lifetime: bool = True
    # If True, include points-per-minute (PPM) and its lag/rolling/lifetime features.
    include_points_per_min: bool = True
    stat_columns: tuple[str, ...] = ("PTS", "MIN", "FGA", "FG3A", "FTA")
    max_rest_days: int = 10


def _require_series(df: pd.DataFrame, col: str) -> pd.Series:
    """Return df[col] as a Series.

    Pandas typing for DataFrame.__getitem__ is conservative and can be
    DataFrame | Series, even when indexing by a single column name.

    In strict pyright mode, pandas stubs can include Unknown in the union.
    We cast here to the expected (Series | DataFrame) union to keep local
    variables fully-typed.
    """
    obj = cast(pd.Series | pd.DataFrame, df[col])
    if isinstance(obj, pd.DataFrame):
        raise ValueError(
            f"Expected column '{col}' to resolve to a Series, got DataFrame. "
            "This can happen if the input has duplicate column names."
        )
    return obj


def _pd_to_datetime(series: pd.Series) -> pd.Series:
    """Coerce a pandas Series into datetimes (UTC-naive)."""
    to_dt: Any = getattr(pd, "to_datetime")
    return cast(pd.Series, to_dt(series, errors="coerce"))


def _pd_to_numeric(series: pd.Series) -> pd.Series:
    to_num: Any = getattr(pd, "to_numeric")
    return cast(pd.Series, to_num(series, errors="coerce"))


def _series_map(series: pd.Series, func: Callable[[Any], Any]) -> pd.Series:
    map_fn: Any = getattr(series, "map")
    return cast(pd.Series, map_fn(func))


def _map_from_dict(local_mapper: dict[str, Any]) -> Callable[[Any], Any]:
    def _map(v: Any) -> Any:
        return local_mapper.get(str(v), np.nan)

    return _map


def _series_fillna(series: pd.Series, value: Any) -> pd.Series:
    fillna_fn: Any = getattr(series, "fillna")
    return cast(pd.Series, fillna_fn(value))


def _series_clip(series: pd.Series, *, lower: Any = None, upper: Any = None) -> pd.Series:
    clip_fn: Any = getattr(series, "clip")
    return cast(pd.Series, clip_fn(lower=lower, upper=upper))


def _series_astype(series: pd.Series, dtype: Any) -> pd.Series:
    astype_fn: Any = getattr(series, "astype")
    return cast(pd.Series, astype_fn(dtype))


def _series_shift(series: pd.Series, periods: int) -> pd.Series:
    shift_fn: Any = getattr(series, "shift")
    return cast(pd.Series, shift_fn(periods))


def _series_copy(series: pd.Series) -> pd.Series:
    copy_fn: Any = getattr(series, "copy")
    return cast(pd.Series, copy_fn())


def _series_to_dict(series: pd.Series) -> dict[str, Any]:
    """Convert a Series to a dict[str, Any] with stable typing under strict Pyright.

    Pandas stubs often surface dict[Unknown, Unknown] here; we normalize keys to str.
    """
    to_dict_fn: Any = getattr(series, "to_dict")
    raw_any: Any = to_dict_fn()
    if not isinstance(raw_any, dict):
        return {}

    raw = cast(dict[Any, Any], raw_any)
    out: dict[str, Any] = {}
    for k, v in raw.items():
        out[str(cast(object, k))] = v
    return out


def _series_get(series: pd.Series, key: Any, default: Any = None) -> Any:
    get_fn: Any = getattr(series, "get")
    return get_fn(key, default)


def _df_set_index(df: pd.DataFrame, key: str) -> pd.DataFrame:
    set_index_fn: Any = getattr(df, "set_index")
    return cast(pd.DataFrame, set_index_fn(key))


def _coerce_float(value: Any) -> float:
    if value is None:
        return float("nan")
    try:
        f = float(value)
    except (TypeError, ValueError):
        return float("nan")
    return f


def _series_rolling_mean(series: pd.Series, *, window: int, min_periods: int = 1) -> pd.Series:
    rolling_fn: Any = getattr(series, "rolling")
    roll_obj: Any = rolling_fn(window=window, min_periods=min_periods)
    mean_fn: Any = getattr(roll_obj, "mean")
    return cast(pd.Series, mean_fn())


def _series_expanding_mean(series: pd.Series, *, min_periods: int = 1) -> pd.Series:
    """Compute an expanding mean with stable typing under strict Pyright."""
    expanding_fn: Any = getattr(series, "expanding")
    exp_obj: Any = expanding_fn(min_periods=min_periods)
    mean_fn: Any = getattr(exp_obj, "mean")
    return cast(pd.Series, mean_fn())


def _df_copy(obj: Any) -> pd.DataFrame:
    copy_fn: Any = getattr(obj, "copy")
    return cast(pd.DataFrame, copy_fn())


def _df_fillna(obj: Any, value: Any) -> pd.DataFrame:
    fillna_fn: Any = getattr(obj, "fillna")
    return cast(pd.DataFrame, fillna_fn(value))


def _df_reset_index(obj: Any, *, drop: bool = True) -> pd.DataFrame:
    reset_fn: Any = getattr(obj, "reset_index")
    return cast(pd.DataFrame, reset_fn(drop=drop))


def _df_reindex(obj: Any, *, columns: list[str], fill_value: Any) -> pd.DataFrame:
    reindex_fn: Any = getattr(obj, "reindex")
    return cast(pd.DataFrame, reindex_fn(columns=columns, fill_value=fill_value))


def _series_reset_index(obj: Any, *, drop: bool = True) -> pd.Series:
    reset_fn: Any = getattr(obj, "reset_index")
    return cast(pd.Series, reset_fn(drop=drop))


def _series_to_str_list(series: pd.Series) -> list[str]:
    tolist_fn: Any = getattr(series, "tolist")
    raw_list = cast(list[Any], tolist_fn())
    return [str(cast(object, x)) for x in raw_list]


def _df_columns_to_str_list(df: pd.DataFrame) -> list[str]:
    cols_any = cast(list[Any], list(df.columns))
    return [str(cast(object, c)) for c in cols_any]


def _compute_rest_days(game_date: pd.Series, *, max_rest_days: int) -> pd.Series:
    """Compute bounded rest days between games.

    Uses getattr/Any to avoid strict pyright failures on pandas' overloaded stubs.
    """
    diff_fn: Any = getattr(game_date, "diff")
    deltas_any: Any = diff_fn()

    to_td: Any = getattr(pd, "to_timedelta")
    deltas_td_any: Any = to_td(deltas_any)

    dt_any: Any = getattr(deltas_td_any, "dt")
    days_any: Any = getattr(dt_any, "days")

    rest_days = cast(pd.Series, days_any)
    rest_days = _series_fillna(rest_days, 0)
    rest_days = _series_clip(rest_days, lower=0, upper=int(max_rest_days))
    rest_days = _series_astype(rest_days, "int64")
    return rest_days


def _minutes_to_float(v: Any) -> float:
    """Coerce NBA "MIN" values to float minutes.

    The NBA stats API sometimes returns minutes as a number (e.g., 34) and
    sometimes as an "MM:SS" string (e.g., "35:12").
    """
    if v is None:
        return float("nan")

    s = str(v).strip()
    if not s or s.lower() == "nan":
        return float("nan")

    if ":" in s:
        mm, ss = s.split(":", 1)
        try:
            return float(mm) + float(ss) / 60.0
        except (TypeError, ValueError):
            return float("nan")

    try:
        return float(s)
    except (TypeError, ValueError):
        return float("nan")


def _parse_matchup(matchup: str) -> tuple[int, str]:
    """Return (is_home, opponent_abbr).

    Examples:
      - "LAL vs. GSW" => (1, "GSW")
      - "LAL @ GSW"   => (0, "GSW")
    """
    m = str(matchup)
    tokens = m.split()
    opp = tokens[-1] if tokens else ""
    if "vs." in m or "vs" in m:
        return 1, opp
    if "@" in m:
        return 0, opp
    # Fallback: assume home if unknown
    return 1, opp


def clean_player_gamelog(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return _df_copy(df)

    out = _df_copy(df)

    # Standardize expected columns
    if "GAME_DATE" in out.columns:
        out["GAME_DATE"] = _pd_to_datetime(_require_series(out, "GAME_DATE"))
    elif "GAME_DATE_EST" in out.columns:
        out["GAME_DATE"] = _pd_to_datetime(_require_series(out, "GAME_DATE_EST"))
    else:
        raise ValueError(f"Unsupported playergamelog schema; columns={list(out.columns)}")

    if "MATCHUP" not in out.columns:
        raise ValueError(f"Expected MATCHUP column in playergamelog; columns={list(out.columns)}")

    if "PTS" not in out.columns:
        raise ValueError(f"Expected PTS column in playergamelog; columns={list(out.columns)}")

    if "MIN" not in out.columns:
        # Some seasons use 'MIN' as string; if absent, attempt 'MINUTES'
        if "MINUTES" in out.columns:
            out["MIN"] = out["MINUTES"]
        else:
            out["MIN"] = np.nan

    # Sort ascending by date to build lag/rolling features
    out = _df_reset_index(out.sort_values("GAME_DATE"), drop=True)

    # Home / opponent parse (avoid pandas apply() typing ambiguity under strict mode)
    matchup_vals: list[str] = _series_to_str_list(_require_series(out, "MATCHUP"))
    parsed = [_parse_matchup(m) for m in matchup_vals]
    is_home = [p[0] for p in parsed]
    opp_abbr = [p[1] for p in parsed]
    out["IS_HOME"] = pd.Series(is_home, index=out.index, dtype="int64")
    out["OPP_ABBR"] = pd.Series(opp_abbr, index=out.index, dtype="string")

    # Coerce numerics
    out["PTS"] = _pd_to_numeric(_require_series(out, "PTS"))
    out["MIN"] = _series_map(_require_series(out, "MIN"), _minutes_to_float)

    # Best-effort: coerce commonly-used stat columns if present.
    for c in ("FGA", "FG3A", "FTA", "TOV", "AST", "REB"):
        if c in out.columns:
            out[c] = _pd_to_numeric(_require_series(out, c))

    return out


def build_training_frame(
    game_log: pd.DataFrame,
    *,
    cfg: FeatureBuildConfig | None = None,
    opponent_strength: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.Series, dict[str, Any]]:
    cfg = cfg or FeatureBuildConfig()

    df = clean_player_gamelog(game_log)
    if df.empty:
        return pd.DataFrame(), pd.Series(dtype=float), {"n_games": 0}

    # Rest days (cap off-season gaps so multi-season history does not dominate the signal).
    df["REST_DAYS"] = _compute_rest_days(
        _require_series(df, "GAME_DATE"), max_rest_days=int(cfg.max_rest_days)
    )

    # Ensure required stat columns exist.
    for c in cfg.stat_columns:
        if c not in df.columns:
            df[c] = np.nan

    # Usage proxy is a stable, low-effort signal for scoring opportunity.
    if "FGA" in df.columns and "FTA" in df.columns:
        fga = _series_fillna(_require_series(df, "FGA"), 0.0)
        fta = _series_fillna(_require_series(df, "FTA"), 0.0)
        df["USG_PROXY"] = fga + 0.44 * fta
    else:
        df["USG_PROXY"] = np.nan

    stat_cols: list[str] = list(cfg.stat_columns)
    usg_proxy = _require_series(df, "USG_PROXY")
    if bool(np.asarray(usg_proxy.notna()).any()):
        stat_cols.append("USG_PROXY")

    if cfg.include_points_per_min:
        pts = _require_series(df, "PTS")
        mins = _require_series(df, "MIN")
        mins_safe = _series_fillna(mins, 0.0)
        denom = np.asarray(mins_safe, dtype=float)
        numer = np.asarray(pts, dtype=float)
        ppm = np.where(denom > 0.0, numer / denom, np.nan)
        df["PTS_PER_MIN"] = pd.Series(ppm, index=df.index, dtype="float64")
        stat_cols.append("PTS_PER_MIN")

    feature_cols: list[str] = ["IS_HOME", "REST_DAYS"]

    # Availability/minutes stability indicators.
    if cfg.include_availability:
        mins = _require_series(df, "MIN")
        played_bool = cast(pd.Series, (_series_fillna(mins, 0.0) > 0.0))
        played = _series_astype(played_bool, "int64")
        df["PLAYED"] = played
        df["PLAYED_LAG1"] = _series_shift(played, 1)
        df["PLAYED_ROLL5"] = _series_rolling_mean(_series_shift(played, 1), window=5, min_periods=1)
        df["PLAYED_ROLL10"] = _series_rolling_mean(
            _series_shift(played, 1), window=10, min_periods=1
        )
        # Minutes trend: recent vs longer window. (Uses lagged mins to prevent leakage.)
        min_lag1 = _series_shift(mins, 1)
        df["MIN_TREND_5v10"] = _series_rolling_mean(
            min_lag1, window=5, min_periods=1
        ) - _series_rolling_mean(min_lag1, window=10, min_periods=1)
        feature_cols.extend(["PLAYED_LAG1", "PLAYED_ROLL5", "PLAYED_ROLL10", "MIN_TREND_5v10"])

    # Opponent strength proxy features (season-to-date), when provided.
    if cfg.include_opp_strength and opponent_strength is not None and not opponent_strength.empty:
        # Expect opponent_strength to have an OPP_ABBR column and one or more numeric metric columns.
        if "OPP_ABBR" in opponent_strength.columns:
            strength = _df_set_index(opponent_strength, "OPP_ABBR")
            for col in _df_columns_to_str_list(strength):
                if col.upper() == "OPP_ABBR":
                    continue
                feat_name = f"OPP_STRENGTH_{col.upper()}"
                # Map current game's opponent -> season-to-date proxy metric.
                mapper = _series_to_dict(_require_series(strength, col))
                map_func = _map_from_dict(mapper)
                df[feat_name] = _series_map(_require_series(df, "OPP_ABBR"), map_func)
                feature_cols.append(feat_name)
    for c in stat_cols:
        base = _require_series(df, c)
        shifted = _series_shift(base, 1)
        df[f"{c}_LAG1"] = shifted
        feature_cols.append(f"{c}_LAG1")
        for w in cfg.rolling_windows:
            df[f"{c}_ROLL{w}"] = _series_rolling_mean(shifted, window=w, min_periods=1)
            feature_cols.append(f"{c}_ROLL{w}")

        # Lifetime (expanding) mean of lagged values.
        if cfg.include_lifetime:
            df[f"{c}_LIFE_MEAN"] = _series_expanding_mean(shifted, min_periods=1)
            feature_cols.append(f"{c}_LIFE_MEAN")
    # Ensure column list is ordered and unique to avoid duplicate labels (fixes XGBoost pandas handling).
    seen: set[str] = set()
    unique_feature_cols: list[str] = []
    for col in feature_cols:
        if col not in seen:
            seen.add(col)
            unique_feature_cols.append(col)
    feature_cols = unique_feature_cols

    x_df = _df_copy(df.loc[:, feature_cols])
    x_df = _df_fillna(x_df, 0.0)
    target = _series_copy(_require_series(df, "PTS"))

    if cfg.include_opponent:
        get_dummies: Any = getattr(pd, "get_dummies")
        opp = cast(
            pd.DataFrame,
            get_dummies(_require_series(df, "OPP_ABBR"), prefix="OPP", dtype=np.float32),
        )
        x_df = pd.concat([x_df, opp], axis=1)

    # Drop first row (no lag) and any rows with missing target
    pts_lag1 = _require_series(df, "PTS_LAG1")
    mask = target.notna() & pts_lag1.notna()

    x_df = _df_reset_index(x_df.loc[mask], drop=True)
    target = _series_reset_index(target.loc[mask], drop=True)

    meta: dict[str, Any] = {
        "n_games_raw": int(len(df)),
        "n_rows": int(len(x_df)),
        "feature_columns": _df_columns_to_str_list(x_df),
        "cfg": {
            "rolling_windows": list(cfg.rolling_windows),
            "include_opponent": cfg.include_opponent,
            "include_opp_strength": cfg.include_opp_strength,
            "include_availability": cfg.include_availability,
            "include_lifetime": cfg.include_lifetime,
            "include_points_per_min": cfg.include_points_per_min,
            "stat_columns": list(cfg.stat_columns),
            "max_rest_days": int(cfg.max_rest_days),
        },
    }
    return x_df, target, meta


def build_next_game_features(
    game_log: pd.DataFrame,
    *,
    feature_columns: list[str],
    next_home: int,
    next_opp: str = "",
    next_rest_days: int | None = None,
    cfg: FeatureBuildConfig | None = None,
    opponent_strength: pd.DataFrame | None = None,
) -> pd.DataFrame:
    cfg = cfg or FeatureBuildConfig()

    df = clean_player_gamelog(game_log)
    if df.empty:
        raise ValueError("No game logs available to build features.")

    df["REST_DAYS"] = _compute_rest_days(
        _require_series(df, "GAME_DATE"), max_rest_days=int(cfg.max_rest_days)
    )

    for c in cfg.stat_columns:
        if c not in df.columns:
            df[c] = np.nan

    if "FGA" in df.columns and "FTA" in df.columns:
        fga = _series_fillna(_require_series(df, "FGA"), 0.0)
        fta = _series_fillna(_require_series(df, "FTA"), 0.0)
        df["USG_PROXY"] = fga + 0.44 * fta
    else:
        df["USG_PROXY"] = np.nan

    stat_cols: list[str] = list(cfg.stat_columns)
    usg_proxy = _require_series(df, "USG_PROXY")
    if bool(np.asarray(usg_proxy.notna()).any()):
        stat_cols.append("USG_PROXY")

    # Points-per-minute (PPM) is a direct scoring efficiency proxy.
    # For next-game inference, we compute it from the historical log and then
    # derive lagged/rolling/lifetime values the same way as training.
    if cfg.include_points_per_min:
        pts = _require_series(df, "PTS")
        mins = _require_series(df, "MIN")
        mins_safe = _series_fillna(mins, 0.0)
        denom = np.asarray(mins_safe, dtype=float)
        numer = np.asarray(pts, dtype=float)
        ppm = np.where(denom > 0.0, numer / denom, np.nan)
        df["PTS_PER_MIN"] = pd.Series(ppm, index=df.index, dtype="float64")
        stat_cols.append("PTS_PER_MIN")

    feature_cols: list[str] = ["IS_HOME", "REST_DAYS"]

    if cfg.include_availability:
        mins = _require_series(df, "MIN")
        played_bool = cast(pd.Series, (_series_fillna(mins, 0.0) > 0.0))
        played = _series_astype(played_bool, "int64")
        df["PLAYED"] = played
        df["PLAYED_LAG1"] = _series_shift(played, 1)
        df["PLAYED_ROLL5"] = _series_rolling_mean(_series_shift(played, 1), window=5, min_periods=1)
        df["PLAYED_ROLL10"] = _series_rolling_mean(
            _series_shift(played, 1), window=10, min_periods=1
        )
        min_lag1 = _series_shift(mins, 1)
        df["MIN_TREND_5v10"] = _series_rolling_mean(
            min_lag1, window=5, min_periods=1
        ) - _series_rolling_mean(min_lag1, window=10, min_periods=1)
        feature_cols.extend(["PLAYED_LAG1", "PLAYED_ROLL5", "PLAYED_ROLL10", "MIN_TREND_5v10"])

    # For next-game features, opponent-strength metrics must be computed against the *next* opponent.
    # We still include the feature names here so the column set is stable; values are filled on `last`.
    strength: pd.DataFrame | None = None
    if cfg.include_opp_strength and opponent_strength is not None and not opponent_strength.empty:
        if "OPP_ABBR" in opponent_strength.columns:
            strength = _df_set_index(opponent_strength, "OPP_ABBR")
            for col in _df_columns_to_str_list(strength):
                if col.upper() == "OPP_ABBR":
                    continue
                feat_name = f"OPP_STRENGTH_{col.upper()}"
                feature_cols.append(feat_name)
    for c in stat_cols:
        base = _require_series(df, c)
        shifted = _series_shift(base, 1)
        df[f"{c}_LAG1"] = shifted
        feature_cols.append(f"{c}_LAG1")
        for w in cfg.rolling_windows:
            df[f"{c}_ROLL{w}"] = _series_rolling_mean(shifted, window=w, min_periods=1)
            feature_cols.append(f"{c}_ROLL{w}")

        if cfg.include_lifetime:
            df[f"{c}_LIFE_MEAN"] = _series_expanding_mean(shifted, min_periods=1)
            feature_cols.append(f"{c}_LIFE_MEAN")

    # Use last row to form next-game input (i.e., latest known stats)
    last = _df_copy(df.iloc[-1:])
    last["IS_HOME"] = int(next_home)
    last["OPP_ABBR"] = str(next_opp).strip().upper() if next_opp else ""
    if next_rest_days is not None:
        last["REST_DAYS"] = int(next_rest_days)

    if strength is not None:
        opp_series = _require_series(last, "OPP_ABBR")
        opp_key = str(cast(object, opp_series.iloc[0])) if not opp_series.empty else ""
        for col in _df_columns_to_str_list(strength):
            if col.upper() == "OPP_ABBR":
                continue
            feat_name = f"OPP_STRENGTH_{col.upper()}"
            series = _require_series(strength, col)
            value_any = _series_get(series, opp_key, np.nan)
            last[feat_name] = _coerce_float(value_any)

    x_next = _df_copy(last.loc[:, feature_cols])
    x_next = _df_fillna(x_next, 0.0)

    if cfg.include_opponent:
        get_dummies: Any = getattr(pd, "get_dummies")
        opp = cast(
            pd.DataFrame,
            get_dummies(_require_series(last, "OPP_ABBR"), prefix="OPP", dtype=np.float32),
        )
        x_next = pd.concat([x_next, opp], axis=1)

    # Align to training feature columns (add missing, drop extras)
    x_next = _df_reindex(x_next, columns=feature_columns, fill_value=0.0)
    return _df_reset_index(x_next, drop=True)
