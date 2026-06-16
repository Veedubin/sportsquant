"""Distribution models for P(X >= N) probability calculations.

This module provides probability distribution classes for calculating
the probability that a player's stat exceeds a threshold (alternate lines).
Used for evaluating props like "Will player score 10+ points?".
"""

import math
from abc import ABC, abstractmethod
from typing import Optional

import numpy as np
from scipy import stats
from scipy.stats import gamma, lognorm, nbinom


def clamp(x: float, lo: float, hi: float) -> float:
    """Clamp value to range [lo, hi]."""
    return max(lo, min(hi, x))


class BaseDistribution(ABC):
    """Abstract base class for distribution models."""

    @abstractmethod
    def probability(self, threshold: float) -> float:
        """Calculate P(X >= threshold)."""

    @abstractmethod
    def sample(self, n: int = 1) -> list[float]:
        """Generate random samples."""

    @abstractmethod
    def fit_quality(self) -> float:
        """Return fit quality score (0-1, higher is better)."""


class EmpiricalCDF(BaseDistribution):
    """Empirical cumulative distribution function from historical data.

    Uses the empirical distribution directly - most accurate when
    sufficient data is available.
    """

    def __init__(self, observations: list[float]):
        """Initialize with historical observations.

        Args:
            observations: List of historical stat values
        """
        if not observations:
            raise ValueError("Empty observations list")

        self.observations = np.array(sorted(observations))
        self.n = len(self.observations)

        # Precompute for efficiency
        self._min = self.observations.min()
        self._max = self.observations.max()
        self._mean = self.observations.mean()
        self._std = self.observations.std()

    def probability(self, threshold: float) -> float:
        """Calculate P(X >= threshold) from empirical data.

        Args:
            threshold: The threshold to exceed

        Returns:
            Probability that X >= threshold (0 to 1)
        """
        if threshold <= 0:
            return 1.0

        # Count how many observations are >= threshold
        count_above = np.sum(self.observations >= threshold)
        return count_above / self.n

    def sample(self, n: int = 1) -> list[float]:
        """Generate random samples from empirical distribution.

        Args:
            n: Number of samples

        Returns:
            List of sampled values
        """
        indices = np.random.randint(0, self.n, size=n)
        return self.observations[indices].tolist()

    def fit_quality(self) -> float:
        """Return fit quality based on sample size.

        Returns:
            Fit quality score (0-1)
        """
        # More data = better empirical fit
        if self.n >= 30:
            return 0.95
        elif self.n >= 20:
            return 0.85
        elif self.n >= 15:
            return 0.75
        return 0.5

    def get_ecdf_value(self, threshold: float) -> float:
        """Get CDF value P(X <= threshold).

        Args:
            threshold: Threshold value

        Returns:
            Probability that X <= threshold
        """
        return 1.0 - self.probability(threshold)


