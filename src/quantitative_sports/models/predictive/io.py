from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pandas as pd
from pandas import DataFrame

from quantitative_sports.data.sources.curated.io import CuratedPaths, resolve_paths_from_config


def load_pra_features(
    cfg: Any,
    *,
    min_rows: int | None = None,
    allow_empty: bool = False,
) -> tuple[str, str, CuratedPaths, Path, DataFrame]:
    """Load PRA features for a config with league/season/cache_root attributes."""
    league, season, paths = resolve_paths_from_config(cfg)
    feat_path = paths.pra_features_path()
    if not feat_path.exists():
        raise FileNotFoundError(f"missing features table: {feat_path}")

    feats = cast(DataFrame, pd.read_parquet(feat_path))  # pyright: ignore[reportUnknownMemberType]
    if feats.empty:
        if allow_empty:
            return league, season, paths, feat_path, feats
        raise RuntimeError("features table is empty")

    if min_rows is not None and len(feats) < int(min_rows):
        raise RuntimeError(f"insufficient feature rows: {len(feats)} < min_rows={int(min_rows)}")

    return league, season, paths, feat_path, feats
