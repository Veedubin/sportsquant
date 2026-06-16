#!/usr/bin/env python3
"""Simple NBA backfill script.

Fetches data from stats.nba.com using Playwright and writes to Kafka topics.
"""

import json
import logging
import sys
from datetime import datetime
from typing import Any

from kafka import KafkaProducer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

KAFKA_BOOTSTRAP = "sports-cluster-kafka-bootstrap:9092"


def create_kafka_producer() -> KafkaProducer:
    """Create Kafka producer."""
    return KafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        acks="all",
        retries=3,
    )


def publish_to_kafka(producer: KafkaProducer, topic: str, data: dict[str, Any]) -> None:
    """Publish data to Kafka topic."""
    future = producer.send(topic, value=data)
    future.get(timeout=10)


def backfill_players(producer: KafkaProducer, season: str = "2024-25") -> int:
    """Backfill NBA players."""
    from nba_stats_package.browser import NBAStatsBrowser, RateLimitConfig

    logger.info(f"Backfilling players for season {season}")
    count = 0

    try:
        rate_limit = RateLimitConfig(
            min_interval_s=1.0,
            max_retries=3,
            max_backoff_s=10.0,
        )

        with NBAStatsBrowser(headless=True, rate_limit=rate_limit) as browser:
            payload = browser.get_json(
                "https://stats.nba.com/stats/commonallplayers",
                params={
                    "LeagueID": "00",
                    "Season": season,
                    "IsOnlyCurrentSeason": 0,
                },
            )

            if "resultSets" in payload:
                row_set = payload["resultSets"][0].get("rowSet", [])
                headers = payload["resultSets"][0].get("headers", [])

                logger.info(f"Got {len(row_set)} players")

                for row in row_set:
                    player_data = {}
                    for i, header in enumerate(headers):
                        player_data[header] = row[i] if i < len(row) else None

                    player_data["fetched_at"] = datetime.now().isoformat()
                    player_data["season"] = season

                    try:
                        publish_to_kafka(producer, "nba-players", player_data)
                        count += 1
                    except Exception as e:
                        logger.warning(f"Failed to publish player: {e}")

                logger.info(f"Published {count} players to nba-players topic")

    except Exception as e:
        logger.error(f"Failed to backfill players: {e}")
        import traceback

        traceback.print_exc()

    return count


def backfill_teams(producer: KafkaProducer, season: str = "2024-25") -> int:
    """Backfill NBA teams."""
    from nba_stats_package.browser import NBAStatsBrowser, RateLimitConfig

    logger.info(f"Backfilling teams for season {season}")
    count = 0

    try:
        rate_limit = RateLimitConfig(
            min_interval_s=1.0,
            max_retries=3,
            max_backoff_s=10.0,
        )

        with NBAStatsBrowser(headless=True, rate_limit=rate_limit) as browser:
            payload = browser.get_json(
                "https://stats.nba.com/stats/leaguedashteamstats",
                params={
                    "LeagueID": "00",
                    "Season": season,
                    "SeasonType": "Regular Season",
                    "MeasureType": "Base",
                    "PerMode": "Totals",
                    "PlusMinus": "N",
                    "Rank": "N",
                },
            )

            if "resultSets" in payload:
                row_set = payload["resultSets"][0].get("rowSet", [])
                headers = payload["resultSets"][0].get("headers", [])

                logger.info(f"Got {len(row_set)} teams")

                for row in row_set:
                    team_data = {}
                    for i, header in enumerate(headers):
                        team_data[header] = row[i] if i < len(row) else None

                    team_data["fetched_at"] = datetime.now().isoformat()
                    team_data["season"] = season

                    try:
                        publish_to_kafka(producer, "nba-teams", team_data)
                        count += 1
                    except Exception as e:
                        logger.warning(f"Failed to publish team: {e}")

                logger.info(f"Published {count} teams to nba-teams topic")

    except Exception as e:
        logger.error(f"Failed to backfill teams: {e}")
        import traceback

        traceback.print_exc()

    return count


