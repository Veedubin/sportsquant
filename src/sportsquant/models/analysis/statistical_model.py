"""Statistical modeling for player props.

This module provides sport-agnostic statistical modeling for player props
using historical game logs. It supports both Normal and Poisson distributions
depending on the stat type.

Key features:
- Robust expected minutes calculation with outlier rejection
- Weighted rate mu/sigma with recency bias
- Dynamic blend weighting based on minutes volatility
- Support for Normal (continuous) and Poisson (count) distributions
"""

import math
import re
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd


# Constants for model building (configurable)
DEFAULT_MIN_GAMES = 12
DEFAULT_MIN_VALID_MINUTES = 6.0
DEFAULT_CAP_MINUTES = 40.0
DEFAULT_N_LOOKBACK = 25

# Stats that should use Poisson distribution (count stats)
POISSON_STATS = {
    "3-PT Made",
    "3PT Made",
    "3 Pointers Made",
    "3PM",
    "Blocks",
    "Steals",
    "Blocks + Steals",
    "Blocks+Steals",
}


def clamp(x: float, lo: float, hi: float) -> float:
    """Clamp value to range [lo, hi]."""
    return max(lo, min(hi, x))


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


def parse_minutes(min_str) -> float:
    """Parse minutes string (e.g., '36:30' or '36.5') to float."""
    if min_str is None:
        return float("nan")
    if isinstance(min_str, (int, float)):
        return float(min_str)
    s = str(min_str).strip()
    if ":" in s:
        a, b = s.split(":", 1)
        try:
            return float(a) + float(b) / 60.0
        except Exception:
            return float("nan")
    try:
        return float(s)
    except Exception:
        return float("nan")


def fantasy_score_from_row(row: pd.Series) -> float:
    """Calculate fantasy score from a gamelog row.

    Formula: pts*1.0 + reb*1.2 + ast*1.5 + blk*3.0 + stl*3.0 - tov*1.0
    """
    pts = safe_float(row.get("PTS"))
    reb = safe_float(row.get("REB"))
    ast = safe_float(row.get("AST"))
    blk = safe_float(row.get("BLK"))
    stl = safe_float(row.get("STL"))
    tov = safe_float(row.get("TOV"))

    if any(np.isnan([pts, reb, ast, blk, stl, tov])):
        return float("nan")

    return (pts * 1.0) + (reb * 1.2) + (ast * 1.5) + (blk * 3.0) + (stl * 3.0) - (tov * 1.0)


def compute_stat_from_gamelog_row(stat_type: str, row: pd.Series) -> float:
    """Compute stat value from a gamelog row based on stat type.

    Args:
        stat_type: The type of stat to compute
        row: DataFrame row from gamelog

    Returns:
        The stat value or NaN if not computable
    """
    pts = safe_float(row.get("PTS"))
    reb = safe_float(row.get("REB"))
    ast = safe_float(row.get("AST"))
    stl = safe_float(row.get("STL"))
    blk = safe_float(row.get("BLK"))
    tov = safe_float(row.get("TOV"))
    fg3m = safe_float(row.get("FG3M"))

    st = (stat_type or "").strip()

    if st == "Points":
        return pts
    if st == "Rebounds":
        return reb
    if st == "Assists":
        return ast
    if st in ("3-PT Made", "3PT Made", "3 Pointers Made", "3PM"):
        return fg3m
    if st == "Turnovers":
        return tov
    if st == "Blocks":
        return blk
    if st == "Steals":
        return stl
    if st in ("Blocks + Steals", "Blocks+Steals"):
        return blk + stl
    if st in ("Pts+Rebs+Asts", "PRA"):
        return pts + reb + ast
    if st in ("Pts+Rebs", "PR"):
        return pts + reb
    if st in ("Pts+Asts", "PA"):
        return pts + ast
    if st in ("Rebs+Asts", "RA"):
        return reb + ast
    if st in ("Fantasy Score", "Fantasy Score (Combo)"):
        return fantasy_score_from_row(row)

    return float("nan")


