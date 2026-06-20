"""Implied probability calculation utilities.

Provides methods to convert bookmaker odds to true probabilities,
including multiplicative, additive, Shin, and power methods for
margin removal and longshot bias correction.
"""

from __future__ import annotations

from pandas import Series


__all__ = ["ImpliedOddsCalculator"]


class ImpliedOddsCalculator:
    """Calculate true probabilities from bookmaker odds."""

    def multiplicative(self, odds: Series) -> Series:
        """Simple 1/odds (underestimates true prob)."""
        return 1.0 / odds

    def additive(self, odds: Series) -> Series:
        """Distribute margin equally."""
        prob = 1.0 / odds
        margin = prob.sum() - 1.0
        adjusted = prob - margin / len(prob)
        return adjusted.clip(lower=0.0)

    def shin(self, odds: Series) -> tuple[Series, float]:
        """Shin's method - information-theoretic margin removal."""
        prob = 1.0 / odds
        total = prob.sum()
        if total <= 1.0:
            return prob, 0.0
        z = (total - 1.0) / (total + 1.0)
        return prob / (1.0 + z), z

    def power(self, odds: Series) -> Series:
        """Power method for longshot bias correction."""
        prob = 1.0 / odds
        total = prob.sum()
        normalized = prob / total
        powered = normalized**0.5
        return powered / powered.sum()
