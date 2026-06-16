#!/usr/bin/env python3
"""NBA mock data backfill for testing the pipeline.

Generates sample NBA data and writes to Kafka topics for testing.
"""

import json
import logging
import random
import sys
from datetime import datetime, timedelta
from typing import Any

from kafka import KafkaProducer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

KAFKA_BOOTSTRAP = "sports-cluster-kafka-bootstrap:9092"

TEAMS = [
    {
        "TEAM_ID": "1610612737",
        "TEAM_NAME": "Atlanta Hawks",
        "TEAM_ABBREVIATION": "ATL",
        "TEAM_CITY": "Atlanta",
    },
    {
        "TEAM_ID": "1610612738",
        "TEAM_NAME": "Boston Celtics",
        "TEAM_ABBREVIATION": "BOS",
        "TEAM_CITY": "Boston",
    },
    {
        "TEAM_ID": "1610612751",
        "TEAM_NAME": "Brooklyn Nets",
        "TEAM_ABBREVIATION": "BKN",
        "TEAM_CITY": "Brooklyn",
    },
    {
        "TEAM_ID": "1610612766",
        "TEAM_NAME": "Charlotte Hornets",
        "TEAM_ABBREVIATION": "CHA",
        "TEAM_CITY": "Charlotte",
    },
    {
        "TEAM_ID": "1610612741",
        "TEAM_NAME": "Chicago Bulls",
        "TEAM_ABBREVIATION": "CHI",
        "TEAM_CITY": "Chicago",
    },
    {
        "TEAM_ID": "1610612739",
        "TEAM_NAME": "Cleveland Cavaliers",
        "TEAM_ABBREVIATION": "CLE",
        "TEAM_CITY": "Cleveland",
    },
    {
        "TEAM_ID": "1610612742",
        "TEAM_NAME": "Dallas Mavericks",
        "TEAM_ABBREVIATION": "DAL",
        "TEAM_CITY": "Dallas",
    },
    {
        "TEAM_ID": "1610612743",
        "TEAM_NAME": "Denver Nuggets",
        "TEAM_ABBREVIATION": "DEN",
        "TEAM_CITY": "Denver",
    },
    {
        "TEAM_ID": "1610612765",
        "TEAM_NAME": "Detroit Pistons",
        "TEAM_ABBREVIATION": "DET",
        "TEAM_CITY": "Detroit",
    },
    {
        "TEAM_ID": "1610612744",
        "TEAM_NAME": "Golden State Warriors",
        "TEAM_ABBREVIATION": "GSW",
        "TEAM_CITY": "Golden State",
    },
    {
        "TEAM_ID": "1610612745",
        "TEAM_NAME": "Houston Rockets",
        "TEAM_ABBREVIATION": "HOU",
        "TEAM_CITY": "Houston",
    },
    {
        "TEAM_ID": "1610612754",
        "TEAM_NAME": "Indiana Pacers",
        "TEAM_ABBREVIATION": "IND",
        "TEAM_CITY": "Indiana",
    },
    {
        "TEAM_ID": "1610612746",
        "TEAM_NAME": "LA Clippers",
        "TEAM_ABBREVIATION": "LAC",
        "TEAM_CITY": "Los Angeles",
    },
    {
        "TEAM_ID": "1610612747",
        "TEAM_NAME": "Los Angeles Lakers",
        "TEAM_ABBREVIATION": "LAL",
        "TEAM_CITY": "Los Angeles",
    },
    {
        "TEAM_ID": "1610612763",
        "TEAM_NAME": "Memphis Grizzlies",
        "TEAM_ABBREVIATION": "MEM",
        "TEAM_CITY": "Memphis",
    },
    {
        "TEAM_ID": "1610612748",
        "TEAM_NAME": "Miami Heat",
        "TEAM_ABBREVIATION": "MIA",
        "TEAM_CITY": "Miami",
    },
    {
        "TEAM_ID": "1610612749",
        "TEAM_NAME": "Milwaukee Bucks",
        "TEAM_ABBREVIATION": "MIL",
        "TEAM_CITY": "Milwaukee",
    },
    {
        "TEAM_ID": "1610612750",
        "TEAM_NAME": "Minnesota Timberwolves",
        "TEAM_ABBREVIATION": "MIN",
        "TEAM_CITY": "Minnesota",
    },
    {
        "TEAM_ID": "1610612740",
        "TEAM_NAME": "New Orleans Pelicans",
        "TEAM_ABBREVIATION": "NOP",
        "TEAM_CITY": "New Orleans",
    },
    {
        "TEAM_ID": "1610612752",
        "TEAM_NAME": "New York Knicks",
        "TEAM_ABBREVIATION": "NYK",
        "TEAM_CITY": "New York",
    },
    {
        "TEAM_ID": "1610612760",
        "TEAM_NAME": "Oklahoma City Thunder",
        "TEAM_ABBREVIATION": "OKC",
        "TEAM_CITY": "Oklahoma City",
    },
    {
        "TEAM_ID": "1610612753",
        "TEAM_NAME": "Orlando Magic",
        "TEAM_ABBREVIATION": "ORL",
        "TEAM_CITY": "Orlando",
    },
    {
        "TEAM_ID": "1610612755",
        "TEAM_NAME": "Philadelphia 76ers",
        "TEAM_ABBREVIATION": "PHI",
        "TEAM_CITY": "Philadelphia",
    },
    {
        "TEAM_ID": "1610612756",
        "TEAM_NAME": "Phoenix Suns",
        "TEAM_ABBREVIATION": "PHX",
        "TEAM_CITY": "Phoenix",
    },
    {
        "TEAM_ID": "1610612757",
        "TEAM_NAME": "Portland Trail Blazers",
        "TEAM_ABBREVIATION": "POR",
        "TEAM_CITY": "Portland",
    },
    {
        "TEAM_ID": "1610612758",
        "TEAM_NAME": "Sacramento Kings",
        "TEAM_ABBREVIATION": "SAC",
        "TEAM_CITY": "Sacramento",
    },
    {
        "TEAM_ID": "1610612759",
        "TEAM_NAME": "San Antonio Spurs",
        "TEAM_ABBREVIATION": "SAS",
        "TEAM_CITY": "San Antonio",
    },
    {
        "TEAM_ID": "1610612761",
        "TEAM_NAME": "Toronto Raptors",
        "TEAM_ABBREVIATION": "TOR",
        "TEAM_CITY": "Toronto",
    },
    {
        "TEAM_ID": "1610612762",
        "TEAM_NAME": "Utah Jazz",
        "TEAM_ABBREVIATION": "UTA",
        "TEAM_CITY": "Utah",
    },
    {
        "TEAM_ID": "1610612764",
        "TEAM_NAME": "Washington Wizards",
        "TEAM_ABBREVIATION": "WAS",
        "TEAM_CITY": "Washington",
    },
]

