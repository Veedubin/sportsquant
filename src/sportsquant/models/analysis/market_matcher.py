# TODO: Replace with direct sportsbook scraping
# Sportsbooks to scrape: DraftKings, FanDuel, BetMGM, Caesars
# These sites have public odds pages that can be scraped with Playwright/requests

"""Market odds matching and interpolation.

This module handles matching PrizePicks lines to market odds
with various interpolation methods.

Key features:
- Generic market matching logic (no external API required)
- Per-book parsing and aggregation
- Logit interpolation for lines not exactly available
- Anchor book priority (DraftKings, FanDuel)

NOTE: Market data must be provided externally via set_market_data().
This module no longer fetches data from any paid API.
"""

import math
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import numpy as np
import pandas as pd


# PrizePicks stat type to market key mapping
PP_STAT_TO_MARKET_KEY = {
    "Points": "player_points",
    "Rebounds": "player_rebounds",
    "Assists": "player_assists",
    "3-PT Made": "player_threes",
    "3PT Made": "player_threes",
    "3 Pointers Made": "player_threes",
    "3PM": "player_threes",
    "Turnovers": "player_turnovers",
    "Blocks": "player_blocks",
    "Steals": "player_steals",
    "Blocks + Steals": "player_blocks_steals",
    "Blocks+Steals": "player_blocks_steals",
    "Pts+Rebs+Asts": "player_points_rebounds_assists",
    "PRA": "player_points_rebounds_assists",
    "Pts+Rebs": "player_points_rebounds",
    "Pts+Asts": "player_points_assists",
    "Rebs+Asts": "player_rebounds_assists",
    "Fantasy Score": None,
    "Fantasy Score (Combo)": None,
}


class InterpolationMethod(Enum):
    """Method used to interpolate probability at a target line."""

    EXACT = "exact"
    INTERP_LOGIT = "interp_logit"
    NEAREST = "nearest"
    NONE = "none"


@dataclass
class LineMatch:
    """Result of matching a PrizePicks line to market odds."""

    method: InterpolationMethod
    probability: float
    line_low: float
    line_high: float
    books_all_count: int
    books_anchor_count: int


def clamp(x: float, lo: float, hi: float) -> float:
    """Clamp value to range [lo, hi]."""
    return max(lo, min(hi, x))


def safe_float(x) -> float:
    """Safely convert to float, returning NaN on failure."""
    try:
        if x is None:
            return float("nan")
        return float(x)
    except (TypeError, ValueError):
        return float("nan")


def _logit(p: float) -> float:
    """Logit function: log(p / (1 - p))."""
    eps = 1e-6
    p = clamp(float(p), eps, 1 - eps)
    return math.log(p / (1 - p))


def _sigmoid(x: float) -> float:
    """Sigmoid function: 1 / (1 + exp(-x))."""
    return 1.0 / (1.0 + math.exp(-x))


def american_to_prob(odds: float) -> float:
    """Convert American odds to implied probability.

    Args:
        odds: American odds (e.g., -110, +150)

    Returns:
        Implied probability as float between 0 and 1
    """
    if odds is None or (isinstance(odds, float) and np.isnan(odds)):
        return float("nan")
    odds = float(odds)
    if odds < 0:
        return abs(odds) / (abs(odds) + 100.0)
    return 100.0 / (odds + 100.0)


def remove_vig_two_way(p_over: float, p_under: float) -> float:
    """Remove overround/vig from two-way over/under probabilities.

    Args:
        p_over: Raw over probability
        p_under: Raw under probability

    Returns:
        Devigged over probability
    """
    if any(np.isnan([p_over, p_under])):
        return float("nan")
    s = p_over + p_under
    if s <= 0:
        return float("nan")
    return p_over / s


def normalize_name(s: str) -> str:
    """Normalize player name for matching."""
    import re

    s = (s or "").strip().lower().replace("'", "'")
    s = re.sub(r"[^a-z0-9\s'-]", " ", s)
    s = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b.?", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+", " ", s).strip()
    return s


