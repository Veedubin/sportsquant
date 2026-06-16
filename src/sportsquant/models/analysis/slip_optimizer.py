"""Monte Carlo slip optimization with correlation modeling.

This module optimizes PrizePicks slips using Monte Carlo simulation
with correlation matrices to properly account for correlated legs.

Key features:
- Cholesky decomposition for multivariate normal sampling
- Correlation matrix based on game/player relationships
- POWER and FLEX payout structures
- Constrained optimization (per-player, per-game limits)
- Tier-aware payout calculations (Standard, Goblin, Demon)
- DNP/Reboot reversion handling

Math:
  Instead of treating legs as independent, we model correlations:
  - Same game: rho = 0.06 (general game correlation)
  - Same player, different stat: rho = 0.12-0.35 (player-level correlation)
  - Same player, same stat bucket: rho = 0.22 (e.g., PTS + REB)

  We sample from multivariate normal using Cholesky decomposition:
  Z ~ N(0, C) where C is the correlation matrix
  L = cholesky(C)
  X = Z @ L.T
"""

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd
from scipy.stats import norm

from .rules import (
    OVER_ONLY_TIERS,
    validate_same_team_restriction,
    calculate_effective_payout as rules_calculate_effective_payout,
)


# PrizePicks payout structures (multiplier = total return)
# Official standard payouts per PrizePicks rules page
PAYOUT_POWER = {
    (2, 2): 3.0,
    (3, 3): 6.0,
    (4, 4): 10.0,
    (5, 5): 20.0,
    (6, 6): 25.0,  # Fixed: was 37.5, official is 25.0
}

PAYOUT_FLEX = {
    (3, 3): 3.0,
    (3, 2): 1.0,
    (4, 4): 6.0,
    (4, 3): 1.5,
    (5, 5): 10.0,
    (5, 4): 2.0,
    (5, 3): 0.4,
    (6, 6): 12.5,  # Fixed: was 25.0, official is 12.5
    (6, 5): 2.0,
    (6, 4): 0.4,
}

# Pool caps for different leg counts (for performance)
POOL_CAP = {2: 220, 3: 160, 4: 130, 5: 90, 6: 75}

# Max combinations to sample
MAX_COMBOS = {2: 120000, 3: 120000, 4: 90000, 5: 80000, 6: 70000}


def clamp(x: float, lo: float, hi: float) -> float:
    """Clamp value to range [lo, hi]."""
    return max(lo, min(hi, x))


def _stat_bucket(stat: str) -> str:
    """Bucket stat type for correlation grouping."""
    s = (stat or "").strip().upper()
    if s in ("POINTS", "PTS"):
        return "PTS"
    if s in ("REBOUNDS", "REB"):
        return "REB"
    if s in ("ASSISTS", "AST"):
        return "AST"
    if s in ("PTS+REBS+ASTS", "PRA", "PTS+REBS+ASTS "):
        return "PRA"
    if s in ("3-PT MADE", "3PT MADE", "3 POINTERS MADE", "3PM"):
        return "3PM"
    return s


def _game_key(team: str, opp: str, start_local: str) -> str:
    """Create game key for correlation grouping."""
    d = (start_local or "")[:10]
    return f"{team}@{opp}|{d}"


@dataclass
class Leg:
    """A single leg in a PrizePicks slip.

    Attributes:
        player: Player name
        team: Team abbreviation
        opponent: Opponent abbreviation
        stat_type: Stat type (e.g., "Points", "Rebounds")
        line: PrizePicks line
        probability: Implied probability (0-1)
        edge: Edge vs market
        tier: PrizePicks tier (Standard, Goblin, Demon)
        side: "Over" or "Under"
        start_local: Local start time (for game key)
        dnp_probability: Probability of player not playing (DNP)
    """

    player: str
    team: str
    opponent: str
    stat_type: str
    line: float
    probability: float
    edge: float
    tier: str = "Standard"
    side: str = "Over"
    start_local: str = ""
    dnp_probability: float = 0.0  # Probability of DNP

    @property
    def player_norm(self) -> str:
        """Normalized player name for matching."""
        import re

        s = (self.player or "").strip().lower().replace("'", "'")
        s = re.sub(r"[^a-z0-9\s'-]", " ", s)
        s = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b.?", "", s, flags=re.IGNORECASE)
        s = re.sub(r"\s+", " ", s).strip()
        return s

    @property
    def stat_bucket(self) -> str:
        """Stat bucket for correlation grouping."""
        return _stat_bucket(self.stat_type)

    @property
    def game_key(self) -> str:
        """Game key for correlation grouping."""
        return _game_key(self.team, self.opponent, self.start_local)


