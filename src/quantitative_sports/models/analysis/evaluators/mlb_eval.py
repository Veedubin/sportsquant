"""MLB-specific statistical model and evaluation.

This module provides MLB-specific statistical modeling using historical
game data. MLB props focus on batting (hits, runs, HRs, RBIs, etc.)
and pitching (strikeouts, outs, ERA, WHIP).

Key features:
- Separate handling for batters and pitchers
- Poisson distribution for counting stats (K's, HRs, hits, etc.)
- Rate-based stats for batting average, ERA, etc.
- Integration with per-site evaluators (PrizePicks, FanDuel, Underdog)
"""

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

from quantitative_sports.models.analysis.engine import BaseEvaluator, EvaluationResult
from quantitative_sports.models.analysis.rules.mlb import (
    MLB_TIER_PAYOUT_MODIFIERS,
    calculate_mlb_fanduel_points,
    get_mlb_stat_key,
    is_mlb_poisson_stat,
    is_pitcher_stat,
)
from quantitative_sports.models.analysis.statistical_model import (
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


def compute_mlb_stat_from_gamelog_row(stat_type: str, row: pd.Series) -> float:
    """Compute MLB stat value from a gamelog row.

    Args:
        stat_type: The type of stat to compute
        row: DataFrame row from gamelog

    Returns:
        The stat value or NaN if not computable
    """
    # Batting stats
    hits = safe_float(row.get("H") or row.get("Hits") or row.get("hits") or row.get("hits"))
    runs = safe_float(row.get("R") or row.get("Runs") or row.get("runs") or row.get("runs"))
    rbi = safe_float(row.get("RBI") or row.get("rbi") or row.get("runsBattedIn"))
    hr = safe_float(row.get("HR") or row.get("homeRuns") or row.get("home_runs"))
    singles = safe_float(row.get("1B") or row.get("singles"))
    doubles = safe_float(row.get("2B") or row.get("doubles") or row.get("doubles"))
    triples = safe_float(row.get("3B") or row.get("triples") or row.get("triples"))
    total_bases = safe_float(row.get("TB") or row.get("total_bases"))
    sb = safe_float(row.get("SB") or row.get("stolen_bases") or row.get("stolenBases"))
    walks = safe_float(row.get("BB") or row.get("walks") or row.get("baseOnBalls"))
    strikeouts = safe_float(
        row.get("K") or row.get("SO") or row.get("strikeouts") or row.get("strikeOuts")
    )

    # Pitching stats
    pitcher_k = safe_float(
        row.get("K") or row.get("SO") or row.get("strikeouts") or row.get("strikeOuts")
    )
    outs = safe_float(
        row.get("OUT") or row.get("Out") or row.get("outs_pitched") or row.get("outsPitched")
    )
    er = safe_float(row.get("ER") or row.get("earned_runs") or row.get("earnedRuns"))
    ip = safe_float(row.get("IP") or row.get("innings_pitched") or row.get("inningsPitched"))
    walks_allowed = safe_float(row.get("BB") or row.get("walks") or row.get("baseOnBalls"))
    hits_allowed = safe_float(row.get("H") or row.get("hits_allowed") or row.get("hitsAllowed"))

    # Fantasy points
    fdp_pts = safe_float(row.get("FDP") or row.get("FanDuelPoints") or row.get("fanduel_points"))

    st = (stat_type or "").strip().lower()

    # Normalize stat type
    st = get_mlb_stat_key(st)

    # Batting stats
    if st == "hits":
        return hits
    if st == "runs":
        return runs
    if st == "rbi":
        return rbi
    if st == "hr":
        return hr
    if st == "singles":
        # Singles = Hits - Doubles - Triples - HRs
        if not math.isnan(hits):
            dbls = doubles if not math.isnan(doubles) else 0
            trpls = triples if not math.isnan(triples) else 0
            hrs = hr if not math.isnan(hr) else 0
            singles_val = hits - dbls - trpls - hrs
            return max(0, singles_val) if not math.isnan(hits) else float("nan")
        return float("nan")
    if st == "doubles":
        return doubles
    if st == "triples":
        return triples
    if st == "total_bases":
        if not math.isnan(total_bases):
            return total_bases
        # total_bases = singles*1 + doubles*2 + triples*3 + hr*4
        sngls = singles if not math.isnan(singles) else 0
        dbls = doubles if not math.isnan(doubles) else 0
        trpls = triples if not math.isnan(triples) else 0
        hrs = hr if not math.isnan(hr) else 0
        return sngls + dbls * 2 + trpls * 3 + hrs * 4
    if st == "stolen_bases":
        return sb
    if st == "walks":
        return walks
    if st == "strikeouts":
        return strikeouts

    # Pitching stats
    if st == "pitcher_strikeouts":
        return pitcher_k
    if st == "pitcher_outs":
        if not math.isnan(outs):
            return outs
        # Convert IP to outs (IP * 3)
        if not math.isnan(ip):
            return ip * 3
        return float("nan")
    if st == "earned_runs":
        return er
    if st == "innings_pitched":
        if not math.isnan(ip):
            return ip
        # Convert outs to IP (outs / 3)
        if not math.isnan(outs):
            return outs / 3
        return float("nan")
    if st == "walks_allowed":
        return walks_allowed
    if st == "hits_allowed":
        return hits_allowed

    # Combined stats
    if st == "hits_runs_rbi":
        h = hits if not math.isnan(hits) else 0
        r = runs if not math.isnan(runs) else 0
        rb = rbi if not math.isnan(rbi) else 0
        if math.isnan(hits) and math.isnan(runs) and math.isnan(rbi):
            return float("nan")
        return h + r + rb
    if st == "runs_rbi":
        r = runs if not math.isnan(runs) else 0
        rb = rbi if not math.isnan(rbi) else 0
        if math.isnan(runs) and math.isnan(rbi):
            return float("nan")
        return r + rb
    if st == "hr_rbi":
        hrs = hr if not math.isnan(hr) else 0
        rb = rbi if not math.isnan(rbi) else 0
        if math.isnan(hr) and math.isnan(rbi):
            return float("nan")
        return hrs + rb
    if st == "hits_runs":
        h = hits if not math.isnan(hits) else 0
        r = runs if not math.isnan(runs) else 0
        if math.isnan(hits) and math.isnan(runs):
            return float("nan")
        return h + r

    # Fantasy score
    if st in ("fantasy_points", "fantasy_score", "fanduel_fantasy"):
        return (
            fdp_pts
            if not math.isnan(fdp_pts)
            else calculate_mlb_fanduel_points(
                {
                    "Singles": singles if not math.isnan(singles) else 0,
                    "Doubles": doubles if not math.isnan(doubles) else 0,
                    "Triples": triples if not math.isnan(triples) else 0,
                    "Home Runs": hr if not math.isnan(hr) else 0,
                    "Runs Scored": runs if not math.isnan(runs) else 0,
                    "Runs Batted In": rbi if not math.isnan(rbi) else 0,
                    "Walks": walks if not math.isnan(walks) else 0,
                    "Stolen Bases": sb if not math.isnan(sb) else 0,
                    "Strikeouts": pitcher_k if not math.isnan(pitcher_k) else 0,
                    "Innings Pitched": ip if not math.isnan(ip) else 0,
                    "Earned Runs Allowed": er if not math.isnan(er) else 0,
                }
            )
        )

    return float("nan")


class MLBDataProvider(PlayerDataProvider):
    """MLB-specific data provider.

    Fetches player data from MLB Stats API (statsapi.mlb.com).
    Free API, no auth required.
    """

    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        n_lookback: int = 25,
    ):
        """Initialize MLB data provider.

        Args:
            cache_dir: Directory for gamelog cache
            n_lookback: Number of games to fetch
        """
        if cache_dir is not None:
            self.cache_dir = Path(cache_dir)
        else:
            self.cache_dir = Path("./cache/gamelogs/mlb")
            try:
                self.cache_dir.mkdir(parents=True, exist_ok=True)
            except (PermissionError, OSError):
                self.cache_dir = None
        self.n_lookback = n_lookback

        self._player_id_cache: dict[str, int] = {}
        self._gamelog_cache: dict[int, pd.DataFrame] = {}

    def get_player_id(self, name: str) -> Optional[int]:
        """Resolve player name to MLB player ID.

        Uses statsapi.mlb.com lookup endpoint.

        Args:
            name: Player name

        Returns:
            MLB player ID or None if not found
        """
        if name in self._player_id_cache:
            return self._player_id_cache[name]

        try:
            import urllib.request
            import json

            # Search for player via MLB Stats API
            encoded_name = urllib.parse.quote(name)
            url = f"https://statsapi.mlb.com/api/v1/people/search?names={encoded_name}&sportId=1&active=true"

            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode())

            people = data.get("people", [])
            if people:
                player_id = int(people[0]["id"])
                self._player_id_cache[name] = player_id
                return player_id
        except Exception:
            pass

        return None

    def get_gamelog(self, player_id: int, lookback: int = 25) -> pd.DataFrame:
        """Fetch MLB gamelog for player with caching.

        Args:
            player_id: MLB player ID
            lookback: Number of games to fetch

        Returns:
            DataFrame with game log data
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

            # Fetch game log from MLB Stats API with proper hydration
            url = f"https://statsapi.mlb.com/api/v1/people/{player_id}/stats?stats=gameLog&group=hitting,pitching&limit={lookback}"

            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as response:
                data = json.loads(response.read().decode())

            rows = []
            stats = data.get("stats", [])

            for stat_group in stats:
                group_name = stat_group.get("group", {}).get("name", "")
                splits = stat_group.get("splits", [])

                for split in splits:
                    game = split.get("game", {})
                    stat = split.get("stat", {})

                    row = {
                        "GAME_DATE": game.get("game_date"),
                        "OPPONENT": game.get("opponent", {}).get("name")
                        if game.get("opponent")
                        else None,
                        "TEAM": game.get("team", {}).get("name") if game.get("team") else None,
                        "stat_group": group_name,
                    }

                    # Copy all stat fields with group prefix
                    for k, v in stat.items():
                        if v is not None:
                            # Use prefixed keys to avoid collisions
                            row[f"{group_name}_{k}"] = v
                            # Also keep unprefixed for convenience
                            if k not in row:
                                row[k] = v

                    rows.append(row)

            if not rows:
                return pd.DataFrame()

            df = pd.DataFrame(rows)

            # Sort by date descending
            if "GAME_DATE" in df.columns:
                df = df.sort_values("GAME_DATE", ascending=False)

            # Save to cache
            if cache_path and not df.empty:
                try:
                    df.to_pickle(cache_path)
                except (PermissionError, OSError):
                    pass

            self._gamelog_cache[cache_key] = df
            return df.head(lookback)

        except Exception as e:
            print(f"MLB gamelog fetch failed for {player_id}: {e}")
            return pd.DataFrame()

    def get_player_info(self, player_id: int) -> Optional[dict]:
        """Fetch player info from MLB Stats API.

        Args:
            player_id: MLB player ID

        Returns:
            Dict with player info or None
        """
        try:
            import urllib.request
            import json

            url = f"https://statsapi.mlb.com/api/v1/people/{player_id}"

            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode())

            people = data.get("people", [])
            if people:
                p = people[0]
                return {
                    "id": p.get("id"),
                    "full_name": p.get("fullName"),
                    "first_name": p.get("firstName"),
                    "last_name": p.get("lastName"),
                    "position": p.get("primaryPosition", {}).get("abbreviation"),
                    "team": p.get("currentTeam", {}).get("name") if p.get("currentTeam") else None,
                    "bats": p.get("batSide", {}).get("description"),
                    "throws": p.get("pitchHand", {}).get("description"),
                }
        except Exception:
            pass
        return None

    def compute_stat(self, stat_type: str, row: pd.Series) -> float:
        """Compute MLB stat from gamelog row."""
        return compute_mlb_stat_from_gamelog_row(stat_type, row)

    def parse_minutes(self, min_str) -> float:
        """Parse MLB game time or plate appearances.

        MLB doesn't use minutes - uses batters faced or innings pitched.
        We use 1.0 to indicate a valid game for simplicity.
        """
        # Return 1.0 for valid game presence
        return 1.0

    def is_poisson_stat(self, stat_type: str) -> bool:
        """MLB-specific Poisson stat check."""
        return is_mlb_poisson_stat(stat_type)


class MLBStatisticalModel(StatisticalModel):
    """MLB-specific statistical model.

    Extends StatisticalModel with MLB-specific stat calculations.
    Uses min_games=8 for MLB (162 game season).
    """

    def __init__(
        self,
        data_provider: Optional[MLBDataProvider] = None,
        base_blend: float = 0.30,
    ):
        """Initialize MLB statistical model.

        Args:
            data_provider: MLB data provider
            base_blend: Base model weight for logit blend
        """
        provider = data_provider or MLBDataProvider()
        super().__init__(
            data_provider=provider,
            min_games=8,  # MLB has 162 games, but we use 8 for recent form
            min_valid_minutes=0.5,  # Any game participation
            cap_minutes=1.0,
            base_blend=base_blend,
        )

    def compute_probability(
        self,
        player_name: str,
        stat_type: str,
        line: float,
    ) -> float:
        """Compute probability for a player's stat over a line.

        Args:
            player_name: Player name
            stat_type: Stat type
            line: Line value

        Returns:
            Probability of over
        """
        models = self.build_model(player_name, [stat_type])
        if models and stat_type in models:
            prob = self.calc_prob_over(models[stat_type], line)
            if not math.isnan(prob):
                return prob
        return 0.52  # Fallback


# =============================================================================
# MLB Evaluator for Per-Site Analysis
# =============================================================================


@dataclass
class MLBLeg:
    """A leg for MLB slip/entry building."""

    player_name: str
    team: str
    opponent: str
    stat_type: str
    line: float
    probability: float
    edge: float
    side: str  # "Over" or "Under"
    position: str = "Batter"
    start_local: str = ""


@dataclass
class MLBEntry:
    """A complete MLB entry recommendation."""

    entry_type: str  # e.g., "PrizePicks_POWER_5"
    format_type: str  # "prizepicks", "underdog", "fanduel"
    n_legs: int
    legs: list[MLBLeg]
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


class MLBEvaluator(BaseEvaluator):
    """Evaluate MLB props for per-site analysis.

    Supports:
    - PrizePicks: More/Less pick'em
    - Underdog: Higher/Lower pick'em
    - FanDuel: Picks format

    MLB markets:
    - Batting: hits, runs, RBI, HR, singles, doubles, triples, total_bases, SB, walks
    - Pitching: strikeouts, outs, earned_runs, innings_pitched
    - Combined: hits+runs+RBI, runs+RBI, HR+RBI
    """

    def __init__(
        self,
        model_weight: float = 0.30,
        min_confidence: float = 45.0,
        min_edge: float = 0.03,
        base_kelly: float = 0.25,
        stat_model: Optional[MLBStatisticalModel] = None,
    ):
        """Initialize MLB evaluator.

        Args:
            model_weight: Weight given to model probability
            min_confidence: Minimum confidence to recommend
            min_edge: Minimum edge to recommend
            base_kelly: Base Kelly fraction
            stat_model: MLB statistical model
        """
        super().__init__(
            model_weight=model_weight,
            min_confidence=min_confidence,
            min_edge=min_edge,
            base_kelly=base_kelly,
        )
        self.stat_model = stat_model or MLBStatisticalModel()

    def _is_pitcher(self, player_name: str) -> bool:
        """Detect if player is likely a pitcher based on stat type context.

        This is a heuristic - in production, we'd use player position data.

        Args:
            player_name: Player name

        Returns:
            True if likely a pitcher
        """
        name_lower = player_name.lower()
        pitcher_indicators = ["pitcher", "pitched", "pitching"]
        return any(ind in name_lower for ind in pitcher_indicators)

    def _detect_player_type_from_stat(self, stat_type: str) -> str:
        """Detect if stat is for pitcher or batter.

        Args:
            stat_type: The stat type

        Returns:
            "pitcher" or "batter"
        """
        stat_key = get_mlb_stat_key(stat_type)
        if is_pitcher_stat(stat_key):
            return "pitcher"
        return "batter"

    def evaluate_projection(
        self,
        projection,
        market_odds: Optional[dict] = None,
        model_prob: Optional[float] = None,
        side_override: Optional[str] = None,
        site: str = "PrizePicks",
    ) -> EvaluationResult:
        """Evaluate a single MLB projection.

        Args:
            projection: MLB Projection object
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
            try:
                model_prob = self.stat_model.compute_probability(player_name, stat_type, line)
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
        payout_mult = MLB_TIER_PAYOUT_MODIFIERS.get(tier, 1.0)
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
            projections: List of MLB Projection objects
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
            projections: List of MLB Projection objects
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
# MLB Per-Site Evaluators
# =============================================================================


class MLBPrizePicksEvaluator(MLBEvaluator):
    """MLB PrizePicks-specific evaluator.

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


class MLBUnderdogEvaluator(MLBEvaluator):
    """MLB Underdog-specific evaluator.

    Uses "Higher" and "Lower" terminology.
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


class MLBFanDuelEvaluator(MLBEvaluator):
    """MLB FanDuel-specific evaluator.

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
