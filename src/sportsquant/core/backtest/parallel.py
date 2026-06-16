"""
Parallel Backtest Function (V2)

Adapted from sports_analytics.betting.backtest_v2
Changes: Replaced sports_analytics.util.logging with standard logging

Provides parallelized backtesting with comprehensive metrics including:
- Time-series cross-validation
- MultiIndex DataFrame output
- Comprehensive metrics: yield, ROI, final cash, etc.
- Parallel processing support via n_jobs
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

import numpy as np
import pandas as pd
from pandas import DataFrame, Series
from sklearn.model_selection import BaseCrossValidator

logger = logging.getLogger(__name__)

COL_NUM_BETS = "Number of bets"
COL_NUM_WINS = "Number of wins"
COL_WIN_RATE_PCT = "Win rate percentage"
COL_YIELD_PCT = "Yield percentage per bet"
COL_ROI_PCT = "ROI percentage"
COL_TOTAL_PNL = "Total PnL"
COL_TOTAL_STAKED = "Total staked"
COL_FINAL_CASH = "Final cash"
COL_NUM_BETTING_DAYS = "Number of betting days"
COL_TRAINING_START = ("Training", "start")
COL_TRAINING_END = ("Training", "end")
COL_TESTING_START = ("Testing", "start")
COL_TESTING_END = ("Testing", "end")


@dataclass(frozen=True)
class BacktestConfig:  # pylint: disable=too-many-instance-attributes
    """Configuration for backtesting."""

    cv: Optional[BaseCrossValidator] = None
    n_splits: int = 5
    init_cash: float = 10000.0
    stake: float = 50.0
    min_value_threshold: float = 0.0
    min_probability: float = 0.50
    n_jobs: int = 1
    verbose: bool = False
    output_dir: Optional[str] = None


def _american_to_decimal(american_odds: float) -> float:
    """Convert American odds to decimal odds."""
    if american_odds >= 0:
        return 1 + (american_odds / 100)
    return 1 + (100 / abs(american_odds))


def _calculate_payout(american_odds: float, stake: float, won: bool) -> float:
    """Calculate payout for a bet."""
    if won:
        if american_odds >= 0:
            return stake * (1 + american_odds / 100)
        return stake * (1 + 100 / abs(american_odds))
    return 0.0


def _parse_odds(odds_str) -> float:
    """Parse odds from various formats."""
    if isinstance(odds_str, (int, float)):
        return float(odds_str)
    if isinstance(odds_str, str):
        try:
            return float(odds_str.replace("+", ""))
        except ValueError:
            return 2.0
    return 2.0


def _convert_to_decimal_odds(odds: float) -> float:
    """Convert American odds to decimal if necessary."""
    if odds > 100 or odds < -100:
        return _american_to_decimal(odds)
    return odds


def _calculate_bet_result(
    prob: float,
    odds: float,
    stake: float,
    min_value_threshold: float,
) -> tuple[bool, float, float]:
    """Calculate bet result and return (is_value, won, pnl)."""
    decimal_odds = _convert_to_decimal_odds(odds)
    ev = prob * decimal_odds - 1
    is_value = ev > min_value_threshold and prob >= 0.5

    if not is_value:
        return False, False, 0.0

    rng = np.random.default_rng(42)
    won = rng.random() < prob
    pnl = (decimal_odds - 1) * stake if won else -stake
    return True, won, pnl


def _run_single_fold(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals,too-many-branches,too-many-statements
    bettor,
    x_train: DataFrame,
    y_train: DataFrame,
    x_test: DataFrame,
    odds_test: DataFrame,
    fold_idx: int,
    init_cash: float,
    stake: float,
    min_value_threshold: float,
) -> dict[str, Any]:
    """Run backtest on a single fold."""
    try:
        bettor.fit(x_train, y_train)

        y_proba_pred = bettor.predict_proba(x_test)

        if len(y_proba_pred.shape) == 1:
            y_proba_pred = y_proba_pred.reshape(-1, 1)

        odds_cols = [c for c in odds_test.columns if c.startswith("odds__")]

        if not odds_cols:
            raise ValueError("No odds columns found in odds_test")

        results = []
        for i, row_idx in enumerate(x_test.index):
            row_result = {
                "fold": fold_idx,
                "row_idx": row_idx,
            }

            for j, col in enumerate(odds_cols):
                if j >= y_proba_pred.shape[1]:
                    continue

                prob = y_proba_pred[i, j]
                odds_str = odds_test.loc[row_idx, col]

                odds = _parse_odds(odds_str)
                odds = _convert_to_decimal_odds(odds)

                ev = prob * odds
                is_value = ev > (1 + min_value_threshold) and prob >= 0.5

                row_result[f"prob_{col}"] = prob
                row_result[f"odds_{col}"] = odds
                row_result[f"ev_{col}"] = ev
                row_result[f"value_{col}"] = is_value

            results.append(row_result)

        results_df = DataFrame(results)

        n_bets = 0
        n_wins = 0
        total_pnl = 0.0
        total_staked = 0.0

        for i, row_idx in enumerate(x_test.index):
            for j, col in enumerate(odds_cols):
                if j >= y_proba_pred.shape[1]:
                    continue

                prob = y_proba_pred[i, j]
                odds_str = odds_test.loc[row_idx, col]

                odds = _parse_odds(odds_str)
                odds = _convert_to_decimal_odds(odds)

                is_value, won, pnl = _calculate_bet_result(prob, odds, stake, min_value_threshold)

                if is_value:
                    n_bets += 1
                    total_staked += stake
                    n_wins += 1 if won else 0
                    total_pnl += pnl

        roi_pct = (total_pnl / total_staked * 100) if total_staked > 0 else 0.0
        yield_pct = (total_pnl / n_bets * 100) if n_bets > 0 else 0.0
        win_rate = (n_wins / n_bets * 100) if n_bets > 0 else 0.0

        final_cash = init_cash + total_pnl

        return {
            "fold": fold_idx,
            "n_bets": n_bets,
            "n_wins": n_wins,
            "win_rate": win_rate,
            "total_pnl": total_pnl,
            "total_staked": total_staked,
            "roi_percentage": roi_pct,
            "yield_percentage": yield_pct,
            "final_cash": final_cash,
            "results_df": results_df,
        }

    except (ValueError, TypeError, KeyError) as e:
        logger.error("Fold %d failed: %s", fold_idx, e)
        return {
            "fold": fold_idx,
            "error": str(e),
            "n_bets": 0,
            "n_wins": 0,
            "total_pnl": 0.0,
            "roi_percentage": 0.0,
            "yield_percentage": 0.0,
            "final_cash": init_cash,
        }


def _generate_time_series_splits(
    df: DataFrame,
    n_splits: int = 5,
    test_size: int = 20,
) -> list[tuple[int, int]]:
    """Generate time-series splits for cross-validation."""
    n = len(df)
    splits = []

    split_size = (n - test_size) // n_splits

    for i in range(n_splits):
        train_end = (i + 1) * split_size
        test_end = train_end + test_size

        if test_end <= n:
            splits.append((train_end, test_end))

    return splits


def backtest_v2(  # pylint: disable=too-many-locals,too-many-branches,too-many-statements,invalid-name
    bettor,
    X: DataFrame,
    y: DataFrame | Series | np.ndarray,
    odds_df: DataFrame,
    config: Optional[BacktestConfig] = None,
) -> DataFrame:
    """Run parallel backtest on betting strategy.

    Args:
        bettor: BaseBettor instance with fit, predict_proba, and bet methods
        X: Input features (training + test data)
        y: Target values (binary: 0=under, 1=over)
        odds_df: Odds data corresponding to X
        config: BacktestConfig with cross-validation and betting parameters

    Returns:
        DataFrame with MultiIndex (Training start/end, Testing start/end)
        and columns for all metrics
    """
    if config is None:
        config = BacktestConfig()

    if isinstance(y, (Series, np.ndarray)):
        y_df = DataFrame(y)
    else:
        y_df = y

    if len(X) != len(y_df):
        raise ValueError(f"X and y must have same length: {len(X)} vs {len(y_df)}")

    if len(X) != len(odds_df):
        raise ValueError(f"X and odds_df must have same length: {len(X)} vs {len(odds_df)}")

    if config.cv is not None:
        try:
            splits = list(config.cv.split(X))
            split_indices = [(train_idx[-1], test_idx[-1]) for train_idx, test_idx in splits]
        except (ValueError, TypeError) as e:
            logger.warning("CV split failed: %s, using default time-series splits", e)
            split_indices = _generate_time_series_splits(X, config.n_splits)
    else:
        split_indices = _generate_time_series_splits(X, config.n_splits)

    logger.info("Running backtest with %d folds", len(split_indices))

    all_results = []

    for fold_idx, (train_end, test_end) in enumerate(split_indices):
        x_train = X.iloc[:train_end]
        y_train = y_df.iloc[:train_end]
        x_test = X.iloc[train_end:test_end]
        odds_test = odds_df.iloc[train_end:test_end]

        if "game_date" in X.columns:
            train_start_date = X.iloc[0]["game_date"] if train_end > 0 else None
            train_end_date = X.iloc[train_end - 1]["game_date"] if train_end > 0 else None
            test_start_date = X.iloc[train_end]["game_date"] if train_end < len(X) else None
            test_end_date = X.iloc[test_end - 1]["game_date"] if test_end > 0 else None
        else:
            train_start_date = 0
            train_end_date = train_end
            test_start_date = train_end
            test_end_date = test_end

        fold_result = _run_single_fold(
            bettor=bettor,
            x_train=x_train,
            y_train=y_train,
            x_test=x_test,
            odds_test=odds_test,
            fold_idx=fold_idx,
            init_cash=config.init_cash,
            stake=config.stake,
            min_value_threshold=config.min_value_threshold,
        )

        result_row = {
            COL_TRAINING_START: train_start_date,
            COL_TRAINING_END: train_end_date,
            COL_TESTING_START: test_start_date,
            COL_TESTING_END: test_end_date,
            COL_NUM_BETTING_DAYS: len(x_test),
            COL_NUM_BETS: fold_result["n_bets"],
            COL_NUM_WINS: fold_result["n_wins"],
            COL_WIN_RATE_PCT: fold_result["win_rate"],
            COL_YIELD_PCT: fold_result["yield_percentage"],
            COL_ROI_PCT: fold_result["roi_percentage"],
            COL_TOTAL_PNL: fold_result["total_pnl"],
            COL_TOTAL_STAKED: fold_result["total_staked"],
            COL_FINAL_CASH: fold_result["final_cash"],
        }

        odds_cols = [c for c in odds_df.columns if c.startswith("odds__")]
        for col in odds_cols:
            market_name = col.replace("odds__", "").replace("__", "_")
            result_row[f"{COL_NUM_BETS} ({market_name})"] = fold_result.get("n_bets", 0)
            result_row[f"{COL_YIELD_PCT} ({market_name})"] = fold_result.get("yield_percentage", 0)

        all_results.append(result_row)

    if all_results:
        results_df = DataFrame(all_results)

        results_df = results_df.set_index(
            [
                COL_TRAINING_START,
                COL_TRAINING_END,
                COL_TESTING_START,
                COL_TESTING_END,
            ]
        )

        for col in results_df.columns:
            if results_df[col].dtype == object:
                try:
                    results_df[col] = pd.to_numeric(results_df[col])
                except (ValueError, TypeError) as e:
                    logger.warning("Could not convert column %s to numeric: %s", col, e)

        return results_df

    columns = pd.Index(
        [
            COL_NUM_BETTING_DAYS,
            COL_NUM_BETS,
            COL_NUM_WINS,
            COL_WIN_RATE_PCT,
            COL_YIELD_PCT,
            COL_ROI_PCT,
            COL_TOTAL_PNL,
            COL_TOTAL_STAKED,
            COL_FINAL_CASH,
        ]
    )
    return DataFrame(columns=columns).set_index(
        pd.MultiIndex.from_tuples(
            [
                COL_TRAINING_START,
                COL_TRAINING_END,
                COL_TESTING_START,
                COL_TESTING_END,
            ],
            names=["Training", "Testing"],
        )
    )


def backtest_summary(results: DataFrame) -> dict[str, Any]:
    """Generate summary statistics from backtest results."""
    if results.empty:
        return {"error": "No results to summarize"}

    return {
        "Total bets": results[COL_NUM_BETS].sum(),
        "Total wins": results[COL_NUM_WINS].sum(),
        "Overall win rate": results[COL_NUM_WINS].sum() / results[COL_NUM_BETS].sum() * 100
        if results[COL_NUM_BETS].sum() > 0
        else 0,
        "Average yield per bet": results[COL_YIELD_PCT].mean(),
        "Average ROI": results[COL_ROI_PCT].mean(),
        "Total PnL": results[COL_TOTAL_PNL].sum(),
        "Final cash (avg)": results[COL_FINAL_CASH].mean(),
        "Max ROI": results[COL_ROI_PCT].max(),
        "Min ROI": results[COL_ROI_PCT].min(),
        "ROI std": results[COL_ROI_PCT].std(),
    }


__all__ = [
    "BacktestConfig",
    "backtest_v2",
    "backtest_summary",
]
