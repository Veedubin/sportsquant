#!/usr/bin/env python3
"""NBA Odds Fetcher using Playwright with correct headers - Dual Write to Kafka + TimescaleDB."""

import json
import sys
import os
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from nba_stats_package.browser import NBAStatsBrowser, RateLimitConfig

# Kafka and TimescaleDB configuration
# For port-forward access, use localhost
KAFKA_BOOTSTRAP = "localhost:9092"
TIMESCALEDB_HOST = "localhost"
TIMESCALEDB_PORT = 5432
TIMESCALEDB_USER = "postgres"
TIMESCALEDB_PASSWORD = "password"
TIMESCALEDB_DB = "sports_analytics"


def fetch_todays_odds():
    """Fetch today's NBA odds from cdn.nba.com with correct headers."""
    
    # Exact headers provided by user to avoid blocking
    custom_headers = {
        "Accept": "*/*",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
        "Origin": "https://www.nba.com",
        "Pragma": "no-cache",
        "Priority": "u=1, i",
        "Referer": "https://www.nba.com/",
        "Sec-Ch-Ua": '"Not(A:Brand";v="8", "Chromium";v="144"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Linux"',
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
    }
    
    rate_limit = RateLimitConfig(
        min_interval_s=2.0,
        max_retries=5,
        max_backoff_s=60.0,
        base_backoff_s=5.0,
        jitter_s=1.0,
    )
    
    print("=" * 60)
    print("NBA Odds Fetcher - Playwright with Correct Headers")
    print("=" * 60)
    
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        print(f"[FAIL] Playwright not installed: {e}")
        print("Install with: pip install playwright && playwright install chromium")
        return None
    
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True)
    context = browser.new_context(
        user_agent=custom_headers["User-Agent"],
        viewport={"width": 1280, "height": 720},
        locale="en-US",
    )
    
    # Set ALL the custom headers
    context.set_extra_http_headers(custom_headers)
    page = context.new_page()
    
    url = "https://cdn.nba.com/static/json/liveData/odds/odds_todaysGames.json"
    print(f"\nFetching: {url}")
    
    for attempt in range(rate_limit.max_retries + 1):
        print(f"\nAttempt {attempt + 1}/{rate_limit.max_retries + 1}")
        
        try:
            resp = page.request.get(url, timeout=30000)
            status = int(getattr(resp, "status", 0))
            
            print(f"  Status: {status}")
            
            if status == 200:
                data = resp.json()
                print(f"\n[OK] Successfully fetched odds data!")
                print(f"  Response keys: {list(data.keys())}")
                print(f"  Games count: {len(data.get('games', []))}")
                
                # Cleanup
                context.close()
                browser.close()
                pw.stop()
                
                return data
            
            elif status == 403 or status == 429:
                print(f"  Blocked (status={status}), backing off...")
                backoff_time = rate_limit.base_backoff_s * (2 ** attempt) + rate_limit.jitter_s
                backoff_time = min(backoff_time, rate_limit.max_backoff_s)
                print(f"  Sleeping {backoff_time:.1f}s before retry...")
                import time
                time.sleep(backoff_time)
                continue
            
            else:
                print(f"  Unexpected status {status}")
        
        except Exception as e:
            print(f"  Error: {e}")
            import time
            time.sleep(5)
    
    # Cleanup on failure
    try:
        context.close()
        browser.close()
        pw.stop()
    except:
        pass
    
    print("\n[FAIL] Failed to fetch odds after all retries")
    return None


