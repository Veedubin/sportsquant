#!/usr/bin/env python3
"""Debug transform function."""

import sys

sys.path.insert(0, "/app")

import json
from kafka import KafkaConsumer
from src.data_pipeline.producer_config import get_transform_function


def main():
    # Get one message from nba-games
    consumer = KafkaConsumer(
        "nba-games",
        bootstrap_servers="sports-cluster-kafka-bootstrap:9092",
        auto_offset_reset="earliest",
        enable_auto_commit=True,
        group_id="debug-{}".format(__import__("time").time()),
        consumer_timeout_ms=5000,
    )

    for msg in consumer:
        if isinstance(msg.value, bytes):
            message_value = msg.value.decode("utf-8")
        else:
            message_value = str(msg.value)
        data = json.loads(message_value)
        print("Raw data type:", type(data))
        if isinstance(data, dict):
            print("Raw data keys:", list(data.keys()))
        else:
            print("Raw data is not a dict")
        print("Raw data (first 500 chars):", json.dumps(data, indent=2)[:500])

        transform_func = get_transform_function("transform_game_results")
        transformed = transform_func(data)
        print("\nTransformed type:", type(transformed))
        if isinstance(transformed, dict):
            print("Transformed keys:", list(transformed.keys()))
        else:
            print("Transformed is not a dict")
        print("Transformed (first 500 chars):", json.dumps(transformed, indent=2)[:500])
        break

    consumer.close()


if __name__ == "__main__":
    main()
