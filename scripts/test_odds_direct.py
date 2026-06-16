#!/usr/bin/env python3
"""
Direct odds backfill test - bypasses Kafka Connect infrastructure issues.
Writes directly to TimescaleDB while also producing to Kafka (for future processing).
"""
import json
import os
import sys
from datetime import datetime, timezone
from typing import Optional

# API client for The-Odds-API
import requests

# Database connection
import psycopg2
from psycopg2.extras import execute_values

# Kafka producer (optional, for future processing)
try:
    from kafka import KafkaProducer
    KAFKA_AVAILABLE = True
except ImportError:
    KAFKA_AVAILABLE = False

# Configuration
THE_ODDS_API_KEY = os.environ.get("THE_ODDS_API_KEY", "")
THE_ODDS_BASE_URL = "https://api.the-odds-api.com/v4"

# Database config
DB_HOST = os.environ.get("DB_HOST", "timescaledb.default.svc")
DB_PORT = int(os.environ.get("DB_PORT", "5432"))
DB_NAME = os.environ.get("DB_NAME", "sports_analytics")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "password")

# Kafka config
KAFKA_BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP", "sports-cluster-kafka-bootstrap.default.svc:9092")
ODDS_TOPIC = "sports-analytics-live-odds"


def get_sports() -> list:
    """Get available sports from The-Odds-API."""
    url = f"{THE_ODDS_BASE_URL}/sports"
    params = {"apiKey": THE_ODDS_API_KEY}
    
    response = requests.get(url, params=params)
    response.raise_for_status()
    return response.json()


def get_odds(sport: str, regions: str = "us", markets: str = "h2h,spreads,totals") -> list:
    """
    Get odds for a specific sport.
    
    Args:
        sport: Sport key (e.g., 'basketball_nba')
        regions: Comma-separated regions (e.g., 'us,us2,us_dfs')
        markets: Comma-separated markets (e.g., 'h2h,spreads,totals')
    """
    url = f"{THE_ODDS_BASE_URL}/sports/{sport}/odds"
    params = {
        "apiKey": THE_ODDS_API_KEY,
        "regions": regions,
        "markets": markets,
        "oddsFormat": "decimal",
        "dateFormat": "iso"
    }
    
    response = requests.get(url, params=params)
    
    # Check for rate limiting or other errors
    if response.status_code == 400:
        error_msg = response.text
        print(f"❌ API Error: {error_msg}")
        return []
    
    response.raise_for_status()
    return response.json()


def create_odds_table(conn):
    """Create the odds table if it doesn't exist."""
    create_sql = """
    CREATE TABLE IF NOT EXISTS odds_events (
        id SERIAL PRIMARY KEY,
        sport_key VARCHAR(50) NOT NULL,
        sport_title VARCHAR(100) NOT NULL,
        event_id VARCHAR(100) NOT NULL,
        commence_time TIMESTAMP WITH TIME ZONE NOT NULL,
        home_team VARCHAR(200),
        away_team VARCHAR(200),
        market VARCHAR(50) NOT NULL,
        outcome_name VARCHAR(200) NOT NULL,
        outcome_price DECIMAL(10, 4),
        outcome_point DECIMAL(10, 4),
        bookmaker VARCHAR(200) NOT NULL,
        last_update TIMESTAMP WITH TIME ZONE NOT NULL,
        fetched_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        UNIQUE(sport_key, event_id, market, outcome_name, bookmaker)
    );
    
    -- Create index for common queries
    CREATE INDEX IF NOT EXISTS idx_odds_events_sport ON odds_events(sport_key);
    CREATE INDEX IF NOT EXISTS idx_odds_events_commence ON odds_events(commence_time);
    CREATE INDEX IF NOT EXISTS idx_odds_events_event ON odds_events(event_id);
    """
    
    with conn.cursor() as cur:
        cur.execute(create_sql)
    conn.commit()
    print("✅ Odds table created/verified")