def write_to_kafka(odds_data, bootstrap="localhost:9092"):
    """Write odds data to Kafka topic."""
    try:
        from confluent_kafka import Producer
    except ImportError:
        print("[SKIP] confluent-kafka not installed, skipping Kafka write")
        return False
    
    print(f"\n--- Writing to Kafka ({bootstrap}) ---")
    
    try:
        producer = Producer({
            "bootstrap.servers": bootstrap,
            "client.id": "nba-odds-fetcher",
        })
        
        def delivery_callback(err, msg):
            if err:
                print(f"  [Kafka] Delivery failed: {err}")
            else:
                print(f"  [Kafka] Delivered to {msg.topic()} [{msg.partition()}] @ {msg.offset()}")
        
        timestamp = datetime.utcnow().isoformat()
        key = f"odds-{datetime.utcnow().strftime('%Y%m%d')}"
        
        message = {
            "timestamp": timestamp,
            "source": "cdn.nba.com",
            "data": odds_data
        }
        
        producer.produce(
            topic="nba-odds",
            key=key,
            value=json.dumps(message),
            callback=delivery_callback
        )
        
        # Wait for delivery
        producer.flush(timeout=10)
        print("[OK] Kafka write complete")
        return True
        
    except Exception as e:
        print(f"[FAIL] Kafka write error: {e}")
        return False


def write_to_timescaledb(odds_data):
    """Write odds data to TimescaleDB."""
    try:
        import psycopg2
    except ImportError:
        print("[SKIP] psycopg2 not installed, skipping TimescaleDB write")
        return False
    
    print(f"\n--- Writing to TimescaleDB ---")
    
    try:
        conn = psycopg2.connect(
            host=TIMESCALEDB_HOST,
            port=TIMESCALEDB_PORT,
            user=TIMESCALEDB_USER,
            password=TIMESCALEDB_PASSWORD,
            database=TIMESCALEDB_DB
        )
        conn.autocommit = False
        cursor = conn.cursor()
        
        # Create table if not exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS nba_odds_snapshots (
                id SERIAL PRIMARY KEY,
                game_id VARCHAR(50),
                home_team_id INTEGER,
                away_team_id INTEGER,
                book_id VARCHAR(50),
                book_name VARCHAR(100),
                outcome_type VARCHAR(20),
                odds DECIMAL(10, 3),
                opening_odds DECIMAL(10, 3),
                odds_trend VARCHAR(20),
                snapshot_time TIMESTAMP DEFAULT NOW(),
                raw_data JSONB
            )
        """)
        conn.commit()
        
        # Insert odds data
        games = odds_data.get("games", [])
        inserted_count = 0
        
        for game in games:
            game_id = game.get("gameId")
            home_team = game.get("homeTeamId")
            away_team = game.get("awayTeamId")
            markets = game.get("markets", [])
            
            for market in markets:
                for book in market.get("books", []):
                    book_id = book.get("id")
                    book_name = book.get("name")
                    outcomes = book.get("outcomes", [])
                    
                    for outcome in outcomes:
                        cursor.execute("""
                            INSERT INTO nba_odds_snapshots 
                            (game_id, home_team_id, away_team_id, book_id, book_name, 
                             outcome_type, odds, opening_odds, odds_trend, raw_data)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """, (
                            game_id, home_team, away_team, book_id, book_name,
                            outcome.get("type"), outcome.get("odds"), 
                            outcome.get("opening_odds"), outcome.get("odds_trend"),
                            json.dumps(game)
                        ))
                        inserted_count += 1
        
        conn.commit()
        print(f"[OK] Inserted {inserted_count} odds records")
        cursor.close()
        conn.close()
        return True
        
    except Exception as e:
        print(f"[FAIL] TimescaleDB write error: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    # Fetch odds data
    data = fetch_todays_odds()
    
    if not data:
        return 1
    
    # Save to file for inspection
    output_file = "/tmp/nba_odds_today.json"
    with open(output_file, "w") as f:
        json.dump(data, f, indent=2)
    print(f"\n[OK] Data saved to {output_file}")
    
    # Write to Kafka
    kafka_success = write_to_kafka(data, KAFKA_BOOTSTRAP)
    
    # Write to TimescaleDB
    db_success = write_to_timescaledb(data)
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Kafka:    {'OK' if kafka_success else 'FAILED'}")
    print(f"  TimescaleDB: {'OK' if db_success else 'FAILED'}")
    print(f"  Games:    {len(data.get('games', []))}")
    print("=" * 60)
    
    return 0 if (kafka_success or db_success) else 1


if __name__ == "__main__":
    sys.exit(main())
