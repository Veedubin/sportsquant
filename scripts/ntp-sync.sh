#!/bin/bash
# Sync time with NIST time servers on boot
# Ensures accurate timestamps for distributed traces

set -e

echo "[ntp-sync] Starting time sync..."

# NIST time servers (in order of preference)
NIST_SERVERS=(
    "time.nist.gov"
    "time-a-g.nist.gov"
    "time-b-g.nist.gov"
    "time-c-g.nist.gov"
)

# Try to sync with ntpdate or chronyd
sync_time() {
    for server in "${NIST_SERVERS[@]}"; do
        echo "[ntp-sync] Trying $server..."
        
        # Try ntpdate first
        if command -v ntpdate &> /dev/null; then
            if ntpdate -q "$server" 2>/dev/null; then
                ntpdate "$server" && echo "[ntp-sync] Synced with $server" && return 0
            fi
        fi
        
        # Try chronyd
        if command -v chronyc &> /dev/null; then
            if chronyc makestep &>/dev/null; then
                echo "[ntp-sync] Chrony stepped" && return 0
            fi
        fi
        
        # Try systemd-timesyncd
        if command -v timedatectl &> /dev/null; then
            timedatectl set-ntp true && echo "[ntp-sync] systemd-timesyncd enabled" && return 0
        fi
    done
    
    echo "[ntp-sync] WARNING: Could not sync with NTP, using system time"
    return 1
}

# Sync time
sync_time

# Verify time is reasonable (within 60 seconds of epoch start check)
CURRENT_YEAR=$(date +%Y)
if [ "$CURRENT_YEAR" -lt 2020 ]; then
    echo "[ntp-sync] ERROR: Time is way off ($CURRENT_YEAR)"
    exit 1
fi

echo "[ntp-sync] Current time: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"

exec "$@"
