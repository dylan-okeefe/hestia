#!/usr/bin/env bash
# Start a self-contained demo/screenshot instance from the ~/Hestia worktree.
# This script does NOT touch the personal ~/Hestia-runtime service or data.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

DEMO_CONFIG="config.demo.py"
DEMO_DATA="demo-data"
PIDFILE="$DEMO_DATA/hestia-demo.pid"
LOGFILE="$DEMO_DATA/logs/demo-server.log"

if [ ! -f "$DEMO_CONFIG" ]; then
    echo "Demo config not found. Copying config.demo.example.py -> $DEMO_CONFIG"
    cp config.demo.example.py "$DEMO_CONFIG"
fi

# Ensure isolated demo directories exist.
mkdir -p "$DEMO_DATA"/{artifacts,slots,browser-sessions,logs}

# Make sure the database and synthetic data are initialized.
echo "Seeding demo data..."
uv run python scripts/seed_demo.py

# If a previous demo process is recorded, make sure it is really gone.
if [ -f "$PIDFILE" ]; then
    OLD_PID=$(cat "$PIDFILE" 2>/dev/null || true)
    if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
        echo "A demo instance is already running (PID $OLD_PID). Run scripts/stop_demo.sh first."
        exit 1
    else
        rm -f "$PIDFILE"
    fi
fi

# Start the server in the background, capturing output.
echo "Starting demo instance (log: $LOGFILE)..."
nohup uv run hestia --config "$DEMO_CONFIG" serve >"$LOGFILE" 2>&1 &
SERVER_PID=$!
echo "$SERVER_PID" > "$PIDFILE"

# Wait briefly for the server to bind before returning.
DEMO_PORT=$(uv run python -c "from pathlib import Path; from hestia.config import HestiaConfig; print(HestiaConfig.from_file(Path('$DEMO_CONFIG')).web.port)")
for _ in {1..30}; do
    if curl -s -o /dev/null "http://127.0.0.1:$DEMO_PORT/api/auth/status"; then
        echo "Demo instance ready at http://127.0.0.1:$DEMO_PORT"
        # Mint a token via the debug-login endpoint so the helper script can
        # verify the mock admin works, and print it for API use.
        if [ -f "$DEMO_DATA/demo-admin.json" ]; then
            USER_ID=$(python3 -c "import json; print(json.load(open('$DEMO_DATA/demo-admin.json'))['user_id'])")
            TOKEN=$(curl -s -X POST "http://127.0.0.1:$DEMO_PORT/api/auth/debug-login" \
                -H "Content-Type: application/json" \
                -d "{\"user_id\":\"$USER_ID\"}" \
                | python3 -c 'import sys, json; print(json.load(sys.stdin)["token"])')
            echo ""
            echo "Mock admin token (for curl/scripts): $TOKEN"
        fi
        echo ""
        echo "To log in via the web UI, open http://127.0.0.1:$DEMO_PORT"
        echo "and select 'Demo Admin'. debug_login is enabled for this demo config only."
        exit 0
    fi
    sleep 0.5
done

echo "Demo instance did not become ready within 15s. Check $LOGFILE"
exit 1