def robust_expected_minutes(
    mins: np.ndarray,
    min_valid_minutes: float = DEFAULT_MIN_VALID_MINUTES,
    cap_minutes: float = DEFAULT_CAP_MINUTES,
) -> float:
    """Calculate robust expected minutes with outlier rejection.

    Uses IQR-based outlier rejection and median estimation.
    This is more robust to blowouts and DNPs than mean.

    Args:
        mins: Array of minutes values
        min_valid_minutes: Minimum minutes to consider valid
        cap_minutes: Maximum minutes to cap at

    Returns:
        Robust expected minutes or NaN if insufficient data
    """
    m = mins[~np.isnan(mins)]
    m = m[m >= min_valid_minutes]

    if len(m) == 0:
        return float("nan")

    q1, q3 = np.percentile(m, [25, 75])
    iqr = max(q3 - q1, 1e-6)
    lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr

    m2 = m[(m >= lo) & (m <= hi)]
    if len(m2) == 0:
        m2 = m

    # Use median of first 5 values if available, else median
    expm = float(np.median(m2[:5])) if len(m2) >= 5 else float(np.median(m2))
    return float(clamp(expm, min_valid_minutes, cap_minutes))


def minutes_volatility_metrics(
    mins: np.ndarray,
    min_valid_minutes: float = DEFAULT_MIN_VALID_MINUTES,
) -> tuple[float, float, float]:
    """Calculate minutes volatility metrics.

    Args:
        mins: Array of minutes values
        min_valid_minutes: Minimum minutes to consider valid

    Returns:
        Tuple of (median, std_dev, coefficient_of_variation)
    """
    m = mins[~np.isnan(mins)]
    m = m[m >= min_valid_minutes]

    if len(m) < 6:
        return float("nan"), float("nan"), float("nan")

    med = float(np.median(m[:10])) if len(m) >= 10 else float(np.median(m))
    sd = float(np.std(m[:10])) if len(m) >= 10 else float(np.std(m))
    cv = float(sd / max(med, 1e-6))

    return med, sd, cv


def weighted_rate_mu_sigma(
    rate_vals: np.ndarray,
) -> tuple[float, float]:
    """Calculate weighted mean and std dev of rate values with recency bias.

    Uses exponential weighting: 35% last 5, 25% last 10, 20% last 20, 20% median.
    This gives more weight to recent performance while staying robust.

    Args:
        rate_vals: Array of per-minute rate values

    Returns:
        Tuple of (mu, sigma) for the rate distribution
    """
    v = rate_vals[~np.isnan(rate_vals)]
    if len(v) == 0:
        return float("nan"), float("nan")

    l5 = np.mean(v[:5]) if len(v) >= 5 else np.mean(v)
    l10 = np.mean(v[:10]) if len(v) >= 10 else np.mean(v)
    l20 = np.mean(v[:20]) if len(v) >= 20 else np.mean(v)
    med = np.median(v)

    # Weighted average with recency bias
    mu = 0.35 * l5 + 0.25 * l10 + 0.20 * l20 + 0.20 * med

    # Std dev favors recent volatility
    s_recent = np.std(v[:10]) if len(v) >= 10 else np.std(v)
    s_full = np.std(v)
    sigma = max(0.85 * s_recent + 0.15 * s_full, 0.02)

    return float(mu), float(sigma)


def dynamic_blend_from_minutes_cv(
    base_blend: float,
    minutes_cv: float,
    min_blend: float = 0.12,
) -> float:
    """Adjust model weight based on minutes volatility.

    Higher CV (volatile minutes) -> lower model weight (more market weight).
    This accounts for players with unstable playing time being harder to model.

    Math: shrink = 1 - 1.6 * cv, clamped to [min_blend, base_blend]

    Args:
        base_blend: Base model weight (e.g., 0.30)
        minutes_cv: Coefficient of variation for minutes
        min_blend: Minimum blend weight

    Returns:
        Adjusted blend weight
    """
    if minutes_cv is None or (isinstance(minutes_cv, float) and math.isnan(minutes_cv)):
        return float(clamp(base_blend * 0.75, min_blend, base_blend))

    vol = float(clamp(minutes_cv, 0.0, 0.50))
    shrink = 1.0 - 1.6 * vol
    return float(clamp(base_blend * shrink, min_blend, base_blend))


