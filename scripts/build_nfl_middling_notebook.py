"""Build the NFL middling + multi-book odds notebook.

Demonstrates:
- Multi-book odds aggregation via The Odds API parser
- Spread and total middling detection
- Integration with the existing arbitrage and value-betting strategies

Run: python scripts/build_nfl_middling_notebook.py
Output: notebooks/football/05_nfl_middling_and_odds.ipynb
"""

from __future__ import annotations

from pathlib import Path

import nbformat as nbf

nb = nbf.v4.new_notebook()
nb.metadata = {
    "kernelspec": {
        "display_name": "Python 3",
        "language": "python",
        "name": "python3",
    },
    "language_info": {"name": "python", "version": "3.12"},
}

cells: list[nbf.NotebookNode] = []


def md(text: str) -> nbf.NotebookNode:
    cell = nbf.v4.new_markdown_cell(text)
    return cell


def code(text: str) -> nbf.NotebookNode:
    cell = nbf.v4.new_code_cell(text)
    cell.outputs = []
    cell.execution_count = None
    return cell


cells.append(
    md(
        """# NFL Middling & Multi-Book Odds

This notebook covers the two modules migrated from `Old-Files/nfl-data-agg`:

1. **Multi-book odds aggregation** — `data/sources/odds_api/game_lines.py`
   parses The Odds API event responses (h2h / spreads / totals / outrights)
   into a per-`(game, bookmaker)` DataFrame.
2. **Middling detection** — `core/betting/strategies/middling.py` finds
   spread and total middles where two books offer materially different
   lines on the same game.

Both are exposed via `NFLDataPipeline`:
- `pipeline.get_multi_book_odds(api_key)` — fetch + parse multi-book lines
- `pipeline.detect_middles(df)` — convenience wrapper around the strategy
"""
    )
)


cells.append(md("""## 1. Imports"""))


cells.append(
    code(
        """from quantitative_sports.data.nfl import NFLDataConfig, NFLDataPipeline
from quantitative_sports.data.sources.odds_api.game_lines import (
    parse_game_lines_to_raw,
    parse_outrights_to_futures,
)
from quantitative_sports.core.betting.strategies.middling import (
    detect_middles,
    detect_spread_middles,
    detect_total_middles,
)
import pandas as pd

print('Modules loaded.')"""
    )
)


cells.append(
    md(
        """## 2. The Odds API game-lines parser

The parser handles The Odds API's `bookmakers → markets → outcomes`
nested structure and flattens it into a row per (game, bookmaker).
It understands three market types:

- **h2h** — moneyline (ml_home, ml_away)
- **spreads** — point spread (spread_home, prices)
- **totals** — over/under (total, prices)

It also gracefully handles outrights/futures via a separate function."""
    )
)


cells.append(
    code(
        """# Synthetic Odds API response (matches the real JSON shape)
sample_event = {
    'id': 'abc123',
    'sport_key': 'americanfootball_nfl',
    'commence_time': '2026-09-07T20:20:00Z',
    'home_team': 'Kansas City Chiefs',
    'away_team': 'Baltimore Ravens',
    'bookmakers': [
        {
            'title': 'DraftKings',
            'last_update': '2026-09-07T18:00:00Z',
            'markets': [
                {'key': 'h2h', 'outcomes': [
                    {'name': 'Kansas City Chiefs', 'price': -150},
                    {'name': 'Baltimore Ravens', 'price': 130},
                ]},
                {'key': 'spreads', 'outcomes': [
                    {'name': 'Kansas City Chiefs', 'point': -3.5, 'price': -110},
                    {'name': 'Baltimore Ravens', 'point': 3.5, 'price': -110},
                ]},
                {'key': 'totals', 'outcomes': [
                    {'name': 'Over', 'point': 47.5, 'price': -110},
                    {'name': 'Under', 'point': 47.5, 'price': -110},
                ]},
            ],
        },
        {
            'title': 'FanDuel',
            'last_update': '2026-09-07T18:01:00Z',
            'markets': [
                {'key': 'h2h', 'outcomes': [
                    {'name': 'Kansas City Chiefs', 'price': -145},
                    {'name': 'Baltimore Ravens', 'price': 125},
                ]},
                {'key': 'spreads', 'outcomes': [
                    {'name': 'Kansas City Chiefs', 'point': -3, 'price': -115},
                    {'name': 'Baltimore Ravens', 'point': 3, 'price': -105},
                ]},
                # FanDuel has no totals market for this event
            ],
        },
    ],
}

df = parse_game_lines_to_raw([sample_event])
print(df[['source_id', 'ml_home', 'ml_away', 'spread_home', 'total']].to_string(index=False))"""
    )
)


cells.append(
    md(
        """## 3. Live multi-book fetch via the pipeline

`NFLDataPipeline.get_multi_book_odds()` wraps the parser with an httpx
GET to `https://api.the-odds-api.com/v4/sports/americanfootball_nfl/odds`.

Without an API key the call would hit the real endpoint; the example
below shows the in-memory parsed path. Provide an API key in production
via the `api_key` arg or an env var."""
    )
)


