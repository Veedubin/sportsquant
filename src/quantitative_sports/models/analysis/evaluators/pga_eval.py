"""PGA-specific statistical model and evaluation.

This module provides PGA-specific statistical modeling using historical
tournament data. PGA props focus on strokes gained, birdies, and finishing position.

Key features:
- Stroke-based modeling with par adjustments
- Tournament-specific factors (course, weather, field strength)
- Integration with per-site evaluators (PrizePicks, FanDuel, Underdog)
"""

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from quantitative_sports.models.analysis.engine import BaseEvaluator, EvaluationResult
from quantitative_sports.models.analysis.rules.pga import (
    PGA_TIER_PAYOUT_MODIFIERS,
    calculate_pga_fanduel_points,
    get_pga_stat_key,
    is_pga_finish_prop,
    is_pga_poisson_stat,
)
from quantitative_sports.models.analysis.statistical_model import (
    PlayerDataProvider,
    weighted_rate_mu_sigma,
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


def compute_pga_stat_from_gamelog_row(stat_type: str, row: pd.Series) -> float:
    """Compute PGA stat value from a tournament/round row.

    Args:
        stat_type: The type of stat to compute
        row: DataFrame row from tournament data

    Returns:
        The stat value or NaN if not computable
    """
    # Strokes gained
    sg_total = safe_float(row.get("SG_T") or row.get("sg_total") or row.get("strokes_gained_total"))
    sg_tee = safe_float(
        row.get("SG_OTT") or row.get("sg_off_the_tee") or row.get("strokes_gained_off_the_tee")
    )
    sg_arg = safe_float(
        row.get("SG_ARG")
        or row.get("sg_around_the_green")
        or row.get("strokes_gained_around_the_green")
    )
    sg_putt = safe_float(
        row.get("SG_P") or row.get("sg_putting") or row.get("strokes_gained_putting")
    )
    sg_apr = safe_float(row.get("SG_APR") or row.get("sg_apr") or row.get("strokes_gained_apr"))

    # Traditional stats
    strokes = safe_float(row.get("Strokes") or row.get("strokes") or row.get("score"))
    birdies = safe_float(row.get("Birdies") or row.get("birdies") or row.get("B"))
    bogeys = safe_float(row.get("Bogeys") or row.get("bogeys") or row.get("Bo"))
    pars = safe_float(row.get("Pars") or row.get("pars") or row.get("P"))
    doubles = safe_float(row.get("Doubles") or row.get("doubles") or row.get("D"))
    eagles = safe_float(row.get("Eagles") or row.get("eagles") or row.get("E"))
    gir = safe_float(row.get("GIR") or row.get("gir") or row.get("greens_in_regulation"))
    fw = safe_float(row.get("FW") or row.get("fairways_hit") or row.get("fairways"))
    putts = safe_float(row.get("Putts") or row.get("putts") or row.get("total_putts"))
    dd = safe_float(row.get("DD") or row.get("driving_distance") or row.get("drive_distance"))

    # Finish stats
    finish = safe_float(row.get("Finish") or row.get("finish") or row.get("position"))
    made_cut = safe_float(row.get("Made") or row.get("made_cut") or row.get("cut_made"))

    # Fantasy points
    fdp_pts = safe_float(row.get("FDP") or row.get("FanDuelPoints") or row.get("fanduel_points"))

    st = (stat_type or "").strip().lower()

    # Normalize stat type
    st = get_pga_stat_key(st)

    # Strokes gained stats
    if st == "strokes_gained_total":
        return sg_total
    if st == "strokes_gained_off_the_tee" or st == "sg_off_the_tee":
        return sg_tee
    if st == "strokes_gained_around_the_green" or st == "sg_arg":
        return sg_arg
    if st == "strokes_gained_putting" or st == "sg_putting":
        return sg_putt
    if st == "strokes_gained_apr" or st == "sg_apr":
        return sg_apr

    # Traditional stats
    if st == "birdies":
        return birdies
    if st == "bogeys":
        return bogeys
    if st == "pars":
        return pars
    if st == "doubles":
        return doubles
    if st == "eagles":
        return eagles
    if st == "greens_in_regulation" or st == "gir":
        return gir
    if st == "fairways_hit" or st == "fairways":
        return fw
    if st == "total_putts" or st == "putts":
        return putts
    if st == "driving_distance" or st == "drive_distance":
        return dd

    # Finish stats
    if st in ("top_5", "top10"):
        return 1.0 if finish <= 5 else 0.0
    if st in ("top_10", "top10"):
        return 1.0 if finish <= 10 else 0.0
    if st in ("top_20", "top20"):
        return 1.0 if finish <= 20 else 0.0
    if st in ("top_25", "top25"):
        return 1.0 if finish <= 25 else 0.0
    if st in ("top_30", "top30"):
        return 1.0 if finish <= 30 else 0.0
    if st in ("top_40", "top40"):
        return 1.0 if finish <= 40 else 0.0
    if st == "cut_made" or st == "make_cut":
        return 1.0 if made_cut == 1 else 0.0
    if st == "miss_cut" or st == "cut_missed":
        return 1.0 if made_cut == 0 else 0.0
    if st == "winner":
        return 1.0 if finish == 1 else 0.0

    # Strokes (total)
    if st in ("strokes", "total_strokes", "score"):
        return strokes

    # Fantasy score
    if st in ("fantasy_points", "fantasy_score", "fanduel_fantasy"):
        if not math.isnan(fdp_pts):
            return fdp_pts
        return calculate_pga_fanduel_points(
            {
                "Strokes": strokes,
                "Birdie or Better": birdies,
                "Top 10": 6.0 if finish <= 10 else 0.0,
                "Top 20": 3.0 if finish <= 20 else 0.0,
                "Made Cut": 1.5 if made_cut == 1 else 0.0,
                "Greens in Regulation": gir,
            }
        )

    return float("nan")


class PGADataProvider(PlayerDataProvider):
    """PGA-specific data provider.

    Fetches player data from ESPN API for player lookup.
    Tournament data is fetched from various sources.
    """

    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        n_lookback: int = 10,  # Tournament rounds
    ):
        """Initialize PGA data provider.

        Args:
            cache_dir: Directory for tournament data cache
            n_lookback: Number of rounds/tournaments to fetch
        """
        if cache_dir is not None:
            self.cache_dir = Path(cache_dir)
        else:
            self.cache_dir = Path("./cache/gamelogs/pga")
            try:
                self.cache_dir.mkdir(parents=True, exist_ok=True)
            except (PermissionError, OSError):
                self.cache_dir = None
        self.n_lookback = n_lookback

        self._player_id_cache: dict[str, int] = {}
        self._gamelog_cache: dict[int, pd.DataFrame] = {}

    def get_player_id(self, name: str) -> Optional[int]:
        """Resolve player name to PGA player ID.

        Uses ESPN search API to find athlete by name.

        Args:
            name: Player name

        Returns:
            ESPN athlete ID or None if not found
        """
        if name in self._player_id_cache:
            return self._player_id_cache[name]

        try:
            import urllib.request
            import json

            # Search ESPN API for athlete
            encoded_name = urllib.parse.quote(name)
            url = f"https://site.api.espn.com/apis/search/v2?query={encoded_name}&limit=5"

            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode())

            # New ESPN search format: results[].type == "player" with contents[]
            results = data.get("results", [])
            for result in results:
                result_type = result.get("type", "")
                if result_type not in ("player", "athlete"):
                    continue

                contents = result.get("contents", [])
                for content in contents:
                    sport = content.get("sport", "").lower()
                    league = (
                        content.get("league", "").lower()
                        or content.get("defaultLeagueSlug", "").lower()
                    )
                    if sport == "golf" and league == "pga":
                        uid = content.get("uid", "")
                        # UID format: s:20~l:28~a:3139477 - extract ID after ~a:
                        if "~a:" in uid:
                            athlete_id = uid.split("~a:")[-1]
                            if athlete_id:
                                self._player_id_cache[name] = int(athlete_id)
                                return int(athlete_id)

            # If no golf result found, try first athlete result
            if results and results[0].get("type") == "athlete":
                athlete_id = results[0].get("id")
                if athlete_id:
                    self._player_id_cache[name] = int(athlete_id)
                    return int(athlete_id)

        except Exception as e:
            print(f"PGA player ID lookup failed for {name}: {e}")

        return None

    def get_gamelog(self, player_id: int, lookback: int = 10) -> pd.DataFrame:
        """Fetch PGA tournament/round data for player with caching.

        Uses ESPN athlete stats API for tournament results.

        Args:
            player_id: ESPN athlete ID
            lookback: Number of rounds to fetch

        Returns:
            DataFrame with round/tournament data
        """
        cache_key = player_id
        if cache_key in self._gamelog_cache:
            return self._gamelog_cache[cache_key]

        # Try disk cache
        cache_path = None
        if self.cache_dir:
            try:
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                cache_path = self.cache_dir / f"gamelog_{player_id}.pkl"
                if cache_path.exists():
                    try:
                        df = pd.read_pickle(cache_path)
                        if df is not None and not df.empty:
                            self._gamelog_cache[cache_key] = df
                            return df.head(lookback)
                    except Exception:
                        try:
                            cache_path.unlink()
                        except (PermissionError, OSError):
                            pass
            except (PermissionError, OSError):
                pass

        try:
            import urllib.request
            import json

            # Fetch athlete stats from ESPN
            url = f"https://site.api.espn.com/apis/common/v3/sports/golf/pga/athletes/{player_id}/stats"

            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as response:
                data = json.loads(response.read().decode())

            rows = []
            events = data.get("events", [])

            for event in events:
                tournament = event.get("tournament", {})
                season = tournament.get("season", {})

                # Get event details
                event_name = tournament.get("fullName", tournament.get("name", ""))
                course = tournament.get("course", {}).get("name", "")

                # Get athlete stats for this event
                competitions = event.get("competitions", [])
                for comp in competitions:
                    for competitor in comp.get("competitors", []):
                        if str(competitor.get("id")) == str(player_id):
                            stats = competitor.get("stats", [])

                            row = {
                                "tournament": event_name,
                                "course": course,
                                "season": season.get("year", ""),
                                "event_id": event.get("id"),
                            }

                            # Extract statistics
                            for stat in stats:
                                stat_key = stat.get("key", "")
                                stat_value = stat.get("value")
                                if stat_key and stat_value is not None:
                                    row[stat_key] = stat_value

                            if len(row) > 4:  # Has at least some stats
                                rows.append(row)

            if not rows:
                return pd.DataFrame()

            df = pd.DataFrame(rows)

            # Sort by season/tournament order if available
            if "season" in df.columns:
                df = df.sort_values("season", ascending=False)

            # Save to cache
            if cache_path and not df.empty:
                try:
                    df.to_pickle(cache_path)
                except (PermissionError, OSError):
                    pass

            self._gamelog_cache[cache_key] = df
            return df.head(lookback)

        except Exception as e:
            print(f"PGA gamelog fetch failed for {player_id}: {e}")
            return pd.DataFrame()

    def compute_stat(self, stat_type: str, row: pd.Series) -> float:
        """Compute PGA stat from row."""
        return compute_pga_stat_from_gamelog_row(stat_type, row)

    def parse_minutes(self, min_str) -> float:
        """Parse PGA round identifier.

        Golf doesn't use minutes, but we can use round number.
        """
        if min_str is None:
            return 1.0
        if isinstance(min_str, (int, float)):
            return float(min_str)
        try:
            return float(min_str)
        except (ValueError, TypeError):
            return 1.0

    def is_poisson_stat(self, stat_type: str) -> bool:
        """PGA-specific Poisson stat check."""
        return is_pga_poisson_stat(stat_type)


