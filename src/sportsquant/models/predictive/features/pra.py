"""PRA (Points + Rebounds + Assists) feature builder.

This module builds a leakage-safe per-player, per-game feature table used for:
- baseline probabilistic evaluation (Normal(mu, sigma))
- component models (minutes + per-minute rates)
- Monte Carlo PRA simulation

Type checking: pandas' typing stubs are frequently partially-unknown under strict
Pyright. We use small, localized `cast(Any, ...)` bridges around those APIs.
"""

from __future__ import annotations

# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
# pylint: disable=too-many-instance-attributes,too-many-locals,too-many-statements,invalid-name

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, cast

import numpy as np
import pandas as pd
from pandas import DataFrame, Index, Series

from sportsquant.util.validation import PRA_CONTEXT_FEATURES, PRA_LABEL_COLUMNS


@dataclass(frozen=True)
class PRAFeatureConfig:
    # Identifiers
    season_col: str = "season"
    game_id_col: str = "game_id"
    date_col: str = "game_date"
    player_id_col: str = "player_id"
    player_name_col: str = "player_name"
    team_col: str = "team_abbr"
    opp_col: str = "opp_team_abbr"
    is_home_col: str = "is_home"

    # Raw stats
    minutes_col: str = "minutes"
    points_col: str = "points"
    rebounds_col: str = "rebounds"
    assists_col: str = "assists"


# -----------------
# Pandas-safe helpers
# -----------------


def _read_parquet_df(path: Path) -> DataFrame:
    pd_any = cast(Any, pd)
    obj = pd_any.read_parquet(path)
    if not isinstance(obj, DataFrame):
        raise TypeError(f"Expected pandas DataFrame from read_parquet; got {type(obj)!r}")
    return obj


def _as_series(obj: Any) -> Series:
    if isinstance(obj, Series):
        return obj
    if isinstance(obj, DataFrame):
        return cast(Series, obj.iloc[:, 0])
    return cast(Series, obj)


def _rolling_mean_lagged(values: Series, window: int) -> Series:
    v = cast(Any, values)
    lag1 = cast(Series, v.shift(1))
    roll = cast(Any, lag1).rolling(window=window, min_periods=1)
    return cast(Series, roll.mean())


def _rolling_std_lagged(values: Series, window: int) -> Series:
    v = cast(Any, values)
    lag1 = cast(Series, v.shift(1))
    roll = cast(Any, lag1).rolling(window=window, min_periods=1)
    return cast(Series, roll.std(ddof=0))


def _expanding_mean_lagged(values: Series) -> Series:
    v = cast(Any, values)
    lag1 = cast(Series, v.shift(1))
    exp = cast(Any, lag1).expanding(min_periods=1)
    return cast(Series, exp.mean())


# Typed transform helpers (avoid lambdas to satisfy Pyright strictness)


def _make_roll_mean(window: int) -> Callable[[Series], Series]:
    def _fn(s: Series) -> Series:
        return _rolling_mean_lagged(_as_series(s), window)

    return _fn


def _make_roll_std(window: int) -> Callable[[Series], Series]:
    def _fn(s: Series) -> Series:
        return _rolling_std_lagged(_as_series(s), window)

    return _fn


def _make_expand_mean() -> Callable[[Series], Series]:
    def _fn(s: Series) -> Series:
        return _expanding_mean_lagged(_as_series(s))

    return _fn


_ROLL_MEAN_5 = _make_roll_mean(5)
_ROLL_MEAN_10 = _make_roll_mean(10)
_ROLL_STD_10 = _make_roll_std(10)
_EXPAND_MEAN = _make_expand_mean()


def _safe_rate(numer: Series, denom: Series, *, fill_value: float = 0.0) -> Series:
    """Compute numer/denom safely (avoid div-by-zero).

    - Returns float64 Series
    - Non-finite results are replaced with fill_value
    """

    n_arr = np.asarray(numer, dtype=float)
    d_arr = np.asarray(denom, dtype=float)

    out_arr = np.full_like(n_arr, np.nan, dtype=float)
    # Avoid exact float equality checks (Sonar) and guard against tiny denominators.
    denom_nonzero = ~np.isclose(d_arr, 0.0, atol=1e-12)
    np.divide(n_arr, d_arr, out=out_arr, where=denom_nonzero)

    out_arr = np.where(np.isfinite(out_arr), out_arr, float(fill_value)).astype(
        "float64", copy=False
    )
    numer_any = cast(Any, numer)
    idx = cast(Index, numer_any.index)
    return Series(out_arr, index=idx, dtype="float64")