@dataclass
class SlipResult:
    """Result of slip optimization."""

    n_legs: int
    ev: float
    avg_probability: float
    legs: list[Leg]
    legs_description: str
    rank: int = 0


class SlipOptimizer:
    """Optimize PrizePicks slips using Monte Carlo simulation.

    This class finds optimal slip combinations by:
    1. Building correlation matrices based on game/player relationships
    2. Running Monte Carlo simulation with Cholesky decomposition
    3. Evaluating combinations under payout structures
    4. Returning top combinations by expected value
    """

    def __init__(
        self,
        n_sims: int = 80000,
        seed: int = 42,
        payout_power: Optional[dict] = None,
        payout_flex: Optional[dict] = None,
        pool_cap: Optional[dict] = None,
        max_combos: Optional[dict] = None,
    ):
        """Initialize SlipOptimizer.

        Args:
            n_sims: Number of Monte Carlo simulations
            seed: Random seed for reproducibility
            payout_power: POWER payout structure
            payout_flex: FLEX payout structure
            pool_cap: Pool size caps per leg count
            max_combos: Max combinations to sample per leg count
        """
        self.n_sims = n_sims
        self.seed = seed
        self.payout_power = payout_power or PAYOUT_POWER
        self.payout_flex = payout_flex or PAYOUT_FLEX
        self.pool_cap = pool_cap or POOL_CAP
        self.max_combos = max_combos or MAX_COMBOS

    def _corr_bucket(self, a: Leg, b: Leg) -> float:
        """Calculate correlation coefficient between two legs.

        Correlation rules:
        - Different games: rho = 0.02 (small general correlation)
        - Same game, same player:
          - PRA with anything: rho = 0.35
          - PTS + 3PM: rho = 0.20
          - PTS + AST: rho = 0.18
          - PTS + REB: rho = 0.12
          - Other same-player combos: rho = 0.22
        - Same game, different players: rho = 0.06

        Args:
            a: First leg
            b: Second leg

        Returns:
            Correlation coefficient (0 to 1)
        """
        if a.game_key != b.game_key:
            return 0.02

        same_player = a.player_norm == b.player_norm
        if same_player:
            st = {a.stat_bucket, b.stat_bucket}
            if "PRA" in st:
                return 0.35
            if st == {"PTS", "3PM"}:
                return 0.20
            if st == {"PTS", "AST"}:
                return 0.18
            if st == {"PTS", "REB"}:
                return 0.12
            return 0.22

        return 0.06

    def _corr_matrix(self, legs: list[Leg]) -> np.ndarray:
        """Build correlation matrix for a list of legs.

        Uses _corr_bucket to calculate pairwise correlations.
        Matrix is symmetric with 1s on diagonal.

        Args:
            legs: List of Leg objects

        Returns:
            N x N correlation matrix
        """
        n = len(legs)
        C = np.eye(n, dtype=float)

        for i in range(n):
            for j in range(i + 1, n):
                rho = self._corr_bucket(legs[i], legs[j])
                C[i, j] = rho
                C[j, i] = rho

        # Add small epsilon to diagonal for numerical stability
        C += np.eye(n) * 1e-6
        return C

    def simulate_ev(
        self,
        legs: list[Leg],
        payout: dict,
        sims: Optional[int] = None,
        seed: Optional[int] = None,
    ) -> float:
        """Run Monte Carlo simulation to estimate EV.

        Uses Cholesky decomposition to sample from multivariate normal
        with the correlation matrix, then calculates payout.

        Args:
            legs: List of Leg objects
            payout: Payout structure dict {(n_legs, n_hits): multiplier}
            sims: Number of simulations (default: self.n_sims)
            seed: Random seed (default: self.seed)

        Returns:
            Expected value (payout - 1)
        """
        n = len(legs)
        sims = sims or self.n_sims
        seed = seed if seed is not None else self.seed

        # Clamp probabilities
        p = np.array([clamp(leg.probability, 1e-6, 1 - 1e-6) for leg in legs], dtype=float)

        # Threshold for each leg (norm.ppf of probability)
        thresh = norm.ppf(p)

        # Build correlation matrix and Cholesky decomposition
        C = self._corr_matrix(legs)
        rng = np.random.default_rng(seed)

        try:
            L = np.linalg.cholesky(C)
        except np.linalg.LinAlgError:
            # Fallback with additional regularization
            L = np.linalg.cholesky(C + np.eye(n) * 1e-3)

        # Sample from multivariate normal
        Z = rng.standard_normal(size=(sims, n))
        X = Z @ L.T

        # Hit if X < thresh (standard normal CDF gives probability)
        hits = (X < thresh).astype(np.int8)
        k = hits.sum(axis=1)

        # Calculate payouts
        payouts = np.zeros(sims, dtype=float)
        for kk in range(n + 1):
            payouts[k == kk] = payout.get((n, kk), 0.0)

        # EV = mean payout - stake (1)
        return float(payouts.mean() - 1.0)

    def _passes_caps(
        self,
        combo: list[Leg],
        max_per_player: int,
        max_per_game: int,
    ) -> bool:
        """Check if combination passes per-player and per-game caps.

        Args:
            combo: List of Leg objects
            max_per_player: Maximum legs per player
            max_per_game: Maximum legs per game

        Returns:
            True if combination passes all constraints
        """
        players = [c.player_norm for c in combo]
        if pd.Series(players).value_counts().max() > max_per_player:
            return False

        games = [c.game_key for c in combo]
        if pd.Series(games).value_counts().max() > max_per_game:
            return False

        # Validate minimum 2 teams requirement
        if not validate_same_team_restriction(combo):
            return False

        return True

    def _sample_combos(
        self,
        pool: list[Leg],
        n: int,
        max_samples: int,
        seed: int,
    ) -> list[list[Leg]]:
        """Sample combinations from pool.

        Uses weighted sampling without replacement.
        Combinations are de-duplicated.

        Args:
            pool: List of candidate Leg objects
            n: Number of legs per combination
            max_samples: Maximum combinations to sample
            seed: Random seed

        Returns:
            List of combinations (each is list of Leg objects)
        """
        if len(pool) < n:
            return []

        rng = np.random.default_rng(seed)

        # Weight by probability (higher prob = more likely)
        w = np.array([max(1e-6, float(leg.probability)) for leg in pool], dtype=float)
        w = w / w.sum()

        seen = set()
        combos = []
        tries = 0
        max_tries = max_samples * 25

        while len(combos) < max_samples and tries < max_tries:
            tries += 1
            idx = rng.choice(len(pool), size=n, replace=False, p=w)
            key = tuple(sorted(int(i) for i in idx))
            if key in seen:
                continue
            seen.add(key)
            combos.append([pool[i] for i in idx])

        return combos

    def calculate_effective_payout(
        self,
        n_legs: int,
        n_hits: int,
        format_type: str,
        tier: str = "Standard",
    ) -> float:
        """Calculate effective payout with tier modifiers.

        Args:
            n_legs: Number of legs in the slip
            n_hits: Number of legs that hit
            format_type: "power" or "flex"
            tier: PrizePicks tier (Standard, Goblin, Demon)

        Returns:
            Effective payout multiplier after tier adjustment
        """
        return rules_calculate_effective_payout(
            n_legs, n_hits, format_type, tier, self.payout_power, self.payout_flex
        )

    def optimize_slips(
        self,
        legs_pool: list[Leg],
        format_type: str,
        n_legs: int,
        max_per_player: int = 1,
        max_per_game: int = 2,
        min_p: float = 0.58,
        top_k: int = 25,
        payout: Optional[dict] = None,
        sims: Optional[int] = None,
        seed: Optional[int] = None,
    ) -> list[SlipResult]:
        """Find optimal slips by sampling and simulation.

        Args:
            legs_pool: Pool of candidate legs
            format_type: "power" or "flex"
            n_legs: Number of legs per slip
            max_per_player: Max legs per player
            max_per_game: Max legs per game
            min_p: Minimum probability threshold
            top_k: Number of top results to return
            payout: Override payout structure
            sims: Number of simulations
            seed: Random seed

        Returns:
            List of SlipResult objects ranked by EV
        """
        sims = sims or self.n_sims
        seed = seed if seed is not None else self.seed

        # Select payout structure
        if payout is None:
            payout = self.payout_power if format_type.lower() == "power" else self.payout_flex

        # Filter by minimum probability
        pool = [leg for leg in legs_pool if float(leg.probability) >= min_p]
        if len(pool) < n_legs:
            return []

        # Sort by probability, edge, and books count (descending)
        pool = sorted(pool, key=lambda x: (x.probability, x.edge, 5), reverse=True)[
            : self.pool_cap.get(n_legs, 120)
        ]

        # Sample combinations
        candidates = self._sample_combos(
            pool,
            n_legs,
            self.max_combos.get(n_legs, 60000),
            seed=seed + n_legs * 17,
        )

        # Evaluate each combination
        rows = []
        for combo in candidates:
            if not self._passes_caps(combo, max_per_player, max_per_game):
                continue

            # Check Over-only restriction for Goblin/Demon tiers
            if any(leg.tier in OVER_ONLY_TIERS for leg in combo):
                if any(leg.side.lower() != "over" for leg in combo):
                    continue  # Goblin/Demon must be all Over

            ev = self.simulate_ev(combo, payout, sims=sims, seed=seed + n_legs * 101)
            avg_p = float(np.mean([c.probability for c in combo]))

            legs_desc = " | ".join(
                [
                    f"{c.player} {c.stat_type} {c.side} {c.line:g} (p={c.probability:.3f})"
                    for c in combo
                ]
            )

            rows.append(
                {
                    "n_legs": n_legs,
                    "ev": ev,
                    "avg_p": avg_p,
                    "legs": combo,
                    "legs_desc": legs_desc,
                }
            )

        if not rows:
            return []

        # Sort by EV and take top k
        rows = sorted(rows, key=lambda x: x["ev"], reverse=True)[:top_k]

        return [
            SlipResult(
                n_legs=r["n_legs"],
                ev=r["ev"],
                avg_probability=r["avg_p"],
                legs=r["legs"],
                legs_description=r["legs_desc"],
                rank=i + 1,
            )
            for i, r in enumerate(rows)
        ]

    def build_legs_from_dataframe(
        self,
        df: pd.DataFrame,
    ) -> list[Leg]:
        """Build Leg objects from a DataFrame.

        Expected columns: Player, Team, Opponent, Stat, PP_Line, PP_Tier,
        Recommended_Side, Final_Prob_Side, Edge_vs_Market, Start_Local

        Args:
            df: DataFrame with playable props

        Returns:
            List of Leg objects
        """
        legs = []
        for _, r in df.iterrows():
            try:
                leg = Leg(
                    player=str(r.get("Player", "")),
                    team=str(r.get("Team", "")),
                    opponent=str(r.get("Opponent", "")),
                    stat_type=str(r.get("Stat", "")),
                    line=float(r.get("PP_Line", 0)),
                    probability=float(r.get("Final_Prob_Side", 0)),
                    edge=float(r.get("Edge_vs_Market", 0)),
                    tier=str(r.get("PP_Tier", "Standard")),
                    side=str(r.get("Recommended_Side", "Over")),
                    start_local=str(r.get("Start_Local", "") or ""),
                )
                legs.append(leg)
            except (TypeError, ValueError):
                continue

        return legs
