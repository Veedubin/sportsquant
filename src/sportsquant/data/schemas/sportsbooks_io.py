"""Sportsbook player-prop CSV I/O helpers.

Read/write player props CSV files with canonical column ordering.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from sportsquant.data.schemas.sportsbooks_schema import PLAYER_PROP_COLUMNS


def read_player_props_csv(path: Path) -> pd.DataFrame:
    """Read a sportsbook player-props CSV into a DataFrame.

    The returned DataFrame will contain all columns in PLAYER_PROP_COLUMNS, with
    any missing columns added as pd.NA.
    """
    df = pd.read_csv(path)  # pyright: ignore[reportUnknownMemberType]
    out = df.copy()
    for col in PLAYER_PROP_COLUMNS:
        if col not in out.columns:
            out[col] = pd.NA
    # Keep a stable column order (extras at the end)
    ordered = [c for c in PLAYER_PROP_COLUMNS if c in out.columns]
    extras = [c for c in out.columns if c not in ordered]
    return out.loc[:, ordered + extras]


def write_player_props_csv(df: pd.DataFrame, path: Path) -> None:
    """Write a player-props DataFrame to CSV with canonical ordering."""
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = [c for c in PLAYER_PROP_COLUMNS if c in df.columns]
    extras = [c for c in df.columns if c not in ordered]
    out = df.loc[:, ordered + extras].copy()
    out.to_csv(path, index=False)  # pyright: ignore[reportUnknownMemberType]