def poisson_cdf(k: int, lam: float) -> float:
    """Cumulative distribution function for Poisson distribution.

    Args:
        k: Number of events
        lam: Lambda (mean) parameter

    Returns:
        P(X <= k) under Poisson(lam)
    """
    if lam <= 0:
        return 1.0 if k >= 0 else 0.0

    k = int(k)
    s = 0.0
    term = math.exp(-lam)
    s += term

    for i in range(1, k + 1):
        term *= lam / i
        s += term

    return float(clamp(s, 0.0, 1.0))


def poisson_prob_over(line: float, lam: float) -> float:
    """Calculate probability of being over a line using Poisson distribution.

    P(X > line) = 1 - P(X <= floor(line))

    Args:
        line: The line (threshold)
        lam: Lambda (mean) parameter

    Returns:
        Probability of exceeding the line
    """
    thr = int(math.floor(line))
    return 1.0 - poisson_cdf(thr, lam)


class PlayerDataProvider(ABC):
    """Abstract interface for fetching player statistical data.

    Implement this for different sports (NBA, NFL, MLB, etc.)
    """

    @abstractmethod
    def get_player_id(self, name: str) -> Optional[int]:
        """Resolve player name to internal player ID.

        Args:
            name: Player name (may be partial/fuzzy)

        Returns:
            Internal player ID or None if not found
        """
        pass

    @abstractmethod
    def get_gamelog(self, player_id: int, lookback: int = 25) -> pd.DataFrame:
        """Fetch recent gamelog for player.

        Args:
            player_id: Internal player ID
            lookback: Number of games to fetch

        Returns:
            DataFrame with game log data
        """
        pass

    @abstractmethod
    def compute_stat(self, stat_type: str, row: pd.Series) -> float:
        """Compute a stat value from a gamelog row.

        Args:
            stat_type: Type of stat to compute
            row: DataFrame row

        Returns:
            Stat value or NaN
        """
        pass

    @abstractmethod
    def parse_minutes(self, min_str) -> float:
        """Parse minutes string to float.

        Args:
            min_str: Minutes string or value

        Returns:
            Minutes as float
        """
        pass

    def is_poisson_stat(self, stat_type: str) -> bool:
        """Whether to use Poisson distribution for this stat.

        Default implementation checks POISSON_STATS set.
        Override for sport-specific count stats.

        Args:
            stat_type: The stat type

        Returns:
            True if should use Poisson distribution
        """
        return stat_type in POISSON_STATS