cells.append(
    code(
        """# Show pipeline signature; live fetch requires ODDS_API_KEY env var
import inspect

sig = inspect.signature(NFLDataPipeline.get_multi_book_odds)
print('get_multi_book_odds signature:')
for name, param in sig.parameters.items():
    print(f'  {name}: default={param.default}')"""
    )
)


cells.append(
    md(
        """## 4. Spread middling detection

A spread middle exists when one book offers the home team at -3.5 and
another offers the home team at -7. If the final margin lands between
4 and 6 points, both bets win — a high-EV situation."""
    )
)


cells.append(
    code(
        """multi_book_df = pd.DataFrame([
    {'game_id': 'G1', 'source_id': 'BookA', 'spread_home': -3.5, 'total': None,
     'ml_home': -150, 'ml_away': 130},
    {'game_id': 'G1', 'source_id': 'BookB', 'spread_home': -7.0, 'total': None,
     'ml_home': -130, 'ml_away': 110},
    {'game_id': 'G2', 'source_id': 'BookA', 'spread_home': -10.0, 'total': None,
     'ml_home': -450, 'ml_away': 350},
    {'game_id': 'G2', 'source_id': 'BookB', 'spread_home': -10.5, 'total': None,
     'ml_home': -475, 'ml_away': 360},
])

spread_middles = detect_spread_middles(multi_book_df, min_middle_points=1.0)
print('Spread middles found:')
print(spread_middles.to_string(index=False))"""
    )
)


cells.append(
    md(
        """## 5. Total middling detection

A total middle exists when one book offers Over 41.5 and another
offers Under 48 on the same game. A final total of 42-47 wins both."""
    )
)


cells.append(
    code(
        """totals_df = pd.DataFrame([
    {'game_id': 'G1', 'source_id': 'BookA', 'total': 41.5, 'spread_home': None},
    {'game_id': 'G1', 'source_id': 'BookB', 'total': 48.0, 'spread_home': None},
    {'game_id': 'G2', 'source_id': 'BookA', 'total': 44.0, 'spread_home': None},
    {'game_id': 'G2', 'source_id': 'BookB', 'total': 44.5, 'spread_home': None},
])

total_middles = detect_total_middles(totals_df, min_middle_points=1.0)
print('Total middles found:')
print(total_middles.to_string(index=False))"""
    )
)


cells.append(
    md(
        """## 6. Combined middling scan

`detect_middles()` returns both spread and total middles in a single
call. The pipeline wrapper `pipeline.detect_middles(df)` exposes the
same API via `NFLDataPipeline`."""
    )
)


cells.append(
    code(
        """combined_df = pd.DataFrame([
    {'game_id': 'G1', 'source_id': 'BookA', 'spread_home': -3.5, 'total': 41.5},
    {'game_id': 'G1', 'source_id': 'BookB', 'spread_home': -7.0, 'total': 48.0},
])
all_middles = detect_middles(combined_df, min_middle_points=1.0)
print('All middles (spread + total):')
print(all_middles.to_string(index=False))

# Same result via the pipeline wrapper
pipeline = NFLDataPipeline(config=NFLDataConfig())
via_pipeline = pipeline.detect_middles(combined_df, min_middle_points=1.0)
assert via_pipeline.equals(all_middles)
print('Pipeline wrapper matches strategy directly ✓')"""
    )
)


cells.append(
    md(
        """## 7. Outrights / futures parser

The Odds API returns futures markets as a separate endpoint. The
`parse_outrights_to_futures()` helper flattens Super Bowl / division
winner markets into a tidy long-format DataFrame."""
    )
)


cells.append(
    code(
        """futures_event = {
    'id': 'fut1',
    'commence_time': '2026-09-01T00:00:00Z',
    'bookmakers': [{
        'title': 'DraftKings',
        'last_update': '2026-09-01T00:00:00Z',
        'markets': [{
            'key': 'outrights',
            'outcomes': [
                {'name': 'Kansas City Chiefs', 'price': 600},
                {'name': 'Buffalo Bills', 'price': 750},
                {'name': 'San Francisco 49ers', 'price': 800},
            ],
        }],
    }],
}

futures_df = parse_outrights_to_futures(
    [futures_event], futures_market='super_bowl_winner'
)
print(futures_df.to_string(index=False))"""
    )
)


cells.append(
    md(
        """## Summary

- **`parse_game_lines_to_raw(events)`** flattens Odds API event responses
  into per-(game, bookmaker) rows with strict schema: `ml_home/ml_away`,
  `spread_home`, `total`, prices, source_id, observed_at.
- **`parse_outrights_to_futures(events, futures_market=...)`** handles
  championship / division winner markets separately.
- **`detect_middles(df)`** (and the `spread` / `total` variants) finds
  middling opportunities across books.
- **`NFLDataPipeline.get_multi_book_odds(api_key)`** is the production
  fetch path; **`NFLDataPipeline.detect_middles(df)`** wraps the strategy.

Next: plug these into the backtester to measure historical middle hit
rate, and wire into the web UI's EV calculator for live cross-book
comparison.
"""
    )
)


nb.cells = cells

out = Path("notebooks/football/05_nfl_middling_and_odds.ipynb")
out.parent.mkdir(parents=True, exist_ok=True)
nbf.write(nb, str(out))
print(f"Wrote {out} with {len(cells)} cells")
