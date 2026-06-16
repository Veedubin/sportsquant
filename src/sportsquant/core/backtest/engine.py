"""
Backtest Module - PRA Strategy Backtesting

Adapted from sports_analytics.betting.backtest
Changes:
- Replaced sports_analytics imports with sportsquant imports
- Removed Airflow dependencies for direct function calls

This module provides backtesting for player prop betting strategies
using historical lines and simulated projections.
"""

from __future__ import annotations

# pylint: disable=too-many-instance-attributes,too-many-locals,too-many-return-statements,broad-exception-caught,duplicate-code,line-too-long,too-many-statements

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, cast

import numpy as np
import pandas as pd
from pandas import DataFrame, Series

from sportsquant.core.betting.engine import BetDecision, decide_over_under
from sportsquant.core.betting.metrics import calculate_performance_metrics
from sportsquant.core.betting.odds import Odds

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PraBacktestConfig:
    """Configuration for PRA backtesting.

    Attributes:
        league: Sports league (e.g., 'NBA').
        season: Season identifier (e.g., '2024-25').
        cache_root: Path to cache directory.
        lines_csv: Path to lines CSV file.
        snapshot_id: Optional snapshot identifier.
        default_american_over: Default American odds for over.
        default_american_under: Default American odds for under.
        col_player_id: Column name for player ID.
        col_game_date: Column name for game date.
        col_line: Column name for betting line.
        col_game_id: Optional column name for game ID.
        col_odds_over: Column name for over odds.
        col_odds_under: Column name for under odds.
        n_sims: Number of simulations.
        random_state: Random seed for reproducibility.
    """

    league: str
    season: str
    cache_root: Path
    lines_csv: Path
    snapshot_id: Optional[str] = None
    default_american_over: int = -110
    default_american_under: int = -110
    col_player_id: str = "player_id"
    col_game_date: str = "game_date"
    col_line: str = "line"
    col_game_id: Optional[str] = "game_id"
    col_odds_over: str = "odds_over"
    col_odds_under: str = "odds_under"
    n_sims: int = 5000
    random_state: int = 1337


def _payout_profit_per_1(d: float) -> float:
    """Net profit per $1 staked for a win at decimal odds d."""
    return float(d - 1.0)


def _is_missing(value: object) -> bool:
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _coerce_series(obj: Any) -> Series:
    if isinstance(obj, Series):
        return obj
    if isinstance(obj, DataFrame):
        if obj.shape[1] == 1:
            return obj.iloc[:, 0]
        raise ValueError("expected single-column DataFrame for coercion")
    return Series(obj)


def _normalize_date(value: Any) -> str | Any:
    if _is_missing(value):
        return pd.NA
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    if isinstance(value, (pd.Timedelta, pd.Period)):
        try:
            return str(value)
        except (TypeError, ValueError):
            return pd.NA
    if isinstance(value, str):
        return _normalize_date_str(value)
    if isinstance(value, (int, float)):
        return _normalize_date_numeric(value)
    return pd.NA


def _normalize_date_str(value: str) -> str | Any:
    text = value.strip()
    if not text:
        return pd.NA
    try:
        parsed = pd.to_datetime(text, errors="coerce")
    except (TypeError, ValueError):
        return pd.NA
    if pd.isna(parsed):
        return pd.NA
    return parsed.date().isoformat()


def _normalize_date_numeric(value: int | float) -> str | Any:
    try:
        parsed = pd.to_datetime(value, errors="coerce")
    except (TypeError, ValueError):
        return pd.NA
    if pd.isna(parsed):
        return pd.NA
    return parsed.date().isoformat()


def _to_float_series(obj: Any) -> Series:
    """Coerce a Series to float64 with NaNs for non-numeric values."""
    series = _coerce_series(obj)
    floats: list[float] = []
    for value in series:
        if _is_missing(value):
            floats.append(float("nan"))
            continue
        try:
            floats.append(float(value))
        except (TypeError, ValueError):
            floats.append(float("nan"))
    return Series(floats, index=series.index, dtype="float64")


def _to_int_series(obj: Any, *, dtype: str = "int64", fill: int = 0) -> Series:
    """Coerce a Series to integer dtype via numeric conversion, filling NaNs."""
    float_series = _to_float_series(obj)
    ints: list[int] = []
    for value in float_series:
        if _is_missing(value):
            ints.append(fill)
        else:
            ints.append(int(value))
    return Series(ints, index=float_series.index, dtype=dtype)


def _to_string_date_series(obj: Any) -> Series:
    """Coerce a Series to a YYYY-MM-DD string date (nullable string dtype)."""
    series = _coerce_series(obj)
    normalized: list[str | Any] = [_normalize_date(val) for val in series]
    return Series(normalized, index=series.index, dtype="string")


