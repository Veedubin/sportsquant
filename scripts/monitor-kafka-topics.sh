#!/bin/bash
# Monitor Kafka topic message counts and consumer lag
# Usage: ./scripts/monitor-kafka-topics.sh [topic_name]
#   If no topic specified, shows all NBA topics

set -e

KAFKA_NAMESPACE="kafka"
KAFKA_POD="kafka-cluster-kafka-0"
NBA_TOPICS=("nba-games" "nba-schedule" "nba-player-logs" "nba-teams" "nba-players")

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Function to get topic message count
get_topic_count() {
    local topic=$1
    local output=$(kubectl exec -n "$KAFKA_NAMESPACE" "$KAFKA_POD" -- \
        kafka-run-class.sh kafka.tools.GetOffsetShell \
        --broker-list localhost:9092 \
        --topic "$topic" \
        --time -1 2>/dev/null || echo "")
    
    if [ -z "$output" ]; then
        echo "0"
        return
    fi
    
    # Parse output: topic:partition:offset
    local count=0
    while IFS=':' read -r t p o; do
        count=$((count + o))
    done <<< "$output"
    echo "$count"
}

# Function to get consumer group lag
get_consumer_lag() {
    local topic=$1
    # Try to find consumer groups for this topic
    local group=$(kubectl exec -n "$KAFKA_NAMESPACE" "$KAFKA_POD" -- \
        kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
        --describe --all-groups 2>/dev/null | \
        grep "$topic" | head -1 | awk '{print $1}' || echo "")
    
    if [ -z "$group" ]; then
        echo "N/A"
        return
    fi
    
    local lag=$(kubectl exec -n "$KAFKA_NAMESPACE" "$KAFKA_POD" -- \
        kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
        --describe --group "$group" 2>/dev/null | \
        grep "$topic" | awk '{sum+=$NF} END {print sum+0}' || echo "0")
    
    echo "$lag"
}

# Function to get partition count
get_partition_count() {
    local topic=$1
    local partitions=$(kubectl exec -n "$KAFKA_NAMESPACE" "$KAFKA_POD" -- \
        kafka-topics.sh --bootstrap-server localhost:9092 \
        --describe --topic "$topic" 2>/dev/null | \
        grep "PartitionCount" | awk '{print $2}' || echo "0")
    echo "$partitions"
}

# Function to format number with commas
format_number() {
    local num=$1
    printf "%'d" "$num"
}

# Display usage if help requested
if [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
    echo "Usage: $0 [topic_name]"
    echo ""
    echo "Monitor Kafka topic message counts and consumer lag."
    echo ""
    echo "Arguments:"
    echo "  topic_name    Optional. Specific topic to monitor."
    echo "                If not provided, monitors all NBA topics."
    echo ""
    echo "Output format:"
    echo "  topic, partition count, message count, consumer lag"
    echo ""
    echo "Examples:"
    echo "  $0                     # Monitor all NBA topics"
    echo "  $0 nba-games           # Monitor specific topic"
    echo "  $0 nba-schedule        # Monitor schedule topic"
    exit 0
fi

# Determine which topics to monitor
if [ -n "$1" ]; then
    TOPICS=("$1")
else
    TOPICS=("${NBA_TOPICS[@]}")
fi

echo "=== Kafka Topic Status ==="
echo "Timestamp: $(date -Iseconds)"
echo ""
printf "%-20s %10s %15s %10s\n" "TOPIC" "PARTITIONS" "MESSAGES" "LAG"
printf "%-20s %10s %15s %10s\n" "─────" "─────────" "────────" "───"

for topic in "${TOPICS[@]}"; do
    partitions=$(get_partition_count "$topic")
    messages=$(get_topic_count "$topic")
    lag=$(get_consumer_lag "$topic")
    
    # Format numbers with commas
    partitions_fmt=$(format_number "$partitions")
    messages_fmt=$(format_number "$messages")
    
    # Color code lag
    if [ "$lag" = "N/A" ]; then
        lag_color="${YELLOW}$lag${NC}"
    elif [ "$lag" -gt 1000 ]; then
        lag_color="${RED}$lag${NC}"
    elif [ "$lag" -gt 0 ]; then
        lag_color="${YELLOW}$lag${NC}"
    else
        lag_color="${GREEN}$lag${NC}"
    fi
    
    printf "%-20s %10s %15s %10s\n" "$topic" "$partitions_fmt" "$messages_fmt" "$lag_color"
done

echo ""
echo "Notes:"
echo "  - Messages: Total messages in topic (sum across all partitions)"
echo "  - Lag: Consumer lag (0 = caught up, N/A = no active consumer)"