def insert_odds(conn, odds_data: list, sport_key: str, sport_title: str):
    """Insert odds data into TimescaleDB."""
    if not odds_data:
        print("⚠️  No odds data to insert")
        return 0
    
    records = []
    for event in odds_data:
        event_id = event.get("id", "")
        commence_time = event.get("commence_time", "")
        home_team = event.get("home_team", "")
        away_team = event.get("away_team", "")
        
        for bookmaker in event.get("bookmakers", []):
            bookmaker_name = bookmaker.get("title", "")
            last_update = bookmaker.get("last_update", "")
            
            for market in bookmaker.get("markets", []):
                market_key = market.get("key", "")
                
                for outcome in market.get("outcomes", []):
                    records.append (
                        (
                            sport_key,
                            sport_title,
                            event_id,
                            commence_time,
                            home_team,
                            away_team,
                            market_key,
                            outcome.get("name", ""),
                            outcome.get("price", 0),
                            outcome.get("point"),
                            bookmaker_name,
                            last_update
                        )
                    )
    
    if not records:
        print("⚠️  No records to insert")
        return 0
    
    insert_sql = """
    INSERT INTO odds_events 
        (sport_key, sport_title, event_id, commence_time, home_team, away_team,
         market, outcome_name, outcome_price, outcome_point, bookmaker, last_update)
    VALUES %s
    ON CONFLICT (sport_key, event_id, market, outcome_name, bookmaker) 
    DO UPDATE SET 
        outcome_price = EXCLUDED.outcome_price,
        outcome_point = EXCLUDED.outcome_point,
        last_update = EXCLUDED.last_update,
        fetched_at = NOW()
    RETURNING id
    """
    
    with conn.cursor() as cur:
        result = execute_values(cur, insert_sql, records, fetch=True)
        affected = len(result)
    
    conn.commit()
    return affected


def produce_to_kafka(odds_data: list, sport_key: str):
    """Produce odds data to Kafka (for future processing)."""
    if not KAFKA_AVAILABLE or not odds_data:
        return
    
    try:
        producer = KafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP,
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            acks='all'
        )
        
        for event in odds_data:
            event["sport_key"] = sport_key
            future = producer.send(ODDS_TOPIC, value=event)
            future.get(timeout=10)
        
        producer.close()
        print(f"✅ Produced {len(odds_data)} events to Kafka topic {ODDS_TOPIC}")
    except Exception as e:
        print(f"⚠️  Kafka production failed: {e}")


def test_single_request(sport: str = "basketball_nba", regions: str = "us"):
    """Test a single odds API request."""
    print(f"\n{'='*60}")
    print(f"Testing Single Odds Request")
    print(f"{'='*60}")
    print(f"Sport: {sport}")
    print(f"Regions: {regions}")
    print(f"Markets: h2h, spreads, totals")
    print()
    
    # Connect to database
    print("📦 Connecting to TimescaleDB...")
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )
    
    # Create table
    create_odds_table(conn)
    
    # Fetch odds
    print(f"\n🔄 Fetching odds from The-Odds-API...")
    odds_data = get_odds(sport, regions=regions)
    
    if not odds_data:
        print("❌ No odds data received")
        conn.close()
        return False
    
    print(f"✅ Received {len(odds_data)} events")
    
    # Insert to database
    print(f"\n💾 Inserting to TimescaleDB...")
    inserted = insert_odds(conn, odds_data, sport, sport.replace("_", " ").title())
    print(f"✅ Inserted/updated {inserted} records")
    
    # Produce to Kafka (optional)
    if KAFKA_AVAILABLE:
        print(f"\n📤 Producing to Kafka (optional)...")
        produce_to_kafka(odds_data, sport)
    
    conn.close()
    
    print(f"\n{'='*60}")
    print("✅ TEST COMPLETE")
    print(f"{'='*60}")
    
    # Show sample data
    print("\n📊 Sample data from database:")
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )
    with conn.cursor() as cur:
        cur.execute("""
            SELECT sport_key, event_id, home_team, away_team, bookmaker, market, outcome_name, outcome_price
            FROM odds_events
            ORDER BY fetched_at DESC
            LIMIT 5
        """)
        for row in cur.fetchall():
            print(f"  {row[5]}: {row[6]} @ {row[7]} ({row[4]}) - {row[2]} vs {row[3]}")
    conn.close()
    
    return True


def main():
    """Main entry point."""
    # Check for API key
    if not THE_ODDS_API_KEY:
        print("❌ ERROR: THE_ODDS_API_KEY environment variable not set")
        print("   Set it with: export THE_ODDS_API_KEY=your_api_key")
        sys.exit(1)
    
    # Get sport from args or default
    sport = sys.argv[1] if len(sys.argv) > 1 else "basketball_nba"
    regions = sys.argv[2] if len(sys.argv) > 2 else "us"
    
    success = test_single_request(sport, regions)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
