#!/usr/bin/env python3
"""Simple Kafka consumer that writes NBA games to TimescaleDB."""
import json
import os
import sys
from datetime import datetime

from kafka import KafkaConsumer
import psycopg2

# Configuration
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "sports-cluster-kafka-bootstrap:9092")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "timescaledb.default.svc")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_DB = os.getenv("POSTGRES_DB", "sports_analytics")
POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "password")
TOPIC = os.getenv("KAFKA_TOPIC", "nba-games")
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "100"))

def get_connection():
    return psycopg2.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        database=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD
    )

def ensure_table(conn):
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS nba_games (
                game_id TEXT NOT NULL,
                season TEXT,
                season_type TEXT DEFAULT 'Regular Season',
                game_date DATE,
                matchup TEXT,
                team_id INTEGER,
                team_abbreviation TEXT,
                points INTEGER,
                opponent_id INTEGER DEFAULT 0,
                outcome TEXT DEFAULT '',
                fetched_at TIMESTAMP DEFAULT NOW(),
                timestamp TIMESTAMP DEFAULT NOW()
            )
        """)
        conn.commit()
        print("Table ensured")

def insert_records(conn, records):
    if not records:
        return 0
    
    with conn.cursor() as cur:
        for record in records:
            value = record.value
            if not isinstance(value, dict):
                continue
                
            game_id = value.get("game_id")
            season = value.get("season")
            season_type = value.get("season_type", "Regular Season")
            game_date = value.get("game_date")
            matchup = value.get("matchup")
            team_id = value.get("team_id")
            team_abbreviation = value.get("team_abbreviation")
            points = value.get("points")
            opponent_id = value.get("opponent_id", 0)
            outcome = value.get("outcome", "")
            fetched_at = value.get("fetched_at")
            
            cur.execute("""
                INSERT INTO nba_games (game_id, season, season_type, game_date, matchup, team_id, team_abbreviation, points, opponent_id, outcome, fetched_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (game_id) DO NOTHING
            """, (game_id, season, season_type, game_date, matchup, team_id, team_abbreviation, points, opponent_id, outcome, fetched_at))
        
        conn.commit()
        return len(records)

def main():
    print(f"Connecting to Kafka at {KAFKA_BOOTSTRAP}...")
    consumer = KafkaConsumer(
        TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP,
        auto_offset_reset="earliest",
        enable_auto_commit=True,
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        consumer_timeout_ms=10000
    )
    
    print(f"Connected. Subscribed to {TOPIC}")
    
    conn = get_connection()
    ensure_table(conn)
    
    batch = []
    total_inserted = 0
    
    try:
        for message in consumer:
            batch.append(message)
            if len(batch) >= BATCH_SIZE:
                inserted = insert_records(conn, batch)
                total_inserted += inserted
                print(f"Inserted {inserted} records (total: {total_inserted})")
                batch = []
    except KeyboardInterrupt:
        pass
    finally:
        if batch:
            inserted = insert_records(conn, batch)
            total_inserted += inserted
            print(f"Final batch: inserted {inserted} records (total: {total_inserted})")
        
        consumer.close()
        conn.close()
        print(f"Done. Total records inserted: {total_inserted}")

if __name__ == "__main__":
    main()
