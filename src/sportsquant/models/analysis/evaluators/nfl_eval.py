"""NFL-specific statistical model and evaluation.

This module provides NFL-specific statistical modeling using historical
game data. NFL props focus on passing, rushing, and receiving yards/TDs.

Key features:
- Usage-adjusted rate calculations (per snap/practice squad weight)
- Position-specific modeling (QB, RB, WR, TE, DEF)
- Poisson distribution for TD props
- Integration with per-site evaluators (PrizePicks, FanDuel, Underdog)
"""

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

from sportsquant.data.nfl import NFLDataConfig, NFLDataPipeline
from sportsquant.models.analysis.engine import BaseEvaluator, EvaluationResult
from sportsquant.models.analysis.rules.nfl import (
    NFL_TIER_PAYOUT_MODIFIERS,
    calculate_nfl_fanduel_points,
    get_nfl_stat_key,
    is_nfl_poisson_stat,
)
from sportsquant.models.analysis.statistical_model import (
    PlayerDataProvider,
    StatisticalModel,
)


def safe_float(x) -> float:
    """Safely convert to float, returning NaN on failure."""
    try:
        if x is None:
            return float("nan")
        return float(x)
    except (TypeError, ValueError):
        return float("nan")


def normalize_name(s: str) -> str:
    """Normalize player name for matching."""
    s = (s or "").strip().lower().replace("'", "'")
    s = re.sub(r"[^a-z0-9\s'-]", " ", s)
    s = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b.?", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def compute_nfl_stat_from_gamelog_row(stat_type: str, row: pd.Series) -> float:
    """Compute NFL stat value from a gamelog row.

    Args:
        stat_type: The type of stat to compute
        row: DataFrame row from gamelog

    Returns:
        The stat value or NaN if not computable
    """
    # Common stats
    pass_yds = safe_float(row.get("PassYds") or row.get("pass_yards") or row.get("passing_yards"))
    pass_tds = safe_float(row.get("PassTD") or row.get("pass_tds") or row.get("passing_tds"))
    pass_att = safe_float(row.get("PassAtt") or row.get("passing_attempts"))
    pass_cmp = safe_float(
        row.get("Cmp") or row.get("Completions") or row.get("passing_completions")
    )
    pass_int = safe_float(row.get("Int") or row.get("interceptions"))

    rush_yds = safe_float(row.get("RushYds") or row.get("rush_yards") or row.get("rushing_yards"))
    rush_tds = safe_float(row.get("RushTD") or row.get("rush_tds") or row.get("rushing_tds"))
    rush_att = safe_float(row.get("RushAtt") or row.get("rushing_attempts"))

    rec_yds = safe_float(row.get("RecYds") or row.get("rec_yards") or row.get("receiving_yards"))
    rec_tds = safe_float(row.get("RecTD") or row.get("rec_tds") or row.get("receiving_tds"))
    receptions = safe_float(row.get("Rec") or row.get("receptions"))
    targets = safe_float(row.get("Tgt") or row.get("targets"))

    # FanDuel style
    fdp_pts = safe_float(row.get("FDP") or row.get("FanDuelPoints") or row.get("fanduel_points"))

    st = (stat_type or "").strip().lower()

    # Normalize stat type
    st = get_nfl_stat_key(st)

    # Passing stats
    if st == "passing_yards":
        return pass_yds
    if st == "passing_tds":
        return pass_tds
    if st == "interceptions":
        return pass_int
    if st == "passing_completions":
        return pass_cmp
    if st == "passing_attempts":
        return pass_att

    # Rushing stats
    if st == "rushing_yards":
        return rush_yds
    if st == "rushing_tds":
        return rush_tds
    if st == "rushing_attempts":
        return rush_att

    # Receiving stats
    if st == "receiving_yards":
        return rec_yds
    if st == "receiving_tds":
        return rec_tds
    if st == "receptions":
        return receptions
    if st == "targets":
        return targets

    # Fantasy score
    if st in ("fantasy_points", "fantasy_score", "fanduel_fantasy"):
        return (
            fdp_pts
            if not math.isnan(fdp_pts)
            else calculate_nfl_fanduel_points(
                {
                    "Passing Yards": pass_yds,
                    "Passing TDs": pass_tds,
                    "Interceptions": pass_int,
                    "Rushing Yards": rush_yds,
                    "Rushing TDs": rush_tds,
                    "Receiving Yards": rec_yds,
                    "Receiving TDs": rec_tds,
                    "Receptions": receptions,
                }
            )
        )

    # Combined
    if st in ("passing yards+rushing yards", "pass_rush_yds"):
        if math.isnan(pass_yds) or math.isnan(rush_yds):
            return float("nan")
        return pass_yds + rush_yds

    if st in ("passing_tds+rushing_tds", "pass_rush_tds"):
        if math.isnan(pass_tds) or math.isnan(rush_tds):
            return float("nan")
        return pass_tds + rush_tds

    return float("nan")


