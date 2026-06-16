#!/bin/bash
# Create JDBC sink connectors for TimescaleDB
# Updated field whitelists to match actual data format from spark-data-producer

KAFKA_CONNECT_URL="http://sports-connect-standalone:8083"

# Connector for NBA games
curl -X POST "${KAFKA_CONNECT_URL}/connectors" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "nba-games-jdbc-sink",
    "config": {
      "connector.class": "io.confluent.connect.jdbc.JdbcSinkConnector",
      "topics": "sports-analytics-game-results",
      "connection.url": "jdbc:postgresql://timescaledb.default.svc:5432/sports_analytics",
      "connection.user": "postgres",
      "connection.password": "password",
      "table.name.format": "nba_games",
      "pk.mode": "none",
      "insert.mode": "upsert",
      "fields.whitelist": "game_id,season,game_date,matchup,team_id,team_abbreviation,points,opponent_id,outcome,fetched_at",
      "errors.tolerance": "all",
      "errors.log.enable": "true"
    }
  }'

echo ""

# Connector for NBA player stats - FIXED field whitelist to match actual data
curl -X POST "${KAFKA_CONNECT_URL}/connectors" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "nba-player-stats-jdbc-sink-v2",
    "config": {
      "connector.class": "io.confluent.connect.jdbc.JdbcSinkConnector",
      "topics": "sports-analytics-player-stats",
      "connection.url": "jdbc:postgresql://timescaledb.default.svc:5432/sports_analytics",
      "connection.user": "postgres",
      "connection.password": "password",
      "table.name.format": "nba_player_stats",
      "pk.mode": "none",
      "insert.mode": "upsert",
      "fields.whitelist": "game_id,season,game_date,player_id,season_type,matchup,points,rebounds,assists,minutes,fetched_at",
      "errors.tolerance": "all",
      "errors.log.enable": "true"
    }
  }'

echo ""
echo "Checking connector status..."
sleep 5
curl -s "${KAFKA_CONNECT_URL}/connectors"
