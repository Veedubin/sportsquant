"""End-to-end +EV analysis pipeline.

This module orchestrates the full analysis pipeline:
1. Fetch PrizePicks projections (using simple_fetcher)
2. Match markets to PrizePicks lines (external market data required)
3. Build statistical models (NBA for now)
4. Calculate +EV plays
5. Optimize slips
6. Output results

NOTE: Market odds must be provided externally via sportsbook scrapers.
The Odds API integration has been removed.

Configuration is via AnalysisConfig dataclass.
"""

import math
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

import pandas as pd

from .market_matcher import MarketMatcher, PP_STAT_TO_MARKET_KEY, InterpolationMethod
from .statistical_model import StatisticalModel, NBADataProvider
from .ev_calculator import EVCalculator
from .slip_optimizer import SlipOptimizer
from sportsquant.data.sources.prizepicks.simple_fetcher import SimplePrizePicksFetcher


# Constants
DEFAULT_TZ_NAME = "America/Chicago"
DEFAULT_HOURS_AHEAD = 36

# Market match thresholds
DEFAULT_MIN_ANCHOR_BOOKS_STANDARD = 1
DEFAULT_MIN_BOOKS_TOTAL_STANDARD = 3
DEFAULT_MAX_LINE_DIST_STANDARD = 0.50
DEFAULT_MIN_BOOKS_TOTAL_ALT = 5
DEFAULT_MAX_LINE_DIST_ALT = 0.25
ALT_REQUIRE_METHODS = {"exact", "interp_logit"}

# Model thresholds
DEFAULT_MAX_CANDIDATES_FOR_MODEL = 350
DEFAULT_MAX_PLAYERS_TO_MODEL = 35

# Optimizer thresholds
DEFAULT_MIN_P_POWER = 0.58
DEFAULT_MIN_P_FLEX_34 = 0.55
DEFAULT_MIN_P_FLEX_56 = 0.535
DEFAULT_MAX_PER_PLAYER_POWER = 1
DEFAULT_MAX_PER_GAME_POWER = 2
DEFAULT_MAX_PER_PLAYER_FLEX = 1
DEFAULT_MAX_PER_GAME_FLEX = 2


@dataclass
class AnalysisConfig:
    """Configuration for the analysis pipeline.

    All settings can be overridden via environment variables.
    """

    # Sport settings
    sport_key: str = "basketball_nba"
    league_id: int = 7
    tz_name: str = DEFAULT_TZ_NAME

    # Market match settings
    hours_ahead: int = DEFAULT_HOURS_AHEAD
    anchor_books: tuple[str, ...] = ("draftkings", "fanduel")
    min_anchor_books_standard: int = DEFAULT_MIN_ANCHOR_BOOKS_STANDARD
    min_books_total_standard: int = DEFAULT_MIN_BOOKS_TOTAL_STANDARD
    max_line_dist_standard: float = DEFAULT_MAX_LINE_DIST_STANDARD
    min_books_total_alt: int = DEFAULT_MIN_BOOKS_TOTAL_ALT
    max_line_dist_alt: float = DEFAULT_MAX_LINE_DIST_ALT

    # Model settings
    max_candidates_for_model: int = DEFAULT_MAX_CANDIDATES_FOR_MODEL
    max_players_to_model: int = DEFAULT_MAX_PLAYERS_TO_MODEL
    base_blend_model: float = 0.30
    n_lookback: int = 25
    min_games: int = 12

    # Optimizer settings
    n_sims: int = 80000
    min_p_power: float = DEFAULT_MIN_P_POWER
    min_p_flex_34: float = DEFAULT_MIN_P_FLEX_34
    min_p_flex_56: float = DEFAULT_MIN_P_FLEX_56
    max_per_player_power: int = DEFAULT_MAX_PER_PLAYER_POWER
    max_per_game_power: int = DEFAULT_MAX_PER_GAME_POWER
    max_per_player_flex: int = DEFAULT_MAX_PER_PLAYER_FLEX
    max_per_game_flex: int = DEFAULT_MAX_PER_GAME_FLEX

    # Cache settings
    cache_dir: Optional[Path] = None

    # Over-only tiers (Goblin, Demon only have Over)
    over_only_tiers: tuple[str, ...] = ("Goblin", "Demon")

    @classmethod
    def from_env(cls) -> "AnalysisConfig":
        """Create config from environment variables."""
        return cls(
            sport_key=os.getenv("SPORT_KEY", "basketball_nba"),
            league_id=int(os.getenv("PRIZEPICKS_LEAGUE_ID", "7")),
            tz_name=os.getenv("TZ_NAME", DEFAULT_TZ_NAME),
        )