class NFLDataProvider(PlayerDataProvider):
    """NFL-specific data provider using the centralized NFL data pipeline.

    Delegates data fetching to NFLDataPipeline from sportsquant.data.nfl,
    which handles nflfastR downloads, caching, and normalization.
    """

    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        n_lookback: int = 10,  # NFL has fewer games
    ):
        """Initialize NFL data provider.

        Args:
            cache_dir: Directory for gamelog cache
            n_lookback: Number of games to fetch
        """
        config = NFLDataConfig(cache_dir=cache_dir or Path("./cache/nfl"))
        self.pipeline = NFLDataPipeline(config)
        self.n_lookback = n_lookback
        self._player_id_cache: dict[str, str] = {}
        self._gamelog_cache: dict[str, pd.DataFrame] = {}

    def get_player_id(self, name: str) -> Optional[str]:
        """Resolve player name to NFL player ID.

        Delegates to NFLfastRSource.search_player which searches
        nflfastR data by last name.

        Args:
            name: Player name

        Returns:
            NFL player ID or None if not found
        """
        if name in self._player_id_cache:
            return self._player_id_cache[name]

        player_id = self.pipeline.nflfastr.search_player(name)
        if player_id is not None:
            self._player_id_cache[name] = player_id
            return player_id

        return None

    def get_gamelog(self, player_id: str, lookback: int = 10) -> pd.DataFrame:
        """Fetch NFL gamelog for player.

        Delegates to NFLfastRSource.get_player_gamelog which handles
        multi-season lookups and caching.

        Args:
            player_id: nflfastr player ID
            lookback: Number of games to fetch

        Returns:
            DataFrame with game log data (weekly stats)
        """
        cache_key = player_id
        if cache_key in self._gamelog_cache:
            return self._gamelog_cache[cache_key].head(lookback)

        result_df = self.pipeline.nflfastr.get_player_gamelog(player_id, n_games=lookback)

        if result_df is not None and not result_df.empty:
            self._gamelog_cache[cache_key] = result_df

        return result_df

    def compute_stat(self, stat_type: str, row: pd.Series) -> float:
        """Compute NFL stat from gamelog row."""
        return compute_nfl_stat_from_gamelog_row(stat_type, row)

    def parse_minutes(self, min_str) -> float:
        """Parse NFL time string.

        NFL uses game time not minutes, but we can estimate
        from snap counts or just return a fixed value.
        """
        # NFL doesn't use minutes in the same way
        # Return 1.0 to indicate a valid game
        return 1.0

    def is_poisson_stat(self, stat_type: str) -> bool:
        """NFL-specific Poisson stat check."""
        return is_nfl_poisson_stat(stat_type)


class NFLStatisticalModel(StatisticalModel):
    """NFL-specific statistical model.

    Extends StatisticalModel with NFL-specific stat calculations
    and rate adjustments.
    """

    def __init__(
        self,
        data_provider: Optional[NFLDataProvider] = None,
        base_blend: float = 0.30,
    ):
        """Initialize NFL statistical model.

        Args:
            data_provider: NFL data provider
            base_blend: Base model weight for logit blend
        """
        provider = data_provider or NFLDataProvider()
        super().__init__(
            data_provider=provider,
            min_games=6,  # Fewer games in NFL season
            min_valid_minutes=1.0,  # Snap-based, not minutes
            cap_minutes=1.0,
            base_blend=base_blend,
        )

    def build_model(
        self,
        player_name: str,
        stat_types: list[str],
        position: str = "WR",
    ) -> dict:
        """Build NFL statistical model.

        Args:
            player_name: Player name
            stat_types: List of stat types
            position: Player position (QB, RB, WR, TE)

        Returns:
            Dict mapping stat_type -> model dict
        """
        return super().build_model(player_name, stat_types)


# =============================================================================
# NFL Evaluator for Per-Site Analysis
# =============================================================================


@dataclass
class NFLLeg:
    """A leg for NFL slip/entry building."""

    player_name: str
    team: str
    opponent: str
    stat_type: str
    line: float
    probability: float
    edge: float
    side: str  # "Over" or "Under"
    position: str = "WR"
    start_local: str = ""