PLAYER_FIRST_NAMES = [
    "LeBron",
    "Steph",
    "Kevin",
    "Giannis",
    "Jayson",
    "Luka",
    "Nikola",
    "Kawhi",
    "Damian",
    "Joel",
    "Devin",
    "Anthony",
    "Jimmy",
    "Donovan",
    "Bradley",
    "Zion",
    "Ja",
    "De'Aaron",
    "Trae",
    "Brad",
]
PLAYER_LAST_NAMES = [
    "James",
    "Curry",
    "Durant",
    "Antetokounmpo",
    "Tatum",
    "Doncic",
    "Jokic",
    "Leonard",
    "Lillard",
    "Embiid",
    "Booker",
    "Edwards",
    "Butler",
    "Mitchell",
    "Beal",
    "Williamson",
    "Morant",
    "Fox",
    "Young",
    "Bill",
]

PLAYER_ID_COUNTER = 1000


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


def generate_player() -> dict[str, Any]:
    """Generate a mock player."""
    global PLAYER_ID_COUNTER
    PLAYER_ID_COUNTER += 1

    first_name = random.choice(PLAYER_FIRST_NAMES)
    last_name = random.choice(PLAYER_LAST_NAMES)

    return {
        "PERSON_ID": PLAYER_ID_COUNTER,
        "DISPLAY_FIRST_LAST": f"{first_name} {last_name}",
        "DISPLAY_LAST_COMMA_FIRST": f"{last_name}, {first_name}",
        "PLAYER_FIRST_NAME": first_name,
        "PLAYER_LAST_NAME": last_name,
        "POSITION": random.choice(["Guard", "Forward", "Center"]),
        "TEAM_ID": random.choice(TEAMS)["TEAM_ID"],
        "TEAM_ABBREVIATION": random.choice(TEAMS)["TEAM_ABBREVIATION"],
        "PLAYER_SLUG": f"{first_name.lower()}-{last_name.lower()}",
        "HEIGHT": f"{random.randint(5, 7)}'{random.randint(0, 11)}\"",
        "WEIGHT": random.randint(180, 280),
        "BIRTHDATE": f"{random.randint(1985, 2002)}-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}",
        "SCHOOL": random.choice(
            [
                "Duke",
                "Kentucky",
                "UCLA",
                "Kansas",
                "North Carolina",
                "Michigan",
                "Villanova",
            ]
        ),
        "ROSTERSTATUS": "Active",
        "FROM_YEAR": random.randint(2015, 2023),
        "TO_YEAR": "2024",
        "DLEAGUE_FLAG": "N",
        "NBA_FLAG": "Y",
        "GAMES_PLAYED_FLAG": "N",
    }