class AnalysisPipeline:
    """End-to-end +EV analysis pipeline.

    This class orchestrates all the analysis components:
    - SimplePrizePicksFetcher for projections
    - MarketMatcher for odds (external data required)
    - StatisticalModel + NBADataProvider for modeling
    - EVCalculator for +EV
    - SlipOptimizer for slip construction

    NOTE: This pipeline no longer fetches market odds from any API.
    Market data must be provided via set_market_data() before running.
    """

    def __init__(self, config: Optional[AnalysisConfig] = None):
        """Initialize pipeline with config.

        Args:
            config: Analysis configuration (default: from environment)
        """
        self.config = config or AnalysisConfig.from_env()
        self.tz = ZoneInfo(self.config.tz_name)

        # Initialize components
        self.fetcher = SimplePrizePicksFetcher(tz_name=self.config.tz_name)
        self.market_matcher = MarketMatcher(
            anchor_books=set(self.config.anchor_books),
        )
        self.data_provider = NBADataProvider(
            cache_dir=self.config.cache_dir,
            n_lookback=self.config.n_lookback,
        )
        self.statistical_model = StatisticalModel(
            data_provider=self.data_provider,
            min_games=self.config.min_games,
            base_blend=self.config.base_blend_model,
        )
        self.ev_calc = EVCalculator(base_blend=self.config.base_blend_model)
        self.optimizer = SlipOptimizer(n_sims=self.config.n_sims)

        # Results storage
        self.projections_df: Optional[pd.DataFrame] = None
        self.candidates_df: Optional[pd.DataFrame] = None
        self.playable_df: Optional[pd.DataFrame] = None
        self.run_info: Optional[dict] = None

        # External market data (set via set_market_data)
        self._market_data_set = False

    def set_market_data(
        self,
        per_book_df: pd.DataFrame,
        event_map: Optional[dict] = None,
    ) -> None:
        """Set market data from external sportsbook scraper.

        Args:
            per_book_df: DataFrame with columns:
                - event_id: str
                - market_key: str
                - player_name_norm: str
                - line: float
                - book: str
                - p_over_devig: float
            event_map: Optional dict mapping (date_str, team_abbr) -> (opponent_abbr, event_id)
        """
        self.market_matcher.set_market_data(per_book_df, event_map or {})
        self._market_data_set = True

    def _normalize_name(self, s: str) -> str:
        """Normalize player name."""
        import re

        s = (s or "").strip().lower().replace("'", "'")
        s = re.sub(r"[^a-z0-9\s'-]", " ", s)
        s = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b.?", "", s, flags=re.IGNORECASE)
        s = re.sub(r"\s+", " ", s).strip()
        return s

    def _safe_float(self, x) -> float:
        """Safely convert to float."""
        try:
            if x is None:
                return float("nan")
            return float(x)
        except (TypeError, ValueError):
            return float("nan")

    def fetch_projections(self) -> pd.DataFrame:
        """Fetch PrizePicks projections.

        Returns:
            DataFrame with projections
        """
        now = datetime.now(self.tz)

        # Fetch PrizePicks projections
        projections = self.fetcher.fetch_projections(
            league_id=self.config.league_id,
            hours_ahead=self.config.hours_ahead,
        )

        if not projections:
            raise RuntimeError("No PrizePicks projections returned")

        # Convert to DataFrame
        pp_rows = []
        for p in projections:
            start_dt = p.start_time
            start_local = start_dt.astimezone(self.tz) if start_dt else None

            pp_rows.append(
                {
                    "Projection_ID": p.id,
                    "Player": p.player_name,
                    "Player_Norm": self._normalize_name(p.player_name or ""),
                    "Team": p.team_name,
                    "Team_Abbr": p.team_abbreviation,
                    "Stat_Type": p.stat_type,
                    "PP_Line": p.line_score,
                    "PP_Tier": p.stat_type,  # Will be normalized later
                    "Start_Time": start_dt,
                    "Start_Local_DT": start_local,
                    "Start_Date": start_local.date().isoformat() if start_local else None,
                }
            )

        pp_df = pd.DataFrame(pp_rows)
        pp_df = pp_df.drop_duplicates(subset=["Player_Norm", "Stat_Type", "PP_Line"]).copy()

        # Filter by start time
        cutoff = now + timedelta(hours=self.config.hours_ahead)
        pp_df = pp_df[pp_df["Start_Local_DT"].notna()].copy()
        pp_df = pp_df[pp_df["Start_Local_DT"] <= cutoff].copy()

        if pp_df.empty:
            raise RuntimeError(f"No props within next {self.config.hours_ahead} hours")

        self.projections_df = pp_df
        return pp_df

    def market_pass(self, pp_df: pd.DataFrame, agg_df: pd.DataFrame) -> pd.DataFrame:
        """Run market matching pass to build candidate list.

        Args:
            pp_df: Projections DataFrame
            agg_df: Aggregated market DataFrame

        Returns:
            DataFrame of candidates that passed market filters
        """
        from difflib import get_close_matches

        cand_rows = []

        for _, r in pp_df.iterrows():
            st = r.get("Stat_Type")
            odds_market = PP_STAT_TO_MARKET_KEY.get(st)
            if not odds_market:
                continue

            eid = str(r.get("Event_ID", ""))
            player_norm = self._normalize_name(r.get("Player", ""))
            line = float(r.get("PP_Line", 0))
            tier = r.get("PP_Tier", "Standard")

            # Find player's lines for this event/market
            sub = agg_df[(agg_df["event_id"] == eid) & (agg_df["market_key"] == odds_market)]

            if sub.empty:
                continue

            # Fuzzy match player name
            psub = sub[sub["player_name_norm"] == player_norm].copy()
            fuzzy_used = ""

            if psub.empty:
                cand = sorted(sub["player_name_norm"].unique().tolist())
                best = get_close_matches(player_norm, cand, n=1, cutoff=0.90)
                if not best:
                    continue
                fuzzy_used = best[0]
                psub = sub[sub["player_name_norm"] == fuzzy_used].copy()
                if psub.empty:
                    continue

            psub = psub.dropna(subset=["line"]).copy()
            psub["line"] = psub["line"].astype(float)
            psub = psub.sort_values("line").reset_index(drop=True)

            # Get anchor and all-books interpolations
            anchor = self.market_matcher.interp_prob_at_line(psub, line, "anchor_over")
            allbk = self.market_matcher.interp_prob_at_line(psub, line, "all_over")

            anchor_prob = self._safe_float(anchor.probability)
            all_prob = self._safe_float(allbk.probability)
            anchor_ct = int(anchor.books_anchor_count or 0)
            books_ct = int(allbk.books_all_count or 0)

            # Calculate line distance
            def _line_dist(a):
                lo = self._safe_float(a.line_low)
                hi = self._safe_float(a.line_high)
                d = float("nan")
                if not math.isnan(lo):
                    d = abs(line - lo)
                if not math.isnan(hi):
                    d2 = abs(line - hi)
                    d = min(d, d2) if not math.isnan(d) else d2
                return d

            line_dist = (
                _line_dist(anchor)
                if anchor.method != InterpolationMethod.NONE
                else _line_dist(allbk)
            )

            market_method = "none"
            market_over = float("nan")
            market_source = ""

            if tier == "Standard":
                if (
                    anchor.method.value in ("exact", "interp_logit")
                    and anchor_ct >= self.config.min_anchor_books_standard
                    and not math.isnan(anchor_prob)
                ):
                    market_method = anchor.method.value
                    market_over = anchor_prob
                    market_source = "DKFD"
                else:
                    continue
                if books_ct < self.config.min_books_total_standard:
                    continue
                if not math.isnan(line_dist) and line_dist > self.config.max_line_dist_standard:
                    continue
            else:
                # Goblin/Demon
                if (
                    anchor.method.value in ("exact", "interp_logit")
                    and anchor_ct >= 1
                    and not math.isnan(anchor_prob)
                ):
                    market_method = anchor.method.value
                    market_over = anchor_prob
                    market_source = "DKFD"
                    line_dist = _line_dist(anchor)
                elif (
                    allbk.method.value in ("exact", "interp_logit")
                    and books_ct >= self.config.min_books_total_alt
                    and not math.isnan(all_prob)
                ):
                    market_method = allbk.method.value
                    market_over = all_prob
                    market_source = "ALL"
                    line_dist = _line_dist(allbk)
                else:
                    continue

                if market_method not in ALT_REQUIRE_METHODS:
                    continue
                if books_ct < self.config.min_books_total_alt:
                    continue
                if not math.isnan(line_dist) and line_dist > self.config.max_line_dist_alt:
                    continue

            # Priority score for sorting
            proxy = (
                abs(market_over - 0.5)
                * math.log1p(float(books_ct))
                * (1.15 if market_source == "DKFD" else 1.0)
            )

            cand_rows.append(
                {
                    "Player": r.get("Player"),
                    "Player_Norm": player_norm,
                    "Team": r.get("Team"),
                    "Team_Abbr": r.get("Team_Abbr"),
                    "Opponent": r.get("Opponent", ""),
                    "Stat": st,
                    "PP_Line": line,
                    "PP_Tier": tier,
                    "Event_ID": eid,
                    "Start_Local": r.get("Start_Local_DT").isoformat()
                    if r.get("Start_Local_DT")
                    else "",
                    "Market_Source": market_source,
                    "Market_Method": market_method,
                    "Market_Over_Prob": market_over,
                    "Market_Under_Prob": 1.0 - market_over,
                    "Books_All_Count": books_ct,
                    "Anchor_Books_Count": anchor_ct,
                    "Market_Line_Dist": line_dist,
                    "Market_Priority": proxy,
                }
            )

        cand_df = pd.DataFrame(cand_rows)
        if cand_df.empty:
            raise RuntimeError("No candidates passed market rules")

        # Sort and cap candidates
        cand_df = cand_df.sort_values(
            ["Market_Priority", "Books_All_Count"],
            ascending=[False, False],
        ).reset_index(drop=True)
        cand_df = cand_df.head(self.config.max_candidates_for_model).copy()

        # Cap players too
        top_players = (
            cand_df.groupby(["Player", "Player_Norm"], as_index=False)["Market_Priority"]
            .max()
            .sort_values("Market_Priority", ascending=False)
            .head(self.config.max_players_to_model)
        )
        cand_df = cand_df.merge(
            top_players[["Player", "Player_Norm"]], on=["Player", "Player_Norm"], how="inner"
        )

        self.candidates_df = cand_df
        return cand_df

    def model_pass(self, cand_df: pd.DataFrame) -> pd.DataFrame:
        """Run statistical model pass.

        Args:
            cand_df: Candidates DataFrame from market_pass

        Returns:
            DataFrame of playable props with +EV
        """
        from concurrent.futures import ThreadPoolExecutor

        # Build player -> stats mapping
        unique_players = cand_df[["Player", "Player_Norm"]].drop_duplicates().to_dict("records")
        player_to_models = {}

        def _fetch_and_build(player: str, pn: str, stat_list: list[str]):
            pid = self.data_provider.get_player_id(player)
            if pid is None:
                return (player, pn, {})

            try:
                gl = self.data_provider.get_gamelog(pid)
            except Exception:
                return (player, pn, {})

            models = self.statistical_model.build_models_from_gamelog(gl, stat_list)
            return (player, pn, models)

        stat_map = {
            (p["Player"], p["Player_Norm"]): sorted(
                set(
                    cand_df[
                        (cand_df["Player"] == p["Player"])
                        & (cand_df["Player_Norm"] == p["Player_Norm"])
                    ]["Stat"].tolist()
                )
            )
            for p in unique_players
        }

        with ThreadPoolExecutor(max_workers=4) as ex:
            futs = [
                ex.submit(_fetch_and_build, player, pn, stats)
                for (player, pn), stats in stat_map.items()
            ]

            for f in futs:
                try:
                    player, pn, models = f.result()
                    player_to_models[(player, pn)] = models
                except Exception:
                    continue

        # Calculate EV for each candidate
        out_rows = []
        over_only_tiers = set(self.config.over_only_tiers)

        for _, rr in cand_df.iterrows():
            models = player_to_models.get((rr.get("Player"), {}))
            model = models.get(rr.get("Stat"))
            if not model:
                continue

            line = float(rr.get("PP_Line"))
            tier = rr.get("PP_Tier")
            market_over = float(rr.get("Market_Over_Prob"))

            if model.get("is_poisson"):
                lam = model.get("lam")
                if lam and lam > 0:
                    model_over = 1.0 - self._poisson_cdf(int(math.floor(line)), lam)
                else:
                    model_over = float("nan")
            else:
                mu = model.get("mu", 0)
                sigma = model.get("sigma", 0)
                if sigma > 0 and not math.isnan(mu) and not math.isnan(sigma):
                    z = (line - mu) / (sigma * math.sqrt(2.0))
                    model_over = 0.5 * (1.0 + math.erf(z))
                else:
                    model_over = float("nan")

            if math.isnan(model_over):
                continue

            model_under = 1.0 - model_over
            market_under = 1.0 - market_over

            blend_eff = self.statistical_model.get_blend_weight(model)

            # Logit blend
            final_over = self.ev_calc.logit_blend(model_over, market_over, blend_eff)
            final_under = self.ev_calc.logit_blend(model_under, market_under, blend_eff)

            if tier in over_only_tiers:
                rec = "Over"
                final_side = final_over
                market_side = market_over
            else:
                if final_over >= final_under:
                    rec = "Over"
                    final_side = final_over
                    market_side = market_over
                else:
                    rec = "Under"
                    final_side = final_under
                    market_side = market_under

            edge = final_side - market_side
            if edge < 0:
                continue

            books_all = float(rr.get("Books_All_Count") or 0)
            base = 100.0 * max(0, min(1, (final_side - 0.5) / 0.5))
            conf = min(100, max(0, base + 6.0 * (1.0 - math.exp(-books_all / 5.0))))

            out_rows.append(
                {
                    "Player": rr.get("Player"),
                    "Team": rr.get("Team"),
                    "Opponent": rr.get("Opponent"),
                    "Stat": rr.get("Stat"),
                    "PP_Line": rr.get("PP_Line"),
                    "PP_Tier": tier,
                    "Recommended_Side": rec,
                    "Final_Prob_Side": round(float(final_side), 4),
                    "Market_Side_Prob": round(float(market_side), 4),
                    "Edge_vs_Market": round(float(edge), 4),
                    "Confidence": round(float(conf), 1),
                    "Market_Source": rr.get("Market_Source"),
                    "Market_Method": rr.get("Market_Method"),
                    "Books_All_Count": int(rr.get("Books_All_Count")),
                    "Anchor_Books_Count": int(rr.get("Anchor_Books_Count")),
                    "Market_Line_Dist": rr.get("Market_Line_Dist"),
                    "Min_Median": model.get("min_med"),
                    "Min_SD": model.get("min_sd"),
                    "Min_CV": model.get("min_cv"),
                    "Blend_Eff": round(float(blend_eff), 3),
                    "Model_Over_Prob": round(float(model_over), 4),
                    "Start_Local": rr.get("Start_Local"),
                }
            )

        playable = pd.DataFrame(out_rows)
        playable = playable.sort_values(
            ["Final_Prob_Side", "Edge_vs_Market", "Books_All_Count", "Confidence"],
            ascending=[False, False, False, False],
            na_position="last",
        ).reset_index(drop=True)

        self.playable_df = playable
        return playable

    def _poisson_cdf(self, k: int, lam: float) -> float:
        """Poisson CDF."""
        if lam <= 0:
            return 1.0 if k >= 0 else 0.0
        s = 0.0
        term = math.exp(-lam)
        s += term
        for i in range(1, k + 1):
            term *= lam / i
            s += term
        return min(1.0, max(0.0, s))

    def optimize_slips(
        self,
        format_type: str = "power",
        n_legs: int = 3,
    ) -> pd.DataFrame:
        """Optimize slips from playable props.

        Args:
            format_type: "power" or "flex"
            n_legs: Number of legs

        Returns:
            DataFrame of optimized slips
        """
        if self.playable_df is None or self.playable_df.empty:
            return pd.DataFrame()

        legs_pool = self.optimizer.build_legs_from_dataframe(self.playable_df)

        if format_type.lower() == "power":
            min_p = self.config.min_p_power
            max_per_player = self.config.max_per_player_power
            max_per_game = self.config.max_per_game_power
        else:
            min_p = self.config.min_p_flex_34 if n_legs <= 4 else self.config.min_p_flex_56
            max_per_player = self.config.max_per_player_flex
            max_per_game = self.config.max_per_game_flex

        results = self.optimizer.optimize_slips(
            legs_pool=legs_pool,
            format_type=format_type,
            n_legs=n_legs,
            max_per_player=max_per_player,
            max_per_game=max_per_game,
            min_p=min_p,
            top_k=20,
        )

        if not results:
            return pd.DataFrame()

        rows = []
        for r in results:
            rows.append(
                {
                    "rank": r.rank,
                    "ev": round(r.ev, 4),
                    "avg_p": round(r.avg_probability, 4),
                    "legs": r.legs_description,
                }
            )

        return pd.DataFrame(rows)

    def run_with_projections(self, pp_df: pd.DataFrame, agg_df: pd.DataFrame) -> dict:
        """Run analysis with provided projections and market data.

        Args:
            pp_df: Projections DataFrame
            agg_df: Aggregated market DataFrame

        Returns:
            Dict with analysis results
        """
        # Store projections
        self.projections_df = pp_df

        # Market pass
        cand_df = self.market_pass(pp_df, agg_df)

        # Model pass
        playable = self.model_pass(cand_df)

        if playable.empty:
            raise RuntimeError("No playable props after model+edge filter")

        # Store run info
        now = datetime.now(self.tz)
        self.run_info = {
            "run_time": now.isoformat(),
            "timezone": self.config.tz_name,
            "hours_ahead_filter": self.config.hours_ahead,
            "candidates_for_model": len(cand_df),
            "players_modeled": playable["Player"].nunique(),
            "playable_count": len(playable),
            "sport_key": self.config.sport_key,
            "league_id": self.config.league_id,
        }

        return {
            "run_info": self.run_info,
            "playable": playable,
        }

    def to_excel(self, filepath: Path) -> None:
        """Export results to Excel workbook.

        Creates a multi-sheet workbook with:
        - Run_Info: Run metadata
        - Playable: All playable props
        - POWER_2..POWER_6: Optimized power slips
        - FLEX_3..FLEX_6: Optimized flex slips

        Args:
            filepath: Output file path
        """
        with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
            if self.run_info:
                pd.DataFrame([self.run_info]).to_excel(writer, sheet_name="Run_Info", index=False)

            if self.playable_df is not None and not self.playable_df.empty:
                self.playable_df.to_excel(writer, sheet_name="Playable", index=False)

            # Optimize slips for different formats
            for n in [2, 3, 4, 5, 6]:
                slip_df = self.optimize_slips(format_type="power", n_legs=n)
                if slip_df.empty:
                    pd.DataFrame([{"note": "No slips found"}]).to_excel(
                        writer, sheet_name=f"POWER_{n}", index=False
                    )
                else:
                    slip_df.to_excel(writer, sheet_name=f"POWER_{n}", index=False)

            for n in [3, 4, 5, 6]:
                slip_df = self.optimize_slips(format_type="flex", n_legs=n)
                if slip_df.empty:
                    pd.DataFrame([{"note": "No slips found"}]).to_excel(
                        writer, sheet_name=f"FLEX_{n}", index=False
                    )
                else:
                    slip_df.to_excel(writer, sheet_name=f"FLEX_{n}", index=False)