class PGATournamentModel:
    """PGA-specific tournament-level model.

    Golf has unique challenges:
    - Multi-round tournaments (cut handling)
    - Course-specific adjustments
    - Field strength normalization
    """

    def __init__(
        self,
        data_provider: Optional[PGADataProvider] = None,
        base_blend: float = 0.25,  # Lower blend for golf
    ):
        """Initialize PGA tournament model.

        Args:
            data_provider: PGA data provider
            base_blend: Base model weight
        """
        self.provider = data_provider or PGADataProvider()
        self.base_blend = base_blend

    def build_player_model(
        self,
        player_name: str,
        stat_types: list[str],
    ) -> dict:
        """Build statistical model for player's tournament performance.

        Args:
            player_name: Player name
            stat_types: List of stat types to model

        Returns:
            Dict mapping stat_type -> model dict
        """
        player_id = self.provider.get_player_id(player_name)
        if not player_id:
            return {}

        try:
            rounds = self.provider.get_gamelog(player_id)
        except Exception:
            return {}

        if rounds.empty or len(rounds) < 4:  # Need at least 4 rounds
            return {}

        out = {}
        for st in stat_types:
            # For PGA, each row is a round
            vals = np.array(
                [self.provider.compute_stat(st, r) for _, r in rounds.iterrows()], dtype=float
            )

            valid = ~np.isnan(vals)
            if np.sum(valid) < 4:
                continue

            vals_v = vals[valid]

            # Use weighted average with recency
            mu, sigma = weighted_rate_mu_sigma(vals_v)

            is_pois = self.provider.is_poisson_stat(st)

            out[st] = {
                "ok": True,
                "mu": float(mu),
                "sigma": float(max(sigma, 0.5)),  # Min sigma for stability
                "is_poisson": bool(is_pois),
                "lam": float(max(mu, 1e-6)) if is_pois else float("nan"),
                "n_rounds": int(np.sum(valid)),
            }

        return out

    def calc_prob_over(
        self,
        model: dict,
        line: float,
    ) -> float:
        """Calculate probability of exceeding a line.

        Args:
            model: Model dict
            line: The line (threshold)

        Returns:
            Probability of exceeding the line
        """
        if not model.get("ok"):
            return float("nan")

        from quantitative_sports.models.analysis.statistical_model import poisson_prob_over

        if model["is_poisson"]:
            lam = model.get("lam", 0)
            if lam <= 0:
                return float("nan")
            return poisson_prob_over(line, lam)
        else:
            mu = model.get("mu", 0)
            sigma = model.get("sigma", 0)
            if sigma <= 0 or math.isnan(mu) or math.isnan(sigma):
                return float("nan")

            # P(X > line) = 1 - norm_cdf(line, mu, sigma)
            z = (line - mu) / (sigma * math.sqrt(2.0))
            return 0.5 * (1.0 + math.erf(z))