def _to_join_keys(lines: DataFrame, cfg: PraBacktestConfig) -> DataFrame:
    """Build normalized join keys from a lines dataframe."""
    player_id_s = lines[cfg.col_player_id]
    game_date_s = lines[cfg.col_game_date]
    line_s = lines[cfg.col_line]

    return DataFrame(
        {
            "_player_id": _to_int_series(player_id_s, dtype="Int64"),
            "_game_date": _to_string_date_series(game_date_s),
            "line": _to_float_series(line_s),
        }
    )


def _attach_odds_column(
    sim_df: DataFrame,
    lines: DataFrame,
    cfg: PraBacktestConfig,
    *,
    side: str,
) -> DataFrame:
    """Attach odds column (over/under) from the lines CSV if present."""
    if side not in {"over", "under"}:
        raise ValueError("side must be 'over' or 'under'")

    col = cfg.col_odds_over if side == "over" else cfg.col_odds_under
    if col not in lines.columns:
        return sim_df

    keys = _to_join_keys(lines, cfg)
    odds = _to_float_series(lines[col])
    tmp = keys.assign(**{f"odds_{side}": odds})

    out = sim_df.merge(
        tmp,
        on=["_player_id", "_game_date", "line"],
        how="left",
        suffixes=("", "_csv"),
    )

    csv_col = f"odds_{side}_csv"
    merged_col = f"odds_{side}"
    if csv_col in out.columns:
        base_series = (
            _to_float_series(out[merged_col])
            if merged_col in out.columns
            else Series(index=out.index, dtype="float64")
        )
        csv_series = _to_float_series(out[csv_col])
        out[merged_col] = csv_series.fillna(base_series)
        out = out.drop(columns=[csv_col])
    return out


def _build_stat_over_columns(sim_df: DataFrame) -> None:
    """Build y_*_over columns for each stat market."""
    stat_markets = ["pra", "fg3m", "tov", "stl", "blk"]
    line_f = _to_float_series(sim_df["line"])
    for stat in stat_markets:
        target_col = f"y_{stat}" if stat != "pra" else "y_pra"
        if target_col not in sim_df.columns:
            continue
        y_stat_f = _to_float_series(sim_df[target_col])
        sim_df[f"y_{stat}_over"] = (y_stat_f > line_f).fillna(False).astype("int64")


def _determine_y_over_column(sim_df: DataFrame) -> str:
    """Determine which y_over column to use based on available columns."""
    if "y_pra" in sim_df.columns:
        return "y_pra_over"
    if "y_fg3m" in sim_df.columns:
        return "y_fg3m_over"
    if "y_tov" in sim_df.columns:
        return "y_tov_over"
    if "y_stl" in sim_df.columns:
        return "y_stl_over"
    if "y_blk" in sim_df.columns:
        return "y_blk_over"
    return ""


def _convert_columns_to_lists(
    sim_df: DataFrame,
) -> tuple[list[float], list[float], list[int], list[float], list[float]]:
    """Convert DataFrame columns to lists for processing."""
    line_vals: list[float] = [float(val) for val in _to_float_series(sim_df["line"])]
    p_over_vals: list[float] = [
        float(val) for val in _to_float_series(sim_df.get("p_over", [0.5] * len(sim_df)))
    ]
    y_over_vals: list[int] = [int(val) for val in _to_int_series(sim_df["y_over"])]
    o_over_vals: list[float] = [float(val) for val in _to_float_series(sim_df["odds_over"])]
    o_under_vals: list[float] = [float(val) for val in _to_float_series(sim_df["odds_under"])]
    return line_vals, p_over_vals, y_over_vals, o_over_vals, o_under_vals


def _process_bet_decisions(
    line_vals: list[float],
    p_over_vals: list[float],
    y_over_vals: list[int],
    o_over_vals: list[float],
    o_under_vals: list[float],
    cfg: PraBacktestConfig,
) -> tuple[list[BetDecision], list[float]]:
    """Process bet decisions for each line."""
    decisions: list[BetDecision] = []
    pnls: list[float] = []
    for idx, line in enumerate(line_vals):
        p_over = p_over_vals[idx] if idx < len(p_over_vals) else 0.5
        y_over = y_over_vals[idx] if idx < len(y_over_vals) else 0
        o_over = o_over_vals[idx] if idx < len(o_over_vals) else cfg.default_american_over
        o_under = o_under_vals[idx] if idx < len(o_under_vals) else cfg.default_american_under

        try:
            dec = cast(
                BetDecision,
                decide_over_under(
                    line=line,
                    p_over=p_over,
                    odds_over=Odds(american=int(round(o_over))),
                    odds_under=Odds(american=int(round(o_under))),
                    true_prob_over=p_over,
                    true_prob_under=1.0 - p_over,
                ),
            )
            decisions.append(dec)

            win = (dec.side == "over" and y_over == 1) or (dec.side == "under" and y_over == 0)
            pnls.append(_payout_profit_per_1(dec.decimal_odds) if win else -1.0)
        except (ValueError, TypeError) as e:
            logger.warning("Failed to make decision for row %d: %s", idx, e)
            decisions.append(
                BetDecision(
                    side="over",
                    line=line,
                    p_win=0.5,
                    decimal_odds=1.91,
                    ev=0.0,
                    kelly_fraction=0.0,
                )
            )
            pnls.append(0.0)
    return decisions, pnls


