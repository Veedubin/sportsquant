#!/usr/bin/env python3
"""Run backfill from inside the cluster."""

import sys

sys.path.insert(0, "/app")

import logging

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

from src.data_pipeline.spark_topic_backfill import backfill_topic
from src.data_pipeline.producer_config import NBA_TOPIC_MAPPINGS


def main():
    results = {}
    for mapping in NBA_TOPIC_MAPPINGS:
        print(f"Backfilling {mapping.source_topic} -> {mapping.spark_topic}")
        processed, published = backfill_topic(
            mapping.source_topic, mapping.spark_topic, mapping.transform_func
        )
        results[mapping.source_topic] = (processed, published)
        print(f"  Processed: {processed}, Published: {published}")

    total_processed = sum(p for p, _ in results.values())
    total_published = sum(pub for _, pub in results.values())
    print(f"\nTotal: processed={total_processed}, published={total_published}")

    if total_processed == 0:
        print("WARNING: No messages were processed!")
        sys.exit(1)

    print("Backfill completed successfully!")
    sys.exit(0)


if __name__ == "__main__":
    main()
