"""Tests for CuratedPaths and snapshot resolution."""

from __future__ import annotations

import json
from pathlib import Path

from quantitative_sports.data.sources.curated.io import (
    CuratedPaths,
    resolve_paths_from_config,
    resolve_snapshot_id,
)


def test_curated_paths_basic_layout(tmp_path: Path) -> None:
    paths = CuratedPaths(cache_root=tmp_path, league="nfl", season=2024, snapshot_id="abc123")
    assert paths.season_dir() == tmp_path / "nfl" / "seasons" / "2024"
    assert paths.snapshots_dir() == tmp_path / "nfl" / "seasons" / "2024" / "snapshots" / "abc123"
    assert paths.features_dir() == (
        tmp_path / "nfl" / "seasons" / "2024" / "snapshots" / "abc123" / "features"
    )
    assert paths.pra_features_path().name == "pra_features_2024.parquet"
    assert paths.game_features_path().name == "game_features_2024.parquet"


def test_resolve_snapshot_id_uses_marker(tmp_path: Path) -> None:
    season_dir = tmp_path / "nfl" / "seasons" / "2024"
    season_dir.mkdir(parents=True)
    (season_dir / "current.json").write_text(json.dumps({"snapshot_id": "snap-xyz"}))
    assert resolve_snapshot_id(tmp_path, "nfl", 2024) == "snap-xyz"


def test_resolve_snapshot_id_falls_back(tmp_path: Path) -> None:
    assert resolve_snapshot_id(tmp_path, "nfl", 2024) == "default"
    assert resolve_snapshot_id(tmp_path, "nfl", 2024, fallback="explicit") == "explicit"


def test_resolve_snapshot_id_handles_bad_marker(tmp_path: Path) -> None:
    season_dir = tmp_path / "nfl" / "seasons" / "2024"
    season_dir.mkdir(parents=True)
    (season_dir / "current.json").write_text("not json")
    assert resolve_snapshot_id(tmp_path, "nfl", 2024, fallback="graceful") == "graceful"


def test_resolve_paths_from_config(tmp_path: Path) -> None:
    class Cfg:
        league = "nfl"
        season = 2024
        cache_root = tmp_path
        snapshot_id = None

    season_dir = tmp_path / "nfl" / "seasons" / "2024"
    season_dir.mkdir(parents=True)
    (season_dir / "current.json").write_text(json.dumps({"snapshot_id": "snap-1"}))

    league, season, paths = resolve_paths_from_config(Cfg())
    assert league == "nfl"
    assert season == 2024
    assert paths.snapshot_id == "snap-1"
