"""Build script for Lab 08: Live Workflow — Start to Finish.

Generates ``08_live_workflow.ipynb`` using nbformat. Run this script to
produce the notebook, then open it in Jupyter to execute the cells.

Usage::

    cd /home/jcharles/Projects/Infrastructure/sportsquant
    uv run python labs/build_lab_08.py
"""

from __future__ import annotations

import nbformat as nbf

OUTPUT_PATH = "labs/08_live_workflow.ipynb"


def build() -> nbf.NotebookNode:
    """Construct the Lab 08 notebook programmatically."""
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
            "# Lab 08: Live Workflow — Start to Finish\n"
            "\n"
            "This lab walks you through a **complete live betting workflow**: from poller "
            "data ingestion, through +EV detection, bet placement, result logging, and "
            "closing line value (CLV) measurement. By the end you will:\n"
            "\n"
            "- Verify the poller is running and collecting data\n"
            "- Watch live odds flow into TimescaleDB\n"
            "- Find positive expected-value (+EV) opportunities (Lab 03 concepts)\n"
            "- Check for middling opportunities (Lab 04 concepts)\n"
            "- Simulate bet placement and log to memory\n"
            "- Wait for game results\n"
            "- Log the outcome and calculate profit/loss\n"
            "- Measure Closing Line Value (CLV)\n"
            "- Update your model and track bankroll over time\n"
            "\n"
            "---"
        )
    )

    # ── Cell 2: Prerequisites ───────────────────────────────────────────
    cells.append(
        nbf.v4.new_markdown_cell(
            "## Prerequisites\n"
            "\n"
            "- **Labs 01-07 completed** — you understand the data pipeline, EV, middling, "
            "and rating systems\n"
            "- **Poller running** — the SportsQuant poller should be actively collecting odds "
            "(or use synthetic data fallback)\n"
            "- **Betting fundamentals** — American odds, expected value, Kelly Criterion\n"
            "\n"
            "### The Live Workflow Loop\n"
            "\n"
            "```\n"
            "  ┌─────────┐     ┌──────────┐     ┌─────────┐     ┌──────────┐\n"
            "  │  Poll   │────▶│  Detect  │────▶│  Bet    │────▶│  Log    │\n"
            "  │  Data   │     │  +EV     │     │  Place  │     │  Result │\n"
            "  └─────────┘     └──────────┘     └─────────┘     └──────────┘\n"
            "       ▲                                                │\n"
            "       │                                                ▼\n"
            "       │           ┌──────────┐     ┌──────────┐     ┌──────────┐\n"
            "       └───────────│  Update  │◀────│  Measure │◀────│  Track  │\n"
            "                   │  Model   │     │  CLV    │     │  P/L    │\n"
            "                   └──────────┘     └──────────┘     └──────────┘\n"
            "```"
        )
    )

    # ── Cell 3: Section 1 — Setup ──────────────────────────────────────
    cells.append(
        nbf.v4.new_markdown_cell(
            "---\n"
            "\n"
            "## Section 1: Setup — Imports and Configuration\n"
            "\n"
            "We import the core SportsQuant modules for database access, odds conversion, "
            "Kelly sizing, and the poller status check. If the database is not available, "
            "we fall back to synthetic data."
        )
    )

    # ── Cell 4: Imports ──────────────────────────────────────────────────
    cells.append(
        nbf.v4.new_code_cell(
            '# Cell 4: Core imports\n'
            'import asyncio\n'
            'import json\n'
            'from dataclasses import dataclass, field\n'
            'from datetime import datetime, timedelta, timezone\n'
            'from typing import Optional\n'
            '\n'
            'import numpy as np\n'
            'import pandas as pd\n'
            'import matplotlib.pyplot as plt\n'
            '\n'
            'from sportsquant.core.betting.odds import Odds\n'
            'from sportsquant.core.betting.kelly import (\n'
            '    KellyCalculator,\n'
            '    KellyCalculatorConfig,\n'
            '    EdgeCalculator,\n'
            '    EdgeCalculatorConfig,\n'
            '    BankrollManager,\n'
            '    BankrollManagerConfig,\n'
            ')\n'
            'from sportsquant.core.betting.engine import (\n'
            '    american_to_decimal,\n'
            '    calculate_ev,\n'
            '    expected_value,\n'
            '    kelly_fraction,\n'
            ')\n'
            'from sportsquant.infra.db.connection import DBConfig, DatabasePool, get_pool, health_check, reset_pool\n'
            'from sportsquant.infra.db.queries import get_poller_health_summary, get_table_stats\n'
            'from sportsquant.util.time_utils import utc_now_iso\n'
            '\n'
            '# Enable nested event loops in Jupyter\n'
            'import nest_asyncio\n'
            'nest_asyncio.apply()\n'
            '\n'
            'print("Imports loaded successfully.")'
        )
    )

    # ── Cell 5: DB connection and synthetic fallback ──────────────────────
    cells.append(
        nbf.v4.new_code_cell(
            '# Cell 5: Connect to database (with fallback to synthetic data)\n'
            '\n'
            'DB_AVAILABLE = False\n'
            'pool = None\n'
            '\n'
            'try:\n'
            '    config = DBConfig.from_env()\n'
            '    pool = await get_pool(config)\n'
            '    health = await health_check(pool)\n'
            '    if health["status"] == "healthy":\n'
            '        DB_AVAILABLE = True\n'
            '        print(f"Database connected: {health[\'status\']}")\n'
            '        print(f"Latency: {health[\'latency_ms\']} ms")\n'
            '    else:\n'
            '        print(f"Database unhealthy: {health}")\n'
            '        await pool.close()\n'
            '        pool = None\n'
            'except Exception as e:\n'
            '    print(f"Database not available: {e}")\n'
            '    print("Falling back to synthetic data for this lab.")\n'
            '\n'
            'if not DB_AVAILABLE:\n'
            '    print("\\n⚠️  Running in SYNTHETIC MODE — all data is generated locally.")\n'
            '    print("   To use live data, start the poller and connect to TimescaleDB.")'
        )
    )

    # ── Cell 6: Section 2 — Verify Poller ──────────────────────────────
    cells.append(
        nbf.v4.new_markdown_cell(
            "---\n"
            "\n"
            "## Section 2: Verify Poller Is Running\n"
            "\n"
            "The poller continuously fetches odds from The Odds API and ESPN injuries. "
            "We check `poller_health` to verify it's been running. If the database isn't "
            "available, we'll use synthetic data throughout."
        )
    )

    # ── Cell 7: Poller health check ──────────────────────────────────────
    cells.append(
        nbf.v4.new_code_cell(
            '# Cell 7: Check poller health\n'
            '\n'
            'if DB_AVAILABLE and pool is not None:\n'
            '    health_summary = await get_poller_health_summary(pool)\n'
            '    if health_summary:\n'
            '        print("Poller Health Status:")\n'
            '        print(f"{\'Poller\':<30} {\'Status\':<12} {\'Failures\':<10} {\'Last Run\':<20}")\n'
            '        print(f"{\'-\'*30} {\'-\'*12} {\'-\'*10} {\'-\'*20}")\n'
            '        for entry in health_summary:\n'
            '            print(f"{entry[\'poller_name\']:<30} {entry[\'status\']:<12} {entry[\'consecutive_failures\']:<10} {str(entry.get(\'last_run_status\', \'N/A\')):<20}")\n'
            '    else:\n'
            '        print("No poller health entries. The poller hasn\'t run yet.")\n'
            'else:\n'
            '    print("Poller health check skipped (no database connection).")\n'
            '    print("Using synthetic data instead.")'
        )
    )

    # ── Cell 8: Section 3 — Watch Data Flow ──────────────────────────────
    cells.append(
        nbf.v4.new_markdown_cell(
            "---\n"
            "\n"
            "## Section 3: Watch Data Flow — Last Hour of Odds\n"
            "\n"
            "If the poller is running, we can query the last hour of odds data. "
            "In synthetic mode, we generate a representative sample."
        )
    )

    # ── Cell 9: Query last hour of odds ──────────────────────────────────
    cells.append(
        nbf.v4.new_code_cell(
            '# Cell 9: Query last hour of odds (or generate synthetic)\n'
            '\n'
            'if DB_AVAILABLE and pool is not None:\n'
            '    # Query real data from the last hour\n'
            '    one_hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()\n'
            '    odds_data = await pool.fetch(\n'
            '        "SELECT event_id, book, market, selection, price, line, ts "\n'
            '        "FROM odds_ticks "\n'
            '        "WHERE ts >= $1 "\n'
            '        "ORDER BY ts DESC LIMIT 100",\n'
            '        one_hour_ago,\n'
            '    )\n'
            '    if odds_data:\n'
            '        odds_df = pd.DataFrame([dict(r) for r in odds_data])\n'
            '        print(f"Found {len(odds_df)} odds ticks in the last hour")\n'
            '        print(odds_df.head())\n'
            '    else:\n'
            '        print("No odds data in the last hour. Generating synthetic data.")\n'
            '        DB_AVAILABLE = False  # Fall back to synthetic\n'
            'else:\n'
            '    print("Generating synthetic odds data...")\n'
            '\n'
            'if not DB_AVAILABLE:\n'
            '    # Synthetic odds data\n'
            '    np.random.seed(42)\n'
            '    books = ["fanduel", "draftkings", "betmgm", "pinnacle", "pointsbet"]\n'
            '    games = [\n'
            '        ("KC vs BUF", "KC", "BUF"),\n'
            '        ("SF vs PHI", "SF", "PHI"),\n'
            '        ("DET vs DAL", "DET", "DAL"),\n'
            '    ]\n'
            '    markets = ["h2h", "spreads", "totals"]\n'
            '    records = []\n'
            '    for game_name, home, away in games:\n'
            '        for book in books:\n'
            '            # Slightly different prices at each book\n'
            '            home_spread = -3.0 + np.random.uniform(-1.0, 1.0)\n'
            '            home_price = -110 + np.random.randint(-10, 15)\n'
            '            away_price = -110 + np.random.randint(-10, 15)\n'
            '            records.append({\n'
            '                "event_id": game_name,\n'
            '                "book": book,\n'
            '                "market": "h2h",\n'
            '                "selection": home,\n'
            '                "price": home_price,\n'
            '                "line": None,\n'
            '                "ts": utc_now_iso(),\n'
            '            })\n'
            '            records.append({\n'
            '                "event_id": game_name,\n'
            '                "book": book,\n'
            '                "market": "h2h",\n'
            '                "selection": away,\n'
            '                "price": away_price,\n'
            '                "line": None,\n'
            '                "ts": utc_now_iso(),\n'
            '            })\n'
            '            # Spread lines\n'
            '            records.append({\n'
            '                "event_id": game_name,\n'
            '                "book": book,\n'
            '                "market": "spreads",\n'
            '                "selection": home,\n'
            '                "price": -110 + np.random.randint(-5, 10),\n'
            '                "line": home_spread,\n'
            '                "ts": utc_now_iso(),\n'
            '            })\n'
            '            records.append({\n'
            '                "event_id": game_name,\n'
            '                "book": book,\n'
            '                "market": "spreads",\n'
            '                "selection": away,\n'
            '                "price": -110 + np.random.randint(-5, 10),\n'
            '                "line": -home_spread,\n'
            '                "ts": utc_now_iso(),\n'
            '            })\n'
            '\n'
            '    odds_df = pd.DataFrame(records)\n'
            '    print(f"Generated {len(odds_df)} synthetic odds ticks")\n'
            '    print(odds_df.head(10).to_string(index=False))'
        )
    )

    # ── Cell 10: Section 4 — Find +EV ──────────────────────────────────
    cells.append(
        nbf.v4.new_markdown_cell(
            "---\n"
            "\n"
            "## Section 4: Find +EV Opportunities\n"
            "\n"
            "From Lab 03, we know that a **+EV bet** is one where our estimated true "
            "probability exceeds the book's implied probability. We:\n"
            "\n"
            "1. Convert American odds to implied probability\n"
            "2. Calculate the vig (overround)\n"
            "3. Remove the vig to get true probability\n"
            "4. Compute EV = true_prob × (decimal_odds - 1) - (1 - true_prob)\n"
            "5. Flag any bet where EV > 0"
        )
    )

    # ── Cell 11: Find +EV bets ──────────────────────────────────────────
    cells.append(
        nbf.v4.new_code_cell(
            '# Cell 11: Find +EV opportunities from odds data\n'
            '\n'
            'def find_ev_opportunities(odds_df: pd.DataFrame, min_ev: float = 0.02) -> pd.DataFrame:\n'
            '    """Find positive EV bets across all books for each market.\n'
            '\n'
            '    Args:\n'
            '        odds_df: DataFrame with columns event_id, book, market, selection, price, line.\n'
            '        min_ev: Minimum EV threshold to flag.\n'
            '\n'
            '    Returns:\n'
            '        DataFrame with EV opportunities.\n'
            '    """\n'
            '    opportunities = []\n'
            '\n'
            '    for (event_id, market), group in odds_df.groupby(["event_id", "market"]):\n'
            '        if market == "h2h":\n'
            '            # For each book, compute implied probability\n'
            '            for book in group["book"].unique():\n'
            '                book_rows = group[group["book"] == book]\n'
            '                if len(book_rows) < 2:\n'
            '                    continue\n'
            '                selections = dict(zip(book_rows["selection"], book_rows["price"]))\n'
            '                if len(selections) < 2:\n'
            '                    continue\n'
            '\n'
            '                # Calculate implied probs\n'
            '                probs = {}\n'
            '                for sel, price in selections.items():\n'
            '                    try:\n'
            '                        odds_obj = Odds(american=price)\n'
            '                        probs[sel] = odds_obj.implied_probability\n'
            '                    except (ValueError, ZeroDivisionError):\n'
            '                        continue\n'
            '\n'
            '                if len(probs) < 2:\n'
            '                    continue\n'
            '\n'
            '                overround = sum(probs.values())\n'
            '                if overround <= 0:\n'
            '                    continue\n'
            '\n'
            '                # Vig-adjusted probabilities\n'
            '                true_probs = {sel: p / overround for sel, p in probs.items()}\n'
            '\n'
            '                # Now compare best odds across books\n'
            '                for sel in true_probs:\n'
            '                    best_price = None\n'
            '                    best_decimal = 0\n'
            '                    for _, row in group[(group["selection"] == sel)].iterrows():\n'
            '                        try:\n'
            '                            odds_obj = Odds(american=row["price"])\n'
            '                            if odds_obj.decimal > best_decimal:\n'
            '                                best_decimal = odds_obj.decimal\n'
            '                                best_price = row["price"]\n'
            '                                best_book = row["book"]\n'
            '                        except (ValueError, ZeroDivisionError):\n'
            '                            continue\n'
            '\n'
            '                    if best_decimal > 0:\n'
            '                        ev = true_probs[sel] * (best_decimal - 1) - (1 - true_probs[sel])\n'
            '                        if ev >= min_ev:\n'
            '                            opportunities.append({\n'
            '                                "event": event_id,\n'
            '                                "market": market,\n'
            '                                "selection": sel,\n'
            '                                "book": best_book,\n'
            '                                "price": best_price,\n'
            '                                "true_prob": true_probs[sel],\n'
            '                                "implied_prob": probs.get(sel, 0),\n'
            '                                "decimal_odds": best_decimal,\n'
            '                                "ev": ev,\n'
            '                                "edge": true_probs[sel] - probs.get(sel, 0),\n'
            '                            })\n'
            '\n'
            '    return pd.DataFrame(opportunities) if opportunities else pd.DataFrame()\n'
            '\n'
            'ev_df = find_ev_opportunities(odds_df, min_ev=0.01)\n'
            '\n'
            'if not ev_df.empty:\n'
            '    print(f"Found {len(ev_df)} +EV opportunities:")\n'
            '    print(ev_df.to_string(index=False))\n'
            'else:\n'
            '    print("No +EV opportunities found with current data.")\n'
            '    print("This is normal — edges are rare and short-lived.")'
        )
    )

    # ── Cell 12: Section 5 — Check for Middles ──────────────────────────
    cells.append(
        nbf.v4.new_markdown_cell(
            "---\n"
            "\n"
            "## Section 5: Check for Middling Opportunities\n"
            "\n"
            "From Lab 04, a **middle** exists when two books offer different enough lines "
            "that you can bet both sides and potentially win both. For spreads:\n"
            "\n"
            "- Book A: KC -3\n"
            "- Book B: KC -7\n"
            "- If KC wins by 4, 5, or 6 → both bets win!\n"
            "\n"
            "The **middle width** is the gap between the lines."
        )
    )

    # ── Cell 13: Check for middles ──────────────────────────────────────
    cells.append(
        nbf.v4.new_code_cell(
            '# Cell 13: Check for middling opportunities\n'
            '\n'
            'def find_middles(odds_df: pd.DataFrame, min_width: float = 1.0) -> pd.DataFrame:\n'
            '    """Find spread middling opportunities across books.\n'
            '\n'
            '    Args:\n'
            '        odds_df: DataFrame with odds data.\n'
            '        min_width: Minimum middle width to flag.\n'
            '\n'
            '    Returns:\n'
            '        DataFrame with middle opportunities.\n'
            '    """\n'
            '    spread_data = odds_df[odds_df["market"] == "spreads"].copy()\n'
            '    if spread_data.empty:\n'
            '        return pd.DataFrame()\n'
            '\n'
            '    middles = []\n'
            '\n'
            '    for event_id in spread_data["event_id"].unique():\n'
            '        event_spreads = spread_data[spread_data["event_id"] == event_id]\n'
            '        # Find the best line for the home team and away team\n'
            '        home_selections = event_spreads[event_spreads["line"] > 0]  # Positive spread = away\n'
            '        away_selections = event_spreads[event_spreads["line"] < 0]  # Negative spread = home\n'
            '\n'
            '        if len(home_selections) == 0 or len(away_selections) == 0:\n'
            '            continue\n'
            '\n'
            '        # Find the most and least favorable home spreads\n'
            '        home_lines = away_selections.groupby("book")["line"].first()\n'
            '        if len(home_lines) < 2:\n'
            '            continue\n'
            '\n'
            '        most_fav = home_lines.max()  # Most points for the underdog\n'
            '        least_fav = home_lines.min()  # Fewest points for the underdog\n'
            '\n'
            '        width = most_fav - least_fav\n'
            '\n'
            '        if width >= min_width:\n'
            '            middles.append({\n'
            '                "event": event_id,\n'
            '                "best_home_line": least_fav,\n'
            '                "worst_home_line": most_fav,\n'
            '                "middle_width": width,\n'
            '                "books": ", ".join(home_lines.index.tolist()[:3]),\n'
            '            })\n'
            '\n'
            '    return pd.DataFrame(middles) if middles else pd.DataFrame()\n'
            '\n'
            'middles_df = find_middles(odds_df, min_width=0.5)\n'
            '\n'
            'if not middles_df.empty:\n'
            '    print(f"Found {len(middles_df)} middling opportunities:")\n'
            '    print(middles_df.to_string(index=False))\n'
            'else:\n'
            '    print("No middling opportunities found.")\n'
            '    print("Middles are rare and require multiple books with different lines.")'
        )
    )

    # ── Cell 14: Section 6 — Place a Bet ──────────────────────────────────
    cells.append(
        nbf.v4.new_markdown_cell(
            "---\n"
            "\n"
            "## Section 6: Place a Bet (Simulated)\n"
            "\n"
            "In a real workflow, you'd place bets via a sportsbook API. Here we simulate "
            "the process and log it to a local bet tracker. We use the Kelly Criterion to "
            "size our bet appropriately."
        )
    )

    # ── Cell 15: Bet placement simulation ──────────────────────────────────
    cells.append(
        nbf.v4.new_code_cell(
            '# Cell 15: Simulated bet placement with Kelly sizing\n'
            '\n'
            '@dataclass\n'
            'class BetRecord:\n'
            '    """Record of a placed bet."""\n'
            '    event: str\n'
            '    market: str\n'
            '    selection: str\n'
            '    book: str\n'
            '    price: int\n'
            '    decimal_odds: float\n'
            '    true_prob: float\n'
            '    ev: float\n'
            '    kelly_fraction: float\n'
            '    bet_amount: float\n'
            '    bankroll_before: float\n'
            '    timestamp: str\n'
            '    result: Optional[str] = None  # "win", "loss", "push", None=pending\n'
            '    profit: Optional[float] = None\n'
            '\n'
            'class BetTracker:\n'
            '    """Track all bets and bankroll."""\n'
            '\n'
            '    def __init__(self, initial_bankroll: float = 10000.0):\n'
            '        self.bankroll = initial_bankroll\n'
            '        self.initial_bankroll = initial_bankroll\n'
            '        self.bets: list[BetRecord] = []\n'
            '\n'
            '    def place_bet(\n'
            '        self,\n'
            '        event: str,\n'
            '        market: str,\n'
            '        selection: str,\n'
            '        book: str,\n'
            '        price: int,\n'
            '        decimal_odds: float,\n'
            '        true_prob: float,\n'
            '        ev: float,\n'
            '        kelly_fraction: float = 0.25,  # Quarter Kelly by default\n'
            '    ) -> BetRecord:\n'
            '        """Place a bet with Kelly sizing."""\n'
            '        # Quarter Kelly for safety\n'
            '        fraction = min(kelly_fraction, 0.10)  # Cap at 10% of bankroll\n'
            '        bet_amount = self.bankroll * fraction\n'
            '\n'
            '        bet = BetRecord(\n'
            '            event=event,\n'
            '            market=market,\n'
            '            selection=selection,\n'
            '            book=book,\n'
            '            price=price,\n'
            '            decimal_odds=decimal_odds,\n'
            '            true_prob=true_prob,\n'
            '            ev=ev,\n'
            '            kelly_fraction=fraction,\n'
            '            bet_amount=round(bet_amount, 2),\n'
            '            bankroll_before=self.bankroll,\n'
            '            timestamp=utc_now_iso(),\n'
            '        )\n'
            '        self.bets.append(bet)\n'
            '        return bet\n'
            '\n'
            '    def settle_bet(self, bet_index: int, result: str) -> None:\n'
            '        """Settle a bet and update bankroll."""\n'
            '        bet = self.bets[bet_index]\n'
            '        if result == "win":\n'
            '            bet.profit = bet.bet_amount * (bet.decimal_odds - 1)\n'
            '            self.bankroll += bet.profit\n'
            '        elif result == "loss":\n'
            '            bet.profit = -bet.bet_amount\n'
            '            self.bankroll -= bet.bet_amount\n'
            '        else:  # push\n'
            '            bet.profit = 0.0\n'
            '        bet.result = result\n'
            '\n'
            '    def summary(self) -> dict:\n'
            '        """Return summary statistics."""\n'
            '        settled = [b for b in self.bets if b.result is not None]\n'
            '        pending = [b for b in self.bets if b.result is None]\n'
            '        wins = [b for b in settled if b.result == "win"]\n'
            '        total_profit = sum(b.profit for b in settled if b.profit is not None)\n'
            '        return {\n'
            '            "total_bets": len(self.bets),\n'
            '            "settled": len(settled),\n'
            '            "pending": len(pending),\n'
            '            "wins": len(wins),\n'
            '            "win_rate": len(wins) / len(settled) if settled else 0,\n'
            '            "total_profit": total_profit,\n'
            '            "roi": total_profit / self.initial_bankroll if self.initial_bankroll > 0 else 0,\n'
            '            "current_bankroll": self.bankroll,\n'
            '        }\n'
            '\n'
            'tracker = BetTracker(initial_bankroll=10000.0)\n'
            'print(f"Bankroll initialized: ${tracker.bankroll:,.2f}")\n'
            'print("BetTracker ready.")'
        )
    )

    # ── Cell 16: Place simulated bets ──────────────────────────────────────
    cells.append(
        nbf.v4.new_code_cell(
            '# Cell 16: Place simulated bets on +EV opportunities\n'
            '\n'
            'if not ev_df.empty:\n'
            '    # Take the top 3 EV opportunities\n'
            '    top_bets = ev_df.nlargest(3, "ev")\n'
            '    print("Placing simulated bets on top +EV opportunities:")\n'
            '    print("=" * 70)\n'
            '\n'
            '    for _, row in top_bets.iterrows():\n'
            '        # Calculate Kelly fraction\n'
            '        b = row["decimal_odds"] - 1  # Net odds\n'
            '        kelly = (row["true_prob"] * b - (1 - row["true_prob"])) / b\n'
            '        kelly = max(kelly, 0.01)  # Minimum 1%\n'
            '        kelly = min(kelly, 0.10)  # Maximum 10% (quarter Kelly cap)\n'
            '\n'
            '        bet = tracker.place_bet(\n'
            '            event=row["event"],\n'
            '            market=row["market"],\n'
            '            selection=row["selection"],\n'
            '            book=row["book"],\n'
            '            price=int(row["price"]),\n'
            '            decimal_odds=row["decimal_odds"],\n'
            '            true_prob=row["true_prob"],\n'
            '            ev=row["ev"],\n'
            '            kelly_fraction=kelly,\n'
            '        )\n'
            '        print(f"\\n  Bet: {bet.selection} @ {bet.price} ({bet.book})")\n'
            '        print(f"  Event: {bet.event}")\n'
            '        print(f"  True Prob: {bet.true_prob:.1%}")\n'
            '        print(f"  EV: {bet.ev:+.4f}")\n'
            '        print(f"  Kelly: {bet.kelly_fraction:.1%}")\n'
            '        print(f"  Bet Amount: ${bet.bet_amount:.2f}")\n'
            '        print(f"  Bankroll: ${tracker.bankroll:,.2f}")\n'
            'else:\n'
            '    print("No +EV bets to place. Creating a sample bet instead.")\n'
            '    # Create a sample bet for demonstration\n'
            '    bet = tracker.place_bet(\n'
            '        event="KC vs BUF",\n'
            '        market="h2h",\n'
            '        selection="KC",\n'
            '        book="pinnacle",\n'
            '        price=-110,\n'
            '        decimal_odds=1.909,\n'
            '        true_prob=0.55,\n'
            '        ev=0.05,\n'
            '        kelly_fraction=0.05,\n'
            '    )\n'
            '    print(f"\\n  Sample Bet: {bet.selection} @ {bet.price}")\n'
            '    print(f"  True Prob: {bet.true_prob:.1%}, EV: {bet.ev:+.4f}")\n'
            '    print(f"  Bet Amount: ${bet.bet_amount:.2f}")'
        )
    )

    # ── Cell 17: Section 7 — Wait for Results ──────────────────────────────
    cells.append(
        nbf.v4.new_markdown_cell(
            "---\n"
            "\n"
            "## Section 7: Wait for Results\n"
            "\n"
            "In production, you'd poll a sportsbook API for game results. Here we "
            "simulate outcomes based on the true probabilities we estimated."
        )
    )

    # ── Cell 18: Simulate results ──────────────────────────────────────────
    cells.append(
        nbf.v4.new_code_cell(
            '# Cell 18: Simulate game results\n'
            '\n'
            'np.random.seed(123)\n'
            '\n'
            'print("Simulating game outcomes...")\n'
            'print("=" * 70)\n'
            '\n'
            'for i, bet in enumerate(tracker.bets):\n'
            '    # Simulate outcome based on estimated true probability\n'
            '    # In production, this would come from the sportsbook API\n'
            '    outcome = "win" if np.random.random() < bet.true_prob else "loss"\n'
            '    tracker.settle_bet(i, outcome)\n'
            '    result_str = f"WIN (+${bet.profit:.2f})" if outcome == "win" else f"LOSS (-${abs(bet.profit):.2f})"\n'
            '    print(f"\\n  Bet {i+1}: {bet.selection} @ {bet.price}")\n'
            '    print(f"  Result: {result_str}")\n'
            '    print(f"  Bankroll: ${tracker.bankroll:,.2f}")\n'
            '\n'
            'summary = tracker.summary()\n'
            'print("\\n" + "=" * 70)\n'
            'print(f"Session Summary:")\n'
            'print(f"  Total Bets: {summary[\'total_bets\']}")\n'
            'print(f"  Wins: {summary[\'wins\']} / {summary[\'settled\']}")\n'
            'print(f"  Win Rate: {summary[\'win_rate\']:.1%}")\n'
            'print(f"  Total Profit: ${summary[\'total_profit\']:,.2f}")\n'
            'print(f"  ROI: {summary[\'roi\']:.2%}")\n'
            'print(f"  Current Bankroll: ${summary[\'current_bankroll\']:,.2f}")'
        )
    )

    # ── Cell 19: Section 8 — Log the Result ──────────────────────────────
    cells.append(
        nbf.v4.new_markdown_cell(
            "---\n"
            "\n"
            "## Section 8: Log the Result\n"
            "\n"
            "Every bet and outcome should be logged for analysis. In production, you'd "
            "write this to TimescaleDB. Here we log to a DataFrame for review."
        )
    )

    # ── Cell 20: Log results ──────────────────────────────────────────
    cells.append(
        nbf.v4.new_code_cell(
            '# Cell 20: Log all bets and results\n'
            '\n'
            'bet_log = pd.DataFrame([\n'
            '    {\n'
            '        "timestamp": b.timestamp,\n'
            '        "event": b.event,\n'
            '        "market": b.market,\n'
            '        "selection": b.selection,\n'
            '        "book": b.book,\n'
            '        "price": b.price,\n'
            '        "true_prob": f"{b.true_prob:.1%}",\n'
            '        "ev": f"{b.ev:+.4f}",\n'
            '        "kelly": f"{b.kelly_fraction:.1%}",\n'
            '        "amount": f"${b.bet_amount:.2f}",\n'
            '        "result": b.result,\n'
            '        "profit": f"${b.profit:.2f}" if b.profit is not None else "pending",\n'
            '    }\n'
            '    for b in tracker.bets\n'
            '])\n'
            '\n'
            'print("Bet Log:")\n'
            'print(bet_log.to_string(index=False))'
        )
    )

    # ── Cell 21: Section 9 — Measure CLV ──────────────────────────────────
    cells.append(
        nbf.v4.new_markdown_cell(
            "---\n"
            "\n"
            "## Section 9: Measure Closing Line Value (CLV)\n"
            "\n"
            "**Closing Line Value (CLV)** is the gold standard for bettors. It measures "
            "how your bet's odds compare to the closing line (the final odds before game "
            "start).\n"
            "\n"
            "- **Positive CLV**: You got better odds than the closing line → good\n"
            "- **Negative CLV**: You got worse odds than the closing line → bad\n"
            "- **CLV ≈ 0**: You matched the closing line\n"
            "\n"
            "CLV is calculated as:\n"
            "```\n"
            "CLV = (your_implied_prob - closing_implied_prob) / closing_implied_prob\n"
            "```\n"
            "\n"
            "A bettor who consistently beats the closing line by 1-2% is a long-term winner."
        )
    )

    # ── Cell 22: CLV calculation ──────────────────────────────────────────
    cells.append(
        nbf.v4.new_code_cell(
            '# Cell 22: Calculate Closing Line Value\n'
            '\n'
            '# Simulate closing lines (in production, these come from the DB)\n'
            '# CLV compares your opening odds to the closing line.\n'
            '\n'
            'print("Closing Line Value Analysis")\n'
            'print("=" * 70)\n'
            '\n'
            'clv_results = []\n'
            'for bet in tracker.bets:\n'
            '    # Simulate: closing line is typically 5-15 cents tighter than opening\n'
            '    # (In production, query odds_ticks for the closing line)\n'
            '    closing_price = bet.price + np.random.randint(-5, 6)  # Simulated closing\n'
            '    try:\n'
            '        opening_odds = Odds(american=bet.price)\n'
            '        closing_odds = Odds(american=closing_price)\n'
            '        opening_implied = opening_odds.implied_probability\n'
            '        closing_implied = closing_odds.implied_probability\n'
            '\n'
            '        # CLV = (closing_implied - opening_implied) / opening_implied\n'
            '        # If closing line moved AGAINST you (your team became more likely),\n'
            '        # your CLV is positive (you got good value).\n'
            '        clv = (closing_implied - opening_implied) / opening_implied\n'
            '\n'
            '        clv_results.append({\n'
            '            "event": bet.event,\n'
            '            "selection": bet.selection,\n'
            '            "opening_price": bet.price,\n'
            '            "closing_price": closing_price,\n'
            '            "opening_implied": f"{opening_implied:.3f}",\n'
            '            "closing_implied": f"{closing_implied:.3f}",\n'
            '            "CLV": f"{clv:+.2%}",\n'
            '        })\n'
            '\n'
            '        clv_sign = "+" if clv > 0 else ""\n'
            '        verdict = "✓ Good value" if clv > 0 else "✗ Beat by the close"\n'
            '        print(f"\\n  {bet.selection} in {bet.event}")\n'
            '        print(f"    Opening: {bet.price} → Closing: {closing_price}")\n'
            '        print(f"    CLV: {clv_sign}{clv:.2%} {verdict}")\n'
            '\n'
            '    except (ValueError, ZeroDivisionError) as e:\n'
            '        print(f"  Could not calculate CLV for {bet.selection}: {e}")\n'
            '\n'
            'if clv_results:\n'
            '    clv_df = pd.DataFrame(clv_results)\n'
            '    print(f"\\n\\nCLV Summary:")\n'
            '    print(clv_df.to_string(index=False))'
        )
    )

    # ── Cell 23: Section 10 — Update Model ──────────────────────────────
    cells.append(
        nbf.v4.new_markdown_cell(
            "---\n"
            "\n"
            "## Section 10: Update the Model\n"
            "\n"
            "After each betting session, update your rating models with the new game results. "
            "This is the **closing of the loop** — new data feeds back into better predictions."
        )
    )

    # ── Cell 24: Model update demonstration ──────────────────────────────────
    cells.append(
        nbf.v4.new_code_cell(
            '# Cell 24: Demonstrate model update cycle\n'
            '#\n'
            '# After games finish, we incorporate results into our rating models.\n'
            '# This is where the live workflow loops back to the beginning.\n'
            '\n'
            'from sportsquant.models.ratings.massey_ratings import MasseyRatings\n'
            'from sportsquant.models.ratings.pagerank_ratings import PageRankRatings\n'
            '\n'
            '# Simulate new game results arriving\n'
            'new_games = pd.DataFrame([\n'
            '    {"HOME_TEAM": "KC", "AWAY_TEAM": "BUF", "HOME_SCORE": 27, "AWAY_SCORE": 24,\n'
            '     "WINNER": "KC", "LOSER": "BUF", "WINNER_SCORE": 27, "LOSER_SCORE": 24},\n'
            '    {"HOME_TEAM": "SF", "AWAY_TEAM": "PHI", "HOME_SCORE": 20, "AWAY_SCORE": 23,\n'
            '     "WINNER": "PHI", "LOSER": "SF", "WINNER_SCORE": 23, "LOSER_SCORE": 20},\n'
            '    {"HOME_TEAM": "DET", "AWAY_TEAM": "DAL", "HOME_SCORE": 31, "AWAY_SCORE": 17,\n'
            '     "WINNER": "DET", "LOSER": "DAL", "WINNER_SCORE": 31, "LOSER_SCORE": 17},\n'
            '])\n'
            '\n'
            'print("New game results:")\n'
            'print(new_games.to_string(index=False))\n'
            '\n'
            '# Update Massey ratings with new data\n'
            '# (In production, we\'d append to the full game history)\n'
            'massey = MasseyRatings(home_advantage=3.0)\n'
            '# Combine with original games\n'
            'combined_games = pd.concat([games_df, new_games], ignore_index=True) if "games_df" in dir() else new_games\n'
            '\n'
            'try:\n'
            '    updated_massey = massey.compute_ratings(combined_games)\n'
            '    print("\\nUpdated Massey Ratings:")\n'
            '    print(updated_massey.sort_values("overall_rating", ascending=False).to_string())\n'
            'except Exception as e:\n'
            '    print(f"Could not compute updated ratings: {e}")\n'
            '    print("(This is expected if games_df from Lab 07 is not in scope)")\n'
            '\n'
            'print("\\n✅ Model update complete. The loop continues: poll → detect → bet → log → update.")'
        )
    )

    # ── Cell 25: Section 11 — Track Bankroll ──────────────────────────────
    cells.append(
        nbf.v4.new_markdown_cell(
            "---\n"
            "\n"
            "## Section 11: Track Bankroll Over Time\n"
            "\n"
            "Professional bettors track their bankroll meticulously. Let's simulate "
            "a full season of betting to see how bankroll evolves."
        )
    )

    # ── Cell 26: Bankroll simulation ──────────────────────────────────────────
    cells.append(
        nbf.v4.new_code_cell(
            '# Cell 26: Simulate a full season of bankroll tracking\n'
            '\n'
            'np.random.seed(42)\n'
            '\n'
            '# Simulation parameters\n'
            'N_WEEKS = 17  # NFL regular season\n'
            'BETS_PER_WEEK = 3\n'
            'INITIAL_BANKROLL = 10000.0\n'
            'EDGE_PER_BET = 0.03  # Average edge per bet (3%)\n'
            'WIN_PROB = 0.55  # True win probability per bet\n'
            'KELLY_FRACTION = 0.25  # Quarter Kelly\n'
            '\n'
            'bankroll_history = [INITIAL_BANKROLL]\n'
            'weekly_profits = []\n'
            'weekly_record = []\n'
            '\n'
            'bankroll = INITIAL_BANKROLL\n'
            '\n'
            'for week in range(1, N_WEEKS + 1):\n'
            '    week_profit = 0.0\n'
            '    week_wins = 0\n'
            '    week_losses = 0\n'
            '\n'
            '    for _ in range(BETS_PER_WEEK):\n'
            '        # Quarter Kelly bet sizing\n'
            '        bet_fraction = KELLY_FRACTION * EDGE_PER_BET\n'
            '        bet_amount = bankroll * min(bet_fraction, 0.05)  # Cap at 5%\n'
            '\n'
            '        # Simulate outcome\n'
            '        if np.random.random() < WIN_PROB:\n'
            '            # Win: profit = bet_amount * (1/true_prob - 1)\n'
            '            avg_decimal = 1 / WIN_PROB + 0.05  # Slightly better than fair odds\n'
            '            profit = bet_amount * (avg_decimal - 1)\n'
            '            week_profit += profit\n'
            '            week_wins += 1\n'
            '        else:\n'
            '            # Loss\n'
            '            week_profit -= bet_amount\n'
            '            week_losses += 1\n'
            '\n'
            '    bankroll += week_profit\n'
            '    bankroll = max(bankroll, 100)  # Minimum bankroll\n'
            '    bankroll_history.append(bankroll)\n'
            '    weekly_profits.append(week_profit)\n'
            '    weekly_record.append((week_wins, week_losses))\n'
            '\n'
            '# Plot bankroll evolution\n'
            'fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10))\n'
            '\n'
            '# Bankroll over time\n'
            'ax1.plot(range(N_WEEKS + 1), bankroll_history, linewidth=2, color=\'#2E86AB\')\n'
            'ax1.axhline(y=INITIAL_BANKROLL, color=\'gray\', linestyle=\'--\', alpha=0.5, label=f\'Starting: ${INITIAL_BANKROLL:,.0f}\')\n'
            'ax1.fill_between(range(N_WEEKS + 1), INITIAL_BANKROLL, bankroll_history,\n'
            '                 where=[b >= INITIAL_BANKROLL for b in bankroll_history],\n'
            '                 alpha=0.2, color=\'green\', label=\'Profit\')\n'
            'ax1.fill_between(range(N_WEEKS + 1), INITIAL_BANKROLL, bankroll_history,\n'
            '                 where=[b < INITIAL_BANKROLL for b in bankroll_history],\n'
            '                 alpha=0.2, color=\'red\', label=\'Loss\')\n'
            'ax1.set_xlabel(\'Week\', fontsize=12)\n'
            'ax1.set_ylabel(\'Bankroll ($)\', fontsize=12)\n'
            'ax1.set_title(\'Bankroll Evolution Over Season\', fontsize=14, fontweight=\'bold\')\n'
            'ax1.legend(fontsize=10)\n'
            'ax1.grid(True, alpha=0.3)\n'
            '\n'
            '# Weekly P/L\n'
            'colors = [\'#2E9D8F\' if p > 0 else \'#E63946\' for p in weekly_profits]\n'
            'ax2.bar(range(1, N_WEEKS + 1), weekly_profits, color=colors, alpha=0.8)\n'
            'ax2.axhline(y=0, color=\'black\', linewidth=0.5)\n'
            'ax2.set_xlabel(\'Week\', fontsize=12)\n'
            'ax2.set_ylabel(\'Weekly P/L ($)\', fontsize=12)\n'
            'ax2.set_title(\'Weekly Profit/Loss\', fontsize=14, fontweight=\'bold\')\n'
            'ax2.grid(True, alpha=0.3, axis=\'y\')\n'
            '\n'
            'plt.tight_layout()\n'
            'plt.show()\n'
            '\n'
            'total_profit = bankroll - INITIAL_BANKROLL\n'
            'roi = total_profit / INITIAL_BANKROLL\n'
            'total_wins = sum(w for w, l in weekly_record)\n'
            'total_losses = sum(l for w, l in weekly_record)\n'
            '\n'
            'print(f"\\nSeason Results:")\n'
            'print(f"  Final Bankroll: ${bankroll:,.2f}")\n'
            'print(f"  Total Profit: ${total_profit:,.2f}")\n'
            'print(f"  ROI: {roi:.2%}")\n'
            'print(f"  Record: {total_wins}W - {total_losses}L ({total_wins/(total_wins+total_losses):.1%})")'
        )
    )

    # ── Cell 27: Section 12 — Closing the Loop ──────────────────────────────
    cells.append(
        nbf.v4.new_markdown_cell(
            "---\n"
            "\n"
            "## Section 12: Closing the Loop\n"
            "\n"
            "The live workflow is a **continuous cycle**:\n"
            "\n"
            "1. **Poll** → Fetch latest odds from the API\n"
            "2. **Detect** → Find +EV and middling opportunities\n"
            "3. **Bet** → Size with Kelly and place\n"
            "4. **Log** → Record the bet and result\n"
            "5. **Measure** → Calculate CLV against closing lines\n"
            "6. **Update** → Feed results back into rating models\n"
            "7. **Track** → Monitor bankroll and ROI over time\n"
            "\n"
            "### Production Considerations\n"
            "\n"
            "| Component | Production | This Lab |\n"
            "|---|---|---|\n"
            "| Odds source | The Odds API via poller | Synthetic data |\n"
            "| Bet placement | Sportsbook API | Simulated |\n"
            "| Result source | Sportsbook API | Random simulation |\n"
            "| CLV data | Closing odds from DB | Simulated |\n"
            "| Model update | Automatic after each game | Manual |\n"
            "| Persistence | TimescaleDB | In-memory |\n"
            "\n"
            "### Key Metrics to Track\n"
            "\n"
            "| Metric | Formula | Target |\n"
            "|---|---|---|\n"
            "| Win Rate | Wins / Total Bets | > 52.4% (at -110) |\n"
            "| ROI | Profit / Total Wagered | > 2% |\n"
            "| CLV | (Closing - Opening) / Opening | > +1% |\n"
            "| Kelly Utilization | Bet Size / Kelly Size | 25-50% |\n"
            "| Bankroll Variance | Std Dev of Weekly P/L | < 5% of bankroll |"
        )
    )

    # ── Cell 28: Exercises ─────────────────────────────────────────────
    cells.append(
        nbf.v4.new_markdown_cell(
            "---\n"
            "\n"
            "## Exercises\n"
            "\n"
            "Try these on your own:\n"
            "\n"
            "1. **Connect to live data** — Start the poller and run this lab with real odds "
            "data. How do the +EV opportunities compare to synthetic data?\n"
            "\n"
            "2. **Different Kelly fractions** — Simulate the season with full Kelly (1.0), "
            "half Kelly (0.5), and quarter Kelly (0.25). Which has the best risk-adjusted return?\n"
            "\n"
            "3. **CLV tracking** — Store every bet in TimescaleDB and calculate rolling CLV "
            "over your last 50 bets. Are you consistently beating the closing line?\n"
            "\n"
            "4. **Automated alerts** — Write a script that polls the database every minute "
            "and sends an alert when a +EV opportunity above a threshold is detected.\n"
            "\n"
            "5. **Model ensemble** — Combine predictions from Lab 07's four rating systems "
            "with the EV detection from this lab. Does the ensemble improve profitability?"
        )
    )

    # ── Cell 29: Summary ─────────────────────────────────────────────
    cells.append(
        nbf.v4.new_markdown_cell(
            "---\n"
            "\n"
            "## Summary\n"
            "\n"
            "In this lab you learned:\n"
            "\n"
            "- How to verify the poller is running and collecting live odds\n"
            "- How to find +EV opportunities by comparing true probability to implied probability\n"
            "- How to detect middling opportunities across multiple sportsbooks\n"
            "- How to simulate bet placement with Kelly Criterion sizing\n"
            "- How to log results and measure profitability\n"
            "- How to calculate Closing Line Value (CLV)\n"
            "- How to update rating models after new game results\n"
            "- How to track bankroll over a full season\n"
            "\n"
            "### Key API Reference\n"
            "\n"
            "| Class/Function | Module | Purpose |\n"
            "|---|---|---|\n"
            "| `Odds` | `sportsquant.core.betting.odds` | Odds conversion |\n"
            "| `KellyCalculator` | `sportsquant.core.betting.kelly` | Kelly Criterion sizing |\n"
            "| `EdgeCalculator` | `sportsquant.core.betting.kelly` | Edge detection |\n"
            "| `BankrollManager` | `sportsquant.core.betting.kelly` | Bankroll tracking |\n"
            "| `american_to_decimal` | `sportsquant.core.betting.engine` | Odds conversion |\n"
            "| `calculate_ev` | `sportsquant.core.betting.engine` | EV calculation |\n"
            "| `MasseyRatings` | `sportsquant.models.ratings.massey_ratings` | Massey method |\n"
            "| `PageRankRatings` | `sportsquant.models.ratings.pagerank_ratings` | PageRank method |\n"
            "\n"
            "### The Live Workflow Pipeline\n"
            "\n"
            "```\n"
            "Poller → Detect +EV → Kelly Size → Place Bet → Wait → Log Result\n"
            "   ↑                                                        ↓\n"
            "   └──── Update Model ← Measure CLV ← Track P/L ←────────┘\n"
            "```\n"
            "\n"
            "### Next Steps\n"
            "\n"
            "This concludes the SportsQuant lab series. To go further:\n"
            "\n"
            "- **Productionize**: Deploy the poller with Docker Compose\n"
            "- **Automate**: Create Prefect flows for the full workflow\n"
            "- **Scale**: Add more sports, books, and rating systems\n"
            "- **Monitor**: Build a dashboard with Grafana and TimescaleDB\n"
            "\n"
            "---\n"
            "\n"
            "*Don't forget to close the pool when you're done:*\n"
            "```python\n"
            "if pool:\n"
            "    await pool.close()\n"
            "```"
        )
    )

    # ── Cell 30: Cleanup ───────────────────────────────────────────────
    cells.append(
        nbf.v4.new_code_cell(
            "# Cell 30: Close the connection pool and clean up\n"
            "if pool is not None:\n"
            "    await pool.close()\n"
            "    print('Connection pool closed.')\n"
            "else:\n"
            "    print('No database connection to close (synthetic mode).')\n"
            "\n"
            "print('\\nLab 08: Live Workflow — Complete!')"
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