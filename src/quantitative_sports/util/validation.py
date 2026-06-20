"""
Data validation utilities for quantitative_sports.

Provides schema validation for input data files like lines.csv.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from pandas import DataFrame

from quantitative_sports.util.exceptions import DataValidationError, LinesCSVError


LINES_CSV_REQUIRED_COLUMNS = ["player_id", "game_date", "line"]
LINES_CSV_OPTIONAL_COLUMNS = ["game_id", "odds_over", "odds_under", "sportsbook", "player_name"]
PRA_CONTEXT_FEATURES = [
    "rest_days",
    "is_back_to_back",
    "is_3_in_4",
    "games_last_4_days",
    "games_last_7_days",
    "min_home_last_5_mean",
    "min_away_last_5_mean",
    "pra_home_last_5_mean",
    "pra_away_last_5_mean",
    "pra_variance_last_10",
    "is_consistent",
    "high_pra_streak",
]
PRA_LABEL_COLUMNS = [
    "y_minutes",
    "y_points",
    "y_rebounds",
    "y_assists",
    "y_pra",
]


@dataclass(frozen=True)
class LinesCSVSchema:
    """Schema contract for lines.csv files."""

    required_columns: frozenset[str] = frozenset(LINES_CSV_REQUIRED_COLUMNS)
    optional_columns: frozenset[str] = frozenset(LINES_CSV_OPTIONAL_COLUMNS)

    def validate(self, df: DataFrame) -> None:
        """Validate a DataFrame against the schema."""
        missing = self.required_columns - set(df.columns)
        if missing:
            raise DataValidationError(
                column=None,
                expected=f"columns: {', '.join(sorted(self.required_columns))}",
                actual=f"columns: {', '.join(sorted(df.columns))}",
            )

        for col in df.columns:
            if col not in self.required_columns and col not in self.optional_columns:
                raise DataValidationError(
                    column=col,
                    expected="required or optional column",
                    actual="unknown column",
                )


@dataclass(frozen=True)
class FeatureSchema:
    """Schema contract for feature DataFrames."""

    required_columns: frozenset[str] = frozenset(
        [
            "season",
            "game_id",
            "game_date",
            "player_id",
            "team_abbr",
            "opp_team_abbr",
            "is_home",
        ]
    )

    label_columns: frozenset[str] = frozenset(PRA_LABEL_COLUMNS)

    feature_columns: frozenset[str] = frozenset(
        [
            "pra_last_10_mean",
            "pra_last_5_mean",
            "pra_last_3_mean",
            "minutes_last_10_mean",
            "minutes_last_5_mean",
            "ppm_last_10_mean",
            "rpm_last_10_mean",
            "apm_last_10_mean",
            *PRA_CONTEXT_FEATURES,
            "opp_pace_s2d",
            "opp_def_rating_s2d",
            "opp_recent_win_rate_10",
        ]
    )

    def validate(self, df: DataFrame, check_features: bool = True) -> None:
        """Validate a feature DataFrame."""
        missing = self.required_columns - set(df.columns)
        if missing:
            raise DataValidationError(
                column=None,
                expected=f"required columns: {', '.join(sorted(self.required_columns))}",
                actual=f"columns: {', '.join(sorted(df.columns))}",
            )

        if check_features:
            for col in self.feature_columns:
                if col not in df.columns:
                    raise DataValidationError(
                        column=col,
                        expected="feature column",
                        actual="missing",
                    )


def validate_lines_csv(file_path: Path) -> DataFrame:
    """Validate and load a lines.csv file."""
    try:
        df = pd.read_csv(file_path)
    except (OSError, ValueError) as e:
        raise LinesCSVError(file_path, f"Failed to read file: {e}") from e

    schema = LinesCSVSchema()
    try:
        schema.validate(df)
    except DataValidationError as e:
        raise LinesCSVError(file_path, e.message, row=0) from e

    def _is_na(value: Any) -> bool:
        return bool(pd.isna(value))

    for row_num, (_, row) in enumerate(df.iterrows(), start=2):
        if _is_na(row["player_id"]) or _is_na(row["game_date"]) or _is_na(row["line"]):
            raise LinesCSVError(file_path, "Missing required value", row=row_num)

        if not _is_na(row.get("odds_over")) and not _is_na(row.get("odds_under")):
            if row["odds_over"] == 0 or row["odds_under"] == 0:
                raise LinesCSVError(file_path, "Odds cannot be zero", row=row_num)

    return df


def validate_feature_df(df: DataFrame, check_features: bool = True) -> None:
    """Validate a feature DataFrame."""
    schema = FeatureSchema()
    schema.validate(df, check_features=check_features)


@dataclass(frozen=True)
class ModelArtifactSchema:
    """Schema contract for model artifacts."""

    required_metadata_keys: frozenset[str] = frozenset(
        [
            "model_type",
            "season",
            "n_features",
            "feature_names",
            "rmse_holdout",
        ]
    )

    def validate_metadata(self, metadata: dict[str, Any]) -> None:
        """Validate model metadata."""
        missing = self.required_metadata_keys - set(metadata.keys())
        if missing:
            raise DataValidationError(
                column="model.meta.json",
                expected=f"metadata keys: {', '.join(sorted(self.required_metadata_keys))}",
                actual=f"keys: {', '.join(sorted(metadata.keys()))}",
            )