def backfill_schedule(producer: KafkaProducer, season: str = "2024-25") -> int:
    """Backfill NBA schedule."""
    from nba_stats_package.browser import NBAStatsBrowser, RateLimitConfig

    logger.info(f"Backfilling schedule for season {season}")
    count = 0

    try:
        rate_limit = RateLimitConfig(
            min_interval_s=1.0,
            max_retries=3,
            max_backoff_s=10.0,
        )

        with NBAStatsBrowser(headless=True, rate_limit=rate_limit) as browser:
            payload = browser.get_json(
                "https://stats.nba.com/stats/schedule",
                params={
                    "LeagueID": "00",
                    "Season": season,
                },
            )

            if "resultSets" in payload:
                for result_set in payload["resultSets"]:
                    row_set = result_set.get("rowSet", [])
                    headers = result_set.get("headers", [])

                    if not row_set:
                        continue

                    logger.info(
                        f"Got {len(row_set)} schedule entries from {result_set.get('name', 'unknown')}"
                    )

                    for row in row_set:
                        schedule_data = {}
                        for i, header in enumerate(headers):
                            schedule_data[header] = row[i] if i < len(row) else None

                        schedule_data["fetched_at"] = datetime.now().isoformat()
                        schedule_data["season"] = season

                        try:
                            publish_to_kafka(producer, "nba-schedule", schedule_data)
                            count += 1
                        except Exception as e:
                            logger.warning(f"Failed to publish schedule entry: {e}")

                logger.info(f"Published {count} schedule entries to nba-schedule topic")

    except Exception as e:
        logger.error(f"Failed to backfill schedule: {e}")
        import traceback

        traceback.print_exc()

    return count


def backfill_games(producer: KafkaProducer, season: str = "2024-25") -> int:
    """Backfill NBA game results."""
    from nba_stats_package.browser import NBAStatsBrowser, RateLimitConfig

    logger.info(f"Backfilling games for season {season}")
    count = 0

    try:
        rate_limit = RateLimitConfig(
            min_interval_s=1.0,
            max_retries=3,
            max_backoff_s=10.0,
        )

        with NBAStatsBrowser(headless=True, rate_limit=rate_limit) as browser:
            payload = browser.get_json(
                "https://stats.nba.com/stats/leaguegamelog",
                params={
                    "LeagueID": "00",
                    "Season": season,
                    "SeasonType": "Regular Season",
                    "Counter": "1000",
                    "Sorter": "DATE",
                    "Direction": "DESC",
                },
            )

            if "resultSets" in payload:
                row_set = payload["resultSets"][0].get("rowSet", [])
                headers = payload["resultSets"][0].get("headers", [])

                logger.info(f"Got {len(row_set)} games")

                for row in row_set:
                    game_data = {}
                    for i, header in enumerate(headers):
                        game_data[header] = row[i] if i < len(row) else None

                    game_data["fetched_at"] = datetime.now().isoformat()
                    game_data["season"] = season

                    try:
                        publish_to_kafka(producer, "nba-games", game_data)
                        count += 1
                    except Exception as e:
                        logger.warning(f"Failed to publish game: {e}")

                logger.info(f"Published {count} games to nba-games topic")

    except Exception as e:
        logger.error(f"Failed to backfill games: {e}")
        import traceback

        traceback.print_exc()

    return count


def backfill_player_stats(producer: KafkaProducer, season: str = "2024-25") -> int:
    """Backfill NBA player stats."""
    from nba_stats_package.browser import NBAStatsBrowser, RateLimitConfig

    logger.info(f"Backfilling player stats for season {season}")
    count = 0

    try:
        rate_limit = RateLimitConfig(
            min_interval_s=1.0,
            max_retries=3,
            max_backoff_s=10.0,
        )

        with NBAStatsBrowser(headless=True, rate_limit=rate_limit) as browser:
            payload = browser.get_json(
                "https://stats.nba.com/stats/leaguegamelog",
                params={
                    "LeagueID": "00",
                    "Season": season,
                    "SeasonType": "Regular Season",
                    "Counter": "1000",
                    "Sorter": "DATE",
                    "Direction": "DESC",
                    "PlayerOrTeam": "Player",
                },
            )

            if "resultSets" in payload:
                row_set = payload["resultSets"][0].get("rowSet", [])
                headers = payload["resultSets"][0].get("headers", [])

                logger.info(f"Got {len(row_set)} player stat entries")

                for row in row_set:
                    stats_data = {}
                    for i, header in enumerate(headers):
                        stats_data[header] = row[i] if i < len(row) else None

                    stats_data["fetched_at"] = datetime.now().isoformat()
                    stats_data["season"] = season

                    try:
                        publish_to_kafka(producer, "nba-player-logs", stats_data)
                        count += 1
                    except Exception as e:
                        logger.warning(f"Failed to publish player stats: {e}")

                logger.info(
                    f"Published {count} player stat entries to nba-player-logs topic"
                )

    except Exception as e:
        logger.error(f"Failed to backfill player stats: {e}")
        import traceback

        traceback.print_exc()

    return count


def main():
    """Run backfill."""
    logger.info("Starting NBA backfill")

    producer = create_kafka_producer()

    total = 0
    total += backfill_players(producer)
    total += backfill_teams(producer)
    total += backfill_schedule(producer)
    total += backfill_games(producer)
    total += backfill_player_stats(producer)

    producer.flush()
    producer.close()

    logger.info(f"Backfill complete. Total messages published: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