class GammaDistribution(BaseDistribution):
    """Gamma distribution for bounded positive variables.

    Good for stats like rebounds, assists, blocks, steals that are
    bounded at zero and have right-skewed distributions.
    """

    def __init__(self, observations: list[float]):
        """Fit Gamma distribution to data.

        Args:
            observations: List of historical stat values
        """
        if not observations:
            raise ValueError("Empty observations list")

        data = np.array(observations)

        # Remove zeros and negative values for fitting
        positive_data = data[data > 0]
        if len(positive_data) < 2:
            # Fall back to empirical if not enough positive data
            positive_data = data

        # Fit Gamma distribution
        # Use method of moments
        self._mean = positive_data.mean()
        self._var = positive_data.var()

        # Handle edge case of zero or very small variance
        # This indicates essentially constant data
        self._zero_variance = self._var < 1e-10

        if self._zero_variance:
            if self._mean > 0:
                self._var = self._mean * 0.1  # Assume 10% CV
            else:
                self._var = 1.0
                self._mean = 1.0

        # Calculate shape and scale parameters
        # Gamma: mean = shape * scale, var = shape * scale^2
        shape = (self._mean**2) / self._var
        scale = self._var / self._mean

        # Ensure valid parameters
        self.shape = max(0.01, shape) if shape > 0 else 1.0
        self.scale = max(0.01, scale) if scale > 0 else self._mean if self._mean > 0 else 1.0

        # Store for sampling
        self._positive_data = positive_data

    def probability(self, threshold: float) -> float:
        """Calculate P(X >= threshold) using Gamma CDF.

        Args:
            threshold: The threshold to exceed

        Returns:
            Probability that X >= threshold (0 to 1)
        """
        if threshold <= 0:
            return 1.0

        # Handle zero variance case - all observations are the same
        if self._zero_variance:
            # All values equal to _mean (before adjustment)
            # P(X >= threshold) = 1 if threshold <= constant value, else 0
            # We use the original mean (stored in _positive_data)
            constant_value = self._positive_data.mean()
            if threshold <= constant_value:
                return 1.0
            else:
                return 0.0

        try:
            # P(X >= threshold) = 1 - P(X < threshold) = 1 - CDF(threshold)
            prob = 1.0 - gamma.cdf(threshold, self.shape, scale=self.scale)
            return clamp(prob, 0.0, 1.0)
        except Exception:
            return 0.5

    def sample(self, n: int = 1) -> list[float]:
        """Generate random samples from Gamma distribution.

        Args:
            n: Number of samples

        Returns:
            List of sampled values
        """
        samples = gamma.rvs(self.shape, scale=self.scale, size=n)
        # Ensure non-negative (Gamma can theoretically produce zeros)
        return [max(0.0, float(s)) for s in samples]

    def fit_quality(self) -> float:
        """Return fit quality based on KS test.

        Returns:
            Fit quality score (0-1)
        """
        try:
            # Perform KS test
            ks_stat, ks_pval = stats.kstest(
                self._positive_data,
                "gamma",
                args=(self.shape, 0, self.scale),
            )
            # Higher p-value = better fit
            return clamp(ks_pval, 0.0, 1.0)
        except Exception:
            return 0.5


class LogNormalDistribution(BaseDistribution):
    """LogNormal distribution for skewed continuous data.

    Good for points, minutes, and other stats that are always positive
    and tend to have right-skewed distributions.
    """

    def __init__(self, observations: list[float]):
        """Fit LogNormal distribution to data.

        Args:
            observations: List of historical stat values
        """
        if not observations:
            raise ValueError("Empty observations list")

        data = np.array(observations)

        # Filter to positive values for log transformation
        positive_data = data[data > 0]
        if len(positive_data) < 2:
            positive_data = data

        # Fit in log space
        log_data = np.log(positive_data + 1e-10)

        # LogNormal parameters: the underlying normal has these stats
        self._mu = log_data.mean()
        self._sigma = log_data.std()

        # Ensure valid sigma
        if self._sigma <= 0:
            self._sigma = 0.5

        # For scipy lognorm: s = sigma, scale = exp(mu)
        self.s = self._sigma
        self.scale = math.exp(self._mu)

        self._positive_data = positive_data

    def probability(self, threshold: float) -> float:
        """Calculate P(X >= threshold) using LogNormal CDF.

        Args:
            threshold: The threshold to exceed

        Returns:
            Probability that X >= threshold (0 to 1)
        """
        if threshold <= 0:
            return 1.0

        try:
            # P(X >= threshold) = 1 - P(X < threshold)
            prob = 1.0 - lognorm.cdf(threshold, self.s, scale=self.scale)
            return clamp(prob, 0.0, 1.0)
        except Exception:
            return 0.5

    def sample(self, n: int = 1) -> list[float]:
        """Generate random samples from LogNormal distribution.

        Args:
            n: Number of samples

        Returns:
            List of sampled values
        """
        samples = lognorm.rvs(self.s, scale=self.scale, size=n)
        return [max(0.0, float(s)) for s in samples]

    def fit_quality(self) -> float:
        """Return fit quality based on KS test.

        Returns:
            Fit quality score (0-1)
        """
        try:
            # Perform KS test in log space
            ks_stat, ks_pval = stats.kstest(
                np.log(self._positive_data + 1e-10),
                "norm",
                args=(self._mu, self._sigma),
            )
            return clamp(ks_pval, 0.0, 1.0)
        except Exception:
            return 0.5