class MarketMatcher:
    """Matches PrizePicks lines to market odds with interpolation.

    This class handles:
    - Accepting external market data (from scrapers)
    - Parsing per-book odds data
    - Aggregating with anchor book priority
    - Logit interpolation at target lines

    NOTE: This class no longer fetches data from any API.
    Market data must be provided via set_market_data() or
    by passing per_book_df directly to build_market_agg().
    """

    def __init__(
        self,
        anchor_books: Optional[set[str]] = None,
    ):
        """Initialize MarketMatcher.

        Args:
            anchor_books: Set of anchor book keys (default: draftkings, fanduel)
        """
        self.anchor_books = anchor_books or {"draftkings", "fanduel"}

        # Market data storage (set externally via set_market_data)
        self._per_book_df: pd.DataFrame = pd.DataFrame()
        self._event_map: dict = {}

    def set_market_data(
        self,
        per_book_df: pd.DataFrame,
        event_map: Optional[dict] = None,
    ) -> None:
        """Set market data from external source (e.g., sportsbook scraper).

        Args:
            per_book_df: DataFrame with columns:
                - event_id: str
                - market_key: str
                - player_name_norm: str
                - line: float
                - book: str
                - p_over_devig: float (devigged over probability)
            event_map: Optional dict mapping (date_str, team_abbr) -> (opponent_abbr, event_id)
        """
        self._per_book_df = per_book_df
        self._event_map = event_map or {}

    def parse_raw_odds_to_per_book_df(
        self,
        raw_odds: list[dict],
        markets_set: set[str],
        allow_books: Optional[set[str]] = None,
    ) -> pd.DataFrame:
        """Parse raw odds data to per-book DataFrame.

        This method accepts raw odds in generic dict format and converts
        them to the standard per-book DataFrame format.

        Args:
            raw_odds: List of raw odds dicts from sportsbook scrapers
            markets_set: Set of market keys to include
            allow_books: Optional whitelist of book keys

        Returns:
            DataFrame with columns: event_id, market_key, player_name_norm,
            line, book, p_over_devig
        """
        out = []
        for payload in raw_odds:
            if not payload:
                continue

            # Handle both single dict and list formats
            if isinstance(payload, dict) and "bookmakers" in payload:
                events_like = [payload]
            else:
                events_like = payload if isinstance(payload, list) else []

            for ev in events_like:
                eid = ev.get("id") or ev.get("event_id")
                if not eid:
                    continue
                eid = str(eid)

                for bm in ev.get("bookmakers", []) or []:
                    bkey = str(bm.get("key", ""))
                    if not bkey:
                        continue
                    if allow_books is not None and bkey not in allow_books:
                        continue

                    for mkt in bm.get("markets", []) or []:
                        mkey = mkt.get("key")
                        if mkey not in markets_set:
                            continue

                        tmp = {}
                        for o in mkt.get("outcomes", []) or []:
                            player = o.get("description") or o.get("name")
                            side = o.get("name")
                            point = o.get("point")
                            price = o.get("price")

                            if player is None or side is None or point is None or price is None:
                                continue

                            k = (normalize_name(str(player)), float(point))
                            tmp.setdefault(k, {})[str(side)] = float(price)

                        for (pn, pt), sides in tmp.items():
                            if "Over" in sides and "Under" in sides:
                                p_over = american_to_prob(sides["Over"])
                                p_under = american_to_prob(sides["Under"])
                                p_over_devig = remove_vig_two_way(p_over, p_under)

                                out.append(
                                    {
                                        "event_id": eid,
                                        "market_key": mkey,
                                        "player_name_norm": pn,
                                        "line": float(pt),
                                        "book": bkey,
                                        "p_over_devig": float(p_over_devig),
                                    }
                                )

        if not out:
            return pd.DataFrame(
                columns=[
                    "event_id",
                    "market_key",
                    "player_name_norm",
                    "line",
                    "book",
                    "p_over_devig",
                ]
            )

        return pd.DataFrame(out)

    def build_market_agg(self, per_book_df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
        """Aggregate per-book data with anchor book priority.

        Args:
            per_book_df: Optional DataFrame from parse_odds_payloads_to_per_book_df.
                If not provided, uses data set via set_market_data().

        Returns:
            DataFrame with aggregated market data including anchor book columns
        """
        df = per_book_df if per_book_df is not None else self._per_book_df

        if df.empty:
            return pd.DataFrame()

        def _books_join(x):
            return ",".join(sorted(set(map(str, x))))

        g = df.groupby(["event_id", "market_key", "player_name_norm", "line"], as_index=False)
        base = g.agg(
            all_over=("p_over_devig", "median"),
            books_all=("book", _books_join),
            books_all_count=("book", lambda x: len(set(map(str, x)))),
        )

        anc = df[df["book"].isin(self.anchor_books)].copy()
        if anc.empty:
            base["anchor_over"] = np.nan
            base["books_anchor"] = ""
            base["books_anchor_count"] = 0
            return base

        g2 = anc.groupby(["event_id", "market_key", "player_name_norm", "line"], as_index=False)
        a = g2.agg(
            anchor_over=("p_over_devig", "median"),
            books_anchor=("book", _books_join),
            books_anchor_count=("book", lambda x: len(set(map(str, x)))),
        )

        out = base.merge(a, on=["event_id", "market_key", "player_name_norm", "line"], how="left")
        out["books_anchor_count"] = out["books_anchor_count"].fillna(0).astype(int)
        out["anchor_over"] = out["anchor_over"].astype(float)
        out["books_anchor"] = out["books_anchor"].fillna("")
        return out

    def interp_prob_at_line(
        self,
        psub: pd.DataFrame,
        pp_line: float,
        prob_col: str,
    ) -> LineMatch:
        """Interpolate probability at target line using logit method.

        This is the key interpolation algorithm. For lines not exactly available,
        it interpolates in logit space between surrounding lines.

        Math: logit(p) is linear between logit(p0) and logit(p1) when the
        relationship between line and probability is modeled as logistic.

        Args:
            psub: DataFrame with player's lines and probabilities
            pp_line: Target PrizePicks line
            prob_col: Column name for probability (e.g., 'anchor_over', 'all_over')

        Returns:
            LineMatch with method, probability, and metadata
        """
        if psub.empty or prob_col not in psub.columns:
            return LineMatch(
                method=InterpolationMethod.NONE,
                probability=float("nan"),
                line_low=float("nan"),
                line_high=float("nan"),
                books_all_count=0,
                books_anchor_count=0,
            )

        # Exact match
        exact = psub[np.isclose(psub["line"].values, float(pp_line), atol=1e-9)]
        if not exact.empty:
            r = exact.iloc[0]
            return LineMatch(
                method=InterpolationMethod.EXACT,
                probability=safe_float(r.get(prob_col)),
                line_low=float(r["line"]),
                line_high=float(r["line"]),
                books_all_count=int(r.get("books_all_count", 0) or 0),
                books_anchor_count=int(r.get("books_anchor_count", 0) or 0),
            )

        # Split into below and above
        below = psub[psub["line"] < float(pp_line)]
        above = psub[psub["line"] > float(pp_line)]

        if below.empty or above.empty:
            # Use nearest
            psub2 = psub.copy()
            psub2["abs_diff"] = (psub2["line"] - float(pp_line)).abs()
            r = psub2.sort_values("abs_diff").iloc[0]
            return LineMatch(
                method=InterpolationMethod.NEAREST,
                probability=safe_float(r.get(prob_col)),
                line_low=float(r["line"]),
                line_high=float(r["line"]),
                books_all_count=int(r.get("books_all_count", 0) or 0),
                books_anchor_count=int(r.get("books_anchor_count", 0) or 0),
            )

        # Logit interpolation between surrounding lines
        low = below.iloc[-1]
        high = above.iloc[0]
        x0 = float(low["line"])
        p0 = safe_float(low.get(prob_col))
        x1 = float(high["line"])
        p1 = safe_float(high.get(prob_col))

        if np.isnan(p0) or np.isnan(p1):
            return LineMatch(
                method=InterpolationMethod.NONE,
                probability=float("nan"),
                line_low=float("nan"),
                line_high=float("nan"),
                books_all_count=0,
                books_anchor_count=0,
            )

        # Linear interpolation in logit space
        t = (float(pp_line) - x0) / (x1 - x0)
        p_hat = _sigmoid(_logit(p0) + t * (_logit(p1) - _logit(p0)))

        return LineMatch(
            method=InterpolationMethod.INTERP_LOGIT,
            probability=float(p_hat),
            line_low=x0,
            line_high=x1,
            books_all_count=int(max(low.get("books_all_count", 0), high.get("books_all_count", 0))),
            books_anchor_count=int(
                max(low.get("books_anchor_count", 0), high.get("books_anchor_count", 0))
            ),
        )