def generate_team() -> dict[str, Any]:
    """Generate mock team stats."""
    team = random.choice(TEAMS)
    return {
        "TEAM_ID": team["TEAM_ID"],
        "TEAM_NAME": team["TEAM_NAME"],
        "TEAM_ABBREVIATION": team["TEAM_ABBREVIATION"],
        "TEAM_CITY": team["TEAM_CITY"],
        "GP": random.randint(20, 50),
        "W": random.randint(10, 35),
        "L": random.randint(5, 25),
        "W_PCT": round(random.uniform(0.35, 0.85), 3),
        "MIN": round(random.uniform(90, 120), 1),
        "PTS": round(random.uniform(100, 120), 1),
        "FGM": round(random.uniform(35, 50), 1),
        "FGA": round(random.uniform(80, 100), 1),
        "FG_PCT": round(random.uniform(0.42, 0.52), 3),
        "FG3M": round(random.uniform(8, 18), 1),
        "FG3A": round(random.uniform(25, 45), 1),
        "FG3_PCT": round(random.uniform(0.32, 0.42), 3),
        "FTM": round(random.uniform(12, 25), 1),
        "FTA": round(random.uniform(15, 30), 1),
        "FT_PCT": round(random.uniform(0.70, 0.85), 3),
        "OREB": round(random.uniform(5, 15), 1),
        "DREB": round(random.uniform(30, 50), 1),
        "REB": round(random.uniform(38, 60), 1),
        "AST": round(random.uniform(18, 32), 1),
        "TOV": round(random.uniform(10, 20), 1),
        "STL": round(random.uniform(5, 12), 1),
        "BLK": round(random.uniform(3, 10), 1),
        "PF": round(random.uniform(15, 25), 1),
        "PTS_PAINT": round(random.uniform(30, 60), 1),
    }


