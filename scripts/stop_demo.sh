#!/usr/bin/env bash
# Stop the self-contained demo/screenshot instance started by start_demo.sh.
# This script does NOT touch the personal ~/Hestia-runtime service.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PIDFILE="$REPO_ROOT/demo-data/hestia-demo.pid"

if [ ! -f "$PIDFILE" ]; then
    echo "No demo PID file found at $PIDFILE (already stopped?)."
    exit 0
fi

PID=$(cat "$PIDFILE")
if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
    echo "Stopping demo instance (PID $PID)..."
    kill "$PID"
    # Wait for the process group to finish.
    for _ in {1..30}; do
        if ! kill -0 "$PID" 2>/dev/null; then
            break
        fi
        sleep 0.5
    done
else
    echo "Demo PID $PID is not running."
fi

rm -f "$PIDFILE"
echo "Demo instance stopped."