@dataclass
class NFLEntry:
    """A complete NFL entry recommendation."""

    entry_type: str  # e.g., "PrizePicks_POWER_5"
    format_type: str  # "prizepicks", "underdog", "fanduel"
    n_legs: int
    legs: list[NFLLeg]
    ev: float
    avg_probability: float
    payout_multiplier: float
    confidence: float
    rank: int = 0

    def legs_description(self) -> str:
        """Human-readable leg descriptions."""
        return " | ".join(
            [
                f"{leg.player_name} {leg.stat_type} {leg.side} {leg.line:g} "
                f"(p={leg.probability:.3f}, edge={leg.edge:+.3f})"
                for leg in self.legs
            ]
        )


class NFLEvaluator(BaseEvaluator):
    """Evaluate NFL props for per-site analysis.

    Supports:
    - PrizePicks: More/Less pick'em
    - Underdog: Higher/Lower pick'em
    - FanDuel: Picks format

    NFL markets:
    - Passing: yards, TDs, completions, interceptions
    - Rushing: yards, TDs, attempts
    - Receiving: yards, TDs, receptions, targets
    """

    def __init__(
        self,
        model_weight: float = 0.30,
        min_confidence: float = 45.0,
        min_edge: float = 0.03,
        base_kelly: float = 0.25,
        stat_model: Optional[NFLStatisticalModel] = None,
    ):
        """Initialize NFL evaluator.

        Args:
            model_weight: Weight given to model probability
            min_confidence: Minimum confidence to recommend
            min_edge: Minimum edge to recommend
            base_kelly: Base Kelly fraction
            stat_model: NFL statistical model
        """
        super().__init__(
            model_weight=model_weight,
            min_confidence=min_confidence,
            min_edge=min_edge,
            base_kelly=base_kelly,
        )
        self.stat_model = stat_model or NFLStatisticalModel()

    def evaluate_projection(
        self,
        projection,
        market_odds: Optional[dict] = None,
        model_prob: Optional[float] = None,
        side_override: Optional[str] = None,
        site: str = "PrizePicks",
    ) -> EvaluationResult:
        """Evaluate a single NFL projection.

        Args:
            projection: NFL Projection object
            market_odds: Market odds dict with 'over' and 'under' American odds
            model_prob: Model probability override
            side_override: Force a specific side
            site: DFS site ("PrizePicks", "Underdog", "FanDuel")

        Returns:
            EvaluationResult with recommendation
        """
        # Extract data from projection
        player_name = getattr(projection, "player_name", None) or getattr(
            projection, "name", "Unknown"
        )
        stat_type = getattr(projection, "stat_display_name", None) or getattr(
            projection, "stat_type", "Unknown"
        )
        line = getattr(projection, "line_score", None) or getattr(projection, "line", 0.0)
        tier = getattr(projection, "tier", "Standard") or "Standard"

        # Get site-specific terminology
        if site.lower() == "prizepicks":
            over_term, under_term = "More", "Less"
        elif site.lower() == "underdog":
            over_term, under_term = "Higher", "Lower"
        else:
            over_term, under_term = "Over", "Under"

        # Determine side
        if side_override:
            recommended_side = side_override
        else:
            # Default based on market odds or model
            if market_odds:
                over_odds = market_odds.get("over", -110)
                over_prob = self.american_to_prob(over_odds)
                recommended_side = over_term if over_prob > 0.5 else under_term
            else:
                recommended_side = over_term

        alternative_side = under_term if recommended_side == over_term else over_term

        # Calculate model probability if not provided
        if model_prob is None:
            # Try to use statistical model
            try:
                models = self.stat_model.build_model(player_name, [stat_type])
                if models and stat_type in models:
                    model_dict = models[stat_type]
                    model_prob = self.stat_model.calc_prob_over(model_dict, line)
                    if math.isnan(model_prob):
                        model_prob = 0.52
                else:
                    model_prob = 0.52
            except Exception:
                model_prob = 0.52

        # Get market odds
        if market_odds:
            over_odds = market_odds.get("over", -110)
            under_odds = market_odds.get("under", -110)
            implied_over = self.american_to_prob(over_odds)
            implied_under = self.american_to_prob(under_odds)
            fair_prob = self.remove_vig(implied_over, implied_under)
            market_prob = (
                implied_over
                if recommended_side in (over_term, "Over", "More", "Higher")
                else implied_under
            )
        else:
            # Assume -110 market
            implied_over = self.american_to_prob(-110)
            implied_under = self.american_to_prob(-110)
            fair_prob = 0.5
            market_prob = fair_prob

        # Blend probabilities
        final_prob = self.logit_blend(model_prob, fair_prob)

        # Calculate edge
        edge = final_prob - market_prob

        # Get payout multiplier
        payout_mult = NFL_TIER_PAYOUT_MODIFIERS.get(tier, 1.0)
        single_payout = 1.91  # ~-110

        # Calculate EV
        ev = final_prob * single_payout * payout_mult - 1.0

        # Calculate confidence
        confidence = self.calculate_confidence(
            final_prob,
            market_prob,
            sample_size=5,
            edge=edge,
        )

        # Calculate Kelly
        kelly_frac = self.kelly_criterion(
            final_prob,
            single_payout * payout_mult,
            self.base_kelly,
        )

        # Risk score
        risk = self.risk_score(final_prob, single_payout)

        return EvaluationResult(
            player_name=player_name,
            stat_type=stat_type,
            line=line,
            model_prob=model_prob,
            market_prob=market_prob,
            fair_prob=fair_prob,
            final_prob=final_prob,
            recommended_side=recommended_side,
            alternative_side=alternative_side,
            edge=edge,
            ev=ev,
            confidence=confidence,
            hit_probability=final_prob,
            kelly_fraction=kelly_frac,
            suggested_stake=kelly_frac,
            risk_score=risk,
            variance=0.0,
            site=site.lower(),
            payout_multiplier=single_payout * payout_mult,
        )

    def rank_projections(
        self,
        projections: list,
        market_data: Optional[dict] = None,
        model_probs: Optional[dict] = None,
        site: str = "PrizePicks",
    ) -> list[EvaluationResult]:
        """Rank projections by expected value.

        Args:
            projections: List of NFL Projection objects
            market_data: Dict mapping projection_id to market odds
            model_probs: Dict mapping projection_id to model probability
            site: DFS site

        Returns:
            Sorted list of EvaluationResult
        """
        results = []
        for i, proj in enumerate(projections):
            proj_id = getattr(proj, "id", i)
            result = self.evaluate_projection(
                proj,
                market_odds=market_data.get(proj_id) if market_data else None,
                model_prob=model_probs.get(proj_id) if model_probs else None,
                site=site,
            )
            results.append(result)

        return sorted(results, key=lambda x: x.ev, reverse=True)

    def get_best_single_picks(
        self,
        projections: list,
        market_data: Optional[dict] = None,
        model_probs: Optional[dict] = None,
        site: str = "PrizePicks",
        min_ev: float = 0.05,
        min_confidence: float = 50.0,
    ) -> list[EvaluationResult]:
        """Get the best single-pick recommendations.

        Args:
            projections: List of NFL Projection objects
            market_data: Market odds
            model_probs: Model probabilities
            site: DFS site
            min_ev: Minimum EV threshold
            min_confidence: Minimum confidence threshold

        Returns:
            Filtered and sorted list of EvaluationResult
        """
        ranked = self.rank_projections(projections, market_data, model_probs, site)

        return [r for r in ranked if r.ev >= min_ev and r.confidence >= min_confidence]


