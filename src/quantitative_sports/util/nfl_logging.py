"""Lightweight logger for NFL-related modules."""

from __future__ import annotations

import logging


def get_logger(name: str) -> logging.Logger:
    """Return a logger configured for NFL modules.

    Mirrors :func:`quantitative_sports.util.nba_logging.get_logger` style so the
    same conventions work across sports. Does NOT configure the root
    logger — callers inherit the host application's logging config.
    """
    return logging.getLogger(name)
