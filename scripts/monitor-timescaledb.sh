#!/bin/bash
# Monitor TimescaleDB record counts for NBA tables
# Usage: ./scripts/monitor-timescaledb.sh [--season SEASON]
#   Optional: Filter by season (e.g., "2022-23")

set -e

TIMESCALEDB_NAMESPACE="default"
TIMESCALEDB_POD="timescaledb-0"
DATABASE="sports_analytics"
NBA_TABLES=("nba_games" "nba_player_stats" "nba_teams" "nba_players")

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Function to get total count for a table
get_table_count() {
    local table=$1
    local count=$(kubectl exec -n "$TIMESCALEDB_NAMESPACE" "$TIMESCALEDB_POD" -- \
        psql -U postgres -d "$DATABASE" -t -c "SELECT COUNT(*) FROM $table;" 2>/dev/null | \
        tr -d ' ' || echo "0")
    echo "$count"
}

# Function to get count by season
get_count_by_season() {
    local table=$1
    local season=$2
    
    # Check if table has season column
    local has_season=$(kubectl exec -n "$TIMESCALEDB_NAMESPACE" "$TIMESCALEDB_POD" -- \
        psql -U postgres -d "$DATABASE" -t -c "
        SELECT column_name FROM information_schema.columns 
        WHERE table_name = '$table' AND column_name LIKE '%season%';" 2>/dev/null | \
        grep -c season || echo "0")
    
    if [ "$has_season" -gt 0 ] && [ -n "$season" ]; then
        local count=$(kubectl exec -n "$TIMESCALEDB_NAMESPACE" "$TIMESCALEDB_POD" -- \
            psql -U postgres -d "$DATABASE" -t -c "
            SELECT COUNT(*) FROM $table 
            WHERE season = '$season' OR season LIKE '%$season%';" 2>/dev/null | \
            tr -d ' ' || echo "0")
        echo "$count"
    else
        echo "N/A"
    fi
}

# Function to get all seasons from a table
get_seasons() {
    local table=$1
    local seasons=$(kubectl exec -n "$TIMESCALEDB_NAMESPACE" "$TIMESCALEDB_POD" -- \
        psql -U postgres -d "$DATABASE" -t -c "
        SELECT DISTINCT season FROM $table ORDER BY season DESC LIMIT 5;" 2>/dev/null | \
        tr -d '\n' || echo "")
    echo "$seasons"
}

# Function to format number with commas
format_number() {
    local num=$1
    if [ "$num" = "N/A" ]; then
        echo "N/A"
    else
        printf "%'d" "$num"
    fi
}

# Parse arguments
SEASON=""
while [[ $# -gt 0 ]]; do
    case $1 in
        --season)
            SEASON="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 [--season SEASON]"
            echo ""
            echo "Monitor TimescaleDB record counts for NBA tables."
            echo ""
            echo "Options:"
            echo "  --season SEASON    Filter by season (e.g., '2022-23')"
            echo ""
            echo "Examples:"
            echo "  $0                         # Show all NBA table counts"
            echo "  $0 --season 2022-23        # Show counts for 2022-23 season"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

echo "=== TimescaleDB NBA Tables ==="
echo "Timestamp: $(date -Iseconds)"
if [ -n "$SEASON" ]; then
    echo "Season filter: $SEASON"
fi
echo ""

printf "%-20s %15s %15s\n" "TABLE" "TOTAL" "BY SEASON"
printf "%-20s %15s %15s\n" "─────" "─────" "────────"

for table in "${NBA_TABLES[@]}"; do
    total=$(get_table_count "$table")
    total_fmt=$(format_number "$total")
    
    if [ -n "$SEASON" ]; then
        by_season=$(get_count_by_season "$table" "$SEASON")
        by_season_fmt=$(format_number "$by_season")
    else
        by_season_fmt="(all seasons)"
    fi
    
    printf "%-20s %15s %15s\n" "$table" "$total_fmt" "$by_season_fmt"
done

echo ""
echo "Tables monitored:"
for table in "${NBA_TABLES[@]}"; do
    echo "  - $table"
done

if [ -z "$SEASON" ]; then
    echo ""
    echo "Tip: Use --season to filter by specific season"
fi
