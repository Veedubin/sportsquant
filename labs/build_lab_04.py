"""Build script for Lab 04: Multi-Book Middling — Detecting and Sizing Middles.

Generates ``04_multi_book_middling.ipynb`` using nbformat. Run this script to
produce the notebook, then open it in Jupyter to execute the cells against a
live TimescaleDB instance (or synthetic data if the DB is empty).

Usage::

    cd /home/jcharles/Projects/Infrastructure/quantitative_sports
    uv run python labs/build_lab_04.py
"""

from __future__ import annotations

import nbformat as nbf

OUTPUT_PATH = "labs/04_multi_book_middling.ipynb"


def build() -> nbf.NotebookNode:
    """Construct the Lab 04 notebook programmatically."""
    nb = nbf.v4.new_notebook()
    nb.metadata.update(
        {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {
                "name": "python",
                "version": "3.12.0",
            },
        }
    )

    cells: list[nbf.NotebookNode] = []

    # ── Cell 1: Title ──────────────────────────────────────────────────
    cells.append(
        nbf.v4.new_markdown_cell(
            "# Lab 04: Multi-Book Middling — Detecting and Sizing Middles\n"
            "\n"
            "A **middle** (or **middling opportunity**) occurs when two sportsbooks offer "
            "different enough lines on the same event that you can bet both sides and "
            "potentially win both bets. This lab teaches you how to detect and size "
            "these opportunities using Quant-Sports's middling detection module.\n"
            "\n"
            "By the end you will:\n"
            "\n"
            "- Understand what a middle is and why it's profitable\n"
            "- Pull spread and total odds from multiple books\n"
            "- Detect spread middles (different point spreads across books)\n"
            "- Detect total middles (different over/under lines across books)\n"
            "- Calculate the EV of a middle opportunity\n"
            "- Size both legs using Kelly Criterion\n"
            "- Use the `MiddlingStrategy` module from `quantitative_sports.core.betting.strategies`\n"
            "- Evaluate risk considerations and book limitations\n"
            "\n"
            "---"
        )
    )

    # ── Cell 2: Prerequisites ──────────────────────────────────────────
    cells.append(
        nbf.v4.new_markdown_cell(
            "## Prerequisites\n"
            "\n"
            "- **Lab 03 completed** — you understand EV, Kelly, and odds conversion\n"
            "- Understanding of spread and total (over/under) betting\n"
            "- Familiarity with point spreads (e.g., KC -3.5, BAL +3.5)\n"
            "\n"
            "### What Is a Middle?\n"
            "\n"
            "A middle occurs when two books offer different lines on the same market:\n"
            "\n"
            "**Spread Middle Example:**\n"
            "```\n"
            "Book A:  KC -3   (bet KC -3)\n"
            "Book B:  KC -7   (bet opponent +7)\n"
            "```\n"
            "If KC wins by 4, 5, or 6 points, **both bets win**.\n"
            'The "middle" is the range [4, 6] — 3 points wide.\n'
            "\n"
            "**Total Middle Example:**\n"
            "```\n"
            "Book A:  Over 41.5  (bet Over 41.5)\n"
            "Book B:  Under 48    (bet Under 48)\n"
            "```\n"
            "If the total lands between 42-47, **both bets win**.\n"
            'The "middle" is the range [42, 47] — 6 points wide.'
        )
    )

    # ── Cell 3: Section 1 — What is a middle? ──────────────────────────
    cells.append(
        nbf.v4.new_markdown_cell(
            "---\n"
            "\n"
            "## Section 1: Understanding Middles in Detail\n"
            "\n"
            "A middle has three possible outcomes:\n"
            "\n"
            "1. **Both bets win** — the final value lands inside the middle range\n"
            "2. **One bet wins, one pushes** — the final value lands on one of the lines\n"
            "3. **One bet wins, one loses** — the final value is outside the range\n"
            "\n"
            "The **middle EV** depends on:\n"
            "- The probability of hitting the middle (both bets win)\n"
            "- The probability of a push on either side\n"
            "- The odds on each leg\n"
            "\n"
            "In a typical middle with -110 odds on both sides:\n"
            "- You risk 2 units (1 on each bet)\n"
            "- If you hit the middle, you win ~1.82 units on each bet = 3.64 units profit\n"
            "- If one side wins and the other loses, you lose the vig (~0.09 units)\n"
            "\n"
            "The wider the middle range, the higher the probability of hitting it."
        )
    )

    # ── Cell 4: Section 2 — Setup ──────────────────────────────────────
    cells.append(
        nbf.v4.new_markdown_cell(
            "---\n"
            "\n"
            "## Section 2: Setup — Imports and DB Connection\n"
            "\n"
            "We'll connect to TimescaleDB for live odds and use the middling detection "
            "module from `quantitative_sports.core.betting.strategies.middling`."
        )
    )

    # ── Cell 5: Imports ────────────────────────────────────────────────
    cells.append(
        nbf.v4.new_code_cell(
            "# Cell 5: Core imports\n"
            "import asyncio\n"
            "import json\n"
            "from dataclasses import dataclass\n"
            "\n"
            "import pandas as pd\n"
            "import numpy as np\n"
            "\n"
            "from quantitative_sports.core.betting.odds import Odds\n"
            "from quantitative_sports.core.betting.kelly import (\n"
            "    KellyCalculator,\n"
            "    EdgeCalculator,\n"
            "    BankrollManager,\n"
            ")\n"
            "from quantitative_sports.core.betting.engine import (\n"
            "    american_to_decimal,\n"
            "    calculate_ev,\n"
            ")\n"
            "from quantitative_sports.core.betting.strategies.middling import (\n"
            "    MiddleOpportunity,\n"
            "    detect_spread_middles,\n"
            "    detect_total_middles,\n"
            "    detect_middles,\n"
            ")\n"
            "from quantitative_sports.util.time_utils import american_to_implied_prob, safe_float\n"
            "from quantitative_sports.infra.db.connection import DBConfig, DatabasePool, get_pool, reset_pool\n"
            "\n"
            "import nest_asyncio\n"
            "nest_asyncio.apply()\n"
            "\n"
            "print('Imports loaded successfully.')"
        )
    )

    # ── Cell 6: DB Connection ──────────────────────────────────────────
    cells.append(
        nbf.v4.new_code_cell(
            "# Cell 6: Connect to TimescaleDB\n"
            "#\n"
            "# If the DB is not available, we'll use synthetic data.\n"
            "\n"
            "db_available = False\n"
            "try:\n"
            "    config = DBConfig.from_env()\n"
            "    pool = await get_pool(config)\n"
            "    db_available = True\n"
            "    print(f'Connected to {config.host}:{config.port}/{config.database}')\n"
            "except Exception as e:\n"
            "    print(f'DB not available: {e}')\n"
            "    print('Will use synthetic data for this lab.')"
        )
    )

    # ── Cell 7: Section 3 — Pull spread/total odds ──────────────────────
    cells.append(
        nbf.v4.new_markdown_cell(
            "---\n"
            "\n"
            "## Section 3: Pull Spread and Total Odds\n"
            "\n"
            "For middling, we need odds from **multiple books** on the same event. "
            "We'll query `odds_ticks` for spread and total markets. The key columns are:\n"
            "\n"
            "- `event_id` — identifies the game\n"
            "- `book` — the sportsbook (e.g., 'draftkings', 'fanduel')\n"
            "- `market` — 'spreads' or 'totals'\n"
            "- `selection` — team name or 'Over'/'Under'\n"
            "- `price` — American odds\n"
            "- `line` — the spread or total value (e.g., -3.5, 48.5)"
        )
    )

    # ── Cell 8: Query spread/total odds ─────────────────────────────────
    cells.append(
        nbf.v4.new_code_cell(
            "# Cell 8: Fetch spread and total odds from odds_ticks\n"
            "#\n"
            "# We query for both spread and total markets across all books.\n"
            "\n"
            "if db_available:\n"
            "    spread_rows = await pool.fetch(\n"
            '        "SELECT sport, league, event_id, book, market, selection, price, line, ts "\n'
            "        \"FROM odds_ticks WHERE market = 'spreads' ORDER BY ts DESC LIMIT 40\"\n"
            "    )\n"
            "    total_rows = await pool.fetch(\n"
            '        "SELECT sport, league, event_id, book, market, selection, price, line, ts "\n'
            "        \"FROM odds_ticks WHERE market = 'totals' ORDER BY ts DESC LIMIT 40\"\n"
            "    )\n"
            "    \n"
            "    if spread_rows or total_rows:\n"
            "        spread_data = [dict(r) for r in spread_rows] if spread_rows else []\n"
            "        total_data = [dict(r) for r in total_rows] if total_rows else []\n"
            "        print(f'Loaded {len(spread_data)} spread rows and {len(total_data)} total rows from DB')\n"
            "    else:\n"
            "        print('No spread/total data in DB. Using synthetic data.')\n"
            "        db_available = False\n"
            "\n"
            "if not db_available or (not spread_rows and not total_rows):\n"
            "    # Synthetic spread data — same game across different books\n"
            "    spread_data = [\n"
            "        # KC vs BAL — varying spreads\n"
            "        {'sport': 'nfl', 'league': 'NFL', 'event_id': 'KC_vs_BAL_2026', 'book': 'draftkings', 'market': 'spreads', 'selection': 'KC Chiefs', 'price': -110, 'line': -3.0, 'ts': '2026-06-17T18:00:00Z'},\n"
            "        {'sport': 'nfl', 'league': 'NFL', 'event_id': 'KC_vs_BAL_2026', 'book': 'fanduel', 'market': 'spreads', 'selection': 'KC Chiefs', 'price': -110, 'line': -3.5, 'ts': '2026-06-17T18:00:05Z'},\n"
            "        {'sport': 'nfl', 'league': 'NFL', 'event_id': 'KC_vs_BAL_2026', 'book': 'betmgm', 'market': 'spreads', 'selection': 'KC Chiefs', 'price': -110, 'line': -4.0, 'ts': '2026-06-17T18:00:10Z'},\n"
            "        {'sport': 'nfl', 'league': 'NFL', 'event_id': 'KC_vs_BAL_2026', 'book': 'pointsbet', 'market': 'spreads', 'selection': 'KC Chiefs', 'price': -105, 'line': -2.5, 'ts': '2026-06-17T18:00:15Z'},\n"
            "        # SF vs DET — tighter spreads\n"
            "        {'sport': 'nfl', 'league': 'NFL', 'event_id': 'SF_vs_DET_2026', 'book': 'draftkings', 'market': 'spreads', 'selection': 'SF 49ers', 'price': -110, 'line': -1.0, 'ts': '2026-06-17T18:01:00Z'},\n"
            "        {'sport': 'nfl', 'league': 'NFL', 'event_id': 'SF_vs_DET_2026', 'book': 'fanduel', 'market': 'spreads', 'selection': 'SF 49ers', 'price': -110, 'line': -1.5, 'ts': '2026-06-17T18:01:05Z'},\n"
            "        # BUF vs MIA — large spread\n"
            "        {'sport': 'nfl', 'league': 'NFL', 'event_id': 'BUF_vs_MIA_2026', 'book': 'draftkings', 'market': 'spreads', 'selection': 'BUF Bills', 'price': -110, 'line': -7.0, 'ts': '2026-06-17T18:02:00Z'},\n"
            "        {'sport': 'nfl', 'league': 'NFL', 'event_id': 'BUF_vs_MIA_2026', 'book': 'betmgm', 'market': 'spreads', 'selection': 'BUF Bills', 'price': -110, 'line': -6.5, 'ts': '2026-06-17T18:02:05Z'},\n"
            "    ]\n"
            "    # Synthetic total data\n"
            "    total_data = [\n"
            "        # KC vs BAL totals\n"
            "        {'sport': 'nfl', 'league': 'NFL', 'event_id': 'KC_vs_BAL_2026', 'book': 'draftkings', 'market': 'totals', 'selection': 'Over', 'price': -110, 'line': 47.5, 'ts': '2026-06-17T18:00:00Z'},\n"
            "        {'sport': 'nfl', 'league': 'NFL', 'event_id': 'KC_vs_BAL_2026', 'book': 'fanduel', 'market': 'totals', 'selection': 'Under', 'price': -110, 'line': 48.5, 'ts': '2026-06-17T18:00:05Z'},\n"
            "        {'sport': 'nfl', 'league': 'NFL', 'event_id': 'KC_vs_BAL_2026', 'book': 'betmgm', 'market': 'totals', 'selection': 'Over', 'price': -105, 'line': 46.5, 'ts': '2026-06-17T18:00:10Z'},\n"
            "        # SF vs DET totals\n"
            "        {'sport': 'nfl', 'league': 'NFL', 'event_id': 'SF_vs_DET_2026', 'book': 'draftkings', 'market': 'totals', 'selection': 'Over', 'price': -110, 'line': 51.0, 'ts': '2026-06-17T18:01:00Z'},\n"
            "        {'sport': 'nfl', 'league': 'NFL', 'event_id': 'SF_vs_DET_2026', 'book': 'fanduel', 'market': 'totals', 'selection': 'Under', 'price': -110, 'line': 52.5, 'ts': '2026-06-17T18:01:05Z'},\n"
            "        # BUF vs MIA totals\n"
            "        {'sport': 'nfl', 'league': 'NFL', 'event_id': 'BUF_vs_MIA_2026', 'book': 'draftkings', 'market': 'totals', 'selection': 'Over', 'price': -110, 'line': 44.5, 'ts': '2026-06-17T18:02:00Z'},\n"
            "        {'sport': 'nfl', 'league': 'NFL', 'event_id': 'BUF_vs_MIA_2026', 'book': 'betmgm', 'market': 'totals', 'selection': 'Under', 'price': -105, 'line': 46.0, 'ts': '2026-06-17T18:02:05Z'},\n"
            "    ]\n"
            "    print(f'Using {len(spread_data)} synthetic spread rows and {len(total_data)} synthetic total rows')\n"
            "\n"
            "spread_df = pd.DataFrame(spread_data)\n"
            "total_df = pd.DataFrame(total_data)\n"
            "print(f'\\nSpread data ({len(spread_df)} rows):')\n"
            "print(spread_df[['event_id', 'book', 'selection', 'price', 'line']].to_string(index=False))\n"
            "print(f'\\nTotal data ({len(total_df)} rows):')\n"
            "print(total_df[['event_id', 'book', 'selection', 'price', 'line']].to_string(index=False))"
        )
    )

    # ── Cell 9: Section 4 — Group by event ──────────────────────────────
    cells.append(
        nbf.v4.new_markdown_cell(
            "---\n"
            "\n"
            "## Section 4: Group by Event\n"
            "\n"
            "For middling detection, we need to group odds by event. For each game, "
            "we look at what different books are offering for the same market."
        )
    )

    # ── Cell 10: Group by event ──────────────────────────────────────────
    cells.append(
        nbf.v4.new_code_cell(
            "# Cell 10: Group odds by event and inspect\n"
            "#\n"
            "# For middling, we need at least two different books on the same event.\n"
            "\n"
            "print('Spread odds grouped by event:')\n"
            "for event_id, group in spread_df.groupby('event_id'):\n"
            "    books = group['book'].unique()\n"
            "    print(f'\\n  {event_id}: {len(books)} books')\n"
            "    for _, row in group.iterrows():\n"
            '        print(f\'    {row["book"]:<15} {row["selection"]:<15} spread={row["line"]:<6} odds={row["price"]}\')\n'
            "\n"
            "print('\\nTotal odds grouped by event:')\n"
            "for event_id, group in total_df.groupby('event_id'):\n"
            "    books = group['book'].unique()\n"
            "    print(f'\\n  {event_id}: {len(books)} books')\n"
            "    for _, row in group.iterrows():\n"
            '        print(f\'    {row["book"]:<15} {row["selection"]:<10} total={row["line"]:<6} odds={row["price"]}\')'
        )
    )

    # ── Cell 11: Section 5 — Detect spread middles ──────────────────────
    cells.append(
        nbf.v4.new_markdown_cell(
            "---\n"
            "\n"
            "## Section 5: Detect Spread Middles\n"
            "\n"
            "A **spread middle** exists when two books offer different point spreads for "
            "the same game. The wider the gap between the spreads, the more likely both "
            "bets can win.\n"
            "\n"
            "**How to bet a spread middle:**\n"
            "1. Find Book A offering the favorite at the *lowest* spread (e.g., -3)\n"
            "2. Find Book B offering the underdog at the *highest* spread (e.g., +7)\n"
            "3. Bet the favorite at Book A and the underdog at Book B\n"
            "4. If the final margin is between 3 and 6, both bets win!\n"
            "\n"
            "We use `detect_spread_middles()` from the middling module, which expects "
            "a DataFrame with columns: `game_id`, `spread_home`, `source_id`."
        )
    )

    # ── Cell 12: Spread middle detection ─────────────────────────────────
    cells.append(
        nbf.v4.new_code_cell(
            "# Cell 12: Detect spread middles\n"
            "#\n"
            "# The detect_spread_middles() function expects columns:\n"
            "#   game_id, spread_home, source_id\n"
            "#\n"
            "# We need to transform our data to match this schema.\n"
            "# spread_home = line (negative means home is favored)\n"
            "\n"
            "# Transform spread data for the middling module\n"
            "spread_for_detect = spread_df.rename(columns={\n"
            "    'event_id': 'game_id',\n"
            "    'line': 'spread_home',\n"
            "    'book': 'source_id',\n"
            "})[['game_id', 'spread_home', 'source_id']]\n"
            "\n"
            "# Detect spread middles (min 0.5 points gap)\n"
            "spread_middles = detect_spread_middles(spread_for_detect, min_middle_points=0.5)\n"
            "\n"
            "if spread_middles.empty:\n"
            "    print('No spread middles detected (gap < 0.5 points between best lines).')\n"
            "    print('Try lowering min_middle_points or adding more data.')\n"
            "else:\n"
            "    print('Spread middle opportunities found:')\n"
            "    print(spread_middles.to_string(index=False))\n"
            "    print(f'\\nTotal: {len(spread_middles)} spread middle(s)')\n"
            "    for _, row in spread_middles.iterrows():\n"
            '        print(f\'\\n  {row["game_id"]}: {row["low_book"]} @ {row["low_line"]} vs \'\n'
            '              f\'{row["high_book"]} @ {row["high_line"]} → \'\n'
            "              f'{row[\"middle_points\"]} point middle')"
        )
    )

    # ── Cell 13: Section 6 — Calculate middle EV ──────────────────────────
    cells.append(
        nbf.v4.new_markdown_cell(
            "---\n"
            "\n"
            "## Section 6: Calculate Middle EV\n"
            "\n"
            "The EV of a middle depends on:\n"
            "\n"
            "1. **Probability of hitting the middle** — both bets win\n"
            "2. **Probability of a push** — one bet pushes (line lands on the number)\n"
            "3. **Probability of one win, one loss** — only one side wins\n"
            "\n"
            "For a rough estimate, assuming each integer score margin is equally likely "
            "within a range, the probability of hitting a middle of width `w` is approximately "
            "`w / total_range`.\n"
            "\n"
            "For NFL games, a common assumption is that the final margin follows a normal "
            "distribution around the spread with σ ≈ 13.5 points. We'll use a simplified model."
        )
    )

    # ── Cell 14: Middle EV calculation ──────────────────────────────────
    cells.append(
        nbf.v4.new_code_cell(
            "# Cell 14: Calculate middle EV for detected spread middles\n"
            "#\n"
            "# For a spread middle:\n"
            "#   - You bet the favorite at the lower spread (e.g., -3)\n"
            "#   - You bet the underdog at the higher spread (e.g., +7)\n"
            "#   - If the margin lands between 3 and 6, both bets win\n"
            "#\n"
            "# We approximate the probability of hitting the middle using\n"
            "# a normal distribution with σ ≈ 13.5 points (typical NFL spread std dev).\n"
            "\n"
            "from scipy import stats\n"
            "\n"
            "def middle_probability(\n"
            "    low_line: float,\n"
            "    high_line: float,\n"
            "    sigma: float = 13.5,\n"
            ") -> tuple[float, float, float]:\n"
            '    """Estimate probability of hitting a spread middle.\n'
            "\n"
            "    Args:\n"
            "        low_line: The lower (more favorable) spread line.\n"
            "        high_line: The higher (less favorable) spread line.\n"
            "        sigma: Standard deviation of the final margin (default 13.5 for NFL).\n"
            "\n"
            "    Returns:\n"
            "        Tuple of (middle_prob, push_prob, miss_prob).\n"
            '    """\n'
            "    # The middle range: margin > abs(low_line) AND margin < abs(high_line)\n"
            "    # For a favorite at -3: margin needs to be > 3 for this bet to win\n"
            "    # For an underdog at +7: margin needs to be < 7 for this bet to win\n"
            "    # Middle: margin between abs(low_line) and abs(high_line) (exclusive of push)\n"
            "    \n"
            "    abs_low = abs(low_line)\n"
            "    abs_high = abs(high_line)\n"
            "    \n"
            "    # Using CDF of normal centered at 0 (the spread is the expected margin)\n"
            "    # P(middle) = P(abs_low < margin < abs_high)\n"
            "    # P(push_low) = P(margin = abs_low) ≈ 0 for continuous\n"
            "    # P(push_high) = P(margin = abs_high) ≈ 0 for continuous\n"
            "    \n"
            "    # For half-point spreads, no push is possible\n"
            "    middle_prob = stats.norm.cdf(abs_high, loc=0, scale=sigma) - stats.norm.cdf(abs_low, loc=0, scale=sigma)\n"
            "    \n"
            "    # Push probability (non-zero only for whole-number spreads)\n"
            "    push_low = stats.norm.pdf(abs_low, loc=0, scale=sigma) if abs_low == int(abs_low) else 0\n"
            "    push_high = stats.norm.pdf(abs_high, loc=0, scale=sigma) if abs_high == int(abs_high) else 0\n"
            "    push_prob = push_low + push_high\n"
            "    \n"
            "    # Miss probability\n"
            "    miss_prob = 1.0 - middle_prob - push_prob\n"
            "    \n"
            "    return (max(0, middle_prob), max(0, push_prob), max(0, miss_prob))\n"
            "\n"
            "\n"
            "def middle_ev(\n"
            "    low_line: float,\n"
            "    high_line: float,\n"
            "    low_odds: int = -110,\n"
            "    high_odds: int = -110,\n"
            "    sigma: float = 13.5,\n"
            ") -> dict[str, float]:\n"
            '    """Calculate EV for a spread middle opportunity.\n'
            "\n"
            "    Args:\n"
            "        low_line: The lower spread line (e.g., -3.0).\n"
            "        high_line: The higher spread line (e.g., -7.0 or +7.0).\n"
            "        low_odds: American odds for the lower line bet.\n"
            "        high_odds: American odds for the higher line bet.\n"
            "        sigma: Standard deviation for margin distribution.\n"
            "\n"
            "    Returns:\n"
            "        Dict with middle_prob, push_prob, miss_prob, EV, and net outcomes.\n"
            '    """\n'
            "    mid_prob, push_prob, miss_prob = middle_probability(low_line, high_line, sigma)\n"
            "    \n"
            "    # Decimal odds for each leg\n"
            "    dec_low = american_to_decimal(low_odds)\n"
            "    dec_high = american_to_decimal(high_odds)\n"
            "    \n"
            "    # Stake 1 unit on each leg (2 units total risk)\n"
            "    # Middle hit: win both bets → profit = (dec_low - 1) + (dec_high - 1) = dec_low + dec_high - 2\n"
            "    middle_profit = (dec_low - 1) + (dec_high - 1)\n"
            "    \n"
            "    # Push one side: one bet refunds, other wins or loses\n"
            "    # Simplified: push returns 0.5 * (middle_profit) on average\n"
            "    push_profit = 0.0  # Push on one side, lose the other → small loss\n"
            "    \n"
            "    # Miss: one wins, one loses → net loss = vig\n"
            "    # Worst case: lose one unit, win (dec_other - 1) units\n"
            "    miss_profit = -1.0 + (dec_low - 1)  # Assume the low line bet wins\n"
            "    if miss_profit > 0:\n"
            "        miss_profit_alt = -1.0 + (dec_high - 1)  # Or the high line bet wins\n"
            "        miss_profit = min(miss_profit, miss_profit_alt)  # Take worst case\n"
            "    \n"
            "    # EV calculation\n"
            "    ev = mid_prob * middle_profit + push_prob * push_profit + miss_prob * miss_profit\n"
            "    \n"
            "    return {\n"
            "        'middle_points': high_line - low_line if high_line > low_line else abs(high_line) - abs(low_line),\n"
            "        'middle_prob': mid_prob,\n"
            "        'push_prob': push_prob,\n"
            "        'miss_prob': miss_prob,\n"
            "        'middle_profit_per_unit': middle_profit,\n"
            "        'miss_loss_per_unit': miss_profit,\n"
            "        'ev_per_unit': ev,\n"
            "    }\n"
            "\n"
            "\n"
            "# Calculate EV for each detected spread middle\n"
            "if not spread_middles.empty:\n"
            "    print('Spread Middle EV Analysis:')\n"
            "    print(f\"{'Game':<20} {'Low':<8} {'High':<8} {'Mid Pts':<8} {'Mid%':<8} {'EV/unit':<10}\")\n"
            "    print(f\"{'-'*20} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*10}\")\n"
            "    \n"
            "    for _, row in spread_middles.iterrows():\n"
            "        ev_result = middle_ev(row['low_line'], row['high_line'])\n"
            "        print(f\"{row['game_id']:<20} {row['low_line']:<8.1f} {row['high_line']:<8.1f} \"\n"
            "              f\"{ev_result['middle_points']:<8.1f} {ev_result['middle_prob']:<8.4f} {ev_result['ev_per_unit']:<10.4f}\")\n"
            "else:\n"
            "    # Demonstrate with synthetic middle\n"
            "    print('No spread middles detected. Demonstrating with synthetic example:')\n"
            "    demo = middle_ev(-3.0, -7.0)\n"
            "    for key, val in demo.items():\n"
            "        print(f'  {key}: {val:.6f}' if isinstance(val, float) else f'  {key}: {val}')"
        )
    )

    # ── Cell 15: Section 7 — Size both legs ──────────────────────────────
    cells.append(
        nbf.v4.new_markdown_cell(
            "---\n"
            "\n"
            "## Section 7: Size Both Legs with Kelly\n"
            "\n"
            "When betting a middle, you're placing two separate bets. Each leg has its "
            "own probability and odds. We size each leg independently using Kelly, but "
            "we must account for the correlation between them.\n"
            "\n"
            "For simplicity, we'll size each leg at quarter-Kelly and ensure the total "
            "exposure doesn't exceed our position limits."
        )
    )

    # ── Cell 16: Kelly sizing for middle legs ────────────────────────────
    cells.append(
        nbf.v4.new_code_cell(
            "# Cell 16: Kelly sizing for middle legs\n"
            "\n"
            "BANKROLL = 10_000.0\n"
            "kelly_calc = KellyCalculator()\n"
            "bm = BankrollManager(bankroll=BANKROLL)\n"
            "\n"
            "def size_middle_legs(\n"
            "    low_line: float,\n"
            "    high_line: float,\n"
            "    low_odds: int = -110,\n"
            "    high_odds: int = -110,\n"
            "    sigma: float = 13.5,\n"
            "    kelly_fraction: float = 0.25,\n"
            ") -> dict[str, float]:\n"
            '    """Size both legs of a middle using fractional Kelly.\n'
            "\n"
            "    Args:\n"
            "        low_line: The lower spread line.\n"
            "        high_line: The higher spread line.\n"
            "        low_odds: American odds for the lower line bet.\n"
            "        high_odds: American odds for the higher line bet.\n"
            "        sigma: Std dev for margin distribution.\n"
            "        kelly_fraction: Fraction of Kelly to use (default 0.25).\n"
            "\n"
            "    Returns:\n"
            "        Dict with bet sizes, Kelly fractions, and total exposure.\n"
            '    """\n'
            "    # Probabilities\n"
            "    abs_low = abs(low_line)\n"
            "    abs_high = abs(high_line)\n"
            "    \n"
            "    # For leg 1 (bet at low_line): P(win) = P(margin > abs_low)\n"
            "    prob_leg1_win = 1 - stats.norm.cdf(abs_low, loc=0, scale=sigma)\n"
            "    # For leg 2 (bet at high_line): P(win) = P(margin < abs_high)\n"
            "    prob_leg2_win = stats.norm.cdf(abs_high, loc=0, scale=sigma)\n"
            "    \n"
            "    dec_low = american_to_decimal(low_odds)\n"
            "    dec_high = american_to_decimal(high_odds)\n"
            "    \n"
            "    # Kelly fractions\n"
            "    kelly_leg1 = kelly_calc.compute_fractional_kelly(prob_leg1_win, dec_low, fraction=kelly_fraction)\n"
            "    kelly_leg2 = kelly_calc.compute_fractional_kelly(prob_leg2_win, dec_high, fraction=kelly_fraction)\n"
            "    \n"
            "    # Bet sizes\n"
            "    bet_size_1 = bm.compute_bet_size(kelly_leg1, dec_low, prob_leg1_win) if kelly_leg1 > 0 else 0\n"
            "    bet_size_2 = bm.compute_bet_size(kelly_leg2, dec_high, prob_leg2_win) if kelly_leg2 > 0 else 0\n"
            "    \n"
            "    total_exposure = bet_size_1 + bet_size_2\n"
            "    \n"
            "    return {\n"
            "        'leg1_prob': prob_leg1_win,\n"
            "        'leg2_prob': prob_leg2_win,\n"
            "        'leg1_kelly': kelly_leg1,\n"
            "        'leg2_kelly': kelly_leg2,\n"
            "        'leg1_bet': round(bet_size_1, 2),\n"
            "        'leg2_bet': round(bet_size_2, 2),\n"
            "        'total_exposure': round(total_exposure, 2),\n"
            "        'pct_bankroll': round(total_exposure / BANKROLL * 100, 1),\n"
            "    }\n"
            "\n"
            "\n"
            "# Size middle legs for detected spread middles\n"
            "if not spread_middles.empty:\n"
            "    print(f'Kelly Sizing for Middle Legs (bankroll=${BANKROLL:,.0f}, quarter-Kelly):')\n"
            "    print()\n"
            "    for _, row in spread_middles.iterrows():\n"
            "        sizing = size_middle_legs(row['low_line'], row['high_line'])\n"
            "        print(f'  {row[\"game_id\"]}:')\n"
            '        print(f\'    Leg 1 ({row["low_book"]} @ {row["low_line"]}): \'\n'
            '              f\'prob={sizing["leg1_prob"]:.4f}, kelly={sizing["leg1_kelly"]:.4f}, bet=${sizing["leg1_bet"]:.2f}\')\n'
            '        print(f\'    Leg 2 ({row["high_book"]} @ {row["high_line"]}): \'\n'
            '              f\'prob={sizing["leg2_prob"]:.4f}, kelly={sizing["leg2_kelly"]:.4f}, bet=${sizing["leg2_bet"]:.2f}\')\n'
            '        print(f\'    Total exposure: ${sizing["total_exposure"]:.2f} ({sizing["pct_bankroll"]:.1f}% of bankroll)\')\n'
            "        print()\n"
            "else:\n"
            "    # Demo with synthetic middle\n"
            "    print('Demo sizing for KC -3 vs KC -7 middle:')\n"
            "    sizing = size_middle_legs(-3.0, -7.0)\n"
            "    for key, val in sizing.items():\n"
            "        print(f'  {key}: {val:.6f}' if isinstance(val, float) else f'  {key}: {val}')"
        )
    )

    # ── Cell 17: Section 8 — Detect total middles ──────────────────────────
    cells.append(
        nbf.v4.new_markdown_cell(
            "---\n"
            "\n"
            "## Section 8: Detect Total Middles\n"
            "\n"
            "A **total middle** works the same way as a spread middle, but with "
            "over/under lines instead of point spreads.\n"
            "\n"
            "**Total Middle Example:**\n"
            "```\n"
            "Book A:  Over 41.5  (bet Over 41.5)\n"
            "Book B:  Under 48   (bet Under 48)\n"
            "```\n"
            "If the total points scored is between 42-47, both bets win.\n"
            "\n"
            "We use `detect_total_middles()` which expects columns: "
            "`game_id`, `total`, `source_id`."
        )
    )

    # ── Cell 18: Total middle detection ─────────────────────────────────
    cells.append(
        nbf.v4.new_code_cell(
            "# Cell 18: Detect total middles\n"
            "#\n"
            "# Transform total data for the middling module.\n"
            "# The detect_total_middles function expects: game_id, total, source_id\n"
            "\n"
            "total_for_detect = total_df.rename(columns={\n"
            "    'event_id': 'game_id',\n"
            "    'line': 'total',\n"
            "    'book': 'source_id',\n"
            "})[['game_id', 'total', 'source_id']]\n"
            "\n"
            "# Detect total middles (min 0.5 points gap)\n"
            "total_middles = detect_total_middles(total_for_detect, min_middle_points=0.5)\n"
            "\n"
            "if total_middles.empty:\n"
            "    print('No total middles detected (gap < 0.5 points between best lines).')\n"
            "    print('This is expected when books have tight total lines.')\n"
            "else:\n"
            "    print('Total middle opportunities found:')\n"
            "    print(total_middles.to_string(index=False))\n"
            "    print(f'\\nTotal: {len(total_middles)} total middle(s)')\n"
            "    for _, row in total_middles.iterrows():\n"
            "        width = row['high_line'] - row['low_line']\n"
            '        print(f\'\\n  {row["game_id"]}: {row["low_book"]} @ {row["low_line"]} vs \'\n'
            '              f\'{row["high_book"]} @ {row["high_line"]} → \'\n'
            "              f'{row[\"middle_points\"]} point middle (width: {width:.1f})')"
        )
    )

    # ── Cell 19: Total middle EV ─────────────────────────────────────────
    cells.append(
        nbf.v4.new_code_cell(
            "# Cell 19: Calculate EV for detected total middles\n"
            "#\n"
            "# For total middles, we use a different sigma (typically ~14 for NFL totals).\n"
            "\n"
            "def total_middle_ev(\n"
            "    low_total: float,\n"
            "    high_total: float,\n"
            "    low_odds: int = -110,\n"
            "    high_odds: int = -110,\n"
            "    sigma: float = 14.0,\n"
            ") -> dict[str, float]:\n"
            '    """Calculate EV for a total middle opportunity.\n'
            "\n"
            "    Args:\n"
            "        low_total: The lower total line (best for Over).\n"
            "        high_total: The higher total line (best for Under).\n"
            "        low_odds: American odds for the Over bet.\n"
            "        high_odds: American odds for the Under bet.\n"
            "        sigma: Std dev for total points distribution.\n"
            "\n"
            "    Returns:\n"
            "        Dict with middle probability, EV, and sizing info.\n"
            '    """\n'
            "    # Middle range: total between low_total and high_total\n"
            "    # For half-point lines, add 0.5; for whole lines, use exact\n"
            "    low_bound = low_total + (0.5 if low_total == int(low_total) else 0)\n"
            "    high_bound = high_total - (0.5 if high_total == int(high_total) else 0)\n"
            "    \n"
            "    # Assume total follows normal distribution centered at midpoint\n"
            "    midpoint = (low_total + high_total) / 2\n"
            "    middle_prob = stats.norm.cdf(high_total, loc=midpoint, scale=sigma) - stats.norm.cdf(low_total, loc=midpoint, scale=sigma)\n"
            "    \n"
            "    dec_low = american_to_decimal(low_odds)\n"
            "    dec_high = american_to_decimal(high_odds)\n"
            "    \n"
            "    # Both win profit\n"
            "    middle_profit = (dec_low - 1) + (dec_high - 1)\n"
            "    # One wins, one loses (typical vig loss)\n"
            "    miss_loss = -1.0 + (dec_low - 1)  # Approximate\n"
            "    \n"
            "    ev = middle_prob * middle_profit + (1 - middle_prob) * miss_loss\n"
            "    \n"
            "    return {\n"
            "        'middle_points': high_total - low_total,\n"
            "        'middle_prob': middle_prob,\n"
            "        'ev_per_unit': ev,\n"
            "        'middle_profit_per_unit': middle_profit,\n"
            "        'miss_loss_per_unit': miss_loss,\n"
            "    }\n"
            "\n"
            "\n"
            "if not total_middles.empty:\n"
            "    print('Total Middle EV Analysis:')\n"
            "    print(f\"{'Game':<20} {'Low':<8} {'High':<8} {'Mid Pts':<8} {'Mid%':<8} {'EV/unit':<10}\")\n"
            "    print(f\"{'-'*20} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*10}\")\n"
            "    \n"
            "    for _, row in total_middles.iterrows():\n"
            "        ev_result = total_middle_ev(row['low_line'], row['high_line'])\n"
            "        print(f\"{row['game_id']:<20} {row['low_line']:<8.1f} {row['high_line']:<8.1f} \"\n"
            "              f\"{ev_result['middle_points']:<8.1f} {ev_result['middle_prob']:<8.4f} {ev_result['ev_per_unit']:<10.4f}\")\n"
            "else:\n"
            "    print('No total middles found. Demonstrating with synthetic example:')\n"
            "    demo = total_middle_ev(47.5, 48.5)\n"
            "    for key, val in demo.items():\n"
            "        print(f'  {key}: {val:.6f}' if isinstance(val, float) else f'  {key}: {val}')"
        )
    )

    # ── Cell 20: Section 9 — Use the middling strategy module ──────────────
    cells.append(
        nbf.v4.new_markdown_cell(
            "---\n"
            "\n"
            "## Section 9: Using the Middling Strategy Module\n"
            "\n"
            "Quant-Sports's `detect_middles()` function combines both spread and total "
            "middle detection into a single call. It returns a DataFrame with all "
            "detected opportunities, their midpoint values, and which books offer them."
        )
    )

    # ── Cell 21: Combined middle detection ──────────────────────────────
    cells.append(
        nbf.v4.new_code_cell(
            "# Cell 21: Use detect_middles() for combined detection\n"
            "#\n"
            "# Combine spread and total data into a single DataFrame for detect_middles().\n"
            "# The function needs columns: game_id, spread_home, total, source_id\n"
            "\n"
            "# Prepare combined data\n"
            "combined_df = spread_df.rename(columns={\n"
            "    'event_id': 'game_id',\n"
            "    'line': 'spread_home',\n"
            "    'book': 'source_id',\n"
            "})[['game_id', 'spread_home', 'source_id']].copy()\n"
            "\n"
            "# Add total data\n"
            "total_for_combined = total_df.rename(columns={\n"
            "    'event_id': 'game_id',\n"
            "    'line': 'total',\n"
            "    'book': 'source_id',\n"
            "})[['game_id', 'total', 'source_id']].copy()\n"
            "\n"
            "# Merge on game_id + source_id\n"
            "combined_df = combined_df.merge(\n"
            "    total_for_combined,\n"
            "    on=['game_id', 'source_id'],\n"
            "    how='outer'\n"
            ")\n"
            "\n"
            "print('Combined data for detect_middles():')\n"
            "print(combined_df.to_string(index=False))\n"
            "\n"
            "# Detect all middles\n"
            "all_middles = detect_middles(combined_df, min_middle_points=0.5)\n"
            "\n"
            "print(f'\\nDetected {len(all_middles)} total middle opportunities:')\n"
            "if not all_middles.empty:\n"
            "    for _, row in all_middles.iterrows():\n"
            '        print(f\'  [{row["market"]}] {row["game_id"]}: {row["low_book"]} @ {row["low_line"]} \'\n'
            '              f\'vs {row["high_book"]} @ {row["high_line"]} → {row["middle_points"]} pt middle\')\n'
            "else:\n"
            "    print('  No middles detected with current data.')\n"
            "    print('  This can happen when all books offer the same line.')"
        )
    )

    # ── Cell 22: Section 10 — Backtest a middling strategy ────────────────
    cells.append(
        nbf.v4.new_markdown_cell(
            "---\n"
            "\n"
            "## Section 10: Backtest a Middling Strategy\n"
            "\n"
            "In a real backtest, you'd use historical odds data to see how often "
            "middles hit and what the profit would be. Since we're working with "
            "a snapshot of current odds, we'll simulate a simple backtest using "
            "the normal distribution model we built earlier."
        )
    )

    # ── Cell 23: Simulated backtest ─────────────────────────────────────
    cells.append(
        nbf.v4.new_code_cell(
            "# Cell 23: Simulated backtest of middling strategy\n"
            "#\n"
            "# We simulate 10,000 games with normal distribution margins\n"
            "# and check how often our detected middles would hit.\n"
            "\n"
            "np.random.seed(42)\n"
            "N_SIMULATIONS = 10_000\n"
            "\n"
            "def simulate_middle_outcome(\n"
            "    low_line: float,\n"
            "    high_line: float,\n"
            "    market: str = 'spread',\n"
            "    sigma: float = 13.5,\n"
            "    n_sim: int = N_SIMULATIONS,\n"
            ") -> dict[str, float | int]:\n"
            '    """Simulate game outcomes and check middle hit rate.\n'
            "\n"
            "    Args:\n"
            "        low_line: The lower line value.\n"
            "        high_line: The higher line value.\n"
            "        market: 'spread' or 'total'.\n"
            "        sigma: Std dev for outcome distribution.\n"
            "        n_sim: Number of simulations.\n"
            "\n"
            "    Returns:\n"
            "        Dict with hit rate, push rate, and miss rate.\n"
            '    """\n'
            "    # Generate random margins/totals\n"
            "    outcomes = np.random.normal(0, sigma, n_sim)\n"
            "    \n"
            "    abs_low = abs(low_line)\n"
            "    abs_high = abs(high_line)\n"
            "    \n"
            "    # For spreads: margin between abs_low and abs_high\n"
            "    if market == 'spread':\n"
            "        hits = np.sum((outcomes > abs_low) & (outcomes < abs_high))\n"
            "        pushes = np.sum((outcomes == abs_low) | (outcomes == abs_high))\n"
            "    else:\n"
            "        # For totals: value between low and high\n"
            "        midpoint = (abs_low + abs_high) / 2\n"
            "        outcomes = np.random.normal(midpoint, sigma, n_sim)\n"
            "        hits = np.sum((outcomes > low_line) & (outcomes < high_line))\n"
            "        pushes = np.sum((outcomes == low_line) | (outcomes == high_line))\n"
            "    \n"
            "    misses = n_sim - hits - pushes\n"
            "    \n"
            "    return {\n"
            "        'hits': int(hits),\n"
            "        'pushes': int(pushes),\n"
            "        'misses': int(misses),\n"
            "        'hit_rate': hits / n_sim,\n"
            "        'push_rate': pushes / n_sim,\n"
            "        'miss_rate': misses / n_sim,\n"
            "    }\n"
            "\n"
            "\n"
            "# Run backtest on detected spread middles\n"
            "if not spread_middles.empty:\n"
            "    print(f'Simulated Backtest ({N_SIMULATIONS:,} simulations per middle):')\n"
            "    print()\n"
            "    for _, row in spread_middles.iterrows():\n"
            "        result = simulate_middle_outcome(row['low_line'], row['high_line'], market='spread')\n"
            '        print(f\'  {row["game_id"]}: {row["low_line"]} vs {row["high_line"]}\')\n'
            '        print(f\'    Hits: {result["hits"]} ({result["hit_rate"]:.2%})\')\n'
            '        print(f\'    Pushes: {result["pushes"]} ({result["push_rate"]:.2%})\')\n'
            '        print(f\'    Misses: {result["misses"]} ({result["miss_rate"]:.2%})\')\n'
            "        print()\n"
            "else:\n"
            "    # Demo with synthetic data\n"
            "    print(f'Simulated Backtest Demo ({N_SIMULATIONS:,} simulations):')\n"
            "    demo = simulate_middle_outcome(-3.0, -7.0, market='spread')\n"
            "    print(f'  KC -3 vs KC -7 (4pt middle):')\n"
            '    print(f\'    Hits: {demo["hits"]} ({demo["hit_rate"]:.2%})\')\n'
            '    print(f\'    Pushes: {demo["pushes"]} ({demo["push_rate"]:.2%})\')\n'
            '    print(f\'    Misses: {demo["misses"]} ({demo["miss_rate"]:.2%})\')'
        )
    )

    # ── Cell 24: Section 11 — Risk considerations ─────────────────────────
    cells.append(
        nbf.v4.new_markdown_cell(
            "---\n"
            "\n"
            "## Section 11: Risk Considerations\n"
            "\n"
            "Middling is one of the lowest-risk betting strategies, but it's not risk-free:\n"
            "\n"
            "### Key Risks\n"
            "\n"
            "1. **Lines move quickly** — Middle opportunities are fleeting. Books adjust "
            "lines within minutes of sharp action.\n"
            "\n"
            "2. **Book limits** — Sportsbooks limit bet sizes, especially for sharp bettors. "
            "You may not be able to bet enough to make the middle profitable.\n"
            "\n"
            "3. **Middles are rare** — The typical NFL weekend might have 0-2 viable middles "
            "across all books. They require significant line disagreement.\n"
            "\n"
            "4. **Vig on both legs** — Even with a middle, you're paying vig on both bets. "
            "The middle hit rate needs to exceed a threshold to overcome the double vig.\n"
            "\n"
            "5. **Correlation risk** — Both legs are on the same game. If the game is "
            "canceled or postponed, both bets may be voided.\n"
            "\n"
            "### Minimum Hit Rate\n"
            "\n"
            "With -110 odds on both sides:\n"
            "- Each bet risks $1.10 to win $1.00\n"
            "- If one wins and one loses: net loss = $0.10 (the vig)\n"
            "- If both win: net win = $2.00 - $2.20 = wait, that's wrong.\n"
            "- Actually: bet $1.10 on each → total risk $2.20\n"
            "  - Both win: win $2.00 (profit on both legs)\n"
            "  - One wins, one loses: net = $1.00 - $1.10 = -$0.10\n"
            "\n"
            "The break-even hit rate is approximately: `vig / (profit_on_middle + vig)`"
        )
    )

    # ── Cell 25: Break-even analysis ─────────────────────────────────────
    cells.append(
        nbf.v4.new_code_cell(
            "# Cell 25: Break-even hit rate analysis for middles\n"
            "#\n"
            "# With -110 odds on both legs:\n"
            "#   Stake on each leg: 1.10 units (to win 1.00)\n"
            "#   Total risk: 2.20 units\n"
            "#   Middle hit: win both → profit = 2.00 - 2.20 = -0.20? No.\n"
            "#   Middle hit: collect 2.10 (1.00 profit + 1.10 stake back on each)\n"
            "#     Wait, let's be more careful:\n"
            "#     Bet 1.10 on leg1 at -110 → if wins, collect 2.10 (1.10 stake + 1.00 profit)\n"
            "#     Bet 1.10 on leg2 at -110 → if wins, collect 2.10 (1.10 stake + 1.00 profit)\n"
            "#     Both win: collect 2.10 + 2.10 = 4.20, risked 2.20 → profit = 2.00\n"
            "#     One wins: collect 2.10 + lose 1.10 = net 1.00, risked 2.20 → loss = 0.10\n"
            "#     Both lose: lose 2.20\n"
            "\n"
            "def middle_breakeven(\n"
            "    odds_leg1: int = -110,\n"
            "    odds_leg2: int = -110,\n"
            ") -> dict[str, float]:\n"
            '    """Calculate break-even hit rate for a middle with given odds.\n'
            "\n"
            "    Args:\n"
            "        odds_leg1: American odds for leg 1.\n"
            "        odds_leg2: American odds for leg 2.\n"
            "\n"
            "    Returns:\n"
            "        Dict with break-even analysis.\n"
            '    """\n'
            "    dec1 = american_to_decimal(odds_leg1)\n"
            "    dec2 = american_to_decimal(odds_leg2)\n"
            "    \n"
            "    # At -110, you risk 1.10 to win 1.00 (stake of 1.10, payout of 2.10)\n"
            "    # Simplify: assume 1 unit stake on each\n"
            "    stake1 = 1.0 / (dec1 - 1)  # Stake needed for $1 profit\n"
            "    stake2 = 1.0 / (dec2 - 1)\n"
            "    \n"
            "    # Total risk\n"
            "    total_risk = 1.0 + 1.0  # 1 unit on each\n"
            "    \n"
            "    # Both win: profit = (dec1 - 1) + (dec2 - 1)\n"
            "    profit_both = (dec1 - 1) + (dec2 - 1)\n"
            "    \n"
            "    # One wins: profit = (1 winning leg payout) - (1 losing leg stake)\n"
            "    profit_one = (dec1 - 1) - 1.0  # Leg1 wins, leg2 loses\n"
            "    \n"
            "    # Break-even: p_hit * profit_both + (1 - p_hit) * profit_one = 0\n"
            "    # p_hit * profit_both + profit_one - p_hit * profit_one = 0\n"
            "    # p_hit * (profit_both - profit_one) = -profit_one\n"
            "    # p_hit = -profit_one / (profit_both - profit_one)\n"
            "    \n"
            "    if abs(profit_both - profit_one) < 1e-10:\n"
            "        breakeven_rate = float('inf')\n"
            "    else:\n"
            "        breakeven_rate = -profit_one / (profit_both - profit_one)\n"
            "    \n"
            "    return {\n"
            "        'odds_leg1': odds_leg1,\n"
            "        'odds_leg2': odds_leg2,\n"
            "        'profit_both_win': profit_both,\n"
            "        'profit_one_win': profit_one,\n"
            "        'total_risk': total_risk,\n"
            "        'breakeven_hit_rate': breakeven_rate,\n"
            "    }\n"
            "\n"
            "# Standard -110 / -110 middle\n"
            "result = middle_breakeven(-110, -110)\n"
            "print('Break-even analysis for -110 / -110 middle:')\n"
            "for key, val in result.items():\n"
            "    if isinstance(val, float):\n"
            "        print(f'  {key}: {val:.4f}')\n"
            "    else:\n"
            "        print(f'  {key}: {val}')\n"
            "print(f'\\nBreak-even hit rate: {result[\"breakeven_hit_rate\"]:.2%}')\n"
            "print('→ You need the middle to hit more than this rate to be profitable.')\n"
            "\n"
            "# Different odds scenarios\n"
            "print('\\nBreak-even hit rates for different odds:')\n"
            "scenarios = [(-110, -110), (-105, -110), (-110, -105), (-105, -105), (-115, -110)]\n"
            "for o1, o2 in scenarios:\n"
            "    r = middle_breakeven(o1, o2)\n"
            "    print(f'  {o1:+d} / {o2:+d}: breakeven = {r[\"breakeven_hit_rate\"]:.2%}, '\n"
            '          f\'both-win profit = {r["profit_both_win"]:.4f}, one-win profit = {r["profit_one_win"]:.4f}\')'
        )
    )

    # ── Cell 26: Section 12 — Multi-book comparison ───────────────────────
    cells.append(
        nbf.v4.new_markdown_cell(
            "---\n"
            "\n"
            "## Section 12: Multi-Book Comparison\n"
            "\n"
            "Not all books offer the same lines. The best middling opportunities come "
            "from books that consistently have different lines. Let's see which books "
            "in our data offer the most favorable middles."
        )
    )

    # ── Cell 27: Book comparison ─────────────────────────────────────────
    cells.append(
        nbf.v4.new_code_cell(
            "# Cell 27: Compare books for middling opportunities\n"
            "#\n"
            "# For each detected middle, show which books are involved.\n"
            "\n"
            "if not all_middles.empty:\n"
            "    # Count middles per book pair\n"
            "    book_pairs = []\n"
            "    for _, row in all_middles.iterrows():\n"
            "        book_pairs.append((row['low_book'], row['high_book']))\n"
            "    \n"
            "    from collections import Counter\n"
            "    pair_counts = Counter(book_pairs)\n"
            "    \n"
            "    print('Book pair frequency in detected middles:')\n"
            "    for (low_b, high_b), count in pair_counts.most_common():\n"
            "        print(f'  {low_b} ↔ {high_b}: {count} middle(s)')\n"
            "else:\n"
            "    print('No middles detected. Book comparison requires detected middles.')\n"
            "\n"
            "# Show spread line comparison per event\n"
            "print('\\nSpread lines by event and book:')\n"
            "for event_id, group in spread_df.groupby('event_id'):\n"
            "    print(f'\\n  {event_id}:')\n"
            "    for _, row in group.iterrows():\n"
            '        print(f\'    {row["book"]:<15} {row["selection"]:<15} line={row["line"]:<+6.1f} odds={row["price"]}\')\n'
            "    \n"
            "    # Check for middle potential\n"
            "    lines = group['line'].values\n"
            "    if len(lines) >= 2:\n"
            "        spread_range = max(lines) - min(lines)\n"
            "        print(f'    → Spread range: {spread_range:.1f} points')\n"
            "        if spread_range >= 1.0:\n"
            "            print(f'    → ⚠️  Middle potential! {spread_range:.1f} point spread range')"
        )
    )

    # ── Cell 28: Exercises ───────────────────────────────────────────────
    cells.append(
        nbf.v4.new_markdown_cell(
            "---\n"
            "\n"
            "## Exercises\n"
            "\n"
            "Try these on your own:\n"
            "\n"
            "1. **Find a current spread middle** — Connect to the live TimescaleDB "
            "and query for recent spread odds. Use `detect_spread_middles()` to find "
            "any current middle opportunities. What's the widest middle you can find?\n"
            "\n"
            "2. **Find a current total middle** — Query for total odds and run "
            "`detect_total_middles()`. Compare the frequency of total middles vs. "
            "spread middles. Which is more common?\n"
            "\n"
            "3. **Compute Kelly for both legs** — For a detected middle, calculate "
            "the Kelly-optimal bet size for each leg using `KellyCalculator`. How does "
            "the total exposure compare to single-bet Kelly sizing?\n"
            "\n"
            "4. **Varying sigma** — In the EV calculation, we assumed σ=13.5 for NFL "
            "spreads. Try different values (e.g., 10, 12, 15) and see how the middle "
            "probability changes. Which sigma is most conservative?\n"
            "\n"
            "5. **Middle portfolio** — If you found 3 independent middles in a single "
            "week, each with a 10% hit rate and 2:1 payout, what would your expected "
            "weekly profit be? How does correlation between middles affect this?"
        )
    )

    # ── Cell 29: Summary ────────────────────────────────────────────────
    cells.append(
        nbf.v4.new_markdown_cell(
            "---\n"
            "\n"
            "## Summary\n"
            "\n"
            "In this lab you learned:\n"
            "\n"
            "- What a middle is and why it's profitable (both sides can win)\n"
            "- How to detect spread and total middles across multiple books\n"
            "- How to use `detect_spread_middles()` and `detect_total_middles()` from "
            "`quantitative_sports.core.betting.strategies.middling`\n"
            "- How to calculate the probability of hitting a middle\n"
            "- How to calculate EV for a middle opportunity\n"
            "- How to size both legs using Kelly Criterion\n"
            "- The risks and limitations of middling (rarity, vig, line movement)\n"
            "- How to compute break-even hit rates for middle bets\n"
            "\n"
            "### Key API Reference\n"
            "\n"
            "| Class/Function | Module | Purpose |\n"
            "|---|---|---|\n"
            "| `detect_spread_middles()` | `quantitative_sports.core.betting.strategies.middling` | Find spread middles |\n"
            "| `detect_total_middles()` | `quantitative_sports.core.betting.strategies.middling` | Find total middles |\n"
            "| `detect_middles()` | `quantitative_sports.core.betting.strategies.middling` | Combined detection |\n"
            "| `MiddleOpportunity` | `quantitative_sports.core.betting.strategies.middling` | Data class for middles |\n"
            "| `KellyCalculator` | `quantitative_sports.core.betting.kelly` | Kelly sizing |\n"
            "| `BankrollManager` | `quantitative_sports.core.betting.kelly` | Position-limited sizing |\n"
            "| `american_to_decimal()` | `quantitative_sports.core.betting.engine` | Odds conversion |\n"
            "\n"
            "### Key Concepts\n"
            "\n"
            "| Concept | Description |\n"
            "|---|---|\n"
            "| **Middle** | Betting both sides of a line across different books |\n"
            "| **Middle points** | The gap between the two lines (wider = better) |\n"
            "| **Hit rate** | Probability that the final value lands in the middle |\n"
            "| **Break-even rate** | Minimum hit rate to overcome double vig |\n"
            "| **Quarter-Kelly** | Conservative sizing for middle legs |\n"
            "\n"
            "### Next Steps\n"
            "\n"
            "Continue to **Lab 05: Backtesting** to learn how to backtest betting "
            "strategies against historical data.\n"
            "\n"
            "---\n"
            "\n"
            "*Don't forget to close the pool:*\n"
            "```python\n"
            "await pool.close()\n"
            "```"
        )
    )

    # ── Cell 30: Cleanup ────────────────────────────────────────────────
    cells.append(
        nbf.v4.new_code_cell(
            "# Cell 30: Close the connection pool\n"
            "if db_available:\n"
            "    await pool.close()\n"
            "    print('Connection pool closed. Lab 04 complete!')\n"
            "else:\n"
            "    print('Lab 04 complete! (used synthetic data, no DB connection to close)')"
        )
    )

    nb.cells = cells
    return nb


def main() -> None:
    """Build and write the notebook."""
    nb = build()
    nbf.write(nb, OUTPUT_PATH)
    print(f"Written {OUTPUT_PATH} with {len(nb.cells)} cells")


if __name__ == "__main__":
    main()
