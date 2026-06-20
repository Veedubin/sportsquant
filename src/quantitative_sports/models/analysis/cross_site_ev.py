"""Cross-Site EV Engine for mapping FanDuel alternate lines to DraftKings standard lines.

This module evaluates alternate lines (e.g., "10+ Points", "25+ Points") from FanDuel
by mapping them to DraftKings standard over/under lines and calculating expected value
using P(X >= N) probability models.

Example Usage:
    engine = CrossSiteEVEngine(
        draftkings_db_path="data/draftkings/draftkings.db",
        fanduel_db_path="data/fanduel/fanduel.db",
        cross_ref_db_path="data/cross_reference/cross_reference.db"
    )

    opportunities = engine.find_opportunities(min_ev=0.02)
    print(opportunities)
"""

import logging
import re
import sqlite3
from pathlib import Path
from typing import Optional

import pandas as pd

from quantitative_sports.models.analysis.alternate_line_eval import AlternateLineEvaluator, american_to_prob
from quantitative_sports.data.schemas.db import CrossReferenceDB
from quantitative_sports.data.schemas.player_mapping import build_player_index
from quantitative_sports.data.sources.draftkings.utils import american_to_prob as dk_american_to_prob
from quantitative_sports.data.sources.draftkings.utils import normalize_odds_string
from quantitative_sports.data.sources.draftkings.utils import remove_vig_two_way

logger = logging.getLogger(__name__)