class NegativeBinomialDistribution(BaseDistribution):
    """Negative Binomial for count data with overdispersion.

    Good for count statistics (rebounds, assists, etc.) when there's
    overdispersion relative to Poisson, or when sample size is small.
    """

    def __init__(self, observations: list[float]):
        """Fit Negative Binomial to data.

        Uses method of moments estimation.

        Args:
            observations: List of historical stat values
        """
        if not observations:
            raise ValueError("Empty observations list")

        data = np.array(observations)
        self._mean = data.mean()
        self._var = data.var()

        # Handle edge cases
        if self._mean <= 0:
            self._mean = 1.0
        if self._var <= self._mean:
            # Add small amount of overdispersion to ensure var > mean
            self._var = self._mean + 0.1 * max(1.0, self._mean**2)

        # Negative Binomial parameterization for scipy:
        # nbinom.fit returns n (number of successes) and p (probability)
        # Using method of moments:
        # mean = n * (1-p) / p => p = n / (n + mean)
        # var = n * (1-p) / p^2 => var = mean + mean^2 / n
        # So: n = mean^2 / (var - mean)

        denom = self._var - self._mean
        n = max(0.1, (self._mean**2) / denom) if denom > 0 else 1.0
        p = min(0.99, max(0.01, n / (n + self._mean)))

        self.n = n
        self.p = p

        self._positive_data = data[data >= 0]

    def probability(self, threshold: float) -> float:
        """Calculate P(X >= threshold) using Negative Binomial CDF.

        Args:
            threshold: The threshold to exceed

        Returns:
            Probability that X >= threshold (0 to 1)
        """
        if threshold <= 0:
            return 1.0

        try:
            # P(X >= k) = 1 - P(X <= k-1) for discrete distribution
            k = int(threshold)
            if k <= 0:
                return 1.0
            # Use survival function: P(X > k-1) = 1 - CDF(k-1)
            prob = 1.0 - nbinom.cdf(k - 1, self.n, self.p)
            return clamp(prob, 0.0, 1.0)
        except Exception:
            return 0.5

    def sample(self, n: int = 1) -> list[float]:
        """Generate random samples from Negative Binomial distribution.

        Args:
            n: Number of samples

        Returns:
            List of sampled values
        """
        samples = nbinom.rvs(self.n, self.p, size=n)
        return [float(max(0, int(s))) for s in samples]

    def fit_quality(self) -> float:
        """Return fit quality based on KS test.

        Returns:
            Fit quality score (0-1)
        """
        try:
            ks_stat, ks_pval = stats.kstest(
                self._positive_data,
                "nbinom",
                args=(self.n, self.p),
            )
            return clamp(ks_pval, 0.0, 1.0)
        except Exception:
            return 0.5


