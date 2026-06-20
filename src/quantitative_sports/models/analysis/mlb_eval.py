"""MLB player prop evaluation — stub.

Full MLB evaluation will be implemented in a future release.
This module provides stub exports for test compatibility.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass
class EvaluationResult:
    """Result of evaluating a single prop projection."""

    player_name: str
    stat_type: str
    line: float
    model_prob: float
    recommended_side: str
    ev: float
    confidence: float
    site: str
    tier: str = "Standard"
    payout_modifier: float = 1.0
    kelly_fraction: float = 0.0
    edge: float = 0.0


def compute_mlb_stat_from_gamelog_row(stat_key: str, row: pd.Series) -> float:
    """Compute an MLB stat value from a gamelog row — stub implementation.

    Returns the stat value if directly available, or NaN for unknown/missing stats.
    """
    # Mapping of stat_key to possible column names
    column_map: dict[str, list[str]] = {
        "hits": ["H"],
        "runs": ["R"],
        "rbi": ["RBI"],
        "hr": ["HR"],
        "singles": ["1B", "Singles"],
        "doubles": ["2B", "Doubles"],
        "triples": ["3B", "Triples"],
        "total_bases": ["TB"],
        "stolen_bases": ["SB"],
        "walks": ["BB", "Walks"],
        "strikeouts": ["SO", "K"],
        "pitcher_strikeouts": ["K", "SO"],
        "pitcher_outs": ["OUT"],
        "earned_runs": ["ER"],
        "innings_pitched": ["IP"],
        "hits_allowed": ["H_allowed"],
        "walks_allowed": ["BB_allowed"],
        "hr_allowed": ["HR_allowed"],
    }

    if stat_key in column_map:
        for col in column_map[stat_key]:
            if col in row.index:
                val = row[col]
                if not (isinstance(val, float) and math.isnan(val)):
                    return float(val)

    # Combined stats
    if stat_key == "hits_runs_rbi":
        h = row.get("H", float("nan"))
        r = row.get("R", float("nan"))
        rbi = row.get("RBI", float("nan"))
        vals = [v for v in [h, r, rbi] if not (isinstance(v, float) and math.isnan(v))]
        return sum(vals) if len(vals) == 3 else float("nan")

    if stat_key == "runs_rbi":
        r = row.get("R", float("nan"))
        rbi = row.get("RBI", float("nan"))
        vals = [v for v in [r, rbi] if not (isinstance(v, float) and math.isnan(v))]
        return sum(vals) if len(vals) == 2 else float("nan")

    if stat_key == "hr_rbi":
        hr = row.get("HR", float("nan"))
        rbi = row.get("RBI", float("nan"))
        vals = [v for v in [hr, rbi] if not (isinstance(v, float) and math.isnan(v))]
        return sum(vals) if len(vals) == 2 else float("nan")

    # Calculated stats
    if stat_key == "singles":
        h = row.get("H", 0.0)
        doubles = row.get("2B", 0.0)
        triples = row.get("3B", 0.0)
        hr = row.get("HR", 0.0)
        if "1B" in row.index:
            return float(row["1B"])
        return float(h - doubles - triples - hr)

    if stat_key == "total_bases":
        if "TB" in row.index:
            return float(row["TB"])
        singles = compute_mlb_stat_from_gamelog_row("singles", row)
        doubles = row.get("2B", 0.0)
        triples = row.get("3B", 0.0)
        hr = row.get("HR", 0.0)
        if math.isnan(singles):
            return float("nan")
        return float(singles + 2 * doubles + 3 * triples + 4 * hr)

    if stat_key == "pitcher_outs":
        if "OUT" in row.index:
            return float(row["OUT"])
        ip = row.get("IP", float("nan"))
        if not (isinstance(ip, float) and math.isnan(ip)):
            return float(ip) * 3.0
        return float("nan")

    return float("nan")


class MLBDataProvider:
    """Data provider for MLB stats — stub implementation."""

    def __init__(self, n_lookback: int = 25, **kwargs: Any) -> None:
        self.n_lookback = n_lookback
        self._gamelog_cache: dict[str, Any] = {}

    def parse_minutes(self, _: Any) -> float:
        return 1.0

    def is_poisson_stat(self, stat: str) -> bool:
        from quantitative_sports.models.analysis.rules.mlb import is_mlb_poisson_stat

        return is_mlb_poisson_stat(stat)

    def compute_stat(self, stat_key: str, row: pd.Series) -> float:
        return compute_mlb_stat_from_gamelog_row(stat_key, row)

    def get_player_id(self, player_name: str) -> int | None:
        return None


class MLBStatisticalModel:
    """Statistical model for MLB prop evaluation — stub implementation."""

    def __init__(
        self, data_provider: MLBDataProvider | None = None, base_blend: float = 0.30, **kwargs: Any
    ) -> None:
        self.min_games = 8
        self.base_blend = base_blend
        self.provider = data_provider or MLBDataProvider()

    def compute_probability(self, player_name: str, stat_key: str, line: float) -> float:
        return 0.52


class MLBEvaluator:
    """MLB prop evaluator — stub implementation."""

    def __init__(self, **kwargs: Any) -> None:
        self.model_weight = 0.30
        self.min_confidence = 45.0
        self.min_edge = 0.03
        self.base_kelly = 0.25
        self._model = MLBStatisticalModel()
        self.site = "PrizePicks"

    def _is_pitcher(self, player_name: str) -> bool:
        return "pitcher" in player_name.lower()

    def _detect_player_type_from_stat(self, stat_key: str) -> str:
        from quantitative_sports.models.analysis.rules.mlb import detect_player_type

        return detect_player_type(stat_key)

    def evaluate_projection(
        self, projection: Any, site: str | None = None, **kwargs: Any
    ) -> EvaluationResult:
        player_name = getattr(projection, "player_name", "Unknown")
        stat_type = getattr(projection, "stat_display_name", "hits")
        line = getattr(projection, "line_score", 0.5)
        tier = getattr(projection, "tier", "Standard")

        effective_site = site if site is not None else self.site
        model_prob = self._model.compute_probability(player_name, stat_type, line)
        site_lower = effective_site.lower()
        if model_prob >= 0.5:
            recommended_side = (
                "More"
                if site_lower == "prizepicks"
                else ("Higher" if site_lower == "underdog" else "Over")
            )
        else:
            recommended_side = (
                "Less"
                if site_lower == "prizepicks"
                else ("Lower" if site_lower == "underdog" else "Under")
            )

        ev = max(model_prob - 0.5, 0.0) * 2
        confidence = model_prob * 100

        return EvaluationResult(
            player_name=player_name,
            stat_type=stat_type,
            line=line,
            model_prob=model_prob,
            recommended_side=recommended_side,
            ev=ev,
            confidence=confidence,
            site=site_lower,
            tier=tier,
        )

    def rank_projections(self, projections: list[Any]) -> list[Any]:
        results = [self.evaluate_projection(p) for p in projections]
        results.sort(key=lambda r: getattr(r, "ev", 0), reverse=True)
        return results

    def get_best_single_picks(
        self,
        projections: list[Any],
        min_ev: float = 0.0,
        min_confidence: float = 0.0,
        **kwargs: Any,
    ) -> list[Any]:
        results = self.rank_projections(projections)
        return [
            r
            for r in results
            if getattr(r, "ev", 0) >= min_ev and getattr(r, "confidence", 0) >= min_confidence
        ]


class MLBPrizePicksEvaluator(MLBEvaluator):
    """PrizePicks-specific MLB evaluator — stub."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.site = "PrizePicks"


class MLBUnderdogEvaluator(MLBEvaluator):
    """Underdog-specific MLB evaluator — stub."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.site = "Underdog"


class MLBFanDuelEvaluator(MLBEvaluator):
    """FanDuel-specific MLB evaluator — stub."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.site = "FanDuel"
