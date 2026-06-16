"""Single-stat simulation for individual player prop markets.

Phase 6: Simulates Points, Rebounds, Assists individually (not combined PRA).
Reuses existing component models (minutes, PPM, RPM, APM) from PRA system.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Optional, cast

import numpy as np
import pandas as pd
from pandas import DataFrame

from sportsquant.models.predictive.simulate import (
    _predict,
    _fillna_frame_mean,
    _to_numeric_series,
)
from sportsquant.models.predictive.pra_components import ComponentModelPaths
from sportsquant.models.predictive.artifact import load_artifact
from sportsquant.util.nba_logging import get_logger

logger = get_logger(__name__)


class StatType(str, Enum):
    """Supported single-stat types."""

    POINTS = "points"
    REBOUNDS = "rebounds"
    ASSISTS = "assists"
    POINTS_REBOUNDS = "points_rebounds"  # P+R
    POINTS_ASSISTS = "points_assists"  # P+A


@dataclass(frozen=True)
class SingleStatSimResult:  # pylint: disable=too-many-instance-attributes
    """Single simulation result for one player/game/stat."""

    stat_type: str
    mean: float
    std: float
    samples: np.ndarray  # Full distribution

    # Quantiles
    q10: float
    q25: float
    q50: float
    q75: float
    q90: float

    def p_over(self, line: float) -> float:
        """Probability of exceeding line."""
        return float(np.mean(self.samples > line))

    def p_under(self, line: float) -> float:
        """Probability of under line."""
        return 1.0 - self.p_over(line)


def simulate_single_stat(
    minutes_samples: np.ndarray,
    rate_samples: np.ndarray,
    *,
    stat_type: StatType,
    min_sigma: float = 2.0,
) -> SingleStatSimResult:
    """Simulate single stat distribution from component samples.

    Args:
        minutes_samples: Monte Carlo samples for minutes (N,)
        rate_samples: Monte Carlo samples for per-minute rate (N,)
        stat_type: Which stat to simulate
        min_sigma: Minimum standard deviation

    Returns:
        SingleStatSimResult with distribution statistics
    """
    # Stat = Minutes × Rate (element-wise multiplication)
    stat_samples = minutes_samples * rate_samples

    # Clamp to non-negative (can't have negative points/rebounds/assists)
    stat_samples = np.maximum(stat_samples, 0.0)

    mean_val = float(np.mean(stat_samples))
    std_val = float(np.std(stat_samples, ddof=1))
    std_val = max(std_val, min_sigma)  # Floor for stability

    return SingleStatSimResult(
        stat_type=stat_type.value,
        mean=mean_val,
        std=std_val,
        samples=stat_samples,
        q10=float(np.percentile(stat_samples, 10)),
        q25=float(np.percentile(stat_samples, 25)),
        q50=float(np.percentile(stat_samples, 50)),
        q75=float(np.percentile(stat_samples, 75)),
        q90=float(np.percentile(stat_samples, 90)),
    )


def simulate_combo_stat(
    minutes_samples: np.ndarray,
    rate1_samples: np.ndarray,
    rate2_samples: np.ndarray,
    *,
    stat_type: StatType,
    min_sigma: float = 3.0,
) -> SingleStatSimResult:
    """Simulate combined stat (e.g., P+R, P+A) from component samples.

    Args:
        minutes_samples: Monte Carlo samples for minutes (N,)
        rate1_samples: Monte Carlo samples for first rate (N,)
        rate2_samples: Monte Carlo samples for second rate (N,)
        stat_type: Which combo to simulate
        min_sigma: Minimum standard deviation

    Returns:
        SingleStatSimResult with distribution statistics
    """
    # Combo = Minutes × (Rate1 + Rate2)
    combo_samples = minutes_samples * (rate1_samples + rate2_samples)
    combo_samples = np.maximum(combo_samples, 0.0)

    mean_val = float(np.mean(combo_samples))
    std_val = float(np.std(combo_samples, ddof=1))
    std_val = max(std_val, min_sigma)

    return SingleStatSimResult(
        stat_type=stat_type.value,
        mean=mean_val,
        std=std_val,
        samples=combo_samples,
        q10=float(np.percentile(combo_samples, 10)),
        q25=float(np.percentile(combo_samples, 25)),
        q50=float(np.percentile(combo_samples, 50)),
        q75=float(np.percentile(combo_samples, 75)),
        q90=float(np.percentile(combo_samples, 90)),
    )


def simulate_single_stat_for_rows(  # pylint: disable=too-many-arguments,too-many-locals,too-many-branches,too-many-statements
    feats: DataFrame,
    *,
    cache_root: Path,
    league: str,
    season: str,
    snapshot_id: Optional[str],
    stat_type: StatType,
    n_sims: int = 5000,
    random_state: int = 1337,
    min_sigma_minutes: float = 2.5,
    min_sigma_rate: float = 0.02,
) -> DataFrame:
    """Simulate single-stat distributions for multiple player-game rows.

    Args:
        feats: PRA features DataFrame with player-game rows
        cache_root: Cache root directory
        league: League name
        season: Season string
        snapshot_id: Snapshot ID
        stat_type: Which stat to simulate
        n_sims: Number of Monte Carlo samples
        random_state: Random seed
        min_sigma_minutes: Minimum std for minutes
        min_sigma_rate: Minimum std for rate

    Returns:
        DataFrame with simulation results per row
    """
    if feats.empty:
        return DataFrame()

    # Load component models
    paths = ComponentModelPaths(
        cache_root=cache_root,
        league=league,
        season=season,
        snapshot_id=snapshot_id or "",
    )

    # Load minutes model
    minutes_model, minutes_meta = load_artifact(paths.minutes_prefix())

    # Initialize rate models to None
    rate_model: Any = None
    rate1_model: Any = None
    rate2_model: Any = None
    rate_meta: dict[str, Any] | None = None
    rate1_meta: dict[str, Any] | None = None
    rate2_meta: dict[str, Any] | None = None

    # Load appropriate rate model(s)
    if stat_type == StatType.POINTS:
        rate_model, rate_meta = load_artifact(paths.ppm_prefix())
    elif stat_type == StatType.REBOUNDS:
        rate_model, rate_meta = load_artifact(paths.rpm_prefix())
    elif stat_type == StatType.ASSISTS:
        rate_model, rate_meta = load_artifact(paths.apm_prefix())
    elif stat_type == StatType.POINTS_REBOUNDS:
        rate1_model, rate1_meta = load_artifact(paths.ppm_prefix())
        rate2_model, rate2_meta = load_artifact(paths.rpm_prefix())
    elif stat_type == StatType.POINTS_ASSISTS:
        rate1_model, rate1_meta = load_artifact(paths.ppm_prefix())
        rate2_model, rate2_meta = load_artifact(paths.apm_prefix())
    else:
        raise ValueError(f"Unsupported stat_type: {stat_type}")

    # Prepare features
    feat_cols = minutes_meta.get("feature_cols", [])
    if not feat_cols:
        raise ValueError("No feature_cols in minutes model metadata")

    # Ensure all feature columns exist
    missing = [c for c in feat_cols if c not in feats.columns]
    if missing:
        raise ValueError(f"Missing feature columns: {missing}")

    features_df = cast(DataFrame, feats[feat_cols]).copy()
    features_df = _fillna_frame_mean(features_df)

    # Predict means
    minutes_mean = _predict(minutes_model, features_df)

    rate_mean: np.ndarray = np.array([], dtype=float)
    rate1_mean: np.ndarray = np.array([], dtype=float)
    rate2_mean: np.ndarray = np.array([], dtype=float)

    if stat_type in (StatType.POINTS, StatType.REBOUNDS, StatType.ASSISTS):
        if rate_model is None or rate_meta is None:
            raise RuntimeError("Rate model metadata missing for single-stat simulation")
        rate_mean = _predict(rate_model, features_df)
    else:
        if rate1_model is None or rate2_model is None or rate1_meta is None or rate2_meta is None:
            raise RuntimeError("Rate model metadata missing for combo-stat simulation")
        rate1_mean = _predict(rate1_model, features_df)
        rate2_mean = _predict(rate2_model, features_df)

    # Monte Carlo simulation
    rng = np.random.default_rng(random_state)

    # Extract RMSE from model metadata for sigma calculation
    min_sig = float(min_sigma_minutes)
    rate_sig = float(min_sigma_rate)

    v = minutes_meta.get("rmse_holdout")
    if isinstance(v, (int, float)) and math.isfinite(float(v)):
        min_sig = max(min_sig, float(v))

    if stat_type in (StatType.POINTS, StatType.REBOUNDS, StatType.ASSISTS):
        rate_meta = cast(dict[str, Any], rate_meta)
        v = rate_meta.get("rmse_holdout")
        if isinstance(v, (int, float)) and math.isfinite(float(v)):
            rate_sig = max(rate_sig, float(v))
    else:
        rate1_meta = cast(dict[str, Any], rate1_meta)
        rate2_meta = cast(dict[str, Any], rate2_meta)
        v = rate1_meta.get("rmse_holdout")
        if isinstance(v, (int, float)) and math.isfinite(float(v)):
            rate_sig = max(rate_sig, float(v))
        v = rate2_meta.get("rmse_holdout")
        if isinstance(v, (int, float)) and math.isfinite(float(v)):
            rate_sig = max(rate_sig, float(v))

    results: list[dict[str, Any]] = []

    for i in range(len(feats)):
        # Sample minutes
        mu_min = float(minutes_mean[i])
        sigma_min = max(min_sig, mu_min * 0.15)  # Floor with metadata RMSE or 15% CV
        minutes_samples = rng.normal(mu_min, sigma_min, n_sims)
        minutes_samples = np.maximum(minutes_samples, 0.0)  # Clamp to non-negative

        if stat_type in (StatType.POINTS, StatType.REBOUNDS, StatType.ASSISTS):
            # Single rate
            mu_rate = float(rate_mean[i])
            sigma_rate = max(rate_sig, mu_rate * 0.20)  # Floor with metadata RMSE or 20% CV
            rate_samples = rng.normal(mu_rate, sigma_rate, n_sims)
            rate_samples = np.maximum(rate_samples, 0.0)

            sim_result = simulate_single_stat(
                minutes_samples,
                rate_samples,
                stat_type=stat_type,
                min_sigma=2.0,
            )
        else:
            # Combo stat (two rates)
            mu_rate1 = float(rate1_mean[i])
            mu_rate2 = float(rate2_mean[i])
            sigma_rate1 = max(rate_sig, mu_rate1 * 0.20)
            sigma_rate2 = max(rate_sig, mu_rate2 * 0.20)

            rate1_samples = rng.normal(mu_rate1, sigma_rate1, n_sims)
            rate2_samples = rng.normal(mu_rate2, sigma_rate2, n_sims)
            rate1_samples = np.maximum(rate1_samples, 0.0)
            rate2_samples = np.maximum(rate2_samples, 0.0)

            sim_result = simulate_combo_stat(
                minutes_samples,
                rate1_samples,
                rate2_samples,
                stat_type=stat_type,
                min_sigma=3.0,
            )

        # Store result
        row_result = {
            "stat_type": sim_result.stat_type,
            f"{sim_result.stat_type}_mean": sim_result.mean,
            f"{sim_result.stat_type}_std": sim_result.std,
            f"{sim_result.stat_type}_q10": sim_result.q10,
            f"{sim_result.stat_type}_q25": sim_result.q25,
            f"{sim_result.stat_type}_q50": sim_result.q50,
            f"{sim_result.stat_type}_q75": sim_result.q75,
            f"{sim_result.stat_type}_q90": sim_result.q90,
        }
        results.append(row_result)

    # Combine with original features
    result_df = DataFrame(results)
    output = pd.concat([feats.reset_index(drop=True), result_df], axis=1)

    logger.info(
        "simulated %s for %d rows (stat_type=%s)",
        stat_type.value,
        len(output),
        stat_type.value,
    )

    return output


def add_betting_columns_single_stat(  # pylint: disable=too-many-arguments,too-many-locals
    sim_df: DataFrame,
    lines_df: DataFrame,
    *,
    stat_type: StatType,
    line_col: str = "line",
    odds_over_col: str = "odds_over",
    odds_under_col: str = "odds_under",
) -> DataFrame:
    """Add betting evaluation columns for single-stat simulations.

    Calculates P(over), EV, Kelly fractions for provided lines.

    Args:
        sim_df: Simulation output with stat distributions
        lines_df: Betting lines with line, odds_over, odds_under
        stat_type: Which stat was simulated
        line_col: Column name for line in lines_df
        odds_over_col: Column name for over odds
        odds_under_col: Column name for under odds

    Returns:
        DataFrame with betting evaluation columns added
    """
    from scipy import stats as sp_stats  # pyright: ignore[reportMissingImports] # pylint: disable=import-outside-toplevel

    from sportsquant.core.betting.engine import expected_value, kelly_fraction  # pylint: disable=import-outside-toplevel
    from sportsquant.core.betting.odds import Odds  # pylint: disable=import-outside-toplevel

    if sim_df.empty or lines_df.empty:
        return sim_df

    # Convert game_date in lines_df to datetime to match sim_df
    lines_df = lines_df.copy()
    if "game_date" in lines_df.columns:
        lines_df["game_date"] = pd.to_datetime(lines_df["game_date"])

    # Merge lines with simulations
    merge_keys = ["player_id", "game_date"]
    available_keys = [k for k in merge_keys if k in sim_df.columns and k in lines_df.columns]

    if not available_keys:
        raise ValueError("Cannot merge: no common keys (player_id, game_date)")

    merged = sim_df.merge(
        lines_df[available_keys + [line_col, odds_over_col, odds_under_col]],
        on=available_keys,
        how="left",
    )

    # Calculate probabilities using Normal distribution
    stat_mean_col = f"{stat_type.value}_mean"
    stat_std_col = f"{stat_type.value}_std"

    if stat_mean_col not in merged.columns or stat_std_col not in merged.columns:
        raise ValueError(f"Missing stat columns: {stat_mean_col}, {stat_std_col}")

    lines = _to_numeric_series(merged[line_col])
    means = _to_numeric_series(merged[stat_mean_col])
    stds = _to_numeric_series(merged[stat_std_col])

    # P(over) = 1 - CDF((line - mean) / std)
    z_scores = (lines - means) / stds
    p_over = 1.0 - sp_stats.norm.cdf(z_scores)
    p_over = np.clip(p_over, 0.01, 0.99)  # Avoid extreme probabilities

    merged["p_over"] = p_over
    merged["p_under"] = 1.0 - p_over

    # Convert odds and calculate EV/Kelly
    def calc_betting_metrics(row: Any) -> dict[str, float]:
        """Calculate betting metrics for a row."""
        # Handle rows without betting lines (NaN from left merge)
        if pd.isna(row[odds_over_col]) or pd.isna(row[odds_under_col]):
            return {
                "odds_over_decimal": float("nan"),
                "odds_under_decimal": float("nan"),
                "ev_over": float("nan"),
                "ev_under": float("nan"),
                "kelly_over": float("nan"),
                "kelly_under": float("nan"),
            }

        odds_over = Odds(american=int(row[odds_over_col]))
        odds_under = Odds(american=int(row[odds_under_col]))

        odds_over_dec = odds_over.to_decimal()
        odds_under_dec = odds_under.to_decimal()

        ev_over = expected_value(row["p_over"], odds_over, true_prob=row["p_over"])
        ev_under = expected_value(row["p_under"], odds_under, true_prob=row["p_under"])

        kelly_over = kelly_fraction(row["p_over"], odds_over)
        kelly_under = kelly_fraction(row["p_under"], odds_under)

        return {
            "odds_over_decimal": odds_over_dec,
            "odds_under_decimal": odds_under_dec,
            "ev_over": ev_over,
            "ev_under": ev_under,
            "kelly_over": kelly_over,
            "kelly_under": kelly_under,
        }

    # Apply betting calculations
    betting_cols = merged.apply(calc_betting_metrics, axis=1, result_type="expand")
    merged = pd.concat([merged, betting_cols], axis=1)

    return merged
