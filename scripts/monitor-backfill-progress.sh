#!/bin/bash
# Master monitoring script for NBA backfill progress
# Aggregates output from Kafka, TimescaleDB, and Ignite monitoring scripts
# Usage: ./scripts/monitor-backfill-progress.sh [--watch] [--interval SECONDS] [--season SEASON]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KAFKA_SCRIPT="${SCRIPT_DIR}/monitor-kafka-topics.sh"
TIMESCALE_SCRIPT="${SCRIPT_DIR}/monitor-timescaledb.sh"
IGNITE_SCRIPT="${SCRIPT_DIR}/monitor-ignite.sh"

# Default settings
WATCH_MODE=false
INTERVAL=30
SEASON=""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --watch)
            WATCH_MODE=true
            shift
            ;;
        --interval)
            INTERVAL="$2"
            shift 2
            ;;
        --season)
            SEASON="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 [--watch] [--interval SECONDS] [--season SEASON]"
            echo ""
            echo "Master monitoring script for NBA backfill progress."
            echo "Aggregates status from Kafka, TimescaleDB, and Ignite."
            echo ""
            echo "Options:"
            echo "  --watch           Continuously monitor (press Ctrl+C to stop)"
            echo "  --interval SECONDS  Refresh interval in seconds (default: 30)"
            echo "  --season SEASON   Filter TimescaleDB by season (e.g., '2022-23')"
            echo "  -h, --help        Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0                         # Single snapshot"
            echo "  $0 --watch                 # Continuous monitoring"
            echo "  $0 --watch --interval 60   # Monitor every minute"
            echo "  $0 --season 2022-23        # Filter by season"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Function to print section header
print_header() {
    echo ""
    echo -e "${CYAN}${BOLD}=== $1 ===${NC}"
    echo ""
}

# Function to run monitoring and capture output
run_monitoring() {
    local timescale_args=""
    if [ -n "$SEASON" ]; then
        timescale_args="--season $SEASON"
    fi
    
    echo -e "${CYAN}${BOLD}=== NBA Backfill Progress ===${NC}"
    echo "Timestamp: $(date -Iseconds)"
    if [ -n "$SEASON" ]; then
        echo "Season filter: $SEASON"
    fi
    echo ""
    
    # Kafka Topics
    print_header "Kafka Topics"
    "$KAFKA_SCRIPT" 2>&1 || echo "Error: Failed to fetch Kafka topic status"
    
    # TimescaleDB
    print_header "TimescaleDB"
    "$TIMESCALE_SCRIPT" $timescale_args 2>&1 || echo "Error: Failed to fetch TimescaleDB status"
    
    # Ignite
    print_header "Ignite Caches"
    "$IGNITE_SCRIPT" 2>&1 || echo "Error: Failed to fetch Ignite cache status"
    
    echo ""
    echo "---"
    echo "Press Ctrl+C to stop watching"
}

# Function to clear screen and show header
clear_and_header() {
    clear 2>/dev/null || true
    echo -e "${CYAN}${BOLD}=== NBA Backfill Progress ===${NC}"
    echo "Timestamp: $(date -Iseconds)"
    echo -e "${YELLOW}Refreshing every ${INTERVAL}s...${NC}"
    if [ -n "$SEASON" ]; then
        echo "Season filter: $SEASON"
    fi
    echo ""
}

# Check if individual scripts exist
for script in "$KAFKA_SCRIPT" "$TIMESCALE_SCRIPT" "$IGNITE_SCRIPT"; do
    if [ ! -f "$script" ]; then
        echo -e "${RED}Error: Required script not found: $script${NC}"
        exit 1
    fi
done

# Main execution
if [ "$WATCH_MODE" = true ]; then
    echo "Starting continuous monitoring..."
    echo "Press Ctrl+C to stop"
    sleep 2
    
    while true; do
        clear_and_header
        
        # Kafka Topics
        echo -e "${CYAN}${BOLD}--- Kafka Topics ---${NC}"
        "$KAFKA_SCRIPT" 2>&1 || echo "Error fetching Kafka status"
        
        # TimescaleDB
        echo ""
        echo -e "${CYAN}${BOLD}--- TimescaleDB ---${NC}"
        timescale_args=""
        if [ -n "$SEASON" ]; then
            timescale_args="--season $SEASON"
        fi
        "$TIMESCALE_SCRIPT" $timescale_args 2>&1 || echo "Error fetching TimescaleDB status"
        
        # Ignite
        echo ""
        echo -e "${CYAN}${BOLD}--- Ignite Caches ---${NC}"
        "$IGNITE_SCRIPT" 2>&1 || echo "Error fetching Ignite status"
        
        sleep "$INTERVAL"
    done
else
    # Single snapshot mode
    run_monitoring
fi