# =============================================================================
# PGA Evaluator for Per-Site Analysis
# =============================================================================


@dataclass
class PGALeg:
    """A leg for PGA slip/entry building."""

    player_name: str
    tournament: str
    course: str
    stat_type: str
    line: float
    probability: float
    edge: float
    side: str  # "Over" or "Under"
    start_local: str = ""


@dataclass
class PGAEntry:
    """A complete PGA entry recommendation."""

    entry_type: str  # e.g., "PrizePicks_POWER_5"
    format_type: str  # "prizepicks", "underdog", "fanduel"
    n_legs: int
    legs: list[PGALeg]
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


class PGAEvaluator(BaseEvaluator):
    """Evaluate PGA props for per-site analysis.

    Supports:
    - PrizePicks: More/Less pick'em
    - Underdog: Higher/Lower pick'em (if available)
    - FanDuel: DFS lineups

    PGA markets:
    - Strokes gained: total, tee-to-green, putting, etc.
    - Traditional: birdies, pars, GIR, putts
    - Finish: top-10, top-20, cut made, winner
    """

    def __init__(
        self,
        model_weight: float = 0.25,  # Lower for golf
        min_confidence: float = 40.0,
        min_edge: float = 0.03,
        base_kelly: float = 0.20,  # Lower Kelly for golf
        stat_model: Optional[PGATournamentModel] = None,
    ):
        """Initialize PGA evaluator.

        Args:
            model_weight: Weight given to model probability
            min_confidence: Minimum confidence to recommend
            min_edge: Minimum edge to recommend
            base_kelly: Base Kelly fraction
            stat_model: PGA tournament model
        """
        super().__init__(
            model_weight=model_weight,
            min_confidence=min_confidence,
            min_edge=min_edge,
            base_kelly=base_kelly,
        )
        self.stat_model = stat_model or PGATournamentModel()

    def evaluate_projection(
        self,
        projection,
        market_odds: Optional[dict] = None,
        model_prob: Optional[float] = None,
        side_override: Optional[str] = None,
        site: str = "PrizePicks",
    ) -> EvaluationResult:
        """Evaluate a single PGA projection.

        Args:
            projection: PGA Projection object
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

        # Check if finish prop
        is_finish = is_pga_finish_prop(stat_type)

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
            if market_odds:
                over_odds = market_odds.get("over", -110)
                over_prob = self.american_to_prob(over_odds)
                # For strokes gained, over means better performance
                # For strokes (total), lower is better
                if is_finish or "gained" in stat_type.lower():
                    recommended_side = over_term if over_prob > 0.5 else under_term
                else:
                    recommended_side = under_term if over_prob > 0.5 else over_term
            else:
                # Default assumption
                recommended_side = (
                    over_term if "gained" in stat_type.lower() or is_finish else under_term
                )

        alternative_side = under_term if recommended_side == over_term else over_term

        # Calculate model probability if not provided
        if model_prob is None:
            try:
                models = self.stat_model.build_player_model(player_name, [stat_type])
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
            implied_over = self.american_to_prob(-110)
            implied_under = self.american_to_prob(-110)
            fair_prob = 0.5
            market_prob = fair_prob

        # Blend probabilities
        final_prob = self.logit_blend(model_prob, fair_prob)

        # Calculate edge
        edge = final_prob - market_prob

        # Get payout multiplier
        payout_mult = PGA_TIER_PAYOUT_MODIFIERS.get(tier, 1.0)
        single_payout = 1.91

        # For finish props, adjust payout
        if is_finish:
            payout_mult *= 1.5

        # Calculate EV
        ev = final_prob * single_payout * payout_mult - 1.0

        # Calculate confidence
        confidence = self.calculate_confidence(
            final_prob,
            market_prob,
            sample_size=3,  # Fewer books for golf
            edge=edge,
        )

        # Calculate Kelly
        kelly_frac = self.kelly_criterion(
            final_prob,
            single_payout * payout_mult,
            self.base_kelly,
        )

        # Risk score - golf is higher variance
        risk = self.risk_score(final_prob, single_payout) * 1.3

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
            projections: List of PGA Projection objects
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
        min_confidence: float = 45.0,
    ) -> list[EvaluationResult]:
        """Get the best single-pick recommendations.

        Args:
            projections: List of PGA Projection objects
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
# PGA Per-Site Evaluators
# =============================================================================


class PGAPrizePicksEvaluator(PGAEvaluator):
    """PGA PrizePicks-specific evaluator.

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


class PGAUnderdogEvaluator(PGAEvaluator):
    """PGA Underdog-specific evaluator.

    Uses "Higher" and "Lower" terminology.
    Note: Underdog typically doesn't have PGA props.
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


class PGAFanDuelEvaluator(PGAEvaluator):
    """PGA FanDuel-specific evaluator.

    Uses "Over" and "Under" terminology.
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
