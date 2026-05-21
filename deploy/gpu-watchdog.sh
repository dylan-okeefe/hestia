#!/usr/bin/env bash
# GPU health watchdog — checks nvidia-smi and reboots if GPU driver is down.
# Run via systemd timer (gpu-watchdog.timer).
#
# Consecutive-failure logic:
#   - Writes a counter to /tmp/gpu-watchdog-failures
#   - On success: counter reset to 0
#   - On failure: counter increments; at THRESHOLD consecutive failures,
#     triggers system reboot and logs the event.

set -euo pipefail

COUNTER_FILE="/tmp/gpu-watchdog-failures"
THRESHOLD="${GPU_WATCHDOG_THRESHOLD:-3}"
LOG_TAG="gpu-watchdog"

failures=0
if [[ -f "$COUNTER_FILE" ]]; then
    failures=$(cat "$COUNTER_FILE" || echo 0)
fi

if nvidia-smi >/dev/null 2>&1; then
    # GPU is healthy
    if (( failures > 0 )); then
        logger -t "$LOG_TAG" "GPU recovered after ${failures} consecutive failure(s)."
    fi
    echo 0 > "$COUNTER_FILE"
    exit 0
fi

# GPU/driver failure detected
failures=$((failures + 1))
echo "$failures" > "$COUNTER_FILE"
logger -t "$LOG_TAG" "GPU check FAILED (${failures}/${THRESHOLD})"

if (( failures >= THRESHOLD )); then
    logger -t "$LOG_TAG" "CRITICAL: ${THRESHOLD} consecutive GPU failures — triggering reboot."
    rm -f "$COUNTER_FILE"
    # On most desktop systemd systems, logincth polkit allows local users to reboot
    systemctl reboot || sudo -n /sbin/reboot || true
fi