def _add_opponent_strength(
    df: DataFrame,
    cfg: PRAFeatureConfig,
    season_team_strength: Mapping[str, Mapping[str, float]] | None,
) -> tuple[DataFrame, list[str]]:
    """Merge opponent strength features on opponent team abbreviation.

    season_team_strength maps: team_abbr -> {feature_name -> value}
    Feature names should already be prefixed with 'opp_' (recommended).
    """

    if not season_team_strength:
        return df, []

    strength_dict: dict[str, dict[str, float]] = {
        str(k): dict(v) for k, v in season_team_strength.items()
    }
    strength_df = pd.DataFrame(strength_dict).T.reset_index().rename(columns={"index": cfg.opp_col})

    strength_cols: list[str] = []
    for raw_col in cast(Any, strength_df.columns):
        col_str = str(raw_col)
        if col_str == cfg.opp_col:
            continue
        strength_cols.append(col_str)
    if not strength_cols:
        return df, []

    out = df.merge(strength_df, how="left", on=cfg.opp_col)
    return out, strength_cols


def _coerce_numeric(df: DataFrame, col: str) -> Series:
    pd_any = cast(Any, pd)
    return cast(Series, pd_any.to_numeric(_as_series(df[col]), errors="coerce"))


def _fill_by_season_then_global(df: DataFrame, cfg: PRAFeatureConfig, cols: list[str]) -> DataFrame:
    """Impute: rolling -> season mean -> global mean."""

    if not cols:
        return df

    df_any = cast(Any, df)
    for c in cols:
        s = cast(Series, df[c])
        # Season mean
        season_mean = cast(Series, df_any.groupby(cfg.season_col, sort=False)[c].transform("mean"))
        s = cast(Series, cast(Any, s).fillna(season_mean))
        # Global mean
        global_mean = float(np.nanmean(np.asarray(s, dtype=float)))
        if not np.isfinite(global_mean):
            global_mean = 0.0
        df[c] = cast(Series, cast(Any, s).fillna(global_mean))

    return df


# ---------------
# Public builder
# ---------------