class CrossSiteEVEngine:
    """Engine for cross-site EV calculation between FanDuel alternate lines and DraftKings standard lines.

    Maps FanDuel alternate lines (e.g., "Points 10+", "Rebounds 5.5+") to DraftKings standard
    over/under lines, then calculates expected value using probability models.
    """

    def __init__(
        self,
        draftkings_db_path: str | Path,
        fanduel_db_path: str | Path,
        cross_ref_db_path: Optional[str | Path] = None,
    ):
        """Initialize the Cross-Site EV Engine.

        Args:
            draftkings_db_path: Path to DraftKings SQLite database
            fanduel_db_path: Path to FanDuel SQLite database
            cross_ref_db_path: Optional path to cross-reference SQLite database.
                              If None, creates in-memory database.
        """
        self.dk_db_path = Path(draftkings_db_path)
        self.fd_db_path = Path(fanduel_db_path)
        self.cross_ref_db_path = Path(cross_ref_db_path) if cross_ref_db_path else None

        # Initialize connections
        self._dk_conn: Optional[sqlite3.Connection] = None
        self._fd_conn: Optional[sqlite3.Connection] = None
        self._cross_ref_db: Optional[CrossReferenceDB] = None

        # Cache for player name indices (built lazily)
        self._dk_player_index: Optional[dict] = None
        self._fd_player_index: Optional[dict] = None

    @property
    def dk_conn(self) -> sqlite3.Connection:
        """Get DraftKings database connection."""
        if self._dk_conn is None:
            self._dk_conn = sqlite3.connect(str(self.dk_db_path))
            self._dk_conn.row_factory = sqlite3.Row
        return self._dk_conn

    @property
    def fd_conn(self) -> sqlite3.Connection:
        """Get FanDuel database connection."""
        if self._fd_conn is None:
            self._fd_conn = sqlite3.connect(str(self.fd_db_path))
            self._fd_conn.row_factory = sqlite3.Row
        return self._fd_conn

    @property
    def cross_ref_db(self) -> CrossReferenceDB:
        """Get cross-reference database."""
        if self._cross_ref_db is None:
            self._cross_ref_db = CrossReferenceDB(self.cross_ref_db_path)
        return self._cross_ref_db

    def close(self) -> None:
        """Close all database connections."""
        if self._dk_conn:
            self._dk_conn.close()
            self._dk_conn = None
        if self._fd_conn:
            self._fd_conn.close()
            self._fd_conn = None
        if self._cross_ref_db:
            self._cross_ref_db.close()
            self._cross_ref_db = None

    def load_market_data(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Load DraftKings standard lines and FanDuel alternate lines.

        Returns:
            Tuple of (dk_df, fd_alternate_df):
            - dk_df: DraftKings standard lines with columns [event_id, market_key, player_name_norm, line, book, p_over_devig]
            - fd_alternate_df: FanDuel alternate lines with columns [event_id, market_key, market_name, player_name_norm, line, odds_american, is_alternate]
        """
        # Load DraftKings standard lines using to_market_dataframe
        dk_storage = self._get_dk_storage()
        dk_df = dk_storage.to_market_dataframe()
        logger.info(f"Loaded {len(dk_df)} DraftKings standard lines")

        # Load FanDuel alternate lines
        fd_alternate_df = self._load_fanduel_alternate_lines()
        logger.info(f"Loaded {len(fd_alternate_df)} FanDuel alternate lines")

        return dk_df, fd_alternate_df

    def _load_fanduel_alternate_lines(self) -> pd.DataFrame:
        """Load FanDuel alternate lines from database.

        Detects alternate lines by:
        1. market_key containing '_alternate'
        2. OR market_name containing patterns like "To Score 15+ Points"

        The threshold is extracted from the market_name (e.g., "To Score 15+ Points" -> threshold=15).

        Note: FanDuel stores odds directly on the markets table, not in outcomes.

        Returns:
            DataFrame with FanDuel alternate lines
        """
        cursor = self.fd_conn.cursor()

        # Query player prop markets directly (odds are on markets table)
        cursor.execute("""
            SELECT
                m.event_id,
                m.market_key,
                m.market_name,
                m.runner_name_norm,
                m.line,
                m.odds_american,
                m.is_alternate
            FROM markets m
            WHERE m.runner_name_norm IS NOT NULL
            AND m.odds_american IS NOT NULL
            AND m.market_key LIKE 'player_%'
            ORDER BY m.event_id, m.market_key
        """)

        rows = cursor.fetchall()

        if not rows:
            return pd.DataFrame(
                columns=[
                    "event_id",
                    "market_key",
                    "market_name",
                    "player_name_norm",
                    "line",
                    "odds_american",
                    "is_alternate",
                ]
            )

        results = []
        for row in rows:
            market_name = row["market_name"] or ""
            market_key = row["market_key"] or ""
            is_alternate = bool(row["is_alternate"])

            # Detect alternate lines by market_key pattern (e.g., player_points_alternate)
            if "_alternate" in market_key:
                is_alternate = True

            # Also detect by market name patterns
            # Examples: "To Score 15+ Points", "To Record 4+ Rebounds"
            if not is_alternate:
                is_alternate = self._is_alternate_market_name(market_name)

            # Extract threshold from market name
            threshold = self._extract_threshold_from_market_name(market_name)

            results.append(
                {
                    "event_id": row["event_id"],
                    "market_key": row["market_key"],
                    "market_name": market_name,
                    "player_name_norm": row["runner_name_norm"],
                    "line": threshold if threshold is not None else row["line"],
                    "threshold": threshold,
                    "odds_american": row["odds_american"],
                    "is_alternate": is_alternate,
                }
            )

        # Filter to only alternate lines
        df = pd.DataFrame(results)
        if df.empty:
            return df

        return df[df["is_alternate"]].reset_index(drop=True)

    def _is_alternate_market_name(self, market_name: str) -> bool:
        """Check if market name indicates an alternate line.

        Alternate lines have patterns like:
        - "To Score 15+ Points"
        - "To Record 4+ Rebounds"
        - "To Have 2+ Assists"

        Standard lines are typically just "Points O/U 10.5" or similar.

        Args:
            market_name: The market display name

        Returns:
            True if this appears to be an alternate line
        """
        if not market_name:
            return False

        name_lower = market_name.lower()

        # Alternate line patterns: "To Score X+", "To Record X+", etc.
        alternate_patterns = [
            r"to\s+(score|record|have|get)\s+\d+\+",  # "To Score 15+"
            r"\d+\+\s+(points|rebounds|assists|threes)",  # "15+ Points"
        ]

        for pattern in alternate_patterns:
            if re.search(pattern, name_lower):
                return True

        return False

    def _extract_threshold_from_market_name(self, market_name: str) -> Optional[float]:
        """Extract numeric threshold from alternate market name.

        Examples:
            "To Score 15+ Points" -> 15.0
            "To Record 4+ Rebounds" -> 4.0
            "2+ Made Threes" -> 2.0
            "To Have 3+ Assists" -> 3.0

        Args:
            market_name: The market display name

        Returns:
            The extracted threshold as float, or None if not found
        """
        if not market_name:
            return None

        # Pattern to find number followed by +
        # Examples: "15+", "4+", "2+"
        match = re.search(r"(\d+)\+", market_name)
        if match:
            return float(match.group(1))

        return None

    def _get_dk_storage(self):
        """Get DraftKings storage instance (lazily imported)."""
        from quantitative_sports.data.sources.draftkings.storage import DraftKingsStorage

        return DraftKingsStorage(self.dk_db_path)

    def _get_fd_storage(self):
        """Get FanDuel storage instance (lazily imported)."""
        from quantitative_sports.data.sources.fanduel.storage import FanDuelStorage

        return FanDuelStorage(self.fd_db_path)

    def _build_player_indices(self) -> None:
        """Build player name indices for fuzzy matching."""
        if self._dk_player_index is not None:
            return

        # Build DK player index
        cursor = self.dk_conn.cursor()
        cursor.execute(
            "SELECT DISTINCT player_name_norm FROM selections WHERE player_name_norm IS NOT NULL"
        )
        dk_players = [row["player_name_norm"] for row in cursor.fetchall()]
        self._dk_player_index = build_player_index(dk_players)

        # Build FD player index
        cursor = self.fd_conn.cursor()
        cursor.execute(
            "SELECT DISTINCT runner_name_norm FROM markets WHERE runner_name_norm IS NOT NULL"
        )
        fd_players = [row["runner_name_norm"] for row in cursor.fetchall()]
        self._fd_player_index = build_player_index(fd_players)

    def map_alternate_to_standard(self, fd_row: pd.Series) -> Optional[dict]:
        """Map a FanDuel alternate line row to DraftKings standard line.

        Maps FanDuel alternate line format (e.g., "Points 10+", "Rebounds 5.5+")
        to DraftKings standard over/under line.

        Args:
            fd_row: FanDuel market row with fields:
                - market_key: Canonical stat key (e.g., "player_points")
                - market_name: FanDuel market name (e.g., "Points 10+")
                - player_name_norm: Normalized player name
                - line: The threshold value

        Returns:
            Mapping dict with:
                - player_name_norm: Normalized player name
                - stat_key: Canonical stat key
                - fd_threshold: FanDuel alternate threshold
                - dk_line: DraftKings standard line (over/under)
                - stat_type: Parsed stat type ("points", "rebounds", etc.)
            or None if mapping fails
        """
        player_name = fd_row.get("player_name_norm")
        market_key = fd_row.get("market_key")
        market_name = fd_row.get("market_name", "")

        # Use extracted threshold from market name, not the raw line (which is 0)
        fd_threshold = fd_row.get("threshold") or fd_row.get("line")

        if not player_name or not market_key:
            return None

        # Parse the FanDuel market name to extract stat type and direction
        # Examples: "Points 10+", "Rebounds 5.5+", "Assists Over 8"
        parsed = self._parse_fanduel_market_name(market_name, market_key)
        if not parsed:
            # Fallback: use market_key directly
            stat_type = self._stat_key_to_stat_type(market_key)
        else:
            stat_type = parsed["stat_type"]

        # Find DraftKings standard line for this player/stat
        dk_line = self._find_dk_standard_line(player_name, market_key)
        if dk_line is None:
            return None

        return {
            "player_name_norm": player_name,
            "stat_key": market_key,
            "fd_threshold": fd_threshold,
            "dk_line": dk_line["line"],
            "stat_type": stat_type,
            "dk_event_id": dk_line["event_id"],
            "dk_odds": dk_line.get("odds_american"),
            "dk_p_over": dk_line.get("p_over_devig"),
        }

    def _parse_fanduel_market_name(self, market_name: str, market_key: str) -> Optional[dict]:
        """Parse FanDuel alternate market name to extract stat type and threshold.

        Args:
            market_name: Market display name (e.g., "Points 10+", "Over 25 Points")
            market_key: Canonical market key

        Returns:
            Dict with stat_type, threshold, direction ("over"/"under"), or None
        """
        if not market_name:
            return None

        name_lower = market_name.lower().strip()

        # Pattern 1: "Points 10+", "Rebounds 5.5+", "Assists 8+"
        # Pattern 2: "Over 25 Points", "Under 10.5 Rebounds"
        # Pattern 3: "Points Over 10", "Rebounds Under 5"

        # Try pattern 1: "stat value+" or "stat value-"
        match = re.match(r"(\w+)\s*([\d.]+)\s*([+-])", name_lower)
        if match:
            stat_type = match.group(1).rstrip("s")  # Remove trailing 's'
            threshold = float(match.group(2))
            direction = "over" if match.group(3) == "+" else "under"
            return {
                "stat_type": stat_type,
                "threshold": threshold,
                "direction": direction,
            }

        # Try pattern 2: "over/under value stat" or "stat over/under value"
        over_match = re.match(r"(over|under)\s*([\d.]+)\s*(\w+)", name_lower)
        if over_match:
            direction = over_match.group(1)
            threshold = float(over_match.group(2))
            stat_type = over_match.group(3).rstrip("s")
            return {
                "stat_type": stat_type,
                "threshold": threshold,
                "direction": direction,
            }

        stat_match = re.match(r"(\w+)\s*(over|under)\s*([\d.]+)", name_lower)
        if stat_match:
            stat_type = stat_match.group(1).rstrip("s")
            direction = stat_match.group(2)
            threshold = float(stat_match.group(3))
            return {
                "stat_type": stat_type,
                "threshold": threshold,
                "direction": direction,
            }

        return None

    def _stat_key_to_stat_type(self, market_key: str) -> str:
        """Convert canonical market key to stat type string.

        Args:
            market_key: Canonical market key (e.g., "player_points")

        Returns:
            Stat type string (e.g., "points", "rebounds")
        """
        # Strip "player_" prefix and convert underscores
        stat = market_key.replace("player_", "").replace("_", "")
        return stat

    def _find_dk_standard_line(self, player_name: str, stat_key: str) -> Optional[dict]:
        """Find DraftKings standard over/under line for player/stat.

        Args:
            player_name: Normalized player name
            stat_key: Canonical stat key

        Returns:
            Dict with line info or None if not found
        """
        cursor = self.dk_conn.cursor()

        cursor.execute(
            """
            SELECT
                s.event_id,
                s.player_name_norm,
                m.market_key,
                s.line,
                s.odds_american,
                s.label
            FROM selections s
            JOIN markets m ON s.market_id = m.id
            WHERE s.player_name_norm = ?
            AND m.market_key = ?
            AND s.line IS NOT NULL
            AND s.odds_american IS NOT NULL
            ORDER BY s.scraped_at DESC
            LIMIT 10
        """,
            (player_name, stat_key),
        )

        rows = cursor.fetchall()

        # Look for a row where label contains "Over" or "Under"
        for row in rows:
            label = row["label"] or ""
            if "over" in label.lower() or "under" in label.lower():
                return {
                    "event_id": row["event_id"],
                    "player_name_norm": row["player_name_norm"],
                    "market_key": row["market_key"],
                    "line": row["line"],
                    "odds_american": normalize_odds_string(row["odds_american"])
                    if row["odds_american"]
                    else None,
                    "label": row["label"],
                }

        # If no label match, return first row
        if rows:
            row = rows[0]
            return {
                "event_id": row["event_id"],
                "player_name_norm": row["player_name_norm"],
                "market_key": row["market_key"],
                "line": row["line"],
                "odds_american": normalize_odds_string(row["odds_american"])
                if row["odds_american"]
                else None,
                "label": row["label"],
            }

        return None

    def calculate_cross_site_ev(
        self,
        player_name: str,
        stat: str,
        threshold: float,
        fd_odds: float,
        dk_line: Optional[float] = None,
        dk_odds: Optional[float] = None,
        player_history: Optional[list[float]] = None,
    ) -> dict:
        """Calculate EV for a FanDuel alternate line vs DraftKings market.

        Uses AlternateLineEvaluator to compute P(X >= threshold) from historical
        data, then calculates expected value.

        Args:
            player_name: Normalized player name
            stat: Canonical stat key (e.g., "player_points")
            threshold: The alternate line threshold (e.g., 10.0 for "10+ points")
            fd_odds: FanDuel American odds for the alternate line
            dk_line: Optional DraftKings standard line for market reference
            dk_odds: Optional DraftKings odds for market reference
            player_history: Optional list of historical stat values for direct input

        Returns:
            Dict with:
                - ev: Expected value (decimal, e.g., 0.05 = 5% EV)
                - probability: Model probability P(X >= threshold)
                - breakeven: Breakeven probability from odds
                - confidence: Confidence score (0-1)
                - market_prob: Market-implied probability from DK (if provided)
                - edge: Edge over market (probability - market_prob)
                - recommendation: "BET" if positive EV, "PASS" otherwise
                - distribution_type: Type of distribution used
                - sample_size: Number of observations used
        """
        # Try to load player history from database if not provided
        if player_history is None:
            player_history = self._load_player_history(player_name, stat)

        # Create evaluator
        evaluator = AlternateLineEvaluator(
            player_history=[{stat: v} for v in player_history] if player_history else [],
            stat_type=stat,
            player_name=player_name,
        )

        if not evaluator.has_data:
            # Return placeholder with no data indicator
            return {
                "ev": 0.0,
                "probability": 0.5,
                "breakeven": american_to_prob(fd_odds),
                "confidence": 0.0,
                "market_prob": None,
                "edge": 0.0,
                "recommendation": "NO_DATA",
                "distribution_type": "none",
                "sample_size": 0,
                "historical_hit_rate": 0.0,
            }

        # Evaluate the alternate line
        result = evaluator.evaluate(threshold, fd_odds)
        if result is None:
            return {
                "ev": 0.0,
                "probability": 0.5,
                "breakeven": american_to_prob(fd_odds),
                "confidence": 0.0,
                "market_prob": None,
                "edge": 0.0,
                "recommendation": "EVAL_ERROR",
                "distribution_type": "none",
                "sample_size": len(player_history) if player_history else 0,
                "historical_hit_rate": 0.0,
            }

        # Calculate market-implied probability from DK if provided
        market_prob = None
        edge = None
        if dk_odds is not None:
            market_prob = dk_american_to_prob(dk_odds)
            edge = result.model_probability - market_prob

        # Build return dict
        ev_result = {
            "ev": result.ev_percent / 100.0,  # Convert to decimal
            "probability": result.model_probability,
            "breakeven": result.breakeven_probability,
            "confidence": result.confidence,
            "market_prob": market_prob,
            "edge": edge,
            "recommendation": "BET" if result.recommended else "PASS",
            "distribution_type": result.distribution_type,
            "sample_size": result.sample_size,
            "historical_hit_rate": result.historical_hit_rate,
            "payout_multiplier": result.payout_multiplier,
            "odds": result.odds,
            "fit_quality": result.fit_quality,
        }

        return ev_result

    def _load_player_history(self, player_name: str, stat_key: str) -> list[float]:
        """Load player historical stats for probability modeling.

        Args:
            player_name: Normalized player name
            stat_key: Canonical stat key

        Returns:
            List of historical stat values
        """
        # This would typically load from a historical database
        # For now, return empty list - the engine can work with direct history input
        return []

    def find_opportunities(
        self,
        min_ev: float = 0.01,
        min_confidence: float = 0.3,
    ) -> pd.DataFrame:
        """Find cross-site EV opportunities.

        Cross-references all FanDuel alternate lines with DraftKings standard lines,
        calculates EV for each, and filters by minimum EV threshold.

        Args:
            min_ev: Minimum expected value to include (default 0.01 = 1%)
            min_confidence: Minimum confidence score to include (default 0.3)

        Returns:
            DataFrame of opportunities sorted by EV descending, with columns:
                - player_name_norm
                - stat_key
                - fd_threshold
                - dk_line
                - fd_odds
                - dk_odds
                - ev
                - probability
                - breakeven
                - confidence
                - market_prob
                - edge
                - recommendation
                - distribution_type
        """
        # Load market data
        dk_df, fd_df = self.load_market_data()

        if fd_df.empty or dk_df.empty:
            logger.warning("Empty market data - no opportunities to find")
            return pd.DataFrame()

        opportunities = []

        for _, fd_row in fd_df.iterrows():
            # Map FanDuel alternate to DraftKings standard
            mapping = self.map_alternate_to_standard(fd_row)
            if mapping is None:
                continue

            # Get FanDuel odds
            fd_odds = fd_row.get("odds_american")
            if fd_odds is None:
                continue

            # Calculate cross-site EV
            ev_result = self.calculate_cross_site_ev(
                player_name=mapping["player_name_norm"],
                stat=mapping["stat_key"],
                threshold=mapping["fd_threshold"],
                fd_odds=fd_odds,
                dk_line=mapping.get("dk_line"),
                dk_odds=mapping.get("dk_odds"),
            )

            # Filter by minimum thresholds
            if ev_result["ev"] < min_ev:
                continue
            if ev_result["confidence"] < min_confidence:
                continue

            opportunities.append(
                {
                    "player_name_norm": mapping["player_name_norm"],
                    "stat_key": mapping["stat_key"],
                    "fd_threshold": mapping["fd_threshold"],
                    "dk_line": mapping.get("dk_line"),
                    "fd_odds": fd_odds,
                    "dk_odds": mapping.get("dk_odds"),
                    "ev": ev_result["ev"],
                    "probability": ev_result["probability"],
                    "breakeven": ev_result["breakeven"],
                    "confidence": ev_result["confidence"],
                    "market_prob": ev_result["market_prob"],
                    "edge": ev_result["edge"],
                    "recommendation": ev_result["recommendation"],
                    "distribution_type": ev_result["distribution_type"],
                    "sample_size": ev_result["sample_size"],
                }
            )

        if not opportunities:
            return pd.DataFrame()

        result_df = pd.DataFrame(opportunities)
        result_df = result_df.sort_values("ev", ascending=False)

        return result_df.reset_index(drop=True)

    def get_draftkings_market_reference(
        self,
        player_name: str,
        stat: str,
    ) -> Optional[dict]:
        """Get DraftKings standard line for a player/stat combination.

        Args:
            player_name: Normalized player name
            stat: Canonical stat key (e.g., "player_points")

        Returns:
            Dict with DraftKings market data:
                - event_id: DraftKings event ID
                - line: Over/Under line
                - odds_american: American odds
                - odds_decimal: Decimal odds
                - p_over_devig: Devigged over probability
                - label: "Over" or "Under"
            or None if not found
        """
        cursor = self.dk_conn.cursor()

        cursor.execute(
            """
            SELECT
                s.event_id,
                s.player_name_norm,
                m.market_key,
                s.line,
                s.odds_american,
                s.odds_decimal,
                s.label
            FROM selections s
            JOIN markets m ON s.market_id = m.id
            WHERE s.player_name_norm = ?
            AND m.market_key = ?
            AND s.line IS NOT NULL
            ORDER BY s.scraped_at DESC
            LIMIT 1
        """,
            (player_name, stat),
        )

        row = cursor.fetchone()

        if not row:
            return None

        # Calculate devigged probability
        p_over_devig = None
        label = row["label"] or ""

        if "over" in label.lower():
            p_over_raw = dk_american_to_prob(row["odds_american"])
            # Need under odds too for devig - query for them
            cursor.execute(
                """
                SELECT s.odds_american
                FROM selections s
                JOIN markets m ON s.market_id = m.id
                WHERE s.event_id = ?
                AND s.player_name_norm = ?
                AND m.market_key = ?
                AND s.label LIKE '%Under%'
                LIMIT 1
            """,
                (row["event_id"], player_name, stat),
            )
            under_row = cursor.fetchone()
            if under_row:
                p_under_raw = dk_american_to_prob(under_row["odds_american"])
                p_over_devig = remove_vig_two_way(p_over_raw, p_under_raw)

        return {
            "event_id": row["event_id"],
            "player_name_norm": row["player_name_norm"],
            "market_key": row["market_key"],
            "line": row["line"],
            "odds_american": normalize_odds_string(row["odds_american"])
            if row["odds_american"]
            else None,
            "odds_decimal": row["odds_decimal"],
            "p_over_devig": p_over_devig,
            "label": label,
        }

    def get_player_stats(
        self,
        player_name: str,
        stat_key: str,
        limit: int = 30,
    ) -> list[dict]:
        """Get recent player stat history for probability modeling.

        Args:
            player_name: Normalized player name
            stat_key: Canonical stat key
            limit: Maximum number of games to return

        Returns:
            List of game log dicts with stat values
        """
        # This is a placeholder - in production, this would query
        # a historical stats database (TimescaleDB or similar)
        return []

    def __repr__(self) -> str:
        return f"CrossSiteEVEngine(dk_db={self.dk_db_path.name}, fd_db={self.fd_db_path.name})"


def demo():
    """Demonstrate CrossSiteEVEngine with sample data."""
    print("=" * 60)
    print("Cross-Site EV Engine Demo")
    print("=" * 60)

    # Check if databases exist
    dk_path = Path("data/draftkings/draftkings.db")
    fd_path = Path("data/fanduel/fanduel.db")
    cr_path = Path("data/cross_reference/cross_reference.db")

    if not dk_path.exists():
        print(f"\nDraftKings database not found at {dk_path}")
        print("Demo will create sample data...")

        # Create sample data for demonstration
        engine = CrossSiteEVEngine(
            draftkings_db_path=":memory:",
            fanduel_db_path=":memory:",
        )

        # Demonstrate with sample calculations
        print("\n--- Sample EV Calculation ---")

        # Sample: Stephen Curry 10+ Points at +120
        sample_result = engine.calculate_cross_site_ev(
            player_name="stephen curry",
            stat="player_points",
            threshold=10.0,
            fd_odds=120,
            dk_line=10.5,
            dk_odds=-110,
            player_history=[25, 28, 32, 18, 35, 22, 29, 31, 27, 33],
        )

        print("\nPlayer: Stephen Curry")
        print("Stat: Points")
        print("FanDuel Alternate: 10+ Points at +120")
        print("DraftKings Standard: 10.5 O/U at -110")
        print("\nResults:")
        print(f"  EV: {sample_result['ev']:.2%}")
        print(f"  Probability: {sample_result['probability']:.2%}")
        print(f"  Breakeven: {sample_result['breakeven']:.2%}")
        print(f"  Confidence: {sample_result['confidence']:.2%}")
        print(
            f"  Market Prob: {sample_result['market_prob']:.2% if sample_result['market_prob'] else 'N/A'}"
        )
        print(f"  Edge: {sample_result['edge']:.2%}" if sample_result["edge"] else "  Edge: N/A")
        print(f"  Recommendation: {sample_result['recommendation']}")
        print(f"  Distribution: {sample_result['distribution_type']}")
        print(f"  Sample Size: {sample_result['sample_size']}")

        print("\n--- Sample Alternate Line Mapping ---")

        sample_fd_row = pd.Series(
            {
                "player_name_norm": "stephen curry",
                "market_key": "player_points",
                "market_name": "Points 10+",
                "line": 10.0,
                "odds_american": 120,
            }
        )

        mapping = engine.map_alternate_to_standard(sample_fd_row)
        if mapping:
            print("\nFanDuel: 'Points 10+' for Stephen Curry")
            print(f"  -> Stat Key: {mapping['stat_key']}")
            print(f"  -> FD Threshold: {mapping['fd_threshold']}")
            print(f"  -> DK Line: {mapping.get('dk_line', 'N/A')}")
        else:
            print("\n  Mapping returned None (no DraftKings line found)")

        print("\n" + "=" * 60)
        print("Demo complete. Run with actual databases for live opportunities.")
        print("=" * 60)

        return

    # Use actual databases
    engine = CrossSiteEVEngine(
        draftkings_db_path=dk_path,
        fanduel_db_path=fd_path,
        cross_ref_db_path=cr_path if cr_path.exists() else None,
    )

    try:
        # Load market data
        print("\nLoading market data...")
        dk_df, fd_df = engine.load_market_data()
        print(f"  DraftKings lines: {len(dk_df)}")
        print(f"  FanDuel alternate lines: {len(fd_df)}")

        if fd_df.empty:
            print("\nNo FanDuel alternate lines found.")
            return

        # Find opportunities
        print("\nSearching for EV opportunities (min_ev=2%)...")
        opportunities = engine.find_opportunities(min_ev=0.02)

        if opportunities.empty:
            print("\nNo opportunities found with current filters.")
        else:
            print(f"\nFound {len(opportunities)} opportunities!")
            print("\nTop 10 by EV:")
            print("-" * 80)

            for i, row in opportunities.head(10).iterrows():
                print(f"{i + 1}. {row['player_name_norm'].title()}")
                print(
                    f"   {row['stat_key'].replace('player_', '').replace('_', ' ')}: "
                    f"{row['fd_threshold']:.1f}+ (FD) vs {row['dk_line']} (DK)"
                )
                print(f"   FD Odds: {row['fd_odds']:+d} | DK Odds: {row['dk_odds']}")
                print(
                    f"   EV: {row['ev']:.2%} | Prob: {row['probability']:.1%} | "
                    f"Conf: {row['confidence']:.0%}"
                )
                print(f"   Rec: {row['recommendation']}")
                print()

    finally:
        engine.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    demo()
