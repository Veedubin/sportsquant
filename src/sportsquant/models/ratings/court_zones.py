"""
Court Zone Features for Shot Location Analysis

Provides court zone-based efficiency and tendency features for NBA player analysis.

Key components:
1. Shot zone detection based on coordinates
2. Zone efficiency metrics (FG% by zone)
3. Shooting tendency profiles
4. Shot distribution analysis

Data Sources:
- Shot data: TimescaleDB (shots table)
- Game data: Kafka topic 'sports-analytics-player-stats'
- Caching: Apache Ignite for computed features

Usage:
    >>> from sportsquant.models.ratings.court_zones import CourtZoneFeatures
    >>> features = CourtZoneFeatures()
    >>> tendencies = features.compute_shooting_tendencies(shot_df)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class CourtZoneConfig:
    """Configuration for court zone features.

    Attributes:
        zone_names: Names of court zones.
        x_ranges: X-coordinate ranges for each zone (in feet).
        y_ranges: Y-coordinate ranges for each zone (in feet).
        corner_3_y_threshold: Y threshold for corner 3 detection.
        use_zone_efficiency: Whether to compute zone-based efficiency.
    """

    zone_names: tuple[str, ...] = (
        "restricted",
        "paint",
        "mid_range",
        "corner_3_left",
        "corner_3_right",
        "above_break_3",
    )
    x_ranges: tuple[tuple[float, float], ...] = (
        (0, 8),
        (8, 16),
        (16, 23),
        (0, 14),
        (0, 14),
        (23, 94),
    )
    y_ranges: tuple[tuple[float, float], ...] = (
        (0, 47),
        (0, 47),
        (0, 47),
        (0, 7.1),
        (42.9, 47),
        (0, 47),
    )
    corner_3_y_threshold: float = 7.1
    use_zone_efficiency: bool = True


@dataclass(frozen=True)
class ShotZoneConfig:
    """Configuration for shot zone analysis.

    Attributes:
        shot_distance_ranges: Distance ranges for shot zones.
        shot_angle_ranges: Angle ranges for shot zones.
        min_shots_for_stats: Minimum shots required for reliable stats.
    """

    shot_distance_ranges: tuple[tuple[float, float], ...] = (
        (0, 5),
        (5, 10),
        (10, 15),
        (15, 20),
        (20, 25),
        (25, 35),
        (35, 50),
    )
    shot_angle_ranges: tuple[tuple[float, float], ...] = (
        (-45, -30),
        (-30, -15),
        (-15, 0),
        (0, 15),
        (15, 30),
        (30, 45),
    )
    min_shots_for_stats: int = 20


RESTRICTED_AREA = {"x": (0, 8), "y": (0, 47)}
PAINT = {"x": (8, 16), "y": (0, 47)}
MID_RANGE = {"x": (16, 23), "y": (0, 47)}
CORNER_3_LEFT = {"x": (0, 14), "y": (0, 7.1)}
CORNER_3_RIGHT = {"x": (0, 14), "y": (42.9, 47)}
ABOVE_BREAK_3 = {"x": (23, 94), "y": (0, 47)}

ZONE_COORDS = {
    "restricted": RESTRICTED_AREA,
    "paint": PAINT,
    "mid_range": MID_RANGE,
    "corner_3_left": CORNER_3_LEFT,
    "corner_3_right": CORNER_3_RIGHT,
    "above_break_3": ABOVE_BREAK_3,
}


def compute_shot_zone(
    x: float,
    y: float,
) -> str:
    """Determine which court zone a shot was taken from.

    Args:
        x: Shot x-coordinate (feet from basket).
        y: Shot y-coordinate (feet from baseline).

    Returns:
        Zone name string.
    """
    if x >= 23:
        return "above_break_3"

    if x <= 14 and y <= 7.1:
        return "corner_3_left"
    if x <= 14 and y >= 42.9:
        return "corner_3_right"

    if x <= 8:
        return "restricted"
    if x <= 16:
        return "paint"

    return "mid_range"


def compute_shot_distance(x: float, y: float) -> float:
    """Compute Euclidean shot distance from basket.

    Args:
        x: Shot x-coordinate.
        y: Shot y-coordinate.

    Returns:
        Shot distance in feet.
    """
    return np.sqrt(x**2 + y**2)


def compute_shot_angle(x: float, y: float) -> float:
    """Compute shot angle relative to baseline.

    Args:
        x: Shot x-coordinate.
        y: Shot y-coordinate.

    Returns:
        Shot angle in degrees.
    """
    if y <= 0:
        return 0.0

    angle_rad = np.arctan2(y, x)
    angle_deg = np.degrees(angle_rad)

    return angle_deg


def compute_zone_efficiency(
    shot_data: pd.DataFrame,
    zone_col: str = "zone",
    made_col: str = "FG MADE",
    attempted_col: str = "FG ATTEMPTED",
) -> dict[str, dict[str, float]]:
    """Compute shooting efficiency by court zone.

    Args:
        shot_data: DataFrame with shot records.
        zone_col: Column containing zone names.
        made_col: Column indicating made shots.
        attempted_col: Column indicating shot attempts.

    Returns:
        Dictionary with zone -> efficiency metrics.
    """
    if shot_data.empty:
        return {}

    efficiency: dict[str, dict[str, float]] = {}

    for zone in shot_data[zone_col].unique():
        zone_shots = shot_data[shot_data[zone_col] == zone]

        attempts = zone_shots[attempted_col].sum()
        makes = zone_shots[made_col].sum()

        if attempts < 1:
            efficiency[zone] = {"pct": 0.0, "attempts": 0, "makes": 0}
            continue

        efficiency[zone] = {
            "pct": makes / attempts if attempts > 0 else 0.0,
            "attempts": float(int(attempts)),
            "makes": float(int(makes)),
            "avg_distance": float(
                zone_shots.apply(
                    lambda r: compute_shot_distance(r.get("LOC_X", 0), r.get("LOC_Y", 0)),
                    axis=1,
                ).mean()
            ),
        }

    return efficiency


def compute_zone_distribution(
    shot_data: pd.DataFrame,
    zone_col: str = "zone",
) -> dict[str, float]:
    """Compute shot distribution across zones.

    Args:
        shot_data: DataFrame with shot records.
        zone_col: Column containing zone names.

    Returns:
        Dictionary with zone -> proportion of shots.
    """
    if shot_data.empty:
        return {}

    total_shots = len(shot_data)

    if total_shots < 1:
        return {}

    distribution: dict[str, float] = {}

    for zone in shot_data[zone_col].unique():
        zone_shots = shot_data[shot_data[zone_col] == zone]
        distribution[zone] = len(zone_shots) / total_shots

    return distribution


def compute_shooting_preference(
    shot_data: pd.DataFrame,
    zone_col: str = "zone",
    made_col: str = "FG MADE",
    attempted_col: str = "FG ATTEMPTED",
) -> dict[str, float]:
    """Compute shooting preference scores by zone.

    Combines shot frequency and efficiency to identify preferred zones.

    Args:
        shot_data: DataFrame with shot records.
        zone_col: Zone column name.
        made_col: Made shots column.
        attempted_col: Attempted shots column.

    Returns:
        Dictionary with zone -> preference score.
    """
    if shot_data.empty:
        return {}

    distribution = compute_zone_distribution(shot_data, zone_col)
    efficiency = compute_zone_efficiency(shot_data, zone_col, made_col, attempted_col)

    preference: dict[str, float] = {}

    for zone, zone_data in distribution.items():
        if zone in efficiency:
            avg_eff = efficiency[zone]["pct"]
            dist = zone_data
            preference[zone] = avg_eff * dist * 2

    return preference


def _add_zone_efficiency_features(
    result: pd.DataFrame,
    zone_efficiency: dict[str, dict[str, float]],
    prefix: str,
) -> None:
    """Add zone efficiency features to result DataFrame."""
    for zone in ZONE_COORDS:
        zone_data = zone_efficiency.get(zone, {})
        result[f"{prefix}_{zone}_pct"] = zone_data.get("pct", 0.0)
        result[f"{prefix}_{zone}_attempts"] = zone_data.get("attempts", 0)


def _add_zone_distribution_features(
    result: pd.DataFrame,
    zone_distribution: dict[str, float],
    prefix: str,
) -> None:
    """Add zone distribution features to result DataFrame."""
    for zone in ZONE_COORDS:
        result[f"{prefix}_{zone}_dist"] = zone_distribution.get(zone, 0.0)


def _add_zone_preference_features(
    result: pd.DataFrame,
    shooting_preference: dict[str, float],
    prefix: str,
) -> None:
    """Add zone preference features to result DataFrame."""
    for zone in ZONE_COORDS:
        result[f"{prefix}_{zone}_preference"] = shooting_preference.get(zone, 0.0)


def _ensure_columns_exist(
    result: pd.DataFrame,
    columns: list[str],
    default_value: float,
) -> None:
    """Ensure columns exist in DataFrame with default value."""
    for col in columns:
        if col not in result.columns:
            result[col] = default_value


def add_zone_features(
    player_data: pd.DataFrame,
    shot_data: pd.DataFrame | None = None,
    prefix: str = "zone",
) -> pd.DataFrame:
    """Add court zone-based features to player data.

    Args:
        player_data: Player statistics DataFrame.
        shot_data: Shot location data (optional).
        prefix: Prefix for new column names.

    Returns:
        DataFrame with added zone features.
    """
    result = player_data.copy()

    if shot_data is not None and not shot_data.empty:
        zone_efficiency = compute_zone_efficiency(shot_data)
        zone_distribution = compute_zone_distribution(shot_data)
        shooting_preference = compute_shooting_preference(shot_data)

        _add_zone_efficiency_features(result, zone_efficiency, prefix)
        _add_zone_distribution_features(result, zone_distribution, prefix)
        _add_zone_preference_features(result, shooting_preference, prefix)

    _ensure_columns_exist(
        result,
        ["shot_dist_avg", "shot_dist_std", "shot_dist_min", "shot_dist_max"],
        0.0,
    )
    _ensure_columns_exist(result, ["shot_angle_avg", "shot_angle_std"], 0.0)

    return result


def _extract_zone_metrics(
    tendencies: dict[str, Any],
    zone_efficiency: dict[str, dict[str, float]],
    zone_name: str,
    prefix: str,
) -> None:
    """Extract zone metrics and add to tendencies dict."""
    zone_data = zone_efficiency.get(zone_name)
    if zone_data:
        tendencies[f"{prefix}_fg_pct"] = zone_data["pct"]
        tendencies[f"{prefix}_attempts"] = zone_data["attempts"]


def _compute_corner_3_stats(
    zone_efficiency: dict[str, dict[str, float]],
) -> tuple[float, float]:
    """Compute combined corner 3 attempts and makes."""
    corner_3_attempts = 0.0
    corner_3_makes = 0.0
    for zone in ["corner_3_left", "corner_3_right"]:
        zone_data = zone_efficiency.get(zone)
        if zone_data:
            corner_3_attempts += zone_data["attempts"]
            corner_3_makes += zone_data["makes"]
    return corner_3_attempts, corner_3_makes


def _compute_corner_to_above_ratio(
    corner_3_attempts: float,
    zone_efficiency: dict[str, dict[str, float]],
) -> float:
    """Compute corner to above break 3 ratio."""
    if corner_3_attempts <= 0:
        return 0.0
    above_break = zone_efficiency.get("above_break_3")
    if not above_break or above_break["attempts"] <= 0:
        return 0.0
    return corner_3_attempts / above_break["attempts"]


def _compute_corner_side_ratio(
    zone_distribution: dict[str, float],
) -> float:
    """Compute corner 3 left vs right distribution ratio."""
    left_dist = zone_distribution.get("corner_3_left", 0.0)
    right_dist = zone_distribution.get("corner_3_right", 0.0)
    total = left_dist + right_dist
    return left_dist / total if total > 0 else 0.5


def compute_shooting_tendencies(
    shot_data: pd.DataFrame,
) -> dict[str, Any]:
    """Compute comprehensive shooting tendency profile.

    Args:
        shot_data: DataFrame with shot records.

    Returns:
        Dictionary with comprehensive tendency metrics.
    """
    if shot_data.empty:
        return {}

    tendencies: dict[str, Any] = {}

    zone_efficiency = compute_zone_efficiency(shot_data)
    zone_distribution = compute_zone_distribution(shot_data)

    tendencies["total_shots"] = len(shot_data)

    _extract_zone_metrics(tendencies, zone_efficiency, "restricted", "restricted")
    _extract_zone_metrics(tendencies, zone_efficiency, "paint", "paint")
    _extract_zone_metrics(tendencies, zone_efficiency, "mid_range", "mid_range")

    corner_3_attempts, corner_3_makes = _compute_corner_3_stats(zone_efficiency)

    if corner_3_attempts > 0:
        tendencies["corner_3_fg_pct"] = corner_3_makes / corner_3_attempts
        tendencies["corner_3_attempts"] = corner_3_attempts
    else:
        tendencies["corner_3_fg_pct"] = 0.0
        tendencies["corner_3_attempts"] = 0

    above_break = zone_efficiency.get("above_break_3")
    if above_break:
        tendencies["above_break_3_fg_pct"] = above_break["pct"]
        tendencies["above_break_3_attempts"] = above_break["attempts"]

    tendencies["corner_to_above_ratio"] = _compute_corner_to_above_ratio(
        corner_3_attempts, zone_efficiency
    )
    tendencies["corner_3_side_ratio"] = _compute_corner_side_ratio(zone_distribution)

    return tendencies


class CourtZoneFeatures:
    """Computes court zone-based efficiency and tendency features.

    Provides methods for analyzing shot distributions and efficiencies
    across different court zones for NBA player analysis.

    All feature calculation logic is preserved from the original implementation.
    Data sources have been adapted to use TimescaleDB and Kafka instead of Redis.
    """

    def __init__(self, config: CourtZoneConfig | None = None) -> None:
        """Initialize court zone features computer.

        Args:
            config: Court zone configuration.
        """
        self.config = config or CourtZoneConfig()

    def compute_zone_efficiency(self, shot_data: pd.DataFrame) -> dict[str, dict[str, float]]:
        """Compute efficiency by court zone.

        Args:
            shot_data: DataFrame with shot records.

        Returns:
            Zone efficiency metrics.
        """
        if shot_data.empty:
            return {}

        shot_data = shot_data.copy()
        shot_data["zone"] = shot_data.apply(
            lambda r: compute_shot_zone(r.get("LOC_X", 0) + 5, r.get("LOC_Y", 0)),
            axis=1,
        )

        return compute_zone_efficiency(shot_data)

    def compute_shooting_tendencies(self, shot_data: pd.DataFrame) -> dict[str, Any]:
        """Compute comprehensive shooting tendencies.

        Args:
            shot_data: DataFrame with shot records.

        Returns:
            Shooting tendency metrics.
        """
        if shot_data.empty:
            return {}

        shot_data = shot_data.copy()
        shot_data["zone"] = shot_data.apply(
            lambda r: compute_shot_zone(r.get("LOC_X", 0) + 5, r.get("LOC_Y", 0)),
            axis=1,
        )

        return compute_shooting_tendencies(shot_data)

    def add_zone_features(
        self, player_data: pd.DataFrame, shot_data: pd.DataFrame | None = None
    ) -> pd.DataFrame:
        """Add zone features to player data.

        Args:
            player_data: Player statistics DataFrame.
            shot_data: Shot location data.

        Returns:
            DataFrame with added zone features.
        """
        return add_zone_features(player_data, shot_data)

    @staticmethod
    def compute_shot_zone(x: float, y: float) -> str:
        """Determine shot zone from coordinates.

        Args:
            x: X-coordinate.
            y: Y-coordinate.

        Returns:
            Zone name.
        """
        return compute_shot_zone(x, y)

    @staticmethod
    def compute_shot_distance(x: float, y: float) -> float:
        """Compute shot distance from basket.

        Args:
            x: X-coordinate.
            y: Y-coordinate.

        Returns:
            Distance in feet.
        """
        return compute_shot_distance(x, y)
