from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, cast

import pandas as pd


def atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    """Write text atomically (tmp + replace).

    This is important when snapshots are seeded using hardlinks; in-place writes
    would mutate prior snapshots.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding=encoding)
    os.replace(tmp, path)


def atomic_write_json(path: Path, obj: Any, *, indent: int = 2) -> None:
    """Write JSON atomically to a file.

    Args:
        path: Path to write the JSON file.
        obj: Python object to serialize as JSON.
        indent: Number of spaces for JSON indentation (default 2).
    """
    atomic_write_text(path, json.dumps(obj, ensure_ascii=False, indent=indent) + "\n")


def atomic_write_dataframe(
    df: pd.DataFrame,
    path: Path,
    *,
    fmt: str = "parquet",
    index: bool = False,
) -> None:
    """Write a DataFrame atomically.

    Supported formats:
      - parquet (requires pyarrow or fastparquet)
      - csv (writes utf-8)
    """

    fmt_norm = fmt.strip().lower()
    path.parent.mkdir(parents=True, exist_ok=True)

    if fmt_norm == "parquet":
        tmp = path.with_suffix(path.suffix + ".tmp")
        cast(Any, df).to_parquet(tmp, index=index)
        os.replace(tmp, path)
        return

    if fmt_norm == "csv":
        tmp = path.with_suffix(path.suffix + ".tmp")
        cast(Any, df).to_csv(tmp, index=index)
        os.replace(tmp, path)
        return

    raise ValueError(f"Unsupported dataframe format: {fmt!r}")


@dataclass(frozen=True)
class TimestampedRun:
    run_id: str
    started_at_utc: str
    finished_at_utc: Optional[str] = None
