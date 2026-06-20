"""Quant-Sports metrics package.

Sport-specific advanced metrics for NFL, NBA, MLB, NHL.
"""

from quantitative_sports.models.metrics.nfl_advanced import (
    compute_epa_per_play,
    compute_anya,
    compute_success_rate,
    compute_cpoe,
    compute_dvoa_approximation,
    compute_qbr_approximation,
)

__all__ = [
    "compute_epa_per_play",
    "compute_anya",
    "compute_success_rate",
    "compute_cpoe",
    "compute_dvoa_approximation",
    "compute_qbr_approximation",
]
