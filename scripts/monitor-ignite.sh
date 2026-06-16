#!/bin/bash
# Monitor Apache Ignite cache sizes via REST API
# Usage: ./scripts/monitor-ignite.sh [cache_name]
#   If no cache specified, shows all NBA caches

set -e

IGNITE_NAMESPACE="default"
IGNITE_SERVICE="ignite"
IGNITE_PORT=8080
IGNITE_URL="http://${IGNITE_SERVICE}.${IGNITE_NAMESPACE}.svc:${IGNITE_PORT}"
NBA_CACHES=("sports:v1:nba-games" "sports:v1:nba-player" "sports:v1:nba-stats")

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Function to get cache size via REST API
get_cache_size() {
    local cache_name=$1
    local result=$(curl -s "${IGNITE_URL}/ignite?cmd=size&cacheName=${cache_name}" 2>/dev/null || echo "")
    
    if [ -z "$result" ]; then
        echo "0"
        return
    fi
    
    # Parse JSON response - Ignite returns: {"successStatus":0,"size":123}
    local size=$(echo "$result" | grep -o '"size":[0-9]*' | grep -o '[0-9]*' || echo "0")
    echo "$size"
}

# Function to check Ignite connectivity
check_ignite_connection() {
    local result=$(curl -s "${IGNITE_URL}/ignite?cmd=version" 2>/dev/null || echo "")
    if echo "$result" | grep -q "successStatus"; then
        return 0
    else
        return 1
    fi
}

# Function to list all caches
list_caches() {
    local result=$(curl -s "${IGNITE_URL}/ignite?cmd=cache&act=names" 2>/dev/null || echo "")
    echo "$result"
}

# Function to format number with commas
format_number() {
    local num=$1
    if [ "$num" = "0" ] || [ "$num" = "" ]; then
        echo "0"
    else
        printf "%'d" "$num"
    fi
}

# Display usage if help requested
if [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
    echo "Usage: $0 [cache_name]"
    echo ""
    echo "Monitor Apache Ignite cache sizes via REST API."
    echo ""
    echo "Arguments:"
    echo "  cache_name    Optional. Specific cache to monitor."
    echo "                If not provided, monitors all NBA caches."
    echo ""
    echo "Output format:"
    echo "  cache name, size (entries)"
    echo ""
    echo "Examples:"
    echo "  $0                          # Monitor all NBA caches"
    echo "  $0 sports:v1:nba-games      # Monitor specific cache"
    echo ""
    echo "NBA Caches:"
    for cache in "${NBA_CACHES[@]}"; do
        echo "  - $cache"
    done
    exit 0
fi

# Determine which caches to monitor
if [ -n "$1" ]; then
    CACHES=("$1")
else
    CACHES=("${NBA_CACHES[@]}")
fi

echo "=== Ignite Cache Status ==="
echo "Timestamp: $(date -Iseconds)"
echo ""

# Check Ignite connectivity
if ! check_ignite_connection; then
    echo -e "${RED}Error: Cannot connect to Ignite at ${IGNITE_URL}${NC}"
    echo "Please verify that:"
    echo "  1. Ignite is deployed: kubectl get pods -n $IGNITE_NAMESPACE | grep ignite"
    echo "  2. Service is available: kubectl get svc -n $IGNITE_NAMESPACE $IGNITE_SERVICE"
    exit 1
fi

printf "%-30s %15s\n" "CACHE NAME" "ENTRIES"
printf "%-30s %15s\n" "─────────" "───────"

for cache in "${CACHES[@]}"; do
    size=$(get_cache_size "$cache")
    size_fmt=$(format_number "$size")
    
    # Color code based on cache size
    if [ "$size" = "0" ]; then
        size_color="${YELLOW}$size_fmt${NC}"
    else
        size_color="${GREEN}$size_fmt${NC}"
    fi
    
    printf "%-30s %15s\n" "$cache" "$size_color"
done

echo ""
echo "Notes:"
echo "  - Entries: Current number of entries in the cache"
echo "  - Cache names use Ignite's distributed cache naming convention"
