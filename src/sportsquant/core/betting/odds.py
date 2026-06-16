"""Odds conversion utilities for betting calculations.

Provides the Odds dataclass for handling American and decimal odds
with conversion methods and implied probability calculations.
"""

from __future__ import annotations

from dataclasses import dataclass


__all__ = ["Odds"]


@dataclass(frozen=True)
class Odds:
    """Odds container.

    Supports either:
      - American odds (e.g. -110, +125)
      - Decimal odds (e.g. 1.91)
    """

    american: int | None = None
    decimal: float | None = None

    def to_decimal(self) -> float:
        """Convert odds to decimal format.

        Returns:
            Decimal odds as a float.

        Raises:
            ValueError: If neither odds type is provided or decimal <= 1.0.
        """
        if self.decimal is not None:
            if self.decimal <= 1.0:
                raise ValueError("decimal odds must be > 1.0")
            return float(self.decimal)
        if self.american is None:
            raise ValueError("either american or decimal odds must be provided")
        a = int(self.american)
        if a == 0:
            raise ValueError("american odds cannot be 0")
        if a > 0:
            return 1.0 + (a / 100.0)
        return 1.0 + (100.0 / abs(a))

    def implied_prob(self) -> float:
        """Calculate implied probability from decimal odds.

        Returns:
            Implied probability as a float between 0 and 1.
        """
        d = self.to_decimal()
        return 1.0 / d