class DistributionSelector:
    """Auto-select best distribution based on data characteristics.

    Selection logic:
    1. If n >= 15: Use EmpiricalCDF as primary
    2. If n < 15: Use parametric fallback
       - For count data (rebounds, assists, blocks, steals): GammaDistribution
       - For skewed continuous (points): LogNormalDistribution
       - For binary/count with overdispersion: NegativeBinomialDistribution
    3. If EmpiricalCDF has all observations >= threshold or all < threshold:
       use parametric to avoid 0.0/1.0 extremes
    """

    # Stat types that are typically count data
    COUNT_STATS = {"rebounds", "assists", "blocks", "steals", "turnovers", "fouls"}
    # Stat types that are typically skewed continuous
    SKEWED_STATS = {"points", "minutes", "pts", "reb", "ast", "fgm", "fgm", "fg3m", "ftm"}

    def __init__(self, observations: list[float], stat_type: Optional[str] = None):
        """Initialize and select best distribution.

        Args:
            observations: List of historical stat values
            stat_type: Optional canonical stat key for better selection
        """
        if not observations:
            raise ValueError("Empty observations list")

        self.observations = list(observations)
        self.stat_type = stat_type or ""
        self.n = len(self.observations)

        # Compute basic statistics
        self._mean = np.mean(self.observations)
        self._std = np.std(self.observations)
        self._cv = self._std / self._mean if self._mean > 0 else 1.0

        # Fit all candidate distributions
        self._empirical = EmpiricalCDF(self.observations)

        self._gamma = None
        self._lognormal = None
        self._nbinom = None

        self._fit_parametric_distributions()

        # Select best distribution
        self._selected: Optional[BaseDistribution] = None
        self._selected_type: str = ""
        self._select_distribution()

    def _fit_parametric_distributions(self) -> None:
        """Fit all parametric distributions."""
        try:
            self._gamma = GammaDistribution(self.observations)
        except Exception:
            self._gamma = None

        try:
            self._lognormal = LogNormalDistribution(self.observations)
        except Exception:
            self._lognormal = None

        try:
            self._nbinom = NegativeBinomialDistribution(self.observations)
        except Exception:
            self._nbinom = None

    def _select_distribution(self) -> None:
        """Select the best distribution based on data characteristics."""
        stat_lower = self.stat_type.lower()

        # Rule 1: If n >= 15, prefer EmpiricalCDF unless extreme
        if self.n >= 15:
            self._selected = self._empirical
            self._selected_type = "empirical"
            return

        # Rule 2: For small samples, use parametric
        # Count stats -> Gamma
        if any(cs in stat_lower for cs in self.COUNT_STATS):
            if self._gamma is not None:
                self._selected = self._gamma
                self._selected_type = "gamma"
                return

        # Skewed continuous -> LogNormal
        if any(ss in stat_lower for ss in self.SKEWED_STATS):
            if self._lognormal is not None:
                self._selected = self._lognormal
                self._selected_type = "lognormal"
                return

        # Default fallback: try Gamma, then LogNormal, then NBiom
        if self._gamma is not None:
            self._selected = self._gamma
            self._selected_type = "gamma"
            return

        if self._lognormal is not None:
            self._selected = self._lognormal
            self._selected_type = "lognormal"
            return

        if self._nbinom is not None:
            self._selected = self._nbinom
            self._selected_type = "negative_binomial"
            return

        # Ultimate fallback
        self._selected = self._empirical
        self._selected_type = "empirical"

    def probability(self, threshold: float) -> float:
        """Calculate P(X >= threshold) using best distribution.

        Also checks for extreme cases (all above or all below threshold)
        and uses parametric extrapolation in those cases.

        Args:
            threshold: The threshold to exceed

        Returns:
            Probability that X >= threshold (0 to 1)
        """
        if threshold <= 0:
            return 1.0

        # Check for extreme empirical cases
        emp_prob = self._empirical.probability(threshold)

        # If empirical gives 0 or 1, use parametric for extrapolation
        if emp_prob == 0.0 or emp_prob == 1.0:
            # Use the selected parametric distribution
            if self._selected is not None and self._selected_type != "empirical":
                return self._selected.probability(threshold)
            elif self._gamma is not None:
                return self._gamma.probability(threshold)
            elif self._lognormal is not None:
                return self._lognormal.probability(threshold)
            elif self._nbinom is not None:
                return self._nbinom.probability(threshold)

        # Use the selected distribution
        if self._selected is not None:
            return self._selected.probability(threshold)

        # Fallback to empirical
        return emp_prob

    def sample(self, n: int = 1) -> list[float]:
        """Generate random samples from selected distribution.

        Args:
            n: Number of samples

        Returns:
            List of sampled values
        """
        if self._selected is not None:
            return self._selected.sample(n)
        return self._empirical.sample(n)

    def get_selected_type(self) -> str:
        """Return name of selected distribution.

        Returns:
            Distribution type name
        """
        return self._selected_type

    def get_fit_quality(self) -> float:
        """Return fit quality of selected distribution.

        Returns:
            Fit quality score (0-1)
        """
        if self._selected is not None:
            return self._selected.fit_quality()
        return 0.0

    def get_all_probabilities(self, threshold: float) -> dict:
        """Get probabilities from all distributions for comparison.

        Args:
            threshold: The threshold to evaluate

        Returns:
            Dict mapping distribution name to probability
        """
        result = {"empirical": self._empirical.probability(threshold)}

        if self._gamma is not None:
            result["gamma"] = self._gamma.probability(threshold)
        if self._lognormal is not None:
            result["lognormal"] = self._lognormal.probability(threshold)
        if self._nbinom is not None:
            result["negative_binomial"] = self._nbinom.probability(threshold)

        return result

    def coefficient_of_variation(self) -> float:
        """Return coefficient of variation.

        Returns:
            CV = std / mean
        """
        return self._cv

    def historical_hit_rate(self, threshold: float) -> float:
        """Calculate historical hit rate at threshold.

        Args:
            threshold: The threshold to check

        Returns:
            Historical proportion of observations >= threshold
        """
        return self._empirical.probability(threshold)