class NBADataProvider(PlayerDataProvider):
    """NBA-specific data provider using nba_api.

    Fetches player data from the NBA's official stats API.
    Includes caching to avoid redundant API calls.
    """

    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        n_lookback: int = DEFAULT_N_LOOKBACK,
        n_timeout: int = 10,
        n_retries: int = 2,
    ):
        """Initialize NBA data provider.

        Args:
            cache_dir: Directory for gamelog cache
            n_lookback: Number of games to fetch
            n_timeout: Timeout for API calls in seconds
            n_retries: Number of retries for failed calls
        """
        if cache_dir is not None:
            self.cache_dir = Path(cache_dir)
        else:
            self.cache_dir = Path("./cache/gamelogs")
            try:
                self.cache_dir.mkdir(parents=True, exist_ok=True)
            except (PermissionError, OSError):
                self.cache_dir = None
        self.n_lookback = n_lookback
        self.n_timeout = n_timeout
        self.n_retries = n_retries

        self._player_id_cache: dict[str, int] = {}
        self._gamelog_cache: dict[int, pd.DataFrame] = {}

        # Lazy imports for nba_api
        self._nba_players = None
        self._playergamelog = None

    def _init_nba_api(self):
        """Lazy initialization of nba_api imports."""
        if self._nba_players is None:
            from nba_api.stats.static import players as nba_players
            from nba_api.stats.endpoints import playergamelog

            self._nba_players = nba_players
            self._playergamelog = playergamelog

    def get_player_id(self, name: str) -> Optional[int]:
        """Find NBA player ID by name using fuzzy matching."""
        if name in self._player_id_cache:
            return self._player_id_cache[name]

        self._init_nba_api()

        matches = self._nba_players.find_players_by_full_name(name)
        if not matches:
            n = normalize_name(name)
            matches = [
                p for p in self._nba_players.get_players() if n == normalize_name(p["full_name"])
            ]
        if not matches:
            n = normalize_name(name)
            matches = [
                p for p in self._nba_players.get_players() if n in normalize_name(p["full_name"])
            ]

        if not matches:
            return None

        pid = int(matches[0]["id"])
        self._player_id_cache[name] = pid
        return pid

    def get_gamelog(self, player_id: int, lookback: int = 25) -> pd.DataFrame:
        """Fetch NBA gamelog for player with caching."""
        cache_key = player_id
        if cache_key in self._gamelog_cache:
            return self._gamelog_cache[cache_key]

        self._init_nba_api()

        # Try cache dir on disk
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
                            return df
                    except Exception:
                        try:
                            cache_path.unlink()
                        except (PermissionError, OSError):
                            pass
            except (PermissionError, OSError):
                pass

        last_err = None
        for attempt in range(1, self.n_retries + 1):
            try:
                gl = self._playergamelog.PlayerGameLog(
                    player_id=player_id,
                    timeout=self.n_timeout,
                )
                df = gl.get_data_frames()[0].head(lookback).copy()

                # Save to cache
                if cache_path:
                    try:
                        df.to_pickle(cache_path)
                    except (PermissionError, OSError):
                        pass

                self._gamelog_cache[cache_key] = df
                return df
            except Exception as e:
                last_err = e
                time.sleep(0.5 * attempt)

        raise last_err if last_err else RuntimeError("Failed to fetch gamelog")

    def compute_stat(self, stat_type: str, row: pd.Series) -> float:
        """Compute NBA stat from gamelog row."""
        return compute_stat_from_gamelog_row(stat_type, row)

    def parse_minutes(self, min_str) -> float:
        """Parse NBA minutes string."""
        return parse_minutes(min_str)

    def is_poisson_stat(self, stat_type: str) -> bool:
        """NBA-specific Poisson stat check."""
        return stat_type in POISSON_STATS


