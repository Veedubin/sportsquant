#!/bin/bash
# Kafka UI Port Forward - Background Service
# Run this script to start a persistent port forward to the Kafka UI

KUBECTL_PID_FILE="/tmp/kafka-ui-portforward.pid"
LOG_FILE="/tmp/kafka-ui-portforward.log"

cleanup() {
    if [ -f "$KUBECTL_PID_FILE" ]; then
        PID=$(cat "$KUBECTL_PID_FILE")
        if kill -0 "$PID" 2>/dev/null; then
            kill "$PID" 2>/dev/null
            echo "Stopped port-forward (PID: $PID)"
        fi
        rm -f "$KUBECTL_PID_FILE"
    fi
}

trap cleanup EXIT

# Kill any existing port-forwards on port 8080
pkill -f "kubectl.*port-forward.*kafka-ui" 2>/dev/null
sleep 1

# Start port-forward in background
nohup kubectl port-forward -n kafka-ui svc/redpanda-console-console 8080:8080 > "$LOG_FILE" 2>&1 &
PF_PID=$!
echo $PF_PID > "$KUBECTL_PID_FILE"

echo "Port forward started (PID: $PF_PID)"
echo "Log file: $LOG_FILE"
echo "Kafka UI available at: http://localhost:8080"

# Wait for port-forward
sleep 3

# Verify it's working
if curl -s http://localhost:8080 > /dev/null 2>&1; then
    echo "✓ Kafka UI is accessible at http://localhost:8080"
else
    echo "✗ Port forward may not be ready yet. Check logs: cat $LOG_FILE"
fi

# Keep running
wait
