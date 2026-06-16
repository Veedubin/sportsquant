from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, cast

import numpy as np
from pandas import DataFrame, Series


@dataclass(frozen=True)
class NormalBaseline:
    """A simple Normal(mu, sigma) baseline for over/under probabilities."""

    mu: float
    sigma: float


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        v = float(x)
        if not np.isfinite(v):
            return float(default)
        return v
    except (TypeError, ValueError, OverflowError):
        return float(default)


def baseline_last_n_mean(values: Series, *, n: int) -> float:
    """Mean of the last N values (expects chronological input)."""
    if values.empty:
        return 0.0
    arr = np.asarray(values.tail(int(n)), dtype=float)
    if arr.size == 0:
        return 0.0
    return _safe_float(np.nanmean(arr), 0.0)


def baseline_season_mean_to_date(values: Series) -> float:
    """Season-to-date mean of values (expects chronological input)."""
    if values.empty:
        return 0.0
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        return 0.0
    return _safe_float(np.nanmean(arr), 0.0)


def baseline_minutes_x_rate(
    *,
    minutes_last_n: Series,
    pra_per_min_szn: Series,
    n_minutes: int = 10,
) -> float:
    """Baseline C (primary): minutes mean × PRA-per-minute season mean."""

    min_mu = baseline_last_n_mean(minutes_last_n, n=int(n_minutes))
    rate_mu = baseline_season_mean_to_date(pra_per_min_szn)
    return float(min_mu * rate_mu)


def estimate_sigma(values: Series, *, n: int = 10, floor: float = 4.0) -> float:
    """Stddev of last N values with a floor."""
    if values.empty:
        return float(floor)
    arr = np.asarray(values.tail(int(n)), dtype=float)
    if arr.size == 0:
        return float(floor)
    sigma = _safe_float(np.nanstd(arr, ddof=0), float(floor))
    return float(max(sigma, float(floor)))


def normal_p_over(line: float, baseline: NormalBaseline) -> float:
    """Compute P(X > line) for X ~ Normal(mu, sigma)."""

    mu = float(baseline.mu)
    sigma = float(max(baseline.sigma, 1e-9))
    z = (float(line) - mu) / sigma

    # Normal CDF via error function to avoid scipy dependency.
    # CDF(z) = 0.5 * (1 + erf(z / sqrt(2)))
    cdf = 0.5 * (1.0 + float(math.erf(z / math.sqrt(2.0))))
    p_over = 1.0 - cdf
    # numeric safety
    return float(min(max(p_over, 0.0), 1.0))


def baseline_from_feature_row(
    row: Series,
    *,
    sigma_floor: float = 4.0,
) -> NormalBaseline:
    """Construct a NormalBaseline from a PRA feature row.

    Expects the PRA features built by sportsquant.models.predictive.features.pra.build_pra_features.
    Uses Baseline C semantics:
      mu = min_last_10_mean * pra_per_min_szn_mean_to_date

    Where the PRA-per-minute season mean is approximated by:
      pra_per_min_szn = ppm_szn_mean_to_date + rpm_szn_mean_to_date + apm_szn_mean_to_date

    Sigma is taken from pra_last_10_std if present, otherwise computed with a floor.
    """

    values = {str(k): v for k, v in row.items()}
    min_mu = _safe_float(values.get("min_last_10_mean"), 0.0)
    ppm = _safe_float(values.get("ppm_szn_mean_to_date"), 0.0)
    rpm = _safe_float(values.get("rpm_szn_mean_to_date"), 0.0)
    apm = _safe_float(values.get("apm_szn_mean_to_date"), 0.0)
    mu = float(min_mu * (ppm + rpm + apm))

    sigma = _safe_float(values.get("pra_last_10_std"), float(sigma_floor))
    sigma = float(max(sigma, float(sigma_floor)))

    return NormalBaseline(mu=mu, sigma=sigma)


def add_baseline_probabilities(
    df: DataFrame,
    *,
    line_col: str,
    out_prob_col: str = "p_over_baseline",
    sigma_floor: float = 4.0,
) -> DataFrame:
    """Add a baseline over probability column given a betting line column."""

    if df.empty:
        return df

    out = df.copy()

    def _row_p(row: Series) -> float:
        b = baseline_from_feature_row(row, sigma_floor=sigma_floor)
        values = {str(k): v for k, v in row.items()}
        line = _safe_float(values.get(line_col), 0.0)
        return normal_p_over(line, b)

    # pandas apply typing under strict mode is imperfect; cast through Any.
    out[out_prob_col] = cast(Any, out).apply(_row_p, axis=1)
    return out
