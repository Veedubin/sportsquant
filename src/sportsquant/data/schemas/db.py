"""SQLite database for cross-reference data.

Maintains mappings between:
- Player names across sites (PrizePicks, FanDuel, Underdog, DraftKings)
- Stat types across sites (canonical keys)
- Individual prop references (site_prop_id -> canonical player + stat)

This allows the analysis engine to match props from different sites
even when names and stat types are formatted differently.
"""

import sqlite3
import logging
from pathlib import Path
from typing import Optional

from sportsquant.util.names import normalize_name
from sportsquant.data.schemas.stat_mapping import to_canonical, CANONICAL_KEYS
from sportsquant.data.schemas.player_mapping import find_player

logger = logging.getLogger(__name__)

# Database path
DB_PATH = Path("data/cross_reference/cross_reference.db")


class CrossReferenceDB:
    """Cross-reference database manager."""

    def __init__(self, db_path: Optional[Path] = None):
        """Initialize cross-reference database.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path or DB_PATH
        self._conn: Optional[sqlite3.Connection] = None

    @property
    def conn(self) -> sqlite3.Connection:
        """Get database connection, creating if needed."""
        if self._conn is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
            self._init_schema()
        return self._conn

    def close(self) -> None:
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def _init_schema(self) -> None:
        """Initialize database schema."""
        cursor = self.conn.cursor()

        # Player mapping table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS player_mapping (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                canonical_name TEXT NOT NULL,
                pp_name TEXT,
                fd_name TEXT,
                ud_name TEXT,
                dk_name TEXT,
                rapidfuzz_score REAL DEFAULT 100.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(canonical_name)
            )
        """)

        # Stat mapping table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS stat_mapping (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                canonical_key TEXT NOT NULL UNIQUE,
                pp_key TEXT,
                fd_key TEXT,
                ud_key TEXT,
                dk_key TEXT
            )
        """)

        # Prop mapping table (tracks individual prop references)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS prop_mapping (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                canonical_name TEXT NOT NULL,
                canonical_stat TEXT NOT NULL,
                site TEXT NOT NULL,
                site_prop_id TEXT NOT NULL,
                line_score REAL,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(site, site_prop_id)
            )
        """)

        # Create indexes
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_prop_mapping_site
            ON prop_mapping(site, site_prop_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_prop_mapping_canonical
            ON prop_mapping(canonical_name, canonical_stat)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_player_mapping_canonical
            ON player_mapping(canonical_name)
        """)

        self.conn.commit()

    # ---- Player Mapping Methods ----

    def get_player_mapping(self, canonical_name: str) -> Optional[dict]:
        """Get player mapping by canonical name.

        Args:
            canonical_name: Normalized player name

        Returns:
            Dict with site->name mappings or None
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM player_mapping WHERE canonical_name = ?",
            (canonical_name,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def upsert_player_mapping(
        self,
        canonical_name: str,
        pp_name: Optional[str] = None,
        fd_name: Optional[str] = None,
        ud_name: Optional[str] = None,
        dk_name: Optional[str] = None,
        score: float = 100.0,
    ) -> None:
        """Insert or update player mapping.

        Args:
            canonical_name: Normalized canonical name
            pp_name: PrizePicks name
            fd_name: FanDuel name
            ud_name: Underdog name
            dk_name: DraftKings name
            score: Rapidfuzz confidence score
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO player_mapping (canonical_name, pp_name, fd_name, ud_name, dk_name, rapidfuzz_score, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(canonical_name) DO UPDATE SET
                pp_name = COALESCE(?, pp_name),
                fd_name = COALESCE(?, fd_name),
                ud_name = COALESCE(?, ud_name),
                dk_name = COALESCE(?, dk_name),
                rapidfuzz_score = COALESCE(?, rapidfuzz_score),
                updated_at = CURRENT_TIMESTAMP
        """,
            (
                canonical_name,
                pp_name,
                fd_name,
                ud_name,
                dk_name,
                score,
                pp_name,
                fd_name,
                ud_name,
                dk_name,
                score,
            ),
        )
        self.conn.commit()

    def get_all_player_mappings(self) -> list[dict]:
        """Get all player mappings."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM player_mapping ORDER BY canonical_name")
        return [dict(row) for row in cursor.fetchall()]

    # ---- Stat Mapping Methods ----

    def get_stat_mapping(self, canonical_key: str) -> Optional[dict]:
        """Get stat mapping by canonical key.

        Args:
            canonical_key: Canonical stat key

        Returns:
            Dict with site->key mappings or None
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM stat_mapping WHERE canonical_key = ?",
            (canonical_key,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def upsert_stat_mapping(
        self,
        canonical_key: str,
        pp_key: Optional[str] = None,
        fd_key: Optional[str] = None,
        ud_key: Optional[str] = None,
        dk_key: Optional[str] = None,
    ) -> None:
        """Insert or update stat mapping.

        Args:
            canonical_key: Canonical stat key
            pp_key: PrizePicks key
            fd_key: FanDuel key
            ud_key: Underdog key
            dk_key: DraftKings key
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO stat_mapping (canonical_key, pp_key, fd_key, ud_key, dk_key)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(canonical_key) DO UPDATE SET
                pp_key = COALESCE(?, pp_key),
                fd_key = COALESCE(?, fd_key),
                ud_key = COALESCE(?, ud_key),
                dk_key = COALESCE(?, dk_key)
        """,
            (canonical_key, pp_key, fd_key, ud_key, dk_key, pp_key, fd_key, ud_key, dk_key),
        )
        self.conn.commit()

    def initialize_stat_mappings(self) -> None:
        """Initialize stat mappings from stat_mapping module."""
        from sportsquant.data.schemas.stat_mapping import get_all_site_keys

        for canonical_key in CANONICAL_KEYS:
            site_keys = get_all_site_keys(canonical_key)
            self.upsert_stat_mapping(
                canonical_key,
                pp_key=site_keys.get("prizepicks"),
                fd_key=site_keys.get("fanduel"),
                ud_key=site_keys.get("underdog"),
                dk_key=site_keys.get("draftkings"),
            )
        logger.info("Initialized %d stat mappings", len(CANONICAL_KEYS))

    # ---- Prop Mapping Methods ----

    def upsert_prop_mapping(
        self,
        canonical_name: str,
        canonical_stat: str,
        site: str,
        site_prop_id: str,
        line_score: Optional[float] = None,
    ) -> None:
        """Insert or update prop mapping.

        Args:
            canonical_name: Normalized player name
            canonical_stat: Canonical stat key
            site: Site name (prizepicks, fanduel, underdog, draftkings)
            site_prop_id: Site-specific prop ID
            line_score: Optional line score for reference
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO prop_mapping (canonical_name, canonical_stat, site, site_prop_id, line_score, last_seen)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(site, site_prop_id) DO UPDATE SET
                canonical_name = COALESCE(?, canonical_name),
                canonical_stat = COALESCE(?, canonical_stat),
                line_score = COALESCE(?, line_score),
                last_seen = CURRENT_TIMESTAMP
        """,
            (
                canonical_name,
                canonical_stat,
                site,
                site_prop_id,
                line_score,
                canonical_name,
                canonical_stat,
                line_score,
            ),
        )
        self.conn.commit()

    def find_prop(
        self,
        canonical_name: str,
        canonical_stat: Optional[str],
        site: str,
    ) -> Optional[dict]:
        """Find prop mapping by canonical name and stat.

        Args:
            canonical_name: Normalized player name
            canonical_stat: Canonical stat key (optional)
            site: Site name

        Returns:
            Prop mapping dict or None
        """
        cursor = self.conn.cursor()
        if canonical_stat:
            cursor.execute(
                """
                SELECT * FROM prop_mapping
                WHERE canonical_name = ? AND canonical_stat = ? AND site = ?
            """,
                (canonical_name, canonical_stat, site),
            )
        else:
            cursor.execute(
                """
                SELECT * FROM prop_mapping
                WHERE canonical_name = ? AND site = ?
            """,
                (canonical_name, site),
            )
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_recent_props(self, site: str, limit: int = 100) -> list[dict]:
        """Get recent prop mappings for a site.

        Args:
            site: Site name
            limit: Maximum number of results

        Returns:
            List of prop mapping dicts
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT * FROM prop_mapping
            WHERE site = ?
            ORDER BY last_seen DESC
            LIMIT ?
        """,
            (site, limit),
        )
        return [dict(row) for row in cursor.fetchall()]

    # ---- Database Seeding Methods ----

    def seed_from_scraper_db(
        self,
        db_path: Path,
        site: str,
        player_col: str = "player_name",
        stat_col: str = "stat_type",
        id_col: str = "id",
        line_col: Optional[str] = None,
    ) -> int:
        """Seed prop mappings from a scraper database.

        Args:
            db_path: Path to scraper SQLite database
            site: Site name (prizepicks, fanduel, underdog, draftkings)
            player_col: Column name for player name
            stat_col: Column name for stat type
            id_col: Column name for prop ID
            line_col: Optional column name for line score

        Returns:
            Number of props seeded
        """
        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Get table name
            table = self._get_prop_table_name(site)

            # Query props
            cols = [player_col, stat_col, id_col]
            if line_col:
                cols.append(line_col)

            cursor.execute(f"SELECT {', '.join(cols)} FROM {table}")
            rows = cursor.fetchall()
            conn.close()

            count = 0
            for row in rows:
                player_name = normalize_name(row[player_col])
                stat_type = row[stat_col]
                site_prop_id = row[id_col]
                line_score = row[line_col] if line_col and len(row) > 3 else None

                if player_name and stat_type:
                    canonical_stat = to_canonical(stat_type, site)
                    if canonical_stat:
                        self.upsert_prop_mapping(
                            player_name,
                            canonical_stat,
                            site,
                            str(site_prop_id),
                            line_score,
                        )
                        count += 1

            logger.info("Seeded %d props from %s", count, site)
            return count

        except Exception as e:
            logger.error("Error seeding from %s: %s", db_path, e)
            return 0

    def _get_prop_table_name(self, site: str) -> str:
        """Get the props table name for a site."""
        table_map = {
            "prizepicks": "projections",
            "fanduel": "markets",
            "underdog": "projections",
            "draftkings": "selections",
        }
        return table_map.get(site, "projections")

    def seed_all_from_scraper_dbs(self) -> dict[str, int]:
        """Seed prop mappings from all scraper databases.

        Returns:
            Dict mapping site -> count of props seeded
        """
        scraper_dbs = {
            "prizepicks": Path("data/prizepicks/prizepicks.db"),
            "fanduel": Path("data/fanduel/fanduel.db"),
            "underdog": Path("data/underdog/underdog.db"),
            "draftkings": Path("data/draftkings/draftkings.db"),
        }

        results = {}
        for site, db_path in scraper_dbs.items():
            if db_path.exists():
                count = self.seed_from_scraper_db(db_path, site)
                results[site] = count
            else:
                logger.warning("Scraper DB not found: %s", db_path)
                results[site] = 0

        return results

    # ---- Player Name Resolution ----

    def resolve_player_name(
        self,
        name: str,
        site: str,
        threshold: float = 80.0,
    ) -> Optional[str]:
        """Resolve a player name to canonical name using stored mappings.

        Args:
            name: Player name to resolve
            site: Site the name is from
            threshold: Minimum fuzzy match score

        Returns:
            Canonical name or None if not found
        """
        normalized = normalize_name(name)
        if not normalized:
            return None

        # Check stored mappings
        mapping = self.get_player_mapping(normalized)
        if mapping:
            return mapping["canonical_name"]

        # Get all known names for fuzzy matching
        all_mappings = self.get_all_player_mappings()
        all_names = []
        for m in all_mappings:
            name_for_site = m.get(f"{site[:2]}_name") or m.get(f"{site}_name")
            if name_for_site:
                all_names.append(name_for_site)

        # Fuzzy match
        result = find_player(name, all_names, threshold)
        if result:
            # Find which canonical name this corresponds to
            for m in all_mappings:
                name_for_site = m.get(f"{site[:2]}_name") or m.get(f"{site}_name")
                if name_for_site == result.matched_name:
                    return m["canonical_name"]

        return None

    # ---- Maintenance Methods ----

    def clear_all_mappings(self) -> None:
        """Clear all mappings from the database."""
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM player_mapping")
        cursor.execute("DELETE FROM stat_mapping")
        cursor.execute("DELETE FROM prop_mapping")
        self.conn.commit()
        logger.info("Cleared all cross-reference mappings")

    def get_stats(self) -> dict:
        """Get database statistics."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM player_mapping")
        player_count = cursor.fetchone()["count"]
        cursor.execute("SELECT COUNT(*) as count FROM stat_mapping")
        stat_count = cursor.fetchone()["count"]
        cursor.execute("SELECT COUNT(*) as count FROM prop_mapping")
        prop_count = cursor.fetchone()["count"]
        return {
            "player_mappings": player_count,
            "stat_mappings": stat_count,
            "prop_mappings": prop_count,
        }


# Global instance
_db_instance: Optional[CrossReferenceDB] = None


def get_db(db_path: Optional[Path] = None) -> CrossReferenceDB:
    """Get or create global CrossReferenceDB instance.

    Args:
        db_path: Optional database path override

    Returns:
        CrossReferenceDB instance
    """
    global _db_instance
    if _db_instance is None or db_path is not None:
        _db_instance = CrossReferenceDB(db_path)
    return _db_instance


def close_db() -> None:
    """Close global database connection."""
    global _db_instance
    if _db_instance:
        _db_instance.close()
        _db_instance = None


# ---- CLI Commands ----


def init_cli():
    """Initialize CLI commands for cross-reference management."""
    import click

    @click.group()
    def cross_ref():
        """Cross-reference database management commands."""
        pass

    @cross_ref.command()
    @click.option("--db-path", type=click.Path(), help="Database path override")
    def init(db_path):
        """Initialize cross-reference database with stat mappings."""
        db = get_db(Path(db_path) if db_path else None)
        db.initialize_stat_mappings()
        click.echo("Initialized stat mappings")

    @cross_ref.command()
    @click.option("--db-path", type=click.Path(), help="Database path override")
    def seed(db_path):
        """Seed prop mappings from all scraper databases."""
        db = get_db(Path(db_path) if db_path else None)
        results = db.seed_all_from_scraper_dbs()
        for site, count in results.items():
            click.echo(f"  {site}: {count} props")
        click.echo("Done seeding prop mappings")

    @cross_ref.command()
    @click.option("--db-path", type=click.Path(), help="Database path override")
    def stats(db_path):
        """Show cross-reference database statistics."""
        db = get_db(Path(db_path) if db_path else None)
        stats_dict = db.get_stats()
        click.echo("Cross-reference database statistics:")
        click.echo(f"  Player mappings: {stats_dict['player_mappings']}")
        click.echo(f"  Stat mappings: {stats_dict['stat_mappings']}")
        click.echo(f"  Prop mappings: {stats_dict['prop_mappings']}")

    @cross_ref.command()
    @click.option("--db-path", type=click.Path(), help="Database path override")
    def clear(db_path):
        """Clear all mappings from the database."""
        db = get_db(Path(db_path) if db_path else None)
        if click.confirm("Are you sure you want to clear all mappings?"):
            db.clear_all_mappings()
            click.echo("Cleared all mappings")

    return cross_ref


if __name__ == "__main__":
    init_cli()
