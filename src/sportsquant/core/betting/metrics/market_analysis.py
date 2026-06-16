"""Market analysis utilities for betting metrics.

Provides tools for analyzing line movements, steam moves, and multi-book
correlations in sports betting markets.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
from pandas import DataFrame, Series


@dataclass(frozen=True)
class MarketAnalysisConfig:
    """Configuration for market analysis parameters."""

    min_movements_for_analysis: int = 10
    steam_threshold_pct: float = 0.05
    volume_weighted: bool = True
    multi_book_correlation_window_minutes: int = 30
    min_books_for_correlation: int = 3
    sharp_books_default: tuple[str, ...] = (
        "pinnacle",
        "betmgm",
        "draftkings",
        "caesars",
        "circa",
    )


class MarketAnalyzer:
    """Analyzer for betting market movements and patterns."""

    def __init__(self, config: MarketAnalysisConfig | None = None):
        """Initialize market analyzer with optional config.

        Args:
            config: Market analysis configuration.
        """
        self.config = config or MarketAnalysisConfig()

    def compute_line_movement_stats(self, line_movements: DataFrame) -> DataFrame:
        """Compute statistics for line movements.

        Args:
            line_movements: DataFrame with line movement data.

        Returns:
            DataFrame with movement statistics per selection/market.
        """
        if line_movements.empty:
            return DataFrame()

        stats = []
        for (selection_key, market), group in line_movements.groupby(  # type: ignore[assignment]
            ["selection_key", "market"]
        ):
            group = DataFrame(group)  # Ensure DataFrame type
            if len(group) < self.config.min_movements_for_analysis:
                continue

            sorted_group = group.sort_values("moved_at")
            line_changes = sorted_group["line"].diff().dropna()

            stats.append(
                {
                    "selection_key": selection_key,
                    "market": market,
                    "num_movements": len(group),
                    "total_movement": float(
                        sorted_group["line"].iloc[-1] - sorted_group["line"].iloc[0]
                    ),
                    "max_single_move": float(line_changes.abs().max())
                    if not line_changes.empty
                    else 0.0,
                    "avg_move_size": float(line_changes.abs().mean())
                    if not line_changes.empty
                    else 0.0,
                    "move_volatility": float(line_changes.std()) if len(line_changes) > 1 else 0.0,
                    "direction": "up"
                    if sorted_group["line"].iloc[-1] > sorted_group["line"].iloc[0]
                    else "down",
                    "first_move_time": sorted_group["moved_at"].iloc[0],
                    "last_move_time": sorted_group["moved_at"].iloc[-1],
                }
            )

        return DataFrame(stats)

    def detect_steam_moves(
        self, line_movements: DataFrame, sharp_books: list[str] | None = None
    ) -> DataFrame:
        """Detect steam moves (sharp money) in line movements.

        Args:
            line_movements: DataFrame with line movement data.
            sharp_books: List of sharp book identifiers.

        Returns:
            DataFrame of detected steam moves.
        """
        if sharp_books is None:
            sharp_books = list(self.config.sharp_books_default)

        if line_movements.empty:
            return DataFrame()

        steam_moves: list[dict[str, Any]] = []
        for (selection_key, market), group in line_movements.groupby(  # type: ignore[assignment]
            ["selection_key", "market"]
        ):
            group = DataFrame(group)  # Ensure DataFrame type
            if len(group) < self.config.min_movements_for_analysis:
                continue

            sorted_group = group.sort_values("moved_at")

            steam_moves.extend(
                self._extract_group_steam_moves(selection_key, market, sorted_group, sharp_books)
            )

        return DataFrame(steam_moves)

    def _extract_group_steam_moves(
        self,
        selection_key: str,
        market: str,
        sorted_group: DataFrame,
        sharp_books: list[str],
    ) -> list[dict[str, Any]]:
        """Extract steam moves from a group of line movements."""
        steam_moves: list[dict[str, Any]] = []

        for i, (_idx, row) in enumerate(sorted_group.iterrows()):
            if row["book"] not in sharp_books:
                continue

            subsequent = sorted_group.iloc[i + 1 :]
            move_record = self._evaluate_potential_steam_move(
                selection_key,
                market,
                row,
                subsequent,
            )
            if move_record:
                steam_moves.append(move_record)

        return steam_moves

    def _evaluate_potential_steam_move(
        self,
        selection_key: str,
        market: str,
        row: Series,
        subsequent: DataFrame,
    ) -> dict[str, Any] | None:
        """Evaluate if a row represents a steam move trigger."""
        if subsequent.empty:
            return None

        initial_line = float(row["line"])  # type: ignore[arg-type]
        direction = str(row["direction"])  # type: ignore[arg-type]
        next_line = float(subsequent["line"].iloc[0])  # type: ignore[arg-type]
        pct_change = self._calculate_pct_change(initial_line, next_line)

        if abs(pct_change) < self.config.steam_threshold_pct:
            return None

        following_books = subsequent["book"].unique().tolist()
        volume_weight = self._compute_volume_weight(subsequent)

        return {
            "selection_key": selection_key,
            "market": market,
            "trigger_book": row["book"],
            "trigger_time": row["moved_at"],
            "initial_line": initial_line,
            "trigger_direction": direction,
            "pct_change": pct_change,
            "following_books": following_books,
            "num_followers": len(following_books),
            "max_follower_move": float((subsequent["line"] - initial_line).abs().max()),
            "volume_weighted_score": abs(pct_change) * volume_weight,
            "correlation_strength": self._compute_correlation_strength(
                subsequent, float(initial_line), str(direction)
            ),
        }

    def _calculate_pct_change(self, initial_line: float, new_line: float) -> float:
        """Calculate percentage change between lines."""
        if initial_line == 0:
            return 0.0
        return (new_line - initial_line) / initial_line

    def _compute_volume_weight(self, subsequent: DataFrame) -> float:
        """Compute volume weight for steam move scoring."""
        if not self.config.volume_weighted or "volume" not in subsequent.columns:
            return 1.0

        avg_volume = float(subsequent["volume"].mean())
        return avg_volume if avg_volume > 0 else 1.0

    def _compute_correlation_strength(
        self, subsequent: DataFrame, initial_line: float, direction: str
    ) -> float:
        """Compute how strongly subsequent moves correlate with trigger."""
        if subsequent.empty or len(subsequent) < 2:
            return 0.0

        moves = subsequent["line"] - initial_line
        expected_sign = 1 if direction == "up" else -1

        aligned_moves = moves * expected_sign
        positive_moves = (aligned_moves > 0).sum()
        total_moves = len(aligned_moves)

        return positive_moves / total_moves if total_moves > 0 else 0.0

    def detect_multi_book_correlation(
        self, line_movements: DataFrame, window_minutes: int | None = None
    ) -> DataFrame:
        """Detect when multiple books move in the same direction.

        Args:
            line_movements: DataFrame with line movement data.
            window_minutes: Time window for correlation analysis.

        Returns:
            DataFrame of detected multi-book correlations.
        """
        window_minutes = window_minutes or self.config.multi_book_correlation_window_minutes

        if line_movements.empty:
            return DataFrame()

        correlations = []
        line_movements = line_movements.copy()
        line_movements["moved_at"] = pd.to_datetime(line_movements["moved_at"])

        for (selection_key, market), group in line_movements.groupby(  # type: ignore[assignment]
            ["selection_key", "market"]
        ):
            group = DataFrame(group)  # Ensure DataFrame type
            if len(group) < self.config.min_books_for_correlation:
                continue

            group = group.sort_values(by="moved_at")

            books_moving = group.groupby("book").size()
            if len(books_moving) < self.config.min_books_for_correlation:
                continue

            window_start = group["moved_at"].max() - pd.Timedelta(minutes=window_minutes)
            window_group = group[group["moved_at"] >= window_start]

            if len(window_group) < self.config.min_books_for_correlation:
                continue

            direction_counts = window_group["direction"].value_counts()  # type: ignore[union-attr]
            dominant_direction = direction_counts.idxmax()
            max_agreement = direction_counts.max() / len(window_group)

            if max_agreement >= 0.7:
                correlations.append(
                    {
                        "selection_key": selection_key,
                        "market": market,
                        "correlation_type": "multi_book",
                        "direction": dominant_direction,
                        "agreement_pct": max_agreement,
                        "books_involved": len(set(window_group["book"].tolist())),  # type: ignore[union-attr]
                        "time_window_minutes": window_minutes,
                        "window_start": window_start,
                        "window_end": group["moved_at"].max(),
                        "total_movements": len(window_group),
                    }
                )

        return DataFrame(correlations)

    def detect_book_hierarchy(self, odds_df: DataFrame) -> dict:
        """Detect bookmaker hierarchy (leaders vs followers).

        Args:
            odds_df: DataFrame with odds data from multiple books.

        Returns:
            Dictionary with book hierarchy and correlations.
        """
        if odds_df.empty:
            return {}

        books = odds_df["book"].unique()

        if len(books) < 2:
            return {}

        book_correlations = self._compute_all_book_correlations(odds_df, books)
        hierarchy = self._build_hierarchy(book_correlations)

        return hierarchy

    def _compute_all_book_correlations(
        self, odds_df: DataFrame, books: Any
    ) -> dict[str, dict[str, float]]:
        """Compute correlation between all pairs of books."""
        book_correlations: dict[str, dict[str, float]] = {}

        for book in books:
            correlations = self._compute_book_correlations(odds_df, books, book)
            book_correlations[book] = correlations

        return book_correlations

    def _compute_book_correlations(
        self, odds_df: DataFrame, books: Any, book: str
    ) -> dict[str, float]:
        """Compute correlations for a single book against all others."""
        correlations: dict[str, float] = {}

        book_data = DataFrame(odds_df[odds_df["book"] == book].copy())
        book_data.sort_values(by="updated_at", inplace=True)
        book_data["line_change"] = book_data.groupby("selection_key")["line"].diff()

        for other_book in books:
            if other_book == book:
                continue

            corr = self._compute_pair_correlation(book_data, odds_df, book, other_book)
            if corr is not None:
                correlations[other_book] = corr

        return correlations

    def _compute_pair_correlation(
        self,
        book_data: DataFrame,
        odds_df: DataFrame,
        book: str,
        other_book: str,
    ) -> float | None:
        """Compute correlation between two books, returning None if insufficient data."""
        other_data = DataFrame(odds_df[odds_df["book"] == other_book].copy())
        other_data.sort_values(by="updated_at", inplace=True)
        other_data["line_change"] = other_data.groupby("selection_key")["line"].diff()

        merged = book_data[["selection_key", "line_change", "updated_at"]].merge(
            other_data[["selection_key", "line_change", "updated_at"]],
            on=["selection_key", "updated_at"],
            suffixes=(f"_{book}", f"_{other_book}"),
        )

        if len(merged) <= 10:
            return 0.0

        book_col = Series(merged[f"line_change_{book}"]).dropna()
        other_col = Series(merged[f"line_change_{other_book}"]).dropna()

        if len(book_col) < 2 or len(other_col) < 2:
            return 0.0

        if book_col.std() == 0 or other_col.std() == 0:
            return 0.0

        corr = book_col.corr(other_col)
        return float(corr) if not pd.isna(corr) else 0.0

    def _build_hierarchy(self, book_correlations: dict[str, dict[str, float]]) -> dict:
        """Build hierarchy classification from book correlations."""
        hierarchy = {"leaders": [], "followers": [], "independent": []}

        for book, correlations in book_correlations.items():
            role = self._classify_book_role(correlations)
            hierarchy[role].append(book)

        hierarchy["correlations"] = book_correlations  # type: ignore[arg-type]
        return hierarchy

    def _classify_book_role(self, correlations: dict[str, float]) -> str:
        """Classify a book as leader, follower, or independent based on correlations."""
        outgoing = sum(1 for c in correlations.values() if c > 0.3)
        incoming = sum(1 for c in correlations.values() if c < -0.3)

        if outgoing > incoming:
            return "leaders"
        if incoming > outgoing:
            return "followers"
        return "independent"

    def compute_clv_by_book(self, bets_df: DataFrame, book_col: str = "book") -> DataFrame:
        """Compute closing line value (CLV) statistics by book.

        Args:
            bets_df: DataFrame with bet records.
            book_col: Column name for book identifier.

        Returns:
            DataFrame with CLV statistics per book.
        """
        if bets_df.empty:
            return DataFrame()

        clv_stats = []
        for book, group in bets_df.groupby(book_col):
            closing_line = group["closing_line"]
            bet_odds = group["odds"]
            clv = (closing_line - bet_odds) / bet_odds
            hits = group["result"] == 1

            clv_stats.append(
                {
                    "book": book,
                    "num_bets": len(group),
                    "win_rate": hits.mean(),
                    "avg_clv": clv.mean(),
                    "clv_std": clv.std(),
                    "clv_median": clv.median(),
                    "market_beating_rate": (clv > 0).mean(),
                    "total_profit": (group["result"] * group["payout"] - group["stake"]).sum(),
                    "roi_pct": (
                        (group["result"] * group["payout"] - group["stake"]).sum()
                        / group["stake"].sum()
                        * 100
                    ),
                }
            )

        return DataFrame(clv_stats)

    def generate_steam_signals(
        self, line_movements: DataFrame, current_odds: DataFrame
    ) -> DataFrame:
        """Generate trading signals from detected steam moves.

        Args:
            line_movements: DataFrame with historical line movements.
            current_odds: DataFrame with current odds.

        Returns:
            DataFrame with steam move signals.
        """
        steam_moves = self.detect_steam_moves(line_movements)

        if steam_moves.empty:
            return DataFrame()

        signals = steam_moves.merge(
            current_odds[["selection_key", "line", "price_american", "book"]],
            on="selection_key",
            how="left",
        )

        signals["signal_strength"] = signals["num_followers"] * abs(signals["pct_change"])

        signals = signals.sort_values("signal_strength", ascending=False)

        return signals