def generate_game() -> dict[str, Any]:
    """Generate a mock game."""
    home_team = random.choice(TEAMS)
    away_team = random.choice(
        [t for t in TEAMS if t["TEAM_ID"] != home_team["TEAM_ID"]]
    )

    home_score = random.randint(85, 140)
    away_score = random.randint(85, 140)

    game_date = datetime.now() - timedelta(days=random.randint(0, 30))

    return {
        "SEASON_ID": "22024",
        "GAME_ID": f"00224{game_date.strftime('%Y%m%d')}{home_team['TEAM_ABBREVIATION']}",
        "GAME_DATE": game_date.strftime("%Y-%m-%d"),
        "MATCHUP": f"{home_team['TEAM_CITY']} vs {away_team['TEAM_CITY']}",
        "TEAM_ID": home_team["TEAM_ID"],
        "TEAM_ABBREVIATION": home_team["TEAM_ABBREVIATION"],
        "TEAM_NAME": home_team["TEAM_NAME"],
        "PTS_HOME": home_score,
        "PTS_AWAY": away_score,
        "WIN": "Y" if home_score > away_score else "N",
        "HOME_TEAM_WINS": 1 if home_score > away_score else 0,
    }


def generate_player_stats(
    game: dict[str, Any], player: dict[str, Any]
) -> dict[str, Any]:
    """Generate mock player stats for a game."""
    return {
        "SEASON_ID": "22024",
        "GAME_ID": game["GAME_ID"],
        "GAME_DATE": game["GAME_DATE"],
        "MATCHUP": game["MATCHUP"],
        "TEAM_ID": player["TEAM_ID"],
        "TEAM_ABBREVIATION": player["TEAM_ABBREVIATION"],
        "PLAYER_ID": player["PERSON_ID"],
        "PLAYER_NAME": player["DISPLAY_FIRST_LAST"],
        "POSITION": player["POSITION"],
        "COMMENT": "",
        "MIN": f"{random.randint(15, 40)}:{random.randint(0, 59):02d}",
        "FGM": random.randint(2, 15),
        "FGA": random.randint(5, 30),
        "FG_PCT": round(random.uniform(0.30, 0.60), 3),
        "FG3M": random.randint(0, 6),
        "FG3A": random.randint(0, 12),
        "FG3_PCT": round(random.uniform(0.25, 0.50), 3) if random.random() > 0.3 else 0,
        "FTM": random.randint(0, 10),
        "FTA": random.randint(0, 12),
        "FT_PCT": round(random.uniform(0.65, 0.90), 3),
        "OREB": random.randint(0, 5),
        "DREB": random.randint(1, 10),
        "REB": random.randint(2, 15),
        "AST": random.randint(1, 12),
        "STL": random.randint(0, 4),
        "BLK": random.randint(0, 3),
        "TOV": random.randint(0, 5),
        "PF": random.randint(1, 6),
        "PTS": random.randint(5, 40),
        "PLUS_MINUS": random.randint(-20, 20),
    }


def backfill_players(producer: KafkaProducer, count: int = 50) -> int:
    """Backfill mock players."""
    logger.info(f"Backfilling {count} mock players")
    published = 0

    for i in range(count):
        player = generate_player()
        player["fetched_at"] = datetime.now().isoformat()
        player["season"] = "2024-25"

        try:
            publish_to_kafka(producer, "nba-players", player)
            published += 1
            if published % 10 == 0:
                logger.info(f"Published {published}/{count} players")
        except Exception as e:
            logger.warning(f"Failed to publish player: {e}")

    logger.info(f"Published {published} players to nba-players topic")
    return published


def backfill_teams(producer: KafkaProducer) -> int:
    """Backfill mock teams."""
    logger.info("Backfilling mock teams")
    published = 0

    for team in TEAMS:
        team_stats = generate_team()
        team_stats.update(team)
        team_stats["fetched_at"] = datetime.now().isoformat()
        team_stats["season"] = "2024-25"

        try:
            publish_to_kafka(producer, "nba-teams", team_stats)
            published += 1
        except Exception as e:
            logger.warning(f"Failed to publish team: {e}")

    logger.info(f"Published {published} teams to nba-teams topic")
    return published


