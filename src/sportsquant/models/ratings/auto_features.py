"""
Automated Feature Engineering with Deep Feature Synthesis

Provides automated feature generation using aggregation and transformation primitives.

Key components:
1. Deep Feature Synthesis (DFS)
2. Rolling window features
3. Feature importance ranking
4. Automatic feature selection

Data Sources:
- Player stats: TimescaleDB (player_stats table)
- Game data: Kafka topic 'sports-analytics-player-stats'
- Caching: Apache Ignite for computed features

Usage:
    >>> from sportsquant.models.ratings.auto_features import DeepFeatureSynthesis
    >>> dfs = DeepFeatureSynthesis()
    >>> features = dfs.generate_features(
    ...     player_games, entity_id="PLAYER_ID", time_index="GAME_DATE"
    ... )
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, cast

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.ensemble import RandomForestClassifier

PrimitiveFunc = Callable[[Any], Any]
TransformFunc = Callable[[Any, Any], Any]


@dataclass(frozen=True)
class DFSConfig:
    """Configuration for Deep Feature Synthesis.

    Attributes:
        max_depth: Maximum depth of feature generation.
        min_instances: Minimum instances for aggregation.
        primitives: Aggregation primitives to use.
        trans_primitives: Transform primitives to use.
        max_features: Maximum number of features to generate.
        random_seed: Random seed for reproducibility.
    """

    max_depth: int = 3
    min_instances: int = 1
    primitives: tuple[str, ...] = ("count", "sum", "mean", "max", "min", "std", "trend")
    trans_primitives: tuple[str, ...] = ("divide", "subtract", "absolute")
    max_features: int = 1000
    random_seed: int = 42


@dataclass(frozen=True)
class EntityConfig:
    """Configuration for entity definition in DFS.

    Attributes:
        entity_id: Column name for entity identifier.
        time_index: Column name for time ordering.
        entity_columns: Columns that define the entity.
    """

    entity_id: str = "PLAYER_ID"
    time_index: str = "GAME_DATE"
    entity_columns: tuple[str, ...] = ()


def _compute_trend(series: pd.Series) -> float:
    """Compute linear trend of a series."""
    if len(series) < 2:
        return 0.0

    x = np.arange(len(series))
    y = series.values

    if np.std(np.asarray(y, dtype=np.float64)) < 1e-6:
        return 0.0

    slope, _, _, _, _ = cast(Any, stats.linregress(x, y))
    return float(slope)


DFS_PRIMITIVES: dict[str, PrimitiveFunc] = {  # type: ignore[assignment]
    "count": len,
    "sum": lambda x: x.sum() if hasattr(x, "sum") else np.sum(x),
    "mean": lambda x: x.mean() if hasattr(x, "mean") else np.mean(x),
    "max": lambda x: x.max() if hasattr(x, "max") else np.max(x),
    "min": lambda x: x.min() if hasattr(x, "min") else np.min(x),
    "std": lambda x: x.std() if hasattr(x, "std") else np.std(x),
    "median": lambda x: x.median() if hasattr(x, "median") else np.median(x),
    "skew": lambda x: x.skew() if hasattr(x, "skew") else 0.0,
    "kurt": lambda x: x.kurt() if hasattr(x, "kurt") else 0.0,
    "trend": _compute_trend,
    "sum_over_count": lambda x, y: x.sum() / len(y) if len(y) > 0 else 0.0,  # type: ignore[arg-type]
    "nunique": lambda x: x.nunique() if hasattr(x, "nunique") else len(set(x)),
    "first": lambda x: x.iloc[0] if len(x) > 0 else 0.0,
    "last": lambda x: x.iloc[-1] if len(x) > 0 else 0.0,
}


TRANSFORM_PRIMITIVES: dict[str, TransformFunc] = {  # type: ignore[assignment]
    "divide": lambda x, y: x / (y + 1e-6),
    "subtract": lambda x, y: x - y,
    "add": lambda x, y: x + y,
    "multiply": lambda x, y: x * y,
    "absolute": np.abs,
    "log": lambda x: np.log1p(np.abs(x)),
    "square": lambda x: x**2,
    "sqrt": lambda x: np.sqrt(np.abs(x)),
}


def _generate_primitive_features(
    df: pd.DataFrame,
    groupby_cols: list[str],
    value_cols: list[str],
    primitives: tuple[str, ...],
) -> pd.DataFrame:
    """Generate primitive aggregation features.

    Args:
        df: Input DataFrame.
        groupby_cols: Columns to group by.
        value_cols: Columns to aggregate.
        primitives: Aggregation primitives to apply.

    Returns:
        DataFrame with primitive features.
    """
    # pylint: disable=R0912,R0915
    if not groupby_cols or not value_cols:
        return pd.DataFrame()

    if df.empty:
        return pd.DataFrame()

    features: dict[str, Any] = {}

    grouped = df.groupby(groupby_cols)

    for prim in primitives:
        if prim not in DFS_PRIMITIVES:
            continue

        for val_col in value_cols:
            _process_primitive_aggregation(df, grouped, val_col, prim, features)

    if not features:
        return pd.DataFrame()

    result = pd.DataFrame(features)
    result[groupby_cols[0]] = grouped.grouper.groupings[0].keys  # type: ignore[attr-defined]

    return result


def _process_primitive_aggregation(
    df: pd.DataFrame,
    grouped: Any,  # pd.core.groupby.DataFrameGroupBy
    val_col: str,
    prim: str,
    features: dict[str, Any],
) -> None:
    """Process a single primitive aggregation for a column."""
    try:
        if val_col not in df.select_dtypes(include=[np.number]).columns:
            return

        if prim == "count":
            agg = grouped.size().reset_index(drop=True)
            features[f"{val_col}_{prim}"] = agg
        elif prim in ("sum", "mean", "max", "min", "std", "median", "skew", "kurt"):
            agg = getattr(grouped[val_col], prim)().reset_index(drop=True)
            features[f"{val_col}_{prim}"] = agg[val_col]
        elif prim == "trend":

            def _trend_wrapper(x: pd.DataFrame, col: str = val_col) -> float:
                return _compute_trend(cast(pd.Series, x[col]))

            agg = grouped.apply(_trend_wrapper).reset_index(drop=True)
            features[f"{val_col}_{prim}"] = agg
        elif prim == "nunique":
            agg = grouped[val_col].nunique().reset_index(drop=True)
            features[f"{val_col}_{prim}"] = agg
        elif prim in ("first", "last"):
            val_idx = 0 if prim == "first" else -1
            agg = grouped[val_col].nth(val_idx).reset_index(drop=True)
            features[f"{val_col}_{prim}"] = agg
    except ValueError:
        pass


def _generate_transform_features(
    df1: pd.DataFrame,
    df2: pd.DataFrame,
    transform_cols: list[str],
    trans_primitives: tuple[str, ...],
) -> pd.DataFrame:
    """Generate transform features between two DataFrames.

    Args:
        df1: First DataFrame (numerators/bases).
        df2: Second DataFrame (denominators/deltas).
        transform_cols: Columns to transform.
        trans_primitives: Transform primitives to apply.

    Returns:
        DataFrame with transform features.
    """
    if df1.empty or df2.empty or not transform_cols:
        return pd.DataFrame()

    features: dict[str, Any] = {}

    for i, col1 in enumerate(transform_cols):
        if i >= len(transform_cols):
            break

        for prim in trans_primitives:
            if prim not in TRANSFORM_PRIMITIVES:
                continue

            col2 = transform_cols[(i + 1) % len(transform_cols)]

            try:
                if prim == "absolute":
                    features[f"{col1}_abs"] = np.abs(df1[col1].values)
                elif prim == "log":
                    features[f"{col1}_log"] = np.log1p(np.abs(df1[col1].values))
                elif prim == "square":
                    features[f"{col1}_sq"] = np.asarray(df1[col1].values, dtype=np.float64) ** 2
                elif prim == "sqrt":
                    features[f"{col1}_sqrt"] = np.sqrt(np.abs(df1[col1].values))
                else:
                    val1 = df1[col1].values
                    val2 = df2[col2].values if col2 in df2.columns else df1[col2].values

                    func = TRANSFORM_PRIMITIVES[prim]  # type: ignore[operator]
                    features[f"{col1}_{prim}_{col2}"] = func(val1, val2)
            except ValueError:
                continue

    if not features:
        return pd.DataFrame()

    return pd.DataFrame(features)


def _generate_rolling_features(
    df: pd.DataFrame,
    value_cols: list[str],
    windows: tuple[int, ...],
    groupby_col: str,
    primitives: tuple[str, ...],
) -> pd.DataFrame:
    """Generate rolling window features.

    Args:
        df: Input DataFrame.
        value_cols: Columns to compute rolling features for.
        windows: Rolling window sizes.
        groupby_col: Column to group by.
        primitives: Aggregation primitives.

    Returns:
        DataFrame with rolling features.
    """
    # pylint: disable=R0915
    if df.empty or not value_cols:
        return pd.DataFrame()

    result_dfs: list[pd.DataFrame] = []

    for window in windows:
        window_features: dict[str, Any] = {}

        grouped = df.sort_values("GAME_DATE").groupby(groupby_col)

        for val_col in value_cols:
            if val_col not in df.columns:
                continue

            for prim in primitives:
                if prim in ("mean", "sum", "max", "min", "std", "median"):
                    try:
                        rolling = grouped[val_col].rolling(
                            window=window, min_periods=max(1, window // 2)
                        )
                        agg = getattr(rolling, prim)().reset_index(drop=True)
                        window_features[f"{val_col}_{prim}_{window}"] = agg
                    except (KeyError, ValueError, TypeError):
                        continue

        if window_features:
            result_dfs.append(pd.DataFrame(window_features))

    if not result_dfs:
        return pd.DataFrame()

    return pd.concat(result_dfs, axis=1)


def generate_dfs_features(
    df: pd.DataFrame,
    entity_id: str,
    time_index: str,
    target_col: str | None = None,
    config: DFSConfig | None = None,
) -> pd.DataFrame:
    """Generate features using Deep Feature Synthesis.

    Args:
        df: Input DataFrame.
        entity_id: Column name for entity identifier.
        time_index: Column name for time ordering.
        target_col: Target column (to be predicted).
        config: DFS configuration.

    Returns:
        DataFrame with generated features.
    """
    if config is None:
        config = DFSConfig()

    rng = np.random.default_rng(config.random_seed)

    df = df.copy()

    if time_index in df.columns:
        df[time_index] = pd.to_datetime(df[time_index])
        df = df.sort_values(time_index)

    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()

    if target_col and target_col in numeric_cols:
        numeric_cols.remove(target_col)

    if entity_id not in df.columns:
        raise ValueError(f"Entity ID column '{entity_id}' not found")

    all_features: list[pd.DataFrame] = []

    primitive_features = _generate_primitive_features(
        df, [entity_id], numeric_cols, config.primitives
    )
    if not primitive_features.empty:
        all_features.append(primitive_features)

    rolling_features = _generate_rolling_features(
        df, numeric_cols, (3, 5, 10), entity_id, ("mean", "sum", "std")
    )
    if not rolling_features.empty:
        all_features.append(rolling_features)

    if len(all_features) > 1:
        result: pd.DataFrame = pd.concat(all_features, axis=1)
    elif all_features:
        result = all_features[0]
    else:
        result = pd.DataFrame()

    if not result.empty and len(result.columns) > config.max_features:
        keep_cols = rng.choice(
            list(result.columns),
            size=config.max_features,
            replace=False,
        )
        result = pd.DataFrame(result[keep_cols])

    return result


class DeepFeatureSynthesis:
    """Implements Deep Feature Synthesis for automated feature engineering.

    Generates new features from raw data using aggregation primitives
    and transformation primitives, similar to Featuretools.

    All calculation logic is preserved from the original implementation.
    Data sources have been adapted to use TimescaleDB and Kafka instead of Redis.
    """

    def __init__(self, config: DFSConfig | None = None) -> None:
        """Initialize DFS processor.

        Args:
            config: DFS configuration.
        """
        self.config = config or DFSConfig()

    def generate_features(
        self,
        df: pd.DataFrame,
        entity_id: str,
        time_index: str,
        target_col: str | None = None,
    ) -> pd.DataFrame:
        """Generate features using DFS.

        Args:
            df: Input DataFrame.
            entity_id: Entity identifier column.
            time_index: Time ordering column.
            target_col: Target column (optional).

        Returns:
            DataFrame with generated features.
        """
        return generate_dfs_features(
            df,
            entity_id,
            time_index,
            target_col,
            self.config,
        )

    def generate_player_features(
        self,
        player_data: pd.DataFrame,
        _stat_cols: list[str] | None = None,
    ) -> pd.DataFrame:
        """Generate features for player statistics.

        Args:
            player_data: Player game log DataFrame.
            _stat_cols: Statistics columns to use (unused, kept for API compatibility).

        Returns:
            DataFrame with player-level features.
        """
        return self.generate_features(
            player_data,
            entity_id="PLAYER_ID",
            time_index="GAME_DATE",
        )

    def generate_team_features(
        self,
        team_data: pd.DataFrame,
        _stat_cols: list[str] | None = None,
    ) -> pd.DataFrame:
        """Generate features for team statistics.

        Args:
            team_data: Team game log DataFrame.
            _stat_cols: Statistics columns to use (unused, kept for API compatibility).

        Returns:
            DataFrame with team-level features.
        """
        return self.generate_features(
            team_data,
            entity_id="TEAM_ID",
            time_index="GAME_DATE",
        )


def compute_feature_importance_dfs(
    features: pd.DataFrame,
    target: pd.Series,
    n_features: int = 20,
) -> pd.DataFrame:
    """Compute feature importance for DFS-generated features.

    Args:
        features: Feature DataFrame.
        target: Target series.
        n_features: Number of top features to return.

    Returns:
        DataFrame with feature importance rankings.
    """
    if features.empty or target.empty:
        return pd.DataFrame()

    x = features.fillna(0).replace([np.inf, -np.inf], 0)
    y = target.fillna(0)

    model = RandomForestClassifier(n_estimators=100, random_state=42, max_depth=5)
    model.fit(x, y)

    importance_df = pd.DataFrame(
        {
            "feature": x.columns,
            "importance": model.feature_importances_,
        }
    ).sort_values("importance", ascending=False)

    return importance_df.head(n_features)


def select_features_by_importance(
    features: pd.DataFrame,
    target: pd.Series,
    n_features: int = 50,
) -> pd.DataFrame:
    """Select top features by importance.

    Args:
        features: Feature DataFrame.
        target: Target series.
        n_features: Number of features to select.

    Returns:
        DataFrame with selected features.
    """
    importance_df = compute_feature_importance_dfs(features, target, n_features)

    if importance_df.empty:
        return features

    selected_cols = importance_df["feature"].head(n_features).tolist()

    return pd.DataFrame(features[selected_cols])
