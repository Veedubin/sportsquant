"""Curated data path resolution.

CuratedPaths is the canonical accessor for NBA/NFL curated feature
parquet files. Files live under::

    {cache_root}/{league}/seasons/{season}/snapshots/{snapshot_id}/features/

This module was previously missing — broken by an earlier refactor that
left imports in :mod:`quantitative_sports.models.predictive.io` and
:mod:`quantitative_sports.core.betting.evaluate_lines` unresolved. This file
restores the API so the import chain works.

The actual layout is created by the data-curation pipeline (not in
this repository) — this module only resolves paths.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


@dataclass(frozen=True)
class CuratedPaths:
    """Resolved paths for a single curated season snapshot."""

    cache_root: Path
    league: str
    season: int
    snapshot_id: str

    def season_dir(self) -> Path:
        """Season root directory."""
        return self.cache_root / self.league / "seasons" / str(self.season)

    def snapshots_dir(self) -> Path:
        """Snapshots directory."""
        return self.season_dir() / "snapshots" / self.snapshot_id

    def features_dir(self) -> Path:
        """Features subdirectory."""
        return self.snapshots_dir() / "features"

    def pra_features_path(self) -> Path:
        """Path to PRA (Points+Rebounds+Assists) features parquet."""
        return self.features_dir() / f"pra_features_{self.season}.parquet"

    def game_features_path(self) -> Path:
        """Path to game-level features parquet."""
        return self.features_dir() / f"game_features_{self.season}.parquet"

    def current_json(self) -> Path:
        """Path to the current-snapshot marker JSON."""
        return self.season_dir() / "current.json"


def resolve_paths_from_config(cfg: Any) -> tuple[str, int, CuratedPaths]:
    """Build a :class:`CuratedPaths` from a config with attributes.

    Args:
        cfg: Any object with ``league``, ``season``, ``cache_root``,
            and ``snapshot_id`` (or None) attributes.

    Returns:
        Tuple ``(league, season, CuratedPaths)``.
    """
    league = str(getattr(cfg, "league"))
    season = int(getattr(cfg, "season"))
    cache_root = Path(str(getattr(cfg, "cache_root")))
    snapshot_id = getattr(cfg, "snapshot_id", None)
    if snapshot_id is None:
        snapshot_id = resolve_snapshot_id(cache_root, league, season)
    return (
        league,
        season,
        CuratedPaths(
            cache_root=cache_root,
            league=league,
            season=season,
            snapshot_id=str(snapshot_id),
        ),
    )


def resolve_snapshot_id(
    cache_root: Path, league: str, season: int, *, fallback: Optional[str] = None
) -> str:
    """Resolve the current snapshot id for a season.

    Reads ``{cache_root}/{league}/seasons/{season}/current.json`` if it
    exists, otherwise returns ``fallback`` (or ``"default"``).

    Args:
        cache_root: Curated cache root.
        league: League code ("nba", "nfl", etc.).
        season: Season year.
        fallback: Snapshot id to use when no marker file exists.

    Returns:
        Snapshot id string.
    """
    marker = cache_root / league / "seasons" / str(season) / "current.json"
    if marker.exists():
        try:
            import json

            data = json.loads(marker.read_text())
            sid = data.get("snapshot_id")
            if sid:
                return str(sid)
        except (OSError, ValueError):
            pass
    return str(fallback or "default")


__all__ = ["CuratedPaths", "resolve_paths_from_config", "resolve_snapshot_id"]
