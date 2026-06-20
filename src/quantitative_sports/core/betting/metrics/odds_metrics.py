"""Odds representation and conversion utilities.

Provides the Odds dataclass for representing American and decimal odds,
with methods to convert between formats and calculate implied probabilities.
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
            Decimal odds value.

        Raises:
            ValueError: If odds are invalid or zero.
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
        """Calculate implied probability from odds.

        Returns:
            Implied probability as a value between 0 and 1.
        """
        d = self.to_decimal()
        return 1.0 / d