def backtest_pra_lines(cfg: PraBacktestConfig) -> tuple[DataFrame, dict[str, Any]]:
    """Backtest a simple over/under strategy on historical lines.

    This is a placeholder that simulates the backtest logic.
    In production, integrate with actual PRA simulation.

    Returns:
        Tuple of (sim_df, summary)
    """
    logger.info("Starting PRA backtest for %s %s", cfg.league, cfg.season)

    try:
        lines = pd.read_csv(Path(cfg.lines_csv))
    except (OSError, ValueError) as e:
        logger.error("Failed to read lines CSV: %s", e)
        return DataFrame(), {"error": str(e)}

    if lines.empty:
        return lines, {"error": "Empty lines data"}

    sim_df = lines.copy()

    _build_stat_over_columns(sim_df)

    y_over_col = _determine_y_over_column(sim_df)
    if y_over_col:
        sim_df["y_over"] = sim_df[y_over_col]
    else:
        logger.warning("No stat target column found, using default y_over")
        sim_df["y_over"] = 0

    sim_df["odds_over"] = float(cfg.default_american_over)
    sim_df["odds_under"] = float(cfg.default_american_under)

    sim_df = _attach_odds_column(sim_df, lines, cfg, side="over")
    sim_df = _attach_odds_column(sim_df, lines, cfg, side="under")

    line_vals, p_over_vals, y_over_vals, o_over_vals, o_under_vals = _convert_columns_to_lists(
        sim_df
    )

    decisions, pnls = _process_bet_decisions(
        line_vals, p_over_vals, y_over_vals, o_over_vals, o_under_vals, cfg
    )

    sim_df["side"] = [d.side for d in decisions]
    sim_df["ev"] = [float(d.ev) for d in decisions]
    sim_df["kelly_fraction"] = [float(d.kelly_fraction) for d in decisions]
    sim_df["p_win"] = [float(d.p_win) for d in decisions]
    sim_df["decimal_odds"] = [float(d.decimal_odds) for d in decisions]
    sim_df["pnl_1"] = pnls

    sim_df["cumulative_pnl"] = np.cumsum(pnls)
    sim_df["outcome"] = (pd.Series(pnls) > 0).astype(bool)

    ev_arr = (
        pd.to_numeric(sim_df.get("ev", pd.Series([0.0] * len(sim_df))), errors="coerce")
        .astype("float64")  # type: ignore[return-value]
        .to_numpy()  # type: ignore[union-attr]
    )
    pnl_arr = (
        pd.to_numeric(sim_df["pnl_1"], errors="coerce")
        .astype("float64")  # type: ignore[return-value]
        .to_numpy()  # type: ignore[union-attr]
    )

    metrics = calculate_performance_metrics(
        pnl_series=pd.Series(pnl_arr),
        ev_series=pd.Series(ev_arr),
        outcome_series=pd.Series(pnls) > 0,
        stake_series=None,
        risk_free_rate=0.0,
    )

    summary: dict[str, Any] = {
        "n": int(len(sim_df)),
        "mean_ev": float(np.nanmean(ev_arr)) if len(ev_arr) > 0 else 0.0,
        "mean_pnl_1": float(np.nanmean(pnl_arr)) if len(pnl_arr) > 0 else 0.0,
        "total_pnl_1": float(np.nansum(pnl_arr)) if len(pnl_arr) > 0 else 0.0,
        "hit_rate": float(np.nanmean((pnl_arr > 0).astype("float64"))) if len(pnl_arr) > 0 else 0.0,
        "metrics": metrics.to_dict(),
    }

    logger.info("Backtest complete: %d bets, P&L: $%.2f", summary["n"], summary["total_pnl_1"])
    return sim_df, summary


__all__ = [
    "PraBacktestConfig",
    "backtest_pra_lines",
]
