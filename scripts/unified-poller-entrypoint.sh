#!/bin/bash
# Unified poller entrypoint - skips NTP sync (use host time)

# Skip NTP sync - use host time which is already synced
# echo "[unified-poller] Using host system time (no NTP sync)"

exec python -m src.unified_poller