def build_pra_features(
    player_game_log_parquet: Path,
    *,
    cfg: PRAFeatureConfig = PRAFeatureConfig(),
    season_team_strength: Mapping[str, Mapping[str, float]] | None = None,
) -> DataFrame:
    """Build leakage-safe PRA features from curated/player_games.parquet."""

    df = _read_parquet_df(player_game_log_parquet)

    required = [
        cfg.season_col,
        cfg.game_id_col,
        cfg.date_col,
        cfg.player_id_col,
        cfg.player_name_col,
        cfg.team_col,
        cfg.opp_col,
        cfg.is_home_col,
        cfg.minutes_col,
        cfg.points_col,
        cfg.rebounds_col,
        cfg.assists_col,
    ]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    pd_any = cast(Any, pd)

    # Normalize date and sort.
    df[cfg.date_col] = cast(
        Series, pd_any.to_datetime(_as_series(df[cfg.date_col]), errors="coerce")
    )
    df = df.sort_values(
        [cfg.player_id_col, cfg.date_col, cfg.game_id_col], ascending=[True, True, True]
    )

    # Labels (targets)
    y_minutes = _coerce_numeric(df, cfg.minutes_col)
    y_points = _coerce_numeric(df, cfg.points_col)
    y_reb = _coerce_numeric(df, cfg.rebounds_col)
    y_ast = _coerce_numeric(df, cfg.assists_col)

    df["y_minutes"] = y_minutes
    df["is_dnp"] = (df["y_minutes"] <= 0).astype("int8")
    df["y_points"] = y_points
    df["y_rebounds"] = y_reb
    df["y_assists"] = y_ast

    y_pra = (
        np.asarray(y_points, dtype=float)
        + np.asarray(y_reb, dtype=float)
        + np.asarray(y_ast, dtype=float)
    ).astype("float64", copy=False)
    df_index = cast(Index, cast(Any, df).index)
    df["y_pra"] = Series(y_pra, index=df_index, dtype="float64")

    # Per-minute rates
    df["y_ppm"] = _safe_rate(df["y_points"], df["y_minutes"], fill_value=0.0)  # type: ignore[arg-type]
    df["y_rpm"] = _safe_rate(df["y_rebounds"], df["y_minutes"], fill_value=0.0)  # type: ignore[arg-type]
    df["y_apm"] = _safe_rate(df["y_assists"], df["y_minutes"], fill_value=0.0)  # type: ignore[arg-type]

    # Baseline-C helper: PRA per minute season-to-date mean (lagged)
    df["pra_per_min"] = _safe_rate(df["y_pra"], df["y_minutes"], fill_value=0.0)  # type: ignore[arg-type]

    # Group-wise feature engineering.
    df_any = cast(Any, df)
    gb = df_any.groupby(cfg.player_id_col, sort=False)

    # Minutes features
    df["min_last_5_mean"] = cast(Series, gb["y_minutes"].transform(_ROLL_MEAN_5))
    df["min_last_10_mean"] = cast(Series, gb["y_minutes"].transform(_ROLL_MEAN_10))
    df["min_last_10_std"] = cast(Series, gb["y_minutes"].transform(_ROLL_STD_10))
    df["min_szn_mean_to_date"] = cast(Series, gb["y_minutes"].transform(_EXPAND_MEAN))
    df["min_games_to_date"] = cast(Series, gb.cumcount())

    df["min_trend_10"] = np.asarray(cast(Series, df["min_last_5_mean"]), dtype=float) - np.asarray(
        cast(Series, df["min_last_10_mean"]), dtype=float
    )

    # PRA history (for sigma + debugging)
    df["pra_last_10_mean"] = cast(Series, gb["y_pra"].transform(_ROLL_MEAN_10))
    df["pra_last_10_std"] = cast(Series, gb["y_pra"].transform(_ROLL_STD_10))

    # Baseline helper (lagged season mean of PRA/min)
    df["pra_per_min_szn_mean"] = cast(Series, gb["pra_per_min"].transform(_EXPAND_MEAN))

    # Rate features (ppm/rpm/apm)
    def _rate_feats(prefix: str, col: str) -> None:
        df[f"{prefix}_last_5_mean"] = cast(Series, gb[col].transform(_ROLL_MEAN_5))
        df[f"{prefix}_last_10_mean"] = cast(Series, gb[col].transform(_ROLL_MEAN_10))
        df[f"{prefix}_last_10_std"] = cast(Series, gb[col].transform(_ROLL_STD_10))
        df[f"{prefix}_szn_mean_to_date"] = cast(Series, gb[col].transform(_EXPAND_MEAN))

    _rate_feats("ppm", "y_ppm")
    _rate_feats("rpm", "y_rpm")
    _rate_feats("apm", "y_apm")

    # === Phase 4: Advanced Features ===

    # Rest days (days since last game) - lagged
    df["rest_days"] = cast(
        Series,
        gb[cfg.date_col].transform(lambda s: cast(Series, cast(Any, s).shift(1).diff()).dt.days),
    )
    df["rest_days"] = df["rest_days"].clip(lower=0, upper=14).fillna(2.0)  # Default 2 days rest

    # Back-to-back indicator (0 or 1 day rest)
    df["is_back_to_back"] = (df["rest_days"] <= 1).astype("int8")

    # 3-in-4 nights indicator (3 games in last 4 days)
    # Count games where date difference <= N days (leakage-safe: only looks backward)
    def count_games_last_n_days(group: Any, n_days: int) -> Series:
        """Count games in last N days for each row."""
        dates = cast(Series, group[cfg.date_col])
        result = pd.Series(0.0, index=group.index)
        for idx in range(len(dates)):
            if idx == 0:
                result.iloc[idx] = 0.0
            else:
                lookback_date = dates.iloc[idx] - pd.Timedelta(days=n_days)
                result.iloc[idx] = float(
                    (
                        (dates.iloc[:idx] >= lookback_date) & (dates.iloc[:idx] < dates.iloc[idx])
                    ).sum()
                )
        return result

    df["games_last_4_days"] = cast(
        Series,
        gb.apply(lambda g: count_games_last_n_days(g, 4), include_groups=False).reset_index(
            level=0, drop=True
        ),
    )
    df["is_3_in_4"] = (df["games_last_4_days"] >= 3).astype("int8")

    # Schedule context: games in last 7 days
    df["games_last_7_days"] = cast(
        Series,
        gb.apply(lambda g: count_games_last_n_days(g, 7), include_groups=False).reset_index(
            level=0, drop=True
        ),
    )

    # Home/away rolling splits (5-game windows)
    def _home_away_splits() -> None:
        # Minutes splits
        home_mask = df[cfg.is_home_col] == 1
        df["min_home_last_5_mean"] = cast(
            Series,
            gb["y_minutes"].transform(
                lambda s: (
                    cast(Any, cast(Any, s).shift(1).where(home_mask))
                    .rolling(5, min_periods=1)
                    .mean()
                )
            ),
        )
        df["min_away_last_5_mean"] = cast(
            Series,
            gb["y_minutes"].transform(
                lambda s: (
                    cast(Any, cast(Any, s).shift(1).where(~home_mask))
                    .rolling(5, min_periods=1)
                    .mean()
                )
            ),
        )

        # PRA splits
        df["pra_home_last_5_mean"] = cast(
            Series,
            gb["y_pra"].transform(
                lambda s: (
                    cast(Any, cast(Any, s).shift(1).where(home_mask))
                    .rolling(5, min_periods=1)
                    .mean()
                )
            ),
        )
        df["pra_away_last_5_mean"] = cast(
            Series,
            gb["y_pra"].transform(
                lambda s: (
                    cast(Any, cast(Any, s).shift(1).where(~home_mask))
                    .rolling(5, min_periods=1)
                    .mean()
                )
            ),
        )

    _home_away_splits()

    # Player form/momentum: variance stability
    df["pra_variance_last_10"] = cast(
        Series,
        gb["y_pra"].transform(
            lambda s: cast(Any, cast(Any, s).shift(1)).rolling(10, min_periods=3).var()
        ),
    )
    df["is_consistent"] = (df["pra_variance_last_10"] < df["pra_variance_last_10"].median()).astype(
        "int8"
    )

    # Win streak effect (approximate: positive momentum from high PRA games)
    pra_shift = cast(Series, cast(Any, df["y_pra"]).shift(1))
    above_mean = pra_shift > df["pra_last_10_mean"]
    streak_groups = (~above_mean).cumsum()
    df["high_pra_streak"] = (
        above_mean.astype("int32")
        .groupby(streak_groups)
        .cumsum()
        .astype("int8")
        .clip(upper=10)
        .fillna(0)
    )

    # Opponent context
    df, opp_cols = _add_opponent_strength(df, cfg, season_team_strength)

    # Floors (std-dev)
    df["has_min_last_10"] = df["min_last_10_std"].notna().astype("int8")
    df["min_last_10_std"] = (
        df["min_last_10_std"].fillna(df["min_last_10_std"].median()).clip(lower=1.0)
    )
    df["has_pra_last_10"] = df["pra_last_10_std"].notna().astype("int8")
    df["pra_last_10_std"] = (
        df["pra_last_10_std"].fillna(df["pra_last_10_std"].median()).clip(lower=4.0)
    )
    # Output schema
    id_cols = [
        cfg.season_col,
        cfg.game_id_col,
        cfg.date_col,
        cfg.player_id_col,
        cfg.player_name_col,
        cfg.team_col,
        cfg.opp_col,
        cfg.is_home_col,
    ]

    label_cols = [
        *PRA_LABEL_COLUMNS,
        "y_ppm",
        "y_rpm",
        "y_apm",
    ]

    feature_cols = [
        # Minutes
        "min_last_5_mean",
        "min_last_10_mean",
        "min_last_10_std",
        "min_szn_mean_to_date",
        "min_games_to_date",
        "min_trend_10",
        # Rates
        "ppm_last_5_mean",
        "ppm_last_10_mean",
        "ppm_last_10_std",
        "ppm_szn_mean_to_date",
        "rpm_last_5_mean",
        "rpm_last_10_mean",
        "rpm_last_10_std",
        "rpm_szn_mean_to_date",
        "apm_last_5_mean",
        "apm_last_10_mean",
        "apm_last_10_std",
        "apm_szn_mean_to_date",
        # PRA context
        "pra_last_10_mean",
        "pra_last_10_std",
        "pra_per_min_szn_mean",
        # Phase 4: Rest/Home/Away/Form
        *PRA_CONTEXT_FEATURES,
        # Data quality indicators (early games with limited history)
        "has_min_last_10",
        "has_pra_last_10",
    ]

    # Opponent columns (already merged)
    feature_cols.extend(opp_cols)

    # Coerce numeric feature cols
    numeric_cols = [*label_cols, *feature_cols]
    for c in numeric_cols:
        df[c] = cast(Series, pd_any.to_numeric(_as_series(df[c]), errors="coerce"))

    # Impute numeric features with season mean then global mean
    df = _fill_by_season_then_global(df, cfg, feature_cols)

    # Final output
    subset = cast(DataFrame, df[id_cols + label_cols + feature_cols])
    out = cast(DataFrame, cast(Any, subset).copy())
    return out


def merge_team_context_data(pra_df: pd.DataFrame, season: int) -> pd.DataFrame:
    # Load team data from the parquet files
    games_path = Path(f"sportsquant/data/sources/team_games_{season}.parquet")
    season_path = Path(f"sportsquant/data/sources/team_season_{season}.parquet")
    team_games_df = _read_parquet_df(games_path)
    team_season_df = _read_parquet_df(season_path)

    # Merge team context data into the PRA dataset
    merged_df = pra_df.merge(team_games_df, on="team_id", how="left")
    merged_df = merged_df.merge(team_season_df, on="team_id", how="left")

    # Return the updated PRA dataset with the team context data
    return merged_df
