"""Quant-Sports — open-source quantitative sports betting toolkit.

QuantLib for sports betting. Computes expected value, applies Kelly sizing,
detects multi-book middles, runs walk-forward backtests, and predicts NFL
game outcomes via an XGBoost ensemble.

Architecture (v0.2.0+):
- Desktop package (this): `uv add quantitative-sports[notebook]`
- Container stack (separate): TimescaleDB + poller + web ops dashboard
- See: https://github.com/Veedubin/quantitative-sports
"""

from __future__ import annotations

__version__ = "0.2.0"
__author__ = "VeeDubin"
__email__ = "veedubin@neuralgentics.dev"
__license__ = "MIT"
__url__ = "https://github.com/Veedubin/quantitative-sports"

__all__ = [
    "__version__",
    "__author__",
    "__email__",
    "__license__",
    "__url__",
]
