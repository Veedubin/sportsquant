"""Name normalization utilities for player matching.

Provides consistent name normalization across the application.
"""

from __future__ import annotations

import re


def normalize_name(s: str) -> str:
    """Normalize player name for matching.

    Strips whitespace, lowercases, removes non-alphanumeric characters
    (except spaces, hyphens, apostrophes), and removes generational suffixes.

    Args:
        s: Raw player name string.

    Returns:
        Normalized name string suitable for comparison.
    """
    s = (s or "").strip().lower().replace("\u2019", "'")
    s = re.sub(r"[^a-z0-9\s'-]", " ", s)
    s = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b.?", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+", " ", s).strip()
    return s
