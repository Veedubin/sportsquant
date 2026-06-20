"""
Statistical significance testing for betting performance.

Provides comprehensive hypothesis testing, confidence intervals, and power analysis
to determine if betting results are statistically significant.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

import numpy as np
from scipy import stats


@dataclass(frozen=True)
class BetRecord:
    """Record of a single bet with all relevant details."""

    bet_id: UUID
    player_id: str
    market: str
    line: float
    odds: float
    stake: float
    side: Literal["over", "under"]
    book: str
    predicted_prob: float
    actual_result: Literal["win", "loss", "push", "pending"]
    profit_loss: float
    clv: float
    timestamp: datetime
    settled: bool = False
    notes: str = ""


@dataclass(frozen=True)
class HypothesisTestResult:
    """Core hypothesis test results."""

    is_significant: bool
    p_value: float
    z_score: float


@dataclass(frozen=True)
class HypothesisRoiResult:
    """ROI-related hypothesis results."""

    observed_roi: float
    null_hypothesis_roi: float
    confidence_level: float
    sample_size: int


@dataclass(frozen=True)
class HypothesisResult:
    """Result of a hypothesis test for betting profitability."""

    test: HypothesisTestResult
    roi: HypothesisRoiResult
    conclusion: str


class SignificanceTester:
    """Statistical significance testing for betting performance."""

    # pylint: disable=R0902

    def __init__(self, bets: list[BetRecord]) -> None:
        self.bets = bets
        self.settled_bets = [b for b in bets if b.settled and b.actual_result != "pending"]
        self.wins = [b for b in self.settled_bets if b.actual_result == "win"]
        self.losses = [b for b in self.settled_bets if b.actual_result == "loss"]
        self.pushes = [b for b in self.settled_bets if b.actual_result == "push"]

    def compute_p_value(self, null_hypothesis_roi: float = 0.0) -> float:
        """Compute p-value for the hypothesis test.

        Args:
            null_hypothesis_roi: ROI under null hypothesis (default 0.0).

        Returns:
            Two-tailed p-value.
        """
        if len(self.settled_bets) < 2:
            return 1.0

        roi = self._compute_observed_roi()
        se = self._compute_roi_standard_error()

        if se == 0:
            return 1.0

        z_score = (roi - null_hypothesis_roi) / se
        p_value = 2.0 * (1.0 - stats.norm.cdf(abs(z_score)))

        return float(p_value)

    def compute_roi_ci(
        self, confidence: float = 0.95, n_bootstraps: int = 10000
    ) -> tuple[float, float]:
        """Compute confidence interval for ROI using bootstrapping.

        Args:
            confidence: Confidence level (default 0.95).
            n_bootstraps: Number of bootstrap iterations (default 10000).

        Returns:
            Tuple of (lower_bound, upper_bound).
        """
        if len(self.settled_bets) < 10:
            return (0.0, 0.0)

        bootstrap_rois = self._bootstrap_roi(n_bootstraps)

        alpha = 1.0 - confidence
        lower_percentile = (alpha / 2) * 100
        upper_percentile = (1.0 - alpha / 2) * 100

        lower = float(np.percentile(bootstrap_rois, lower_percentile))
        upper = float(np.percentile(bootstrap_rois, upper_percentile))

        return (lower, upper)

    def compute_required_sample_size(
        self,
        alpha: float = 0.05,
        power: float = 0.8,
        min_detectable_roi: float = 0.02,
    ) -> int:
        """Calculate required sample size to detect given effect size.

        Args:
            alpha: Significance level (default 0.05).
            power: Desired statistical power (default 0.8).
            min_detectable_roi: Minimum ROI effect size to detect (default 0.02).

        Returns:
            Required number of samples.
        """
        if len(self.settled_bets) < 2:
            return 0

        observed_std = self._compute_pnl_std()
        if observed_std == 0:
            return 0

        z_alpha = stats.norm.ppf(1.0 - alpha / 2)
        z_beta = stats.norm.ppf(power)

        effect_size = min_detectable_roi
        sample_size = int(((z_alpha + z_beta) * observed_std / effect_size) ** 2)

        sample_size = max(sample_size, 30)
        return sample_size

    def test_profitability_hypothesis(self) -> HypothesisResult:
        """Test if betting strategy is statistically profitable.

        Returns:
            HypothesisResult with test statistics and conclusion.
        """
        alpha = 0.05
        null_roi = 0.0

        if len(self.settled_bets) < 30:
            return HypothesisResult(
                test=HypothesisTestResult(
                    is_significant=False,
                    p_value=1.0,
                    z_score=0.0,
                ),
                roi=HypothesisRoiResult(
                    observed_roi=0.0,
                    null_hypothesis_roi=null_roi,
                    confidence_level=1.0 - alpha,
                    sample_size=len(self.settled_bets),
                ),
                conclusion="Insufficient data for statistical test (need 30+ bets)",
            )

        roi = self._compute_observed_roi()
        p_value = self.compute_p_value(null_roi)
        z_score = self.compute_z_score()
        sample_size = len(self.settled_bets)

        is_significant = p_value < alpha

        if is_significant:
            if roi > 0:
                conclusion = (
                    f"Statistically significant profit. "
                    f"ROI={roi * 100:.2f}%, p-value={p_value:.4f} < {alpha}. "
                    f"Evidence supports profitable strategy."
                )
            else:
                conclusion = (
                    f"Statistically significant loss. "
                    f"ROI={roi * 100:.2f}%, p-value={p_value:.4f} < {alpha}. "
                    f"Strategy is losing money."
                )
        else:
            conclusion = (
                f"Results not statistically significant. "
                f"ROI={roi * 100:.2f}%, p-value={p_value:.4f} >= {alpha}. "
                f"Insufficient evidence to conclude profitability."
            )

        return HypothesisResult(
            test=HypothesisTestResult(
                is_significant=is_significant,
                p_value=p_value,
                z_score=z_score,
            ),
            roi=HypothesisRoiResult(
                observed_roi=roi,
                null_hypothesis_roi=null_roi,
                confidence_level=1.0 - alpha,
                sample_size=sample_size,
            ),
            conclusion=conclusion,
        )

    def compute_z_score(self) -> float:
        """Compute z-score for observed ROI."""
        if len(self.settled_bets) < 2:
            return 0.0

        roi = self._compute_observed_roi()
        se = self._compute_roi_standard_error()

        if se == 0:
            return 0.0

        return float(roi / se)

    def _compute_observed_roi(self) -> float:
        """Calculate observed ROI from settled bets."""
        if not self.settled_bets:
            return 0.0

        total_stake = sum(b.stake for b in self.settled_bets)
        if total_stake == 0:
            return 0.0

        total_profit = sum(b.profit_loss for b in self.settled_bets)
        return total_profit / total_stake

    def _compute_roi_standard_error(self) -> float:
        """Calculate standard error of ROI estimate."""
        if len(self.settled_bets) < 2:
            return 0.0

        pnl_values = np.array([b.profit_loss / b.stake for b in self.settled_bets])
        std = np.std(pnl_values, ddof=1)

        if len(self.settled_bets) < 2:
            return 0.0

        return std / np.sqrt(len(self.settled_bets))

    def _compute_pnl_std(self) -> float:
        """Calculate standard deviation of PnL returns."""
        if len(self.settled_bets) < 2:
            return 0.0

        roi_values = np.array([b.profit_loss / b.stake for b in self.settled_bets])
        return float(np.std(roi_values, ddof=1))

    def _bootstrap_roi(self, n_iterations: int) -> np.ndarray:
        """Bootstrap ROI estimate by resampling with replacement."""
        rng = np.random.default_rng(42)
        n_bets = len(self.settled_bets)

        if n_bets == 0:
            return np.array([0.0])

        roi_values = np.array([b.profit_loss / b.stake for b in self.settled_bets])

        bootstrap_rois = np.zeros(n_iterations)
        for i in range(n_iterations):
            indices = rng.integers(0, n_bets, size=n_bets)
            sample_rois = roi_values[indices]
            bootstrap_rois[i] = float(np.mean(sample_rois))

        return bootstrap_rois


class ConfidenceIntervalCalculator:
    """Confidence interval calculations for betting statistics."""

    # pylint: disable=R0902

    def __init__(self, bets: list[BetRecord]) -> None:
        self.bets = bets
        self.settled_bets = [b for b in bets if b.settled and b.actual_result != "pending"]

    def bootstrap_roi(self, n_iterations: int = 10000) -> list[float]:
        """Bootstrap ROI distribution.

        Args:
            n_iterations: Number of bootstrap iterations (default 10000).

        Returns:
            List of bootstrapped ROI values.
        """
        if len(self.settled_bets) < 2:
            return [0.0]

        rng = np.random.default_rng(42)
        n_bets = len(self.settled_bets)
        roi_values = np.array([b.profit_loss / b.stake for b in self.settled_bets])

        bootstrap_rois: list[float] = []
        for _ in range(n_iterations):
            indices = rng.integers(0, n_bets, size=n_bets)
            sample_rois = roi_values[indices]
            bootstrap_rois.append(float(np.mean(sample_rois)))

        return bootstrap_rois

    def compute_roi_percentiles(self, percentiles: list[float] | None = None) -> dict[float, float]:
        """Compute percentiles of the ROI bootstrap distribution.

        Args:
            percentiles: List of percentile values to compute (default [2.5, 50, 97.5]).

        Returns:
            Dictionary mapping percentile values to their estimates.
        """
        if percentiles is None:
            percentiles = [2.5, 50, 97.5]
        if len(self.settled_bets) < 2:
            return dict.fromkeys(percentiles, 0.0)

        n_iterations = 10000
        bootstrap_rois = self.bootstrap_roi(n_iterations)

        results: dict[float, float] = {}
        for p in percentiles:
            results[p] = float(np.percentile(bootstrap_rois, p))

        return results

    def compute_probability_of_profit(self) -> float:
        """Estimate probability of positive ROI from bootstrap distribution."""
        if len(self.settled_bets) < 2:
            return 0.5

        n_iterations = 10000
        bootstrap_rois = self.bootstrap_roi(n_iterations)

        prob_positive = float(np.mean(np.array(bootstrap_rois) > 0))

        return prob_positive
