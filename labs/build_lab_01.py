"""Build script for Lab 01: Getting Started with SportsQuant.

Generates ``01_getting_started.ipynb`` using nbformat. Run this script to
produce the notebook, then open it in Jupyter to execute the cells against a
live TimescaleDB instance.

Usage::

    cd /home/jcharles/Projects/Infrastructure/sportsquant
    uv run python labs/build_lab_01.py
"""

from __future__ import annotations

import nbformat as nbf

OUTPUT_PATH = "labs/01_getting_started.ipynb"


def build() -> nbf.NotebookNode:
    """Construct the Lab 01 notebook programmatically."""
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
            "# Lab 01: Getting Started with SportsQuant\n"
            "\n"
            "Welcome! This lab walks you through installing SportsQuant, connecting to "
            "TimescaleDB, and running your first queries. By the end you will:\n"
            "\n"
            "- Install the `sportsquant` package with notebook extras\n"
            "- Connect to a running TimescaleDB instance\n"
            "- Verify the database is healthy\n"
            "- Explore the schema (tables, hypertables, materialized views)\n"
            "- Use the built-in read-side query helpers\n"
            "- Insert and clean up a test row\n"
            "\n"
            "---"
        )
    )

    # ── Cell 2: Prerequisites ───────────────────────────────────────────
    cells.append(
        nbf.v4.new_markdown_cell(
            "## Prerequisites\n"
            "\n"
            "- **Python 3.12+** installed\n"
            "- A running **TimescaleDB** instance (Docker or remote)\n"
            "- Environment variables set for DB connection (or defaults work for local Docker)\n"
            "\n"
            "### Default connection (works with Docker Compose)\n"
            "\n"
            "| Variable | Default |\n"
            "|---|---|\n"
            "| `SPORTSQUANT_DB_HOST` | `timescaledb` |\n"
            "| `SPORTSQUANT_DB_PORT` | `5432` |\n"
            "| `SPORTSQUANT_DB_USER` | `sportsquant` |\n"
            "| `SPORTSQUANT_DB_PASSWORD` | `sportsquant` |\n"
            "| `SPORTSQUANT_DB_DATABASE` | `sportsquant` |\n"
            "\n"
            "If you are running outside Docker, set `SPORTSQUANT_DB_HOST=localhost`."
        )
    )

    # ── Cell 3: Install ────────────────────────────────────────────────
    cells.append(
        nbf.v4.new_code_cell(
            "# Cell 3: Install sportsquant with notebook extras\n"
            "# Run this cell once. In a notebook environment you can use:\n"
            "#   %pip install sportsquant[notebook]\n"
            "#\n"
            "# If using uv:\n"
            "#   !uv add sportsquant[notebook]\n"
            "#\n"
            "# For now we assume sportsquant is already installed in the environment.\n"
            "import sportsquant\n"
            'print(f"sportsquant version: {sportsquant.__version__}")'
        )
    )

    # ── Cell 4: Section 1 — Setup ──────────────────────────────────────
    cells.append(
        nbf.v4.new_markdown_cell(
            "---\n"
            "\n"
            "## Section 1: Setup — Import and Configure\n"
            "\n"
            "SportsQuant uses an async connection pool backed by **asyncpg**. "
            "All database operations are `async def`, so we run them inside "
            "an event loop (Jupyter handles this for us via `nest_asyncio`)."
        )
    )

    # ── Cell 5: Imports ────────────────────────────────────────────────
    cells.append(
        nbf.v4.new_code_cell(
            "# Cell 5: Core imports\n"
            "import asyncio\n"
            "import json\n"
            "\n"
            "from sportsquant.infra.db.connection import DBConfig, DatabasePool, get_pool, health_check, reset_pool\n"
            "from sportsquant.infra.db.queries import (\n"
            "    get_poller_health_summary,\n"
            "    get_poller_runs,\n"
            "    get_poller_logs,\n"
            "    get_table_stats,\n"
            "    get_db_size,\n"
            ")\n"
            "from sportsquant.infra.db.schema import verify_schema, create_schema, EXPECTED_TABLES, EXPECTED_HYPERTABLES\n"
            "from sportsquant.infra.db.writers import write_odds_ticks\n"
            "\n"
            "# Enable nested event loops in Jupyter\n"
            "import nest_asyncio\n"
            "nest_asyncio.apply()\n"
            "\n"
            'print("Imports loaded successfully.")'
        )
    )

    # ── Cell 6: DBConfig from env ──────────────────────────────────────
    cells.append(
        nbf.v4.new_code_cell(
            "# Cell 6: Create a DBConfig from environment variables\n"
            "#\n"
            "# DBConfig reads from env vars with the SPORTSQUANT_DB_ prefix.\n"
            "# Defaults: host=timescaledb, port=5432, user=sportsquant, etc.\n"
            "#\n"
            "# To override, set env vars before starting the kernel:\n"
            "#   export SPORTSQUANT_DB_HOST=localhost\n"
            "\n"
            "config = DBConfig.from_env()\n"
            'print(f"DBConfig: host={config.host}, port={config.port}, database={config.database}")\n'
            "print(f\"DSN: {config.to_dsn().split('@')[1]}\")  # Hide password"
        )
    )

    # ── Cell 7: Open connection pool ───────────────────────────────────
    cells.append(
        nbf.v4.new_code_cell(
            "# Cell 7: Open the connection pool\n"
            "#\n"
            "# get_pool() returns a singleton DatabasePool. On the first call it\n"
            "# creates and connects the pool. Subsequent calls return the same\n"
            "# instance.\n"
            "\n"
            "pool = await get_pool(config)\n"
            'print(f"Pool connected: {pool.pool is not None}")'
        )
    )

    # ── Cell 8: Section 2 — Verify DB reachable ────────────────────────
    cells.append(
        nbf.v4.new_markdown_cell(
            "---\n"
            "\n"
            "## Section 2: Verify the Database is Reachable\n"
            "\n"
            "The `health_check` function runs a lightweight `SELECT 1` and "
            "retrieves PostgreSQL/TimescaleDB version strings."
        )
    )

    # ── Cell 9: Health check ────────────────────────────────────────────
    cells.append(
        nbf.v4.new_code_cell(
            "# Cell 9: Run a health check\n"
            "health = await health_check(pool)\n"
            "print(json.dumps(health, indent=2))\n"
            "print(f\"\\nStatus: {health['status']}\")\n"
            "print(f\"Latency: {health['latency_ms']} ms\")\n"
            "print(f\"PostgreSQL: {health['version'].split(',')[0]}\")\n"
            "print(f\"TimescaleDB: {health['timescaledb']}\")"
        )
    )

    # ── Cell 10: Section 3 — Explore schema ────────────────────────────
    cells.append(
        nbf.v4.new_markdown_cell(
            "---\n"
            "\n"
            "## Section 3: Explore the Schema\n"
            "\n"
            "SportsQuant uses TimescaleDB hypertables for time-series data "
            "(odds ticks and injuries), regular PostgreSQL tables for metadata, "
            "and a materialized view for metrics."
        )
    )

    # ── Cell 11: Verify schema ──────────────────────────────────────────
    cells.append(
        nbf.v4.new_code_cell(
            "# Cell 11: Verify the schema and list what's present\n"
            "report = await verify_schema(pool)\n"
            "print(json.dumps(report, indent=2))"
        )
    )

    # ── Cell 12: List tables ────────────────────────────────────────────
    cells.append(
        nbf.v4.new_code_cell(
            "# Cell 12: List all public tables\n"
            "tables = await pool.fetch(\"SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename\")\n"
            "print(\"Tables in 'public' schema:\")\n"
            "for row in tables:\n"
            "    print(f\"  - {row['tablename']}\")"
        )
    )

    # ── Cell 13: List hypertables ───────────────────────────────────────
    cells.append(
        nbf.v4.new_code_cell(
            "# Cell 13: List TimescaleDB hypertables\n"
            "#\n"
            "# Hypertables partition time-series data by the 'ts' column into\n"
            "# chunks (1-day intervals by default). This is what makes TimescaleDB\n"
            "# fast for large volumes of odds and injury data.\n"
            "\n"
            "try:\n"
            "    hypertables = await pool.fetch(\n"
            '        "SELECT hypertable_name, num_chunks, compression_enabled "\n'
            '        "FROM timescaledb_information.hypertables"\n'
            "    )\n"
            '    print("TimescaleDB Hypertables:")\n'
            "    for row in hypertables:\n"
            "        print(f\"  - {row['hypertable_name']} (chunks={row['num_chunks']}, compressed={row['compression_enabled']}\")\n"
            "except Exception as e:\n"
            '    print(f"Could not query hypertables: {e}")'
        )
    )

    # ── Cell 14: List materialized views ────────────────────────────────
    cells.append(
        nbf.v4.new_code_cell(
            "# Cell 14: List materialized views\n"
            "views = await pool.fetch(\n"
            "    \"SELECT matviewname, definition FROM pg_matviews WHERE schemaname = 'public'\"\n"
            ")\n"
            "print(f\"Materialized views in 'public' schema: {len(views)}\")\n"
            "for row in views:\n"
            "    print(f\"  - {row['matviewname']}\")"
        )
    )

    # ── Cell 15: Section 4 — First query ────────────────────────────────
    cells.append(
        nbf.v4.new_markdown_cell(
            "---\n"
            "\n"
            "## Section 4: Your First Query\n"
            "\n"
            "Let's count the rows in the main data tables. If the poller hasn't "
            "run yet, you'll see 0 rows — that's perfectly fine."
        )
    )

    # ── Cell 16: Count odds_ticks ──────────────────────────────────────
    cells.append(
        nbf.v4.new_code_cell(
            "# Cell 16: Count rows in key tables\n"
            'for table_name in ["odds_ticks", "injuries", "poller_runs", "poller_health"]:\n'
            '    count = await pool.fetchval(f"SELECT count(*) FROM {table_name}")\n'
            '    print(f"{table_name}: {count} rows")'
        )
    )

    # ── Cell 17: Section 5 — Schema introspection ──────────────────────
    cells.append(
        nbf.v4.new_markdown_cell(
            "---\n"
            "\n"
            "## Section 5: Schema Introspection\n"
            "\n"
            "Let's look at the column definitions for each table. Understanding "
            "the schema is essential before writing queries."
        )
    )

    # ── Cell 18: Column introspection ───────────────────────────────────
    cells.append(
        nbf.v4.new_code_cell(
            "# Cell 18: Show column definitions for each table\n"
            "for table in sorted(EXPECTED_TABLES):\n"
            "    columns = await pool.fetch(\n"
            '        "SELECT column_name, data_type, is_nullable "\n'
            '        "FROM information_schema.columns "\n'
            "        \"WHERE table_schema = 'public' AND table_name = $1 \"\n"
            '        "ORDER BY ordinal_position",\n'
            "        table,\n"
            "    )\n"
            '    print(f"\\n{table}:")\n'
            "    print(f\"  {'Column':<20} {'Type':<25} {'Nullable':<8}\")\n"
            "    print(f\"  {'-'*20} {'-'*25} {'-'*8}\")\n"
            "    for col in columns:\n"
            "        print(f\"  {col['column_name']:<20} {col['data_type']:<25} {col['is_nullable']:<8}\")"
        )
    )

    # ── Cell 19: Section 6 — Read-side helpers ──────────────────────────
    cells.append(
        nbf.v4.new_markdown_cell(
            "---\n"
            "\n"
            "## Section 6: Read-Side Query Helpers\n"
            "\n"
            "SportsQuant ships with convenience query functions that wrap common "
            "dashboard queries. Let's try each one."
        )
    )

    # ── Cell 20: Poller health summary ─────────────────────────────────
    cells.append(
        nbf.v4.new_code_cell(
            "# Cell 20: Get poller health summary\n"
            "health_summary = await get_poller_health_summary(pool)\n"
            "if health_summary:\n"
            "    print(f\"{'Poller':<30} {'Status':<12} {'Failures':<10} {'Last Run':<12}\")\n"
            "    print(f\"{'-'*30} {'-'*12} {'-'*10} {'-'*12}\")\n"
            "    for entry in health_summary:\n"
            "        print(f\"{entry['poller_name']:<30} {entry['status']:<12} {entry['consecutive_failures']:<10} {entry.get('last_run_status', 'N/A'):<12}\")\n"
            "else:\n"
            '    print("No poller health entries yet. The poller hasn\'t run.")'
        )
    )

    # ── Cell 21: Table stats ───────────────────────────────────────────
    cells.append(
        nbf.v4.new_code_cell(
            "# Cell 21: Get table statistics\n"
            "#\n"
            "# get_table_stats() queries the db_metrics materialized view for\n"
            "# row counts, 24h deltas, and timestamp bounds.\n"
            "# If the view is stale, refresh it first:\n"
            "\n"
            "from sportsquant.infra.db.queries import refresh_db_metrics\n"
            "await refresh_db_metrics(pool)\n"
            "\n"
            "stats = await get_table_stats(pool)\n"
            "if stats:\n"
            "    print(f\"{'Table':<15} {'Rows':<12} {'24h':<10} {'Oldest':<25} {'Newest':<25}\")\n"
            "    print(f\"{'-'*15} {'-'*12} {'-'*10} {'-'*25} {'-'*25}\")\n"
            "    for s in stats:\n"
            "        print(f\"{s['table_name']:<15} {s['total_rows']:<12} {s['rows_24h']:<10} {str(s.get('oldest_ts', 'N/A')):<25} {str(s.get('newest_ts', 'N/A')):<25}\")\n"
            "else:\n"
            '    print("No table stats available yet.")'
        )
    )

    # ── Cell 22: Database size ──────────────────────────────────────────
    cells.append(
        nbf.v4.new_code_cell(
            "# Cell 22: Get database size\n"
            "db_info = await get_db_size(pool)\n"
            "print(f\"Total database size: {db_info['database_size_pretty']}\")\n"
            'print("\\nPer-table sizes:")\n'
            "for t in db_info['table_sizes']:\n"
            "    print(f\"  {t['table_name']:<20} {t['size_pretty']:<12} ~{t['row_estimate']} rows\")"
        )
    )

    # ── Cell 23: Section 7 — Insert test row ──────────────────────────
    cells.append(
        nbf.v4.new_markdown_cell(
            "---\n"
            "\n"
            "## Section 7: Insert a Test Row\n"
            "\n"
            "Let's write a synthetic odds tick to verify the write path works. "
            "We'll use `write_odds_ticks`, the same function the poller uses for "
            "bulk inserts."
        )
    )

    # ── Cell 24: Write synthetic data ──────────────────────────────────
    cells.append(
        nbf.v4.new_code_cell(
            "# Cell 24: Insert a synthetic odds tick\n"
            "from sportsquant.util.time_utils import utc_now_iso\n"
            "\n"
            "test_tick = {\n"
            '    "sport": "nfl",\n'
            '    "league": "NFL",\n'
            '    "event_id": "test_event_lab01",\n'
            '    "book": "test_book",\n'
            '    "market": "h2h",\n'
            '    "selection": "Test Team",\n'
            '    "price": -110,\n'
            '    "line": None,\n'
            '    "ts": utc_now_iso(),\n'
            '    "source_raw": {"note": "synthetic test row from Lab 01"},\n'
            "}\n"
            "\n"
            "rows_written = await write_odds_ticks(pool, [test_tick])\n"
            'print(f"Wrote {rows_written} row(s) to odds_ticks")'
        )
    )

    # ── Cell 25: Verify test row ────────────────────────────────────────
    cells.append(
        nbf.v4.new_code_cell(
            "# Cell 25: Verify the test row appears\n"
            "result = await pool.fetch(\n"
            "    \"SELECT * FROM odds_ticks WHERE event_id = 'test_event_lab01' ORDER BY ts DESC LIMIT 5\"\n"
            ")\n"
            "for row in result:\n"
            "    print(dict(row))"
        )
    )

    # ── Cell 26: Section 8 — Clean up ──────────────────────────────────
    cells.append(
        nbf.v4.new_markdown_cell(
            "---\n"
            "\n"
            "## Section 8: Clean Up the Test Row\n"
            "\n"
            "Always clean up after yourself! Let's delete the synthetic row we just inserted."
        )
    )

    # ── Cell 27: Delete test row ────────────────────────────────────────
    cells.append(
        nbf.v4.new_code_cell(
            "# Cell 27: Delete the test row\n"
            "await pool.execute(\"DELETE FROM odds_ticks WHERE event_id = 'test_event_lab01'\")\n"
            "\n"
            "# Verify it's gone\n"
            "count = await pool.fetchval(\"SELECT count(*) FROM odds_ticks WHERE event_id = 'test_event_lab01'\")\n"
            'print(f"Test rows remaining: {count}")'
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
            "1. **Count rows by sport** — Write a query that counts how many "
            "`odds_ticks` rows exist for each `sport`. Hint:\n"
            "   ```sql\n"
            "   SELECT sport, COUNT(*) FROM odds_ticks GROUP BY sport;\n"
            "   ```\n"
            "\n"
            "2. **Find the most recent injury** — Query the `injuries` table "
            "for the latest row, ordered by `ts DESC`.\n"
            "\n"
            "3. **Check poller run history** — Use `get_poller_runs(pool, 'odds_api_nfl')` "
            "to see the last 10 runs for the NFL odds poller.\n"
            "\n"
            "4. **Schema validation** — Call `verify_schema(pool)` and check that "
            "`is_valid` is `True`. What happens if you call `create_schema(pool)` "
            "when the schema already exists?"
        )
    )

    # ── Cell 29: Summary ───────────────────────────────────────────────
    cells.append(
        nbf.v4.new_markdown_cell(
            "---\n"
            "\n"
            "## Summary\n"
            "\n"
            "In this lab you learned:\n"
            "\n"
            "- How to configure and connect to TimescaleDB using `DBConfig` and `get_pool`\n"
            "- How to verify database health with `health_check`\n"
            "- The SportsQuant schema: 7 tables, 2 hypertables, 1 materialized view\n"
            "- How to use read-side helpers: `get_poller_health_summary`, `get_table_stats`, `get_db_size`\n"
            "- How to write and delete data with `write_odds_ticks`\n"
            "- How to introspect the schema with `information_schema` queries\n"
            "\n"
            "### Next Steps\n"
            "\n"
            "Continue to **Lab 02: Data Ingestion** to learn how the poller architecture "
            "works and how data flows from external APIs into TimescaleDB.\n"
            "\n"
            "---\n"
            "\n"
            "*Don't forget to close the pool when you're done:*\n"
            "```python\n"
            "await pool.close()\n"
            "```"
        )
    )

    # ── Cell 30: Cleanup ───────────────────────────────────────────────
    cells.append(
        nbf.v4.new_code_cell(
            "# Cell 30: Close the connection pool\n"
            "await pool.close()\n"
            'print("Connection pool closed. Lab 01 complete!")'
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