class StatisticalModel:
    """Builds player performance models from historical game logs.

    This is the core statistical modeling engine. It takes a player's
    gamelog data and produces probability distributions for each stat.

    Key algorithms:
    - Robust expected minutes (median with IQR outlier rejection)
    - Weighted per-minute rates with recency bias
    - Dynamic blend based on minutes volatility
    - Normal or Poisson distribution selection
    """

    def __init__(
        self,
        data_provider: PlayerDataProvider,
        min_games: int = DEFAULT_MIN_GAMES,
        min_valid_minutes: float = DEFAULT_MIN_VALID_MINUTES,
        cap_minutes: float = DEFAULT_CAP_MINUTES,
        base_blend: float = 0.30,
    ):
        """Initialize StatisticalModel.

        Args:
            data_provider: Data provider for fetching player data
            min_games: Minimum games required for modeling
            min_valid_minutes: Minimum minutes to count as valid game
            cap_minutes: Maximum minutes to cap at
            base_blend: Base model weight for logit blend
        """
        self.provider = data_provider
        self.min_games = min_games
        self.min_valid_minutes = min_valid_minutes
        self.cap_minutes = cap_minutes
        self.base_blend = base_blend

    def build_model(
        self,
        player_name: str,
        stat_types: list[str],
    ) -> dict:
        """Build statistical models for a player's stats.

        Args:
            player_name: Name of the player
            stat_types: List of stat types to model

        Returns:
            Dict mapping stat_type -> model dict with mu, sigma, is_poisson, etc.
        """
        player_id = self.provider.get_player_id(player_name)
        if not player_id:
            return {}

        try:
            gamelog = self.provider.get_gamelog(player_id)
        except Exception:
            return {}

        return self.build_models_from_gamelog(gamelog, stat_types)

    def build_models_from_gamelog(
        self,
        gl: pd.DataFrame,
        stat_types: list[str],
    ) -> dict:
        """Build models from gamelog DataFrame.

        Args:
            gl: Gamelog DataFrame
            stat_types: List of stat types to model

        Returns:
            Dict mapping stat_type -> model dict
        """
        # Parse minutes
        mins = np.array(
            [self.provider.parse_minutes(r.get("MIN")) for _, r in gl.iterrows()], dtype=float
        )

        mins_ok = (~np.isnan(mins)) & (mins >= self.min_valid_minutes)

        if np.sum(mins_ok) < self.min_games:
            return {}

        mins_v = mins[mins_ok]
        exp_min = robust_expected_minutes(mins_v, self.min_valid_minutes, self.cap_minutes)
        med, sd, cv = minutes_volatility_metrics(mins_v, self.min_valid_minutes)

        if np.isnan(exp_min):
            return {}

        out = {}
        for st in stat_types:
            vals = np.array(
                [self.provider.compute_stat(st, r) for _, r in gl.iterrows()], dtype=float
            )

            valid = mins_ok & (~np.isnan(vals))
            if np.sum(valid) < self.min_games:
                continue

            mins_s = mins[valid]
            vals_s = vals[valid]

            # Per-minute rate
            rate = vals_s / mins_s
            rmu, rs = weighted_rate_mu_sigma(rate)

            # Scale by expected minutes
            mu = rmu * exp_min
            sigma = max(rs * exp_min, 0.90)

            is_pois = self.provider.is_poisson_stat(st)

            out[st] = {
                "ok": True,
                "min_med": float(med) if not np.isnan(med) else float("nan"),
                "min_sd": float(sd) if not np.isnan(sd) else float("nan"),
                "min_cv": float(cv) if not np.isnan(cv) else float("nan"),
                "mu": float(mu),
                "sigma": float(sigma),
                "is_poisson": bool(is_pois),
                "lam": float(max(mu, 1e-6)) if is_pois else float("nan"),
                "exp_min": float(exp_min),
            }

        return out

    def calc_prob_over(
        self,
        model: dict,
        line: float,
    ) -> float:
        """Calculate probability of exceeding a line using the model.

        Args:
            model: Model dict from build_models_from_gamelog
            line: The line (threshold)

        Returns:
            Probability of exceeding the line
        """
        if not model.get("ok"):
            return float("nan")

        if model["is_poisson"]:
            lam = model.get("lam", 0)
            if lam <= 0:
                return float("nan")
            return poisson_prob_over(line, lam)
        else:
            mu = model.get("mu", 0)
            sigma = model.get("sigma", 0)
            if sigma <= 0 or np.isnan(mu) or np.isnan(sigma):
                return float("nan")

            # P(X > line) = 1 - norm_cdf(line, mu, sigma)
            z = (mu - line) / (sigma * math.sqrt(2.0))
            return 0.5 * (1.0 + math.erf(z))

    def get_blend_weight(self, model: dict) -> float:
        """Get dynamic blend weight for a model based on minutes CV.

        Args:
            model: Model dict

        Returns:
            Blend weight to use in logit blending
        """
        cv = model.get("min_cv")
        return dynamic_blend_from_minutes_cv(self.base_blend, cv)
