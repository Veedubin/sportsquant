"""NFL advanced metrics.

Implements key NFL analytics metrics:
- EPA/play (Expected Points Added)
- DVOA approximation (Defense-adjusted Value Over Average)
- QBR approximation (Total Quarterback Rating)
- ANY/A (Adjusted Net Yards per Attempt)
- Success Rate
- CPOE (Completion Percentage Over Expected)

All metrics are designed to work with nflfastR data formats.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd


def compute_epa_per_play(play_by_play: pd.DataFrame) -> dict:
    """Compute EPA/play from nflfastR play-by-play data.

    nflfastR includes pre-computed EPA columns:
    - epa: Expected Points Added on the play
    - ep: Expected Points before the play
    - epa_share: EPA share (for attribution)

    Args:
        play_by_play: nflfastR play-by-play DataFrame with 'epa' column

    Returns:
        Dict with overall_epa_per_play, team_epa DataFrame, down_epa DataFrame
    """
    if "epa" not in play_by_play.columns:
        raise ValueError("play_by_play must have 'epa' column (nflfastR format)")

    # Overall EPA/play
    epa_per_play = play_by_play["epa"].mean()

    # EPA by team (if posteam column exists)
    team_epa = pd.DataFrame()
    if "posteam" in play_by_play.columns:
        team_epa = play_by_play.groupby("posteam")["epa"].agg(["mean", "sum", "count"])
        team_epa.columns = ["epa_per_play", "total_epa", "plays"]

    # EPA by down (if down column exists)
    down_epa = pd.DataFrame()
    if "down" in play_by_play.columns:
        down_epa = play_by_play.groupby("down")["epa"].agg(["mean", "count"])

    return {
        "overall_epa_per_play": epa_per_play,
        "team_epa": team_epa,
        "down_epa": down_epa,
    }


def compute_anya(passing_stats: pd.DataFrame) -> pd.Series:
    """Compute Adjusted Net Yards per Attempt (ANY/A).

    Formula:
        ANY/A = (pass_yards + 20*pass_tds - 45*interceptions - sack_yards_lost)
                / (pass_attempts + sacks)

    Args:
        passing_stats: DataFrame with columns:
            passing_yards, passing_tds, interceptions,
            sack_yards_lost (or sacks * avg_sack_loss),
            passing_attempts, sacks

    Returns:
        Series of ANY/A values
    """
    pass_yds = passing_stats.get("passing_yards", 0)
    pass_tds = passing_stats.get("passing_tds", 0)
    ints = passing_stats.get("interceptions", 0)
    pass_att = passing_stats.get("passing_attempts", 0)
    sacks = passing_stats.get("sacks", 0)

    # Estimate sack yards lost if not available (avg ~7 yards per sack)
    if "sack_yards_lost" in passing_stats.columns:
        sack_yds = passing_stats["sack_yards_lost"]
    else:
        sack_yds = sacks * 7

    numerator = pass_yds + 20 * pass_tds - 45 * ints - sack_yds
    denominator = pass_att + sacks

    result = numerator / denominator.replace(0, np.nan)
    return result


def compute_success_rate(play_by_play: pd.DataFrame) -> float:
    """Compute success rate (% of plays with positive EPA).

    A play is "successful" if EPA > 0.

    Args:
        play_by_play: nflfastR play-by-play DataFrame with 'epa' column

    Returns:
        Success rate as a float (0.0 to 1.0)
    """
    if "epa" not in play_by_play.columns:
        raise ValueError("play_by_play must have 'epa' column")

    successful = (play_by_play["epa"] > 0).sum()
    total = len(play_by_play)
    return successful / total if total > 0 else 0.0


def compute_cpoe(passing_stats: pd.DataFrame) -> pd.Series:
    """Compute Completion Percentage Over Expected (CPOE).

    CPOE = actual_completion_pct - expected_completion_pct

    Expected completion % is modeled based on air yards per attempt.
    Simplified version uses league-average completion rate
    adjusted for air yards.

    Args:
        passing_stats: DataFrame with completions, attempts, air_yards

    Returns:
        Series of CPOE values
    """
    completions = passing_stats.get("completions", 0)
    attempts = passing_stats.get("passing_attempts", 0)
    air_yards = passing_stats.get("air_yards", 0)

    actual_pct = completions / attempts.replace(0, np.nan)

    # Simplified expected completion model
    # League average ~65%, decreases ~1.5% per air yard beyond 5
    air_yards_per_att = air_yards / attempts.replace(0, np.nan)
    expected_pct = 0.65 - 0.015 * (air_yards_per_att - 5).clip(lower=0)

    return actual_pct - expected_pct


def compute_dvoa_approximation(
    team_epa: pd.DataFrame,
    league_avg_epa: float,
    opponent_adjustments: Optional[pd.Series] = None,
) -> pd.Series:
    """Compute DVOA approximation from EPA data.

    DVOA = (team_epa_per_play - league_avg_epa) * opponent_strength_factor

    Full DVOA requires:
    - Play-by-play data with situation (down, distance, field position)
    - Opponent adjustments (strength of schedule)
    - Situation-specific league averages

    This approximation uses team EPA/play vs league average,
    adjusted by opponent strength if available.

    Args:
        team_epa: DataFrame with team EPA/play (from compute_epa_per_play)
        league_avg_epa: League average EPA/play
        opponent_adjustments: Optional opponent strength multiplier per team

    Returns:
        Series of DVOA approximations (higher = better, in percentage points)
    """
    if "epa_per_play" not in team_epa.columns:
        raise ValueError("team_epa must have 'epa_per_play' column")

    raw_dvoa = team_epa["epa_per_play"] - league_avg_epa

    if opponent_adjustments is not None:
        # Align opponent adjustments with team_epa index
        aligned = opponent_adjustments.reindex(team_epa.index, fill_value=1.0)
        raw_dvoa = raw_dvoa * aligned

    # Scale to percentage (DVOA is typically expressed as %)
    return raw_dvoa * 100


def compute_qbr_approximation(
    player_stats: pd.DataFrame,
    league_averages: Optional[dict] = None,
) -> pd.Series:
    """Compute QBR approximation from available stats.

    ESPN's Total QBR is proprietary and complex. This approximation
    uses a weighted combination of:
    - ANY/A
    - CPOE
    - TD/INT ratio
    - Sack avoidance (not yet implemented)

    Scaled to 0-100 scale (like ESPN QBR).

    Args:
        player_stats: DataFrame with QB stats
        league_averages: Optional dict of league average values for normalization.
            Defaults: anya=6.0, anya_std=1.5, cpoe=0.0, cpoe_std=5.0,
            td_int_ratio=2.5, td_int_std=1.0

    Returns:
        Series of QBR approximations (0-100 scale)
    """
    if league_averages is None:
        league_averages = {
            "anya": 6.0,
            "anya_std": 1.5,
            "cpoe": 0.0,
            "cpoe_std": 5.0,
            "td_int_ratio": 2.5,
            "td_int_std": 1.0,
        }

    # Compute component scores
    anya = compute_anya(player_stats)
    cpoe = compute_cpoe(player_stats)

    # TD/INT ratio
    tds = player_stats.get("passing_tds", 0)
    ints = player_stats.get("interceptions", 0).replace(0, 1)
    td_int_ratio = tds / ints

    # Normalize each component to league average (z-score)
    anya_z = (anya - league_averages["anya"]) / league_averages["anya_std"]
    cpoe_z = (cpoe - league_averages["cpoe"]) / league_averages["cpoe_std"]
    td_int_z = (td_int_ratio - league_averages["td_int_ratio"]) / league_averages["td_int_std"]

    # Weighted combination (approximate ESPN weights)
    qbr_raw = (
        0.35 * anya_z
        + 0.25 * cpoe_z
        + 0.20 * td_int_z
        + 0.20 * 0  # Clutch weight (not computable without play-by-play context)
    )

    # Scale to 0-100 (mean=50, std=10)
    qbr_scaled = 50 + 10 * qbr_raw
    return qbr_scaled.clip(0, 100)


# ──────────────────────────────────────────────
# Utility: Compute all metrics for a player
# ──────────────────────────────────────────────


def compute_all_nfl_metrics(
    player_stats: pd.DataFrame,
    play_by_play: Optional[pd.DataFrame] = None,
) -> dict:
    """Compute all available NFL advanced metrics for a player.

    Args:
        player_stats: DataFrame with player game-level stats
        play_by_play: Optional play-by-play data for EPA-based metrics

    Returns:
        Dict with all computed metrics
    """
    metrics = {}

    # ANY/A (always computable from player stats)
    try:
        metrics["anya"] = float(compute_anya(player_stats).mean())
    except Exception:
        metrics["anya"] = None

    # CPOE (requires air_yards column)
    try:
        if "air_yards" in player_stats.columns:
            metrics["cpoe"] = float(compute_cpoe(player_stats).mean())
        else:
            metrics["cpoe"] = None
    except Exception:
        metrics["cpoe"] = None

    # QBR approximation
    try:
        metrics["qbr"] = float(compute_qbr_approximation(player_stats).mean())
    except Exception:
        metrics["qbr"] = None

    # EPA-based metrics (require play-by-play)
    if play_by_play is not None and not play_by_play.empty:
        try:
            epa_results = compute_epa_per_play(play_by_play)
            metrics["epa_per_play"] = float(epa_results["overall_epa_per_play"])
            metrics["success_rate"] = float(compute_success_rate(play_by_play))
        except Exception:
            metrics["epa_per_play"] = None
            metrics["success_rate"] = None
    else:
        metrics["epa_per_play"] = None
        metrics["success_rate"] = None

    return metrics