# =============================================================================
# NFL Per-Site Evaluators
# =============================================================================


class NFLPrizePicksEvaluator(NFLEvaluator):
    """NFL PrizePicks-specific evaluator.

    Uses "More" (Over) and "Less" (Under) terminology.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.site = "PrizePicks"

    def evaluate_projection(
        self,
        projection,
        market_odds: Optional[dict] = None,
        model_prob: Optional[float] = None,
        side_override: Optional[str] = None,
    ) -> EvaluationResult:
        return super().evaluate_projection(
            projection,
            market_odds=market_odds,
            model_prob=model_prob,
            side_override=side_override,
            site="PrizePicks",
        )


class NFLUnderdogEvaluator(NFLEvaluator):
    """NFL Underdog-specific evaluator.

    Uses "Higher" and "Lower" terminology.
    Note: Underdog may not have NFL props available.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.site = "Underdog"

    def evaluate_projection(
        self,
        projection,
        sportsbook_odds: Optional[dict] = None,
        model_prob: Optional[float] = None,
        side_override: Optional[str] = None,
    ) -> EvaluationResult:
        # Convert Underdog-style odds to standard market_odds
        market_odds = None
        if sportsbook_odds:
            market_odds = {
                "over": sportsbook_odds.get("higher"),
                "under": sportsbook_odds.get("lower"),
            }
        return super().evaluate_projection(
            projection,
            market_odds=market_odds,
            model_prob=model_prob,
            side_override=side_override,
            site="Underdog",
        )


class NFLFanDuelEvaluator(NFLEvaluator):
    """NFL FanDuel-specific evaluator.

    Uses "Over" and "Under" terminology.
    Supports Picks format evaluation.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.site = "FanDuel"

    def evaluate_projection(
        self,
        projection,
        market_odds: Optional[dict] = None,
        model_prob: Optional[float] = None,
        side_override: Optional[str] = None,
    ) -> EvaluationResult:
        return super().evaluate_projection(
            projection,
            market_odds=market_odds,
            model_prob=model_prob,
            side_override=side_override,
            site="FanDuel",
        )
