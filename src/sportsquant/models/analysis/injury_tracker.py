"""Injury Tracker for flagging projections with injured players.

This module provides the analysis layer that:
- Checks if a player has an active injury
- Flags projections that involve injured players
- Calculates DNP (Did Not Play) probability
- Integrates with the evaluation engine
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from sportsquant.data.sources.espn_injuries.models import (
    FlaggedProjection,
    InjuryStatus,
    PlayerInjury,
)
from sportsquant.data.sources.espn_injuries.scraper import InjuryScraper

logger = logging.getLogger(__name__)


class InjuryTracker:
    """Track player injuries and flag affected projections.

    Integrates with scrapers to provide real-time injury status
    checking for any projections in the system.

    Example:
        ```python
        tracker = InjuryTracker()
        flagged = tracker.flag_injured_projections(projections)
        ```
    """

    def __init__(self, storage_path: Optional[str] = None):
        """Initialize injury tracker.

        Args:
            storage_path: Optional path to injury database.
        """
        self.scraper = InjuryScraper(storage_path)
        self._injury_cache: dict[str, PlayerInjury] = {}
        self._cache_time: Optional[datetime] = None
        self._cache_ttl = timedelta(minutes=15)

    def __enter__(self) -> "InjuryTracker":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.close()

    def close(self) -> None:
        """Close resources."""
        self.scraper.close()

    def _is_cache_valid(self) -> bool:
        """Check if the cache is still valid."""
        if self._cache_time is None:
            return False
        return datetime.utcnow() - self._cache_time < self._cache_ttl

    def _get_cached_injury(self, player_name: str) -> Optional[PlayerInjury]:
        """Get injury from cache if valid."""
        if self._is_cache_valid():
            return self._injury_cache.get(player_name.lower())
        return None

    def _cache_injury(self, injury: PlayerInjury) -> None:
        """Cache an injury record."""
        if not self._is_cache_valid():
            self._injury_cache.clear()
            self._cache_time = datetime.utcnow()
        self._injury_cache[injury.player_name.lower()] = injury

    def check_player(self, player_name: str, use_cache: bool = True) -> dict:
        """Check injury status for a player.

        Args:
            player_name: Name of player to check.
            use_cache: Whether to use cached results.

        Returns:
            Dictionary with injury status details.
        """
        # Check cache first
        if use_cache:
            cached = self._get_cached_injury(player_name)
            if cached:
                return self._format_player_check(cached)

        # Check database
        injury = self.scraper.get_player_injury(player_name)

        if injury:
            self._cache_injury(injury)
            return self._format_player_check(injury)

        # Player not in injury reports - assume active
        return {
            "player_name": player_name,
            "injured": False,
            "status": "active",
            "dnp_probability": 0.0,
            "message": f"{player_name} is not on injury report (active)",
        }

    def _format_player_check(self, injury: PlayerInjury) -> dict:
        """Format injury as player check result."""
        return {
            "player_name": injury.player_name,
            "team": injury.team,
            "injured": not injury.is_active,
            "status": injury.injury_status.value,
            "injury_type": injury.injury_type,
            "dnp_probability": injury.dnp_probability,
            "expected_return": injury.expected_return,
            "message": self._format_message(injury),
        }

    def _format_message(self, injury: PlayerInjury) -> str:
        """Format injury information as a readable message."""
        if injury.is_active:
            return f"{injury.player_name} is ACTIVE"

        status = injury.injury_status.value.upper()
        msg = f"{injury.player_name} ({injury.team}) - {status}"

        if injury.injury_type:
            msg += f": {injury.injury_type}"

        return msg

    def is_player_injured(self, player_name: str) -> bool:
        """Quick check if player is injured.

        Args:
            player_name: Name of player to check.

        Returns:
            True if player has active injury.
        """
        result = self.check_player(player_name)
        return result.get("injured", False)

    def get_dnp_probability(self, player_name: str) -> float:
        """Get DNP probability for a player.

        Args:
            player_name: Name of player to check.

        Returns:
            DNP probability from 0.0 to 1.0.
        """
        result = self.check_player(player_name)
        return result.get("dnp_probability", 0.0)

    def flag_projection(self, projection: dict) -> Optional[FlaggedProjection]:
        """Flag a single projection if player is injured.

        Args:
            projection: Projection dict with keys:
                - id: projection ID
                - player_name: name of player
                - team: team name
                - stat_type: type of stat
                - line_score: betting line

        Returns:
            FlaggedProjection if player injured, None otherwise.
        """
        player_name = projection.get("player_name", "")
        if not player_name:
            return None

        injury = self.scraper.get_player_injury(player_name)

        if injury and not injury.is_active:
            return FlaggedProjection.from_injury_and_projection(
                injury=injury,
                projection_id=projection.get("id", ""),
                player_name=player_name,
                team=projection.get("team", ""),
                stat_type=projection.get("stat_type", ""),
                line_score=projection.get("line_score", 0.0),
            )

        return None

    def flag_injured_projections(
        self,
        projections: list[dict],
        min_severity: str = "low",
    ) -> list[FlaggedProjection]:
        """Flag all projections with injured players.

        Args:
            projections: List of projection dicts.
            min_severity: Minimum severity to flag ('low', 'medium', 'high').

        Returns:
            List of FlaggedProjection models.
        """
        severity_order = {"low": 0, "medium": 1, "high": 2}
        min_severity_level = severity_order.get(min_severity, 0)

        flagged = []

        for proj in projections:
            flagged_proj = self.flag_projection(proj)
            if flagged_proj:
                severity_level = severity_order.get(flagged_proj.flag_severity, 0)
                if severity_level >= min_severity_level:
                    flagged.append(flagged_proj)

        logger.info(f"Flagged {len(flagged)} injured projections")
        return flagged

    def filter_healthy_projections(
        self,
        projections: list[dict],
        max_dnp_prob: float = 0.25,
    ) -> list[dict]:
        """Filter out projections with high injury risk.

        Args:
            projections: List of projection dicts.
            max_dnp_prob: Maximum DNP probability to include (default 25%).

        Returns:
            List of projections that pass the injury filter.
        """
        healthy = []

        for proj in projections:
            player_name = proj.get("player_name", "")
            if not player_name:
                healthy.append(proj)
                continue

            dnp_prob = self.get_dnp_probability(player_name)
            if dnp_prob <= max_dnp_prob:
                healthy.append(proj)
            else:
                logger.debug(f"Filtered {player_name} due to high DNP probability: {dnp_prob:.0%}")

        filtered_count = len(projections) - len(healthy)
        if filtered_count > 0:
            logger.info(f"Filtered {filtered_count} projections due to injury risk")

        return healthy

    def get_injury_impact_score(
        self,
        player_name: str,
        stat_type: str,
        line_score: float,
    ) -> float:
        """Calculate injury impact score for a projection.

        Combines DNP probability with severity of the specific prop
        to return an impact score from 0.0 to 1.0.

        Args:
            player_name: Player name.
            stat_type: Type of stat being targeted.
            line_score: The betting line.

        Returns:
            Impact score from 0.0 (safe) to 1.0 (very risky).
        """
        dnp_prob = self.get_dnp_probability(player_name)

        if dnp_prob >= 1.0:
            return 1.0

        # Higher impact for centers/primary scorers (harder to replace)
        position_multiplier = 1.0  # Could enhance based on position

        # Higher impact for high-volume stats (points > assists > rebounds)
        stat_multiplier = {
            "pts": 1.2,
            "points": 1.2,
            "reb": 1.0,
            "rebs": 1.0,
            "ast": 1.0,
            "asts": 1.0,
            "stl": 0.9,
            "blk": 0.9,
            "tov": 0.8,
        }.get(stat_type.lower(), 1.0)

        impact = min(1.0, dnp_prob * position_multiplier * stat_multiplier)

        return impact

    def get_injury_report_summary(self) -> dict:
        """Get summary of current injuries.

        Returns:
            Dictionary with injury counts and summary.
        """
        return self.scraper.get_injury_summary()

    def fetch_latest_injuries(self, source: str = "nba") -> int:
        """Fetch latest injuries from source.

        Args:
            source: Source to fetch from ('nba', 'espn', 'both').

        Returns:
            Number of injuries fetched.
        """
        report = self.scraper.fetch_injuries(source=source)

        # Clear cache to force refresh
        self._injury_cache.clear()
        self._cache_time = None

        return report.total_count

    def get_players_by_status(self, status: InjuryStatus) -> list[PlayerInjury]:
        """Get all players with a specific injury status.

        Args:
            status: InjuryStatus to filter by.

        Returns:
            List of PlayerInjury models.
        """
        return self.scraper.storage.get_injuries(status=status, limit=200)


class ProjectionInjuryChecker:
    """Check projections against injury database.

    Provides methods to check individual projections or batches
    of projections for injury-related issues.

    Example:
        ```python
        checker = ProjectionInjuryChecker()
        is_safe = checker.is_projection_safe(projection)
        ```
    """

    def __init__(self, tracker: Optional[InjuryTracker] = None):
        """Initialize checker.

        Args:
            tracker: Optional InjuryTracker instance.
        """
        self.tracker = tracker or InjuryTracker()

    def __enter__(self) -> "ProjectionInjuryChecker":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.tracker.close()

    def is_projection_safe(
        self,
        projection: dict,
        max_dnp_prob: float = 0.25,
    ) -> bool:
        """Check if a projection is safe to bet on.

        Args:
            projection: Projection dict.
            max_dnp_prob: Maximum DNP probability threshold.

        Returns:
            True if projection is safe.
        """
        player_name = projection.get("player_name", "")
        if not player_name:
            return True  # Unknown players assumed safe

        dnp_prob = self.tracker.get_dnp_probability(player_name)
        return dnp_prob <= max_dnp_prob

    def get_projection_risk(
        self,
        projection: dict,
    ) -> dict:
        """Get detailed risk assessment for a projection.

        Args:
            projection: Projection dict.

        Returns:
            Dictionary with risk assessment details.
        """
        player_name = projection.get("player_name", "")
        stat_type = projection.get("stat_type", "")
        line_score = projection.get("line_score", 0.0)

        injury_info = self.tracker.check_player(player_name)
        impact_score = self.tracker.get_injury_impact_score(player_name, stat_type, line_score)

        risk_level = "low"
        if impact_score >= 0.75:
            risk_level = "high"
        elif impact_score >= 0.4:
            risk_level = "medium"

        return {
            "projection_id": projection.get("id", ""),
            "player_name": player_name,
            "injury_status": injury_info.get("status", "active"),
            "dnp_probability": injury_info.get("dnp_probability", 0.0),
            "impact_score": impact_score,
            "risk_level": risk_level,
            "is_safe": impact_score < 0.25,
            "notes": injury_info.get("message", ""),
        }

    def batch_check(
        self,
        projections: list[dict],
    ) -> list[dict]:
        """Check multiple projections for injury risk.

        Args:
            projections: List of projection dicts.

        Returns:
            List of risk assessment dicts.
        """
        return [self.get_projection_risk(p) for p in projections]

    def get_high_risk_projections(
        self,
        projections: list[dict],
        min_risk_level: str = "medium",
    ) -> list[dict]:
        """Get projections with high injury risk.

        Args:
            projections: List of projection dicts.
            min_risk_level: Minimum risk level to include.

        Returns:
            List of high-risk projection dicts.
        """
        risk_order = {"low": 0, "medium": 1, "high": 2}
        min_level = risk_order.get(min_risk_level, 1)

        high_risk = []
        for proj in projections:
            risk = self.get_projection_risk(proj)
            if risk_order.get(risk["risk_level"], 0) >= min_level:
                high_risk.append({**proj, "injury_risk": risk})

        return high_risk
