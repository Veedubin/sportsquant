"""Shared time/date helpers for Quant-Sports."""

from __future__ import annotations

from datetime import datetime, timezone


def utc_now_iso() -> str:
    """Return current UTC time as ISO 8601 string with Z suffix.

    Example:
        >>> utc_now_iso()
        '2026-06-17T09:30:00Z'
    """
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def safe_float(value: object) -> float | None:
    """Safely coerce a value to float, returning None on failure.

    Used by odds normalization layers to handle missing or malformed
    numeric fields without raising.
    """
    if value is None:
        return None
    if isinstance(value, str) and value.strip() == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def american_to_implied_prob(odds_american: float | int | None) -> float | None:
    """Convert American odds to implied probability.

    Args:
        odds_american: American odds (e.g. +150 or -120).

    Returns:
        Implied probability in [0, 1] or None if conversion fails.

    Example:
        >>> american_to_implied_prob(-110)
        0.5238095238095238
        >>> american_to_implied_prob(150)
        0.4
    """
    if odds_american is None:
        return None
    try:
        o = float(odds_american)
    except (TypeError, ValueError):
        return None
    if o == 0:
        return None
    if o > 0:
        return 100.0 / (o + 100.0)
    return (-o) / ((-o) + 100.0)
