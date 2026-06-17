"""NFL middling detection.

A "middle" occurs when two books offer materially different lines on the
same market. By betting each side at the more favorable book you can win
both bets if the final value lands between the two lines.

Adapted from Old-Files/nfl-data-agg (detect_middling), rewritten on top of
pandas for SportsQuant's DataFrame conventions.

Spread middle example:
    Book A: home -3.5  → bet home -3.5
    Book B: home -7    → bet away +7
    If final margin is 4-6 points, both bets win.

Total middle example:
    Book A: total 41.5 (Over)  → bet Over 41.5
    Book B: total 48   (Under) → bet Under 48
    If final total is 42-47 points, both bets win.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class MiddleOpportunity:
    """Container for a single middling opportunity."""

    market: str  # "spread" or "total"
    game_id: str
    low_line: float
    low_book: str
    high_line: float
    high_book: str
    middle_points: float

    def to_dict(self) -> dict[str, object]:
        """Convert to dictionary."""
        return {
            "market": self.market,
            "game_id": self.game_id,
            "low_line": self.low_line,
            "low_book": self.low_book,
            "high_line": self.high_line,
            "high_book": self.high_book,
            "middle_points": self.middle_points,
        }


def _empty_middles_df() -> pd.DataFrame:
    """Return canonical empty middles DataFrame."""
    return pd.DataFrame(
        columns=[
            "market",
            "game_id",
            "low_line",
            "low_book",
            "high_line",
            "high_book",
            "middle_points",
        ]
    )


def detect_spread_middles(
    df: pd.DataFrame,
    *,
    min_middle_points: float = 1.0,
) -> pd.DataFrame:
    """Find spread middling opportunities.

    For each game, identify the book with the highest spread_home line
    (home favored most) and the book with the lowest (home favored least).
    If the gap between them exceeds ``min_middle_points``, it's a middle.

    Args:
        df: DataFrame with columns ``game_id``, ``spread_home``, ``source_id``.
            ``spread_home`` is positive when home is favored (Pinnacle / Odds API
            convention; transform sign if your source stores the opposite).
        min_middle_points: Minimum gap between the two best lines to count.

    Returns:
        DataFrame of middling opportunities with columns:
        ``game_id``, ``low_line``, ``low_book``, ``high_line``,
        ``high_book``, ``middle_points``, ``market`` (``"spread"``).
    """
    if df.empty or "game_id" not in df.columns:
        return _empty_middles_df()

    needed = {"spread_home", "source_id"}
    if not needed.issubset(df.columns):
        return _empty_middles_df()

    work = df[["game_id", "spread_home", "source_id"]].dropna(subset=["spread_home"])
    if work.empty:
        return _empty_middles_df()

    # Best for home bettors: highest (least negative) spread
    best_home = (
        work.sort_values(["game_id", "spread_home"], ascending=[True, False])
        .groupby("game_id", as_index=False)
        .first()
        .rename(columns={"spread_home": "high_line", "source_id": "high_book"})
    )
    # Best for away bettors: lowest spread (home favored most → best for away +)
    best_away = (
        work.sort_values(["game_id", "spread_home"], ascending=[True, True])
        .groupby("game_id", as_index=False)
        .first()
        .rename(columns={"spread_home": "low_line", "source_id": "low_book"})
    )

    joined = best_home.merge(best_away, on="game_id", how="inner")
    if joined.empty:
        return _empty_middles_df()

    joined["middle_points"] = joined["high_line"] - joined["low_line"]
    joined["market"] = "spread"
    joined = joined[joined["middle_points"] >= min_middle_points]

    if joined.empty:
        return _empty_middles_df()

    return joined[
        [
            "market",
            "game_id",
            "low_line",
            "low_book",
            "high_line",
            "high_book",
            "middle_points",
        ]
    ].reset_index(drop=True)


def detect_total_middles(
    df: pd.DataFrame,
    *,
    min_middle_points: float = 1.0,
) -> pd.DataFrame:
    """Find total middling opportunities.

    For each game, identify the book with the lowest total (best for Over)
    and the book with the highest total (best for Under). If the gap exceeds
    ``min_middle_points``, it's a middle.

    Args:
        df: DataFrame with columns ``game_id``, ``total``, ``source_id``.
        min_middle_points: Minimum gap between the two best lines to count.

    Returns:
        DataFrame of middling opportunities.
    """
    if df.empty or "game_id" not in df.columns:
        return _empty_middles_df()

    needed = {"total", "source_id"}
    if not needed.issubset(df.columns):
        return _empty_middles_df()

    work = df[["game_id", "total", "source_id"]].dropna(subset=["total"])
    if work.empty:
        return _empty_middles_df()

    # Lowest total → best for Over bettors
    lowest = (
        work.sort_values(["game_id", "total"], ascending=[True, True])
        .groupby("game_id", as_index=False)
        .first()
        .rename(columns={"total": "low_line", "source_id": "low_book"})
    )
    # Highest total → best for Under bettors
    highest = (
        work.sort_values(["game_id", "total"], ascending=[True, False])
        .groupby("game_id", as_index=False)
        .first()
        .rename(columns={"total": "high_line", "source_id": "high_book"})
    )

    joined = lowest.merge(highest, on="game_id", how="inner")
    if joined.empty:
        return _empty_middles_df()

    joined["middle_points"] = joined["high_line"] - joined["low_line"]
    joined["market"] = "total"
    joined = joined[joined["middle_points"] >= min_middle_points]

    if joined.empty:
        return _empty_middles_df()

    return joined[
        [
            "market",
            "game_id",
            "low_line",
            "low_book",
            "high_line",
            "high_book",
            "middle_points",
        ]
    ].reset_index(drop=True)


def detect_middles(
    df: pd.DataFrame,
    *,
    min_middle_points: float = 1.0,
) -> pd.DataFrame:
    """Detect both spread and total middles, return concatenated results.

    Args:
        df: DataFrame containing spread_home and/or total columns.
        min_middle_points: Minimum gap to count.

    Returns:
        DataFrame with both spread and total middles, empty schema if none.
    """
    spreads = detect_spread_middles(df, min_middle_points=min_middle_points)
    totals = detect_total_middles(df, min_middle_points=min_middle_points)
    if spreads.empty and totals.empty:
        return _empty_middles_df()
    if spreads.empty:
        return totals.reset_index(drop=True)
    if totals.empty:
        return spreads.reset_index(drop=True)
    return pd.concat([spreads, totals], ignore_index=True)
