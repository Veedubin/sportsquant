"""Odds API NFL game lines parser.

Parses h2h, spreads, and totals markets from The Odds API event odds
responses into a normalized DataFrame with one row per (game, bookmaker).

Adapted from Old-Files/nfl-data-agg (theoddsapi.parse_featured_to_raw_lines)
and rewritten on top of pandas (SportsQuant's DataFrame library).

Schema:
    event_id, commence_time, home_team, away_team,
    source_id, observed_at, effective_at, available_at,
    ml_home, ml_away,
    spread_home, spread_home_price, spread_away_price,
    total, total_over_price, total_under_price

Example:
    >>> import httpx
    >>> resp = httpx.get("https://api.the-odds-api.com/v4/sports/americanfootball_nfl/odds",
    ...                  params={"apiKey": "...", "regions": "us", "markets": "h2h,spreads,totals",
    ...                          "oddsFormat": "american"})
    >>> events = resp.json()
    >>> df = parse_game_lines_to_raw(events)
"""

from __future__ import annotations

from typing import Any, Iterable

import pandas as pd

from sportsquant.util.time_utils import utc_now_iso


def _as_list(x: Any) -> list:
    return list(x) if x else []


def _book_source_id(book: dict[str, Any]) -> str:
    return str(book.get("title") or book.get("key") or "TheOddsAPI")


def _book_observed_at(book: dict[str, Any]) -> str:
    return str(book.get("last_update") or utc_now_iso())


def _base_line_row(event: dict[str, Any], book: dict[str, Any]) -> dict[str, Any]:
    observed_at = _book_observed_at(book)
    return {
        "event_id": event.get("id"),
        "commence_time": event.get("commence_time"),
        "home_team": event.get("home_team"),
        "away_team": event.get("away_team"),
        "source_id": _book_source_id(book),
        "observed_at": observed_at,
        "effective_at": observed_at,
        "available_at": observed_at,
    }


def _apply_h2h(
    row: dict[str, Any],
    outcomes: list[dict[str, Any]],
    *,
    home: Any,
    away: Any,
) -> None:
    """Fill moneyline prices by matching outcome name to home/away."""
    for o in outcomes:
        name = o.get("name")
        if name == away:
            row["ml_away"] = o.get("price")
        elif name == home:
            row["ml_home"] = o.get("price")


def _apply_spreads(
    row: dict[str, Any],
    outcomes: list[dict[str, Any]],
    *,
    home: Any,
    away: Any,
) -> None:
    """Fill spread points and prices. Convention: spread_home is positive
    when home is favored (e.g. -3.5 stored as -3.5)."""
    for o in outcomes:
        name = o.get("name")
        if name == home:
            row["spread_home"] = o.get("point")
            row["spread_home_price"] = o.get("price")
        elif name == away:
            row["spread_away_price"] = o.get("price")


def _apply_totals(
    row: dict[str, Any],
    outcomes: list[dict[str, Any]],
) -> None:
    """Fill total points and Over/Under prices."""
    for o in outcomes:
        side = o.get("name")
        if side == "Over":
            row["total"] = o.get("point")
            row["total_over_price"] = o.get("price")
        elif side == "Under":
            row["total_under_price"] = o.get("price")


_MARKET_APPLIERS = {
    "h2h": _apply_h2h,
    "spreads": _apply_spreads,
    "totals": _apply_totals,
}


_COLUMNS = [
    "event_id",
    "commence_time",
    "home_team",
    "away_team",
    "source_id",
    "observed_at",
    "effective_at",
    "available_at",
    "ml_home",
    "ml_away",
    "spread_home",
    "spread_home_price",
    "spread_away_price",
    "total",
    "total_over_price",
    "total_under_price",
]


def parse_game_lines_to_raw(events: Iterable[dict[str, Any]]) -> pd.DataFrame:
    """Parse Odds API events into a per-(game, bookmaker) DataFrame.

    Each bookmaker's markets are flattened into a single row with h2h,
    spreads, and totals fields merged. Returns an empty DataFrame with
    the canonical schema when ``events`` is empty.

    Args:
        events: Iterable of raw Odds API event dicts (the JSON array
            returned by the /odds endpoint).

    Returns:
        DataFrame with the columns listed in module-level ``_COLUMNS``.
    """
    rows: list[dict[str, Any]] = []

    for event in events:
        if not isinstance(event, dict):
            continue
        home = event.get("home_team")
        away = event.get("away_team")
        if not home or not away:
            continue

        for book in _as_list(event.get("bookmakers")):
            row = _base_line_row(event, book)
            for market in _as_list(book.get("markets")):
                market_key = market.get("key")
                applier = _MARKET_APPLIERS.get(market_key)
                if applier is None:
                    continue
                outcomes = _as_list(market.get("outcomes"))
                if market_key in ("h2h", "spreads"):
                    applier(row, outcomes, home=home, away=away)  # type: ignore[arg-type]
                else:
                    applier(row, outcomes)  # type: ignore[misc]

            rows.append(row)

    if not rows:
        return pd.DataFrame(columns=_COLUMNS)

    df = pd.DataFrame(rows)
    # Ensure column order even when no rows had certain markets
    for col in _COLUMNS:
        if col not in df.columns:
            df[col] = pd.NA
    return df[_COLUMNS]


def parse_outrights_to_futures(
    events: Iterable[dict[str, Any]],
    *,
    futures_market: str,
) -> pd.DataFrame:
    """Parse outright/futures markets (e.g. Super Bowl winner) into rows.

    Args:
        events: Iterable of raw Odds API event dicts containing outrights.
        futures_market: Market label (e.g. ``"super_bowl_winner"``).

    Returns:
        DataFrame with columns: event_id, commence_time, futures_market,
        outcome_name, odds_american, observed_at, source_id.
    """
    rows: list[dict[str, Any]] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        event_id = event.get("id") or event.get("event_id")
        commence_time = event.get("commence_time")
        for book in _as_list(event.get("bookmakers")):
            src = _book_source_id(book)
            observed_at = _book_observed_at(book)
            for market in _as_list(book.get("markets")):
                if market.get("key") not in ("outrights", "outrights_lay"):
                    continue
                for outcome in _as_list(market.get("outcomes")):
                    rows.append(
                        {
                            "event_id": event_id,
                            "commence_time": commence_time,
                            "futures_market": futures_market,
                            "outcome_name": outcome.get("name"),
                            "odds_american": outcome.get("price"),
                            "observed_at": observed_at,
                            "source_id": src,
                        }
                    )

    if not rows:
        return pd.DataFrame(
            columns=[
                "event_id",
                "commence_time",
                "futures_market",
                "outcome_name",
                "odds_american",
                "observed_at",
                "source_id",
            ]
        )
    return pd.DataFrame(rows)
