#!/usr/bin/env python3
"""
JSON test producer for verifying Kafka → TimescaleDB pipeline.
Simpler approach without Avro complexity.
"""
import json
import time
import sys
from datetime import datetime, timezone

try:
    from kafka import KafkaProducer
except ImportError:
    print("ERROR: kafka-python not installed. Install with: pip install kafka-python")
    sys.exit(1)

KAFKA_BOOTSTRAP = "sports-cluster-kafka-bootstrap.default.svc:9092"
NBA_PLAYER_STATS_TOPIC = "sports-analytics-player-stats"


def create_test_record(player_num: int) -> dict:
    """Create a test NBA player stats record."""
    base_time = datetime(2025, 1, 26, 12, 0, 0, tzinfo=timezone.utc)
    timestamp_ms = int(base_time.timestamp() * 1000)
    
    return {
        "game_id": f"002240001{player_num}",
        "season": 2024,
        "season_type": "Regular Season",
        "game_date": "2025-01-26",
        "matchup": f"LAL vs GSW",
        "player_id": f"p{player_num:04d}",
        "player_name": f"Test Player {player_num}",
        "team": "Los Angeles Lakers",
        "team_abbreviation": "LAL",
        "points": 10.0 + player_num,
        "rebounds": 5.0 + player_num * 0.5,
        "assists": 3.0 + player_num * 0.2,
        "minutes": 20.0 + player_num,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "timestamp": timestamp_ms
    }


def produce_json_record(topic: str, key: str, record: dict) -> bool:
    """Produce a JSON-encoded record to Kafka."""
    try:
        producer = KafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP,
            client_id=f"json-test-{__import__('socket').gethostname()}",
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            key_serializer=lambda k: k.encode('utf-8'),
            acks='all',
            retries=3
        )
        
        future = producer.send(topic, key=key, value=record)
        record_metadata = future.get(timeout=10)
        print(f"✅ Produced to {topic}: partition={record_metadata.partition}, offset={record_metadata.offset}")
        producer.close()
        return True
    except Exception as e:
        print(f"❌ Failed to produce: {e}")
        return False


def check_timescaledb_for_records(expected_count: int, timeout: int = 30) -> bool:
    """Check if records were inserted into TimescaleDB."""
    import subprocess
    
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        try:
            result = subprocess.run([
                'kubectl', 'exec', 'timescaledb-0', '--',
                'psql', '-U', 'postgres', '-d', 'sports_analytics', '-t',
                '-c', f"SELECT COUNT(*) FROM nba_player_stats WHERE game_id LIKE '002240001%';"
            ], capture_output=True, text=True, timeout=5)
            
            count = int(result.stdout.strip() or 0)
            print(f"📊 Records in TimescaleDB: {count}")
            
            if count >= expected_count:
                print(f"✅ Found {count} records in TimescaleDB!")
                return True
            
        except Exception as e:
            print(f"⚠️  Query error (retrying): {e}")
        
        time.sleep(2)
    
    print(f"❌ Timeout waiting for records in TimescaleDB")
    return False


def main():
    print("=" * 60)
    print("JSON Test Producer for Kafka → TimescaleDB Pipeline")
    print("=" * 60)
    
    # Step 1: Produce test records
    print("\n📤 Producing 3 test records to Kafka...")
    records_to_produce = 3
    
    for i in range(1, records_to_produce + 1):
        record = create_test_record(i)
        key = record["player_id"]
        
        print(f"\n  Record {i}: {record['player_name']}")
        success = produce_json_record(NBA_PLAYER_STATS_TOPIC, key, record)
        if not success:
            print(f"❌ Failed to produce record {i}")
            return 1
    
    # Step 2: Wait for Kafka Connect to process
    print("\n⏳ Waiting for Kafka Connect to process records...")
    time.sleep(5)
    
    # Step 3: Verify TimescaleDB
    print("\n🔍 Verifying TimescaleDB insertion...")
    success = check_timescaledb_for_records(records_to_produce, timeout=30)
    
    print("\n" + "=" * 60)
    if success:
        print("✅ PIPELINE VERIFICATION SUCCESSFUL!")
        print("=" * 60)
        return 0
    else:
        print("❌ PIPELINE VERIFICATION FAILED!")
        print("Check Kafka Connect logs: kubectl logs -l app=sports-connect -f")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    exit(main())
