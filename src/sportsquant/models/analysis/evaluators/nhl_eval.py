"""NHL-specific statistical model and evaluation.

This module provides NHL-specific statistical modeling using historical
game data. NHL props focus on goals, assists, points, saves, and shutouts.

Key features:
- Separate modeling for skaters and goalies
- Poisson distribution for goal-based stats
- Integration with per-site evaluators (PrizePicks, FanDuel, Underdog)
"""

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

from sportsquant.models.analysis.engine import BaseEvaluator, EvaluationResult
from sportsquant.models.analysis.rules.nhl import (
    NHL_TIER_PAYOUT_MODIFIERS,
    calculate_nhl_fanduel_points,
    get_nhl_stat_key,
    is_nhl_goalie_stat,
    is_nhl_poisson_stat,
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


def compute_nhl_stat_from_gamelog_row(stat_type: str, row: pd.Series) -> float:
    """Compute NHL stat value from a gamelog row.

    Args:
        stat_type: The type of stat to compute
        row: DataFrame row from gamelog

    Returns:
        The stat value or NaN if not computable
    """
    # Skater stats
    goals = safe_float(row.get("G") or row.get("Goals") or row.get("goals"))
    assists = safe_float(row.get("A") or row.get("Assists") or row.get("assists"))
    points = safe_float(row.get("Pts") or row.get("Points") or row.get("points"))
    shots = safe_float(
        row.get("SOG") or row.get("Shots") or row.get("shots_on_goal") or row.get("shots")
    )
    hits = safe_float(row.get("Hits") or row.get("hits"))
    blocks = safe_float(row.get("BS") or row.get("Blocks") or row.get("blocked_shots"))
    pp_points = safe_float(row.get("PPP") or row.get("PowerPlayPoints") or row.get("pp_points"))
    sh_points = safe_float(row.get("SHP") or row.get("SHPoints") or row.get("sh_points"))
    takeaways = safe_float(row.get("TK") or row.get("Takeaways") or row.get("takeaways"))
    giveaways = safe_float(row.get("GV") or row.get("Giveaways") or row.get("giveaways"))
    fow = safe_float(row.get("FOW") or row.get("FaceoffWins") or row.get("faceoff_wins"))
    plus_minus = safe_float(row.get("+/-") or row.get("PlusMinus") or row.get("plus_minus"))
    pim = safe_float(row.get("PIM") or row.get("PenaltyMinutes") or row.get("penalty_minutes"))

    # Goalie stats
    saves = safe_float(row.get("S") or row.get("Saves") or row.get("saves"))
    shots_against = safe_float(row.get("SA") or row.get("ShotsAgainst") or row.get("shots_against"))
    goals_against = safe_float(row.get("GA") or row.get("GoalsAgainst") or row.get("goals_against"))
    shutouts = safe_float(row.get("SO") or row.get("Shutouts") or row.get("shutouts"))
    wins = safe_float(row.get("W") or row.get("Wins") or row.get("wins"))

    # Fantasy points
    fdp_pts = safe_float(row.get("FDP") or row.get("FanDuelPoints") or row.get("fanduel_points"))

    st = (stat_type or "").strip().lower()

    # Normalize stat type
    st = get_nhl_stat_key(st)

    # Skater stats
    if st == "goals":
        return goals
    if st == "assists":
        return assists
    if st == "points":
        return (
            points
            if not math.isnan(points)
            else (
                goals + assists if not (math.isnan(goals) or math.isnan(assists)) else float("nan")
            )
        )
    if st == "shots_on_goal":
        return shots
    if st == "hits":
        return hits
    if st == "blocked_shots":
        return blocks
    if st == "power_play_points":
        return pp_points
    if st == "shorthanded_points":
        return sh_points
    if st == "takeaways":
        return takeaways
    if st == "giveaways":
        return giveaways
    if st == "faceoff_wins":
        return fow
    if st == "plus_minus":
        return plus_minus
    if st == "penalty_minutes":
        return pim

    # Goalie stats
    if st == "saves":
        return saves
    if st == "shots_against":
        return shots_against
    if st == "goals_against":
        return goals_against
    if st == "shutouts":
        return shutouts
    if st == "wins":
        return wins
    if st == "save_percentage":
        if math.isnan(saves) or math.isnan(shots_against) or shots_against == 0:
            return float("nan")
        return saves / shots_against
    if st == "goals_against_average":
        return goals_against

    # Fantasy score
    if st in ("fantasy_points", "fantasy_score", "fanduel_fantasy"):
        if not math.isnan(fdp_pts):
            return fdp_pts
        return calculate_nhl_fanduel_points(
            {
                "Goals": goals,
                "Assists": assists,
                "Shots on Goal": shots,
                "Power Play Points": pp_points,
                "Shorthanded Points": sh_points,
                "Blocked Shots": blocks,
                "Hits": hits,
                "Takeaways": takeaways,
                "Faceoff Wins": fow,
                "Goalie Wins": wins,
                "Goalie Saves": saves,
                "Goalie Shutouts": shutouts,
                "Goals Against": goals_against,
            }
        )

    return float("nan")


class NHLDataProvider(PlayerDataProvider):
    """NHL-specific data provider.

    Fetches player data from NHL Stats API (statsapi.web.nhl.com).
    No authentication required.
    """

    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        n_lookback: int = 15,  # NHL season has 82 games
    ):
        """Initialize NHL data provider.

        Args:
            cache_dir: Directory for gamelog cache
            n_lookback: Number of games to fetch
        """
        if cache_dir is not None:
            self.cache_dir = Path(cache_dir)
        else:
            self.cache_dir = Path("./cache/gamelogs/nhl")
            try:
                self.cache_dir.mkdir(parents=True, exist_ok=True)
            except (PermissionError, OSError):
                self.cache_dir = None
        self.n_lookback = n_lookback

        self._player_id_cache: dict[str, int] = {}
        self._gamelog_cache: dict[int, pd.DataFrame] = {}
        self._roster_cache: Optional[pd.DataFrame] = None
        self._roster_loaded: bool = False

    def _load_roster(self) -> pd.DataFrame:
        """Load NHL roster data from API with caching."""
        if self._roster_loaded and self._roster_cache is not None:
            return self._roster_cache

        try:
            import urllib.request
            import json

            url = "https://api.nhle.com/stats/rest/en/players?limit=500"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as response:
                data = json.loads(response.read().decode())

            players = data.get("data", [])
            self._roster_cache = pd.DataFrame(players)
            self._roster_loaded = True
            return self._roster_cache
        except Exception as e:
            print(f"Failed to load NHL roster: {e}")
            self._roster_cache = pd.DataFrame()
            self._roster_loaded = True
            return self._roster_cache

    def get_player_id(self, name: str) -> Optional[int]:
        """Resolve player name to NHL player ID.

        Uses NHL Stats API to search for player by name.
        Returns the player's id from the API.

        Args:
            name: Player name

        Returns:
            NHL player ID or None if not found
        """
        if name in self._player_id_cache:
            return self._player_id_cache[name]

        try:
            import urllib.request
            import json

            # Search players by full name - encode properly for URL
            # Use the statsapi.web.nhl.com endpoint instead
            encoded_name = name.replace(" ", "%20").replace("#", "%23")
            url = f"https://statsapi.web.nhl.com/api/v1/search/players?name={encoded_name}"

            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode())

            players = data.get("players", [])
            if players:
                # Take the first match
                player_id = int(players[0]["id"])
                self._player_id_cache[name] = player_id
                return player_id

        except Exception as e:
            print(f"NHL player ID lookup failed for {name}: {e}")

        return None

    def get_gamelog(self, player_id: int, lookback: int = 15) -> pd.DataFrame:
        """Fetch NHL gamelog for player with caching.

        Uses NHL Stats API to get game log data.

        Args:
            player_id: NHL player ID
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

            # Fetch player stats game log
            url = f"https://statsapi.web.nhl.com/api/v1/people/{player_id}/stats?stats=gameLog"

            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as response:
                data = json.loads(response.read().decode())

            rows = []
            stats = data.get("stats", [])
            if stats and "splits" in stats[0]:
                for split in stats[0]["splits"]:
                    game = split.get("game", {})
                    stat = split.get("stat", {})

                    row = {
                        "game_id": game.get("id"),
                        "game_date": game.get("game_date"),
                        "season": game.get("season"),
                        "game_type": game.get("game_type"),
                        "team": game.get("team", {}).get("name") if game.get("team") else None,
                        "opponent": game.get("opponent", {}).get("name")
                        if game.get("opponent")
                        else None,
                    }

                    # Copy all stat fields
                    for k, v in stat.items():
                        if v is not None:
                            row[k] = v

                    rows.append(row)

            df = pd.DataFrame(rows)

            # Sort by date descending
            if "game_date" in df.columns:
                df = df.sort_values("game_date", ascending=False)

            # Save to cache
            if cache_path and not df.empty:
                try:
                    df.to_pickle(cache_path)
                except (PermissionError, OSError):
                    pass

            self._gamelog_cache[cache_key] = df
            return df.head(lookback)

        except Exception as e:
            print(f"Failed to fetch NHL gamelog for {player_id}: {e}")
            return pd.DataFrame()

    def compute_stat(self, stat_type: str, row: pd.Series) -> float:
        """Compute NHL stat from gamelog row."""
        return compute_nhl_stat_from_gamelog_row(stat_type, row)

    def parse_minutes(self, min_str) -> float:
        """Parse NHL time on ice string.

        Format: "MM:SS" or just return 1.0 for validity
        """
        if min_str is None:
            return 1.0
        if isinstance(min_str, (int, float)):
            return float(min_str)
        s = str(min_str).strip()
        if ":" in s:
            try:
                mins, secs = s.split(":", 1)
                return float(mins) + float(secs) / 60.0
            except (ValueError, TypeError):
                return 1.0
        try:
            return float(s)
        except (ValueError, TypeError):
            return 1.0

    def is_poisson_stat(self, stat_type: str) -> bool:
        """NHL-specific Poisson stat check."""
        return is_nhl_poisson_stat(stat_type)


class NHLStatisticalModel(StatisticalModel):
    """NHL-specific statistical model.

    Extends StatisticalModel with NHL-specific stat calculations.
    """

    def __init__(
        self,
        data_provider: Optional[NHLDataProvider] = None,
        base_blend: float = 0.30,
    ):
        """Initialize NHL statistical model.

        Args:
            data_provider: NHL data provider
            base_blend: Base model weight for logit blend
        """
        provider = data_provider or NHLDataProvider()
        super().__init__(
            data_provider=provider,
            min_games=10,  # Need sufficient sample for hockey
            min_valid_minutes=1.0,  # Shift-based, not minutes
            cap_minutes=1.0,
            base_blend=base_blend,
        )

    def is_goalie(self, player_name: str) -> bool:
        """Check if player is a goalie.

        Args:
            player_name: Player name

        Returns:
            True if likely a goalie
        """
        goalie_indicators = ["goalie", "goalkeeper", "gk"]
        return any(g in player_name.lower() for g in goalie_indicators)


# =============================================================================
# NHL Evaluator for Per-Site Analysis
# =============================================================================


@dataclass
class NHLLeg:
    """A leg for NHL slip/entry building."""

    player_name: str
    team: str
    opponent: str
    stat_type: str
    line: float
    probability: float
    edge: float
    side: str  # "Over" or "Under"
    position: str = "F"  # F (forward), D (defense), G (goalie)
    is_goalie: bool = False
    start_local: str = ""


@dataclass
class NHLEntry:
    """A complete NHL entry recommendation."""

    entry_type: str  # e.g., "PrizePicks_POWER_5"
    format_type: str  # "prizepicks", "underdog", "fanduel"
    n_legs: int
    legs: list[NHLLeg]
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


class NHLEvaluator(BaseEvaluator):
    """Evaluate NHL props for per-site analysis.

    Supports:
    - PrizePicks: More/Less pick'em
    - Underdog: Higher/Lower pick'em
    - FanDuel: Picks format

    NHL markets:
    - Skaters: goals, assists, points, shots, hits, blocks, PPP, SHP
    - Goalies: wins, saves, shutouts, GAA, save %
    """

    def __init__(
        self,
        model_weight: float = 0.30,
        min_confidence: float = 45.0,
        min_edge: float = 0.03,
        base_kelly: float = 0.25,
        stat_model: Optional[NHLStatisticalModel] = None,
    ):
        """Initialize NHL evaluator.

        Args:
            model_weight: Weight given to model probability
            min_confidence: Minimum confidence to recommend
            min_edge: Minimum edge to recommend
            base_kelly: Base Kelly fraction
            stat_model: NHL statistical model
        """
        super().__init__(
            model_weight=model_weight,
            min_confidence=min_confidence,
            min_edge=min_edge,
            base_kelly=base_kelly,
        )
        self.stat_model = stat_model or NHLStatisticalModel()

    def evaluate_projection(
        self,
        projection,
        market_odds: Optional[dict] = None,
        model_prob: Optional[float] = None,
        side_override: Optional[str] = None,
        site: str = "PrizePicks",
    ) -> EvaluationResult:
        """Evaluate a single NHL projection.

        Args:
            projection: NHL Projection object
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

        # Check if goalie
        is_goalie = is_nhl_goalie_stat(stat_type)

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
                recommended_side = over_term if over_prob > 0.5 else under_term
            else:
                # Goalies tend to have juice to the under on saves
                recommended_side = under_term if is_goalie else over_term

        alternative_side = under_term if recommended_side == over_term else over_term

        # Calculate model probability if not provided
        if model_prob is None:
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
            implied_over = self.american_to_prob(-110)
            implied_under = self.american_to_prob(-110)
            fair_prob = 0.5
            market_prob = fair_prob

        # Blend probabilities
        final_prob = self.logit_blend(model_prob, fair_prob)

        # Calculate edge
        edge = final_prob - market_prob

        # Get payout multiplier
        payout_mult = NHL_TIER_PAYOUT_MODIFIERS.get(tier, 1.0)
        single_payout = 1.91

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
            projections: List of NHL Projection objects
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
            projections: List of NHL Projection objects
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
# NHL Per-Site Evaluators
# =============================================================================


class NHLPrizePicksEvaluator(NHLEvaluator):
    """NHL PrizePicks-specific evaluator.

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


class NHLUnderdogEvaluator(NHLEvaluator):
    """NHL Underdog-specific evaluator.

    Uses "Higher" and "Lower" terminology.
    Note: Underdog may not have NHL props available.
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


class NHLFanDuelEvaluator(NHLEvaluator):
    """NHL FanDuel-specific evaluator.

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
