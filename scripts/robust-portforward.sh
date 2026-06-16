#!/bin/bash
# Robust port-forward script with keepalive and auto-restart
# Usage: ./scripts/robust-portforward.sh <service> <local_port> <remote_port> <namespace>

set -e

SERVICE="${1:-sports-cluster-kafka-bootstrap}"
LOCAL_PORT="${2:-9093}"
REMOTE_PORT="${3:-9092}"
NAMESPACE="${4:-default}"
LOG_FILE="${5:-/tmp/portforward-${SERVICE}.log}"

KUBECTL="kubectl"
PID_FILE="/tmp/portforward-${SERVICE}.pid"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $*" | tee -a "$LOG_FILE"
}

cleanup() {
    log "Cleaning up..."
    if [ -f "$PID_FILE" ]; then
        kill $(cat "$PID_FILE") 2>/dev/null || true
        rm -f "$PID_FILE"
    fi
    exit 0
}

trap cleanup SIGTERM SIGINT SIGHUP

restart_portforward() {
    log "Starting port-forward: $SERVICE:$REMOTE_PORT -> localhost:$LOCAL_PORT"
    
    # Kill any existing process on the port
    fuser -k ${LOCAL_PORT}/tcp 2>/dev/null || true
    sleep 1
    
    # Start port-forward in background
    $KUBECTL port-forward -n "$NAMESPACE" "svc/$SERVICE" "$LOCAL_PORT:$REMOTE_PORT" >> "$LOG_FILE" 2>&1 &
    PF_PID=$!
    
    echo $PF_PID > "$PID_FILE"
    log "Port-forward started with PID: $PF_PID"
    
    # Wait for port to be ready
    for i in {1..30}; do
        if nc -z 127.0.0.1 "$LOCAL_PORT" 2>/dev/null; then
            log "Port $LOCAL_PORT is ready"
            return 0
        fi
        sleep 1
    done
    
    log "ERROR: Port $LOCAL_PORT failed to become ready"
    return 1
}

# Keepalive loop - sends periodic data to prevent idle timeout
keepalive_loop() {
    log "Starting keepalive for port $LOCAL_PORT"
    while true; do
        sleep 30
        # Use nc or curl to send periodic data
        if nc -z 127.0.0.1 "$LOCAL_PORT" 2>/dev/null; then
            echo "" | nc -w 1 127.0.0.1 "$LOCAL_PORT" 2>/dev/null || true
        fi
    done
}

# Main loop
log "Starting robust port-forward manager for $SERVICE"
mkdir -p "$(dirname "$LOG_FILE")"

# Start keepalive in background
keepalive_loop &
KEEPALIVE_PID=$!

# Start initial port-forward
restart_portforward

# Monitor and restart if needed
while true; do
    if [ -f "$PID_FILE" ]; then
        PF_PID=$(cat "$PID_FILE")
        if ! kill -0 "$PF_PID" 2>/dev/null; then
            log "Port-forward died (PID $PF_PID), restarting..."
            restart_portforward
        fi
    else
        log "No PID file found, restarting port-forward..."
        restart_portforward
    fi
    
    sleep 10
done

# Cleanup (never reached)
kill $KEEPALIVE_PID 2>/dev/null || true