def backfill_games(producer: KafkaProducer, count: int = 100) -> int:
    """Backfill mock games."""
    logger.info(f"Backfilling {count} mock games")
    published = 0

    for i in range(count):
        game = generate_game()
        game["fetched_at"] = datetime.now().isoformat()
        game["season"] = "2024-25"

        try:
            publish_to_kafka(producer, "nba-games", game)
            published += 1
            if published % 25 == 0:
                logger.info(f"Published {published}/{count} games")
        except Exception as e:
            logger.warning(f"Failed to publish game: {e}")

    logger.info(f"Published {published} games to nba-games topic")
    return published


def backfill_schedule(producer: KafkaProducer, count: int = 50) -> int:
    """Backfill mock schedule entries."""
    logger.info(f"Backfilling {count} mock schedule entries")
    published = 0

    for i in range(count):
        game_date = datetime.now() + timedelta(days=random.randint(1, 14))
        home_team = random.choice(TEAMS)
        away_team = random.choice(
            [t for t in TEAMS if t["TEAM_ID"] != home_team["TEAM_ID"]]
        )

        schedule_entry = {
            "GAME_ID": f"00224{game_date.strftime('%Y%m%d')}{home_team['TEAM_ABBREVIATION']}",
            "GAME_DATE": game_date.strftime("%Y-%m-%d"),
            "GAME_TIME": f"{random.randint(12, 21)}:{random.choice(['00', '15', '30', '45'])}:00",
            "HOME_TEAM_ID": home_team["TEAM_ID"],
            "HOME_TEAM_CITY": home_team["TEAM_CITY"],
            "HOME_TEAM_NAME": home_team["TEAM_NAME"],
            "HOME_TEAM_ABBREVIATION": home_team["TEAM_ABBREVIATION"],
            "AWAY_TEAM_ID": away_team["TEAM_ID"],
            "AWAY_TEAM_CITY": away_team["TEAM_CITY"],
            "AWAY_TEAM_NAME": away_team["TEAM_NAME"],
            "AWAY_TEAM_ABBREVIATION": away_team["TEAM_ABBREVIATION"],
            "STATUS": "Scheduled",
            "STATUS_DESC": "Scheduled",
            "fetched_at": datetime.now().isoformat(),
            "season": "2024-25",
        }

        try:
            publish_to_kafka(producer, "nba-schedule", schedule_entry)
            published += 1
        except Exception as e:
            logger.warning(f"Failed to publish schedule entry: {e}")

    logger.info(f"Published {published} schedule entries to nba-schedule topic")
    return published


def backfill_player_stats(
    producer: KafkaProducer, games_count: int = 50, players_per_game: int = 10
) -> int:
    """Backfill mock player stats."""
    logger.info(f"Backfilling {games_count * players_per_game} mock player stats")
    published = 0

    players = [generate_player() for _ in range(20)]

    for _ in range(games_count):
        game = generate_game()

        team_players = [p for p in players if p["TEAM_ID"] == game["TEAM_ID"]]
        if len(team_players) < 5:
            team_players = random.sample(players, min(5, len(players)))

        for player in random.sample(
            team_players, min(players_per_game, len(team_players))
        ):
            stats = generate_player_stats(game, player)
            stats["fetched_at"] = datetime.now().isoformat()
            stats["season"] = "2024-25"

            try:
                publish_to_kafka(producer, "nba-player-logs", stats)
                published += 1
            except Exception as e:
                logger.warning(f"Failed to publish player stats: {e}")

    logger.info(f"Published {published} player stat entries to nba-player-logs topic")
    return published


def main():
    """Run backfill."""
    logger.info("Starting NBA mock data backfill")

    producer = create_kafka_producer()

    total = 0
    total += backfill_players(producer, count=50)
    total += backfill_teams(producer)
    total += backfill_games(producer, count=100)
    total += backfill_schedule(producer, count=50)
    total += backfill_player_stats(producer, games_count=50, players_per_game=10)

    producer.flush()
    producer.close()

    logger.info(f"Mock backfill complete. Total messages published: {total}")
    logger.info(
        "Data pipeline will now transform and route to Spark topics and TimescaleDB"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
