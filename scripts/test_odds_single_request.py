#!/usr/bin/env python3
"""Single-request odds API test script.

Tests the odds backfill by making a single API request to The-Odds-API
for a controlled date range and verifying data flows through the pipeline.

Usage:
    # Dry run (no API calls, no writes)
    python scripts/test_odds_single_request.py --date 2026-01-25 --dry-run

    # Real test (makes API call, writes to Kafka and TimescaleDB)
    python scripts/test_odds_single_request.py --date 2026-01-25

    # Test with verbose logging
    python scripts/test_odds_single_request.py --date 2026-01-25 --verbose
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from typing import Any

import httpx
from confluent_kafka import Producer
from psycopg2 import connect
from psycopg2.extras import execute_values

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Configuration constants
KAFKA_BOOTSTRAP = "sports-cluster-kafka-bootstrap.default.svc:9092"
ODDS_TOPIC = "sports-analytics-live-odds"
API_URL = "https://api.the-odds-api.com/v4/sports/basketball_nba/odds"
MARKETS = ["us", "us2", "us_dfs"]


def get_api_key() -> str:
    """Get The-Odds-API key from environment."""
    api_key = os.environ.get("THE_ODDS_API_KEY", "")
    if not api_key:
        logger.error("THE_ODDS_API_KEY environment variable not set")
        sys.exit(1)
    return api_key


def create_kafka_producer() -> Producer:
    """Create and return a Kafka producer."""
    conf = {
        "bootstrap.servers": KAFKA_BOOTSTRAP,
        "client.id": "odds-single-request-test",
        "acks": "all",
        "retries": 3,
        "retry.backoff.ms": 1000,
    }
    return Producer(conf)


def create_db_connection():
    """Create a connection to TimescaleDB."""
    return connect(
        host="timescaledb.default.svc.cluster.local",
        port=5432,
        database="sports_analytics",
        user="postgres",
        password=os.environ.get("POSTGRES_PASSWORD", "password"),
    )


def fetch_odds_for_date(api_key: str, date_str: str) -> list[dict[str, Any]]:
    """Fetch odds for a single date from The-Odds-API.

    Args:
        api_key: The-Odds-API key
        date_str: Date in YYYY-MM-DD format

    Returns:
        List of odds events from the API
    """
    all_odds = []
    date_from = f"{date_str}T00:00:00Z"
    date_to = f"{date_str}T23:59:59Z"

    for region in MARKETS:
        params = {
            "apiKey": api_key,
            "regions": region,
            "oddsFormat": "decimal",
            "commenceDateFrom": date_from,
            "commenceDateTo": date_to,
        }

        logger.info(f"Fetching odds for {date_str} ({region})...")
        try:
            response = httpx.get(
                API_URL,
                params=params,
                timeout=30.0,
                follow_redirects=True,
            )
            response.raise_for_status()
            odds = response.json()

            if odds:
                logger.info(f"  Got {len(odds)} odds events for {date_str} ({region})")
                all_odds.extend(odds)
            else:
                logger.info(f"  No odds events for {date_str} ({region})")

        except httpx.HTTPStatusError as e:
            logger.error(f"  HTTP error for {date_str} ({region}): {e.response.status_code}")
            logger.error(f"  Response: {e.response.text[:200]}")
        except httpx.RequestError as e:
            logger.error(f"  Request error for {date_str} ({region}): {e}")

    return all_odds


def transform_odds_event(odds_data: dict[str, Any], date_str: str) -> dict[str, Any]:
    """Transform odds event from API format to pipeline format.

    Args:
        odds_data: Raw odds event from API
        date_str: The date being queried

    Returns:
        Transformed odds event suitable for pipeline
    """
    return {
        "game_id": odds_data.get("id", ""),
        "sport_key": odds_data.get("sport_key", "basketball_nba"),
        "event_id": odds_data.get("id", ""),
        "commence_time": odds_data.get("commence_time", ""),
        "home_team": odds_data.get("home_team", ""),
        "away_team": odds_data.get("away_team", ""),
        "bookmakers": odds_data.get("bookmakers", []),
        "timestamp": datetime.utcnow().isoformat(),
        "poll_date": date_str,
        "source": "the-odds-api",
        "version": "1.0",
    }


def write_to_kafka(producer: Producer, odds_events: list[dict[str, Any]], date_str: str) -> int:
    """Write odds events to Kafka topic.

    Args:
        producer: Kafka producer instance
        odds_events: List of transformed odds events
        date_str: Date for logging

    Returns:
        Number of events successfully produced
    """
    if not odds_events:
        logger.info("No odds events to write to Kafka")
        return 0

    count = 0
    for odds_event in odds_events:
        transformed = transform_odds_event(odds_event, date_str)
        game_id = odds_event.get("id", "")

        try:
            producer.produce(
                ODDS_TOPIC,
                key=game_id.encode("utf-8"),
                value=json.dumps(transformed).encode("utf-8"),
            )
            count += 1
            logger.debug(f"Produced odds for game {game_id}")
        except Exception as e:
            logger.error(f"Failed to produce odds for game {game_id}: {e}")

    producer.flush()
    logger.info(f"Wrote {count} odds events to Kafka topic {ODDS_TOPIC}")
    return count


def write_to_timescale(conn, odds_events: list[dict[str, Any]], date_str: str) -> int:
    """Write odds events to TimescaleDB.

    Args:
        conn: PostgreSQL connection
        odds_events: List of raw odds events from API
        date_str: Date for logging

    Returns:
        Number of records inserted
    """
    if not odds_events:
        logger.info("No odds events to write to TimescaleDB")
        return 0

    cursor = conn.cursor()

    # Prepare insert data
    records = []
    for odds_event in odds_events:
        commence_time = odds_event.get("commence_time", "")
        if commence_time:
            try:
                commence_dt = datetime.fromisoformat(commence_time.replace("Z", "+00:00"))
            except ValueError:
                commence_dt = None
        else:
            commence_dt = None

        bookmakers_json = json.dumps(odds_event.get("bookmakers", []))

        for bookmaker in odds_event.get("bookmakers", []):
            book_name = bookmaker.get("title", "Unknown")

            for market in bookmaker.get("markets", []):
                market_type = market.get("key", "unknown")

                for outcome in market.get("outcomes", []):
                    records.append((
                        datetime.utcnow(),
                        odds_event.get("id", ""),
                        odds_event.get("home_team", ""),
                        odds_event.get("away_team", ""),
                        book_name,
                        market_type,
                        outcome.get("name", ""),
                        outcome.get("price", 0),
                        outcome.get("point", None),
                        commence_dt,
                        bookmakers_json,
                    ))

    if not records:
        logger.info("No individual odds records to insert")
        return 0

    # Insert records
    insert_query = """
        INSERT INTO nba_odds_snapshots (
            time, game_id, team_home, team_away, sportsbook,
            market_type, selection, price, line,
            commence_time, raw_payload
        ) VALUES %s
        ON CONFLICT DO NOTHING
    """

    execute_values(cursor, insert_query, records)
    conn.commit()

    logger.info(f"Wrote {len(records)} odds records to TimescaleDB")
    return len(records)


def verify_pipeline_status():
    """Print current pipeline status for verification."""
    logger.info("=" * 60)
    logger.info("PIPELINE STATUS VERIFICATION")
    logger.info("=" * 60)

    # Check Kafka topic
    logger.info("Checking Kafka topic...")
    try:
        producer = create_kafka_producer()
        logger.info(f"  Kafka producer connected to {KAFKA_BOOTSTRAP}")
        logger.info(f"  Target topic: {ODDS_TOPIC}")
        producer.close()
        logger.info("  Kafka: ✅ Connected")
    except Exception as e:
        logger.error(f"  Kafka: ❌ Failed to connect: {e}")

    # Check TimescaleDB
    logger.info("Checking TimescaleDB...")
    try:
        conn = create_db_connection()
        cursor = conn.cursor()

        # Check if table exists
        cursor.execute("""
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_name = 'nba_odds_snapshots'
        """)
        if cursor.fetchone()[0] > 0:
            logger.info("  Table 'nba_odds_snapshots': ✅ Exists")

            # Get record count
            cursor.execute("SELECT COUNT(*) FROM nba_odds_snapshots")
            count = cursor.fetchone()[0]
            logger.info(f"  Record count: {count}")
        else:
            logger.error("  Table 'nba_odds_snapshots': ❌ Not found")

        conn.close()
    except Exception as e:
        logger.error(f"  TimescaleDB: ❌ Failed: {e}")

    logger.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Single-request odds API test script",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Dry run - show what would happen without making API calls
    python scripts/test_odds_single_request.py --date 2026-01-25 --dry-run

    # Real test - makes API call and writes to pipeline
    python scripts/test_odds_single_request.py --date 2026-01-25

    # Verbose output
    python scripts/test_odds_single_request.py --date 2026-01-25 --verbose
        """,
    )

    parser.add_argument(
        "--date",
        required=True,
        help="Date in YYYY-MM-DD format (e.g., 2026-01-25)",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would happen without making API calls or writing data",
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Validate date format
    try:
        test_date = datetime.strptime(args.date, "%Y-%m-%d")
        logger.info(f"Testing odds for date: {args.date}")
    except ValueError:
        logger.error(f"Invalid date format: {args.date}. Use YYYY-MM-DD")
        sys.exit(1)

    # Show pipeline status
    verify_pipeline_status()

    if args.dry_run:
        logger.info("DRY RUN MODE - No API calls or data writes")
        logger.info(f"Would fetch odds for date: {args.date}")
        logger.info(f"Would write to Kafka topic: {ODDS_TOPIC}")
        logger.info(f"Would write to TimescaleDB table: nba_odds_snapshots")
        return 0

    # Get API key
    api_key = get_api_key()

    # Fetch odds
    logger.info(f"Fetching odds for {args.date}...")
    odds_events = fetch_odds_for_date(api_key, args.date)

    if not odds_events:
        logger.warning(f"No odds events returned for {args.date}")
        logger.info("This is expected if there are no NBA games on this date")
        return 0

    logger.info(f"Got {len(odds_events)} odds events total")

    # Write to Kafka
    logger.info("Writing to Kafka...")
    kafka_count = 0
    try:
        producer = create_kafka_producer()
        kafka_count = write_to_kafka(producer, odds_events, args.date)
    except Exception as e:
        logger.error(f"Failed to write to Kafka: {e}")

    # Write to TimescaleDB
    logger.info("Writing to TimescaleDB...")
    db_count = 0
    try:
        conn = create_db_connection()
        db_count = write_to_timescale(conn, odds_events, args.date)
        conn.close()
    except Exception as e:
        logger.error(f"Failed to write to TimescaleDB: {e}")

    # Summary
    logger.info("=" * 60)
    logger.info("TEST SUMMARY")
    logger.info("=" * 60)
    logger.info(f"Date tested: {args.date}")
    logger.info(f"Odds events fetched: {len(odds_events)}")
    logger.info(f"Events written to Kafka: {kafka_count}")
    logger.info(f"Records written to TimescaleDB: {db_count}")
    logger.info("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
