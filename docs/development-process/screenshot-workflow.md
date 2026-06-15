# Screenshot / demo workflow

A self-contained, throwaway Hestia instance that runs from the `~/Hestia` dev
worktree. It is fully isolated from the personal `~/Hestia-runtime` instance:
separate database, separate data directories, and a separate localhost port.

Use this when you want to screenshot or demo any web UI page (including admin
views) without exposing real names, memories, sessions, or chat history.

## What is isolated

| Resource | Demo instance | Personal instance |
|---|---|---|
| Database | `./demo-data/hestia.db` | `~/Hestia-runtime/runtime-data/hestia.db` |
| Artifacts | `./demo-data/artifacts/` | `~/Hestia-runtime/runtime-data/artifacts/` |
| Slot snapshots | `./demo-data/slots/` | `~/Hestia-runtime/runtime-data/slots/` |
| Browser sessions | `./demo-data/browser-sessions/` | `~/.hestia/browser-sessions/` |
| Compiled identity | `./demo-data/compiled_identity.txt` | `.hestia/compiled_identity.txt` (worktree-local) |
| Web port | `127.0.0.1:8766` | `0.0.0.0:8765` (default) |
| Platform adapters | Disabled | Telegram / Matrix / email as configured |

The demo config leaves Telegram, Matrix, email, and voice at their empty
defaults, so `hestia serve` starts **only** the web dashboard.

## One-time setup

```bash
cd ~/Hestia
cp config.demo.example.py config.demo.py
```

`config.demo.py` is gitignored. It contains no secrets, but it is local to your
machine.

If you want Context Lab previews to work, make sure a local llama-server is
running on `http://127.0.0.1:8001` (the default in the demo config). The rest
of the web UI does not need an inference server.

## Start the demo instance

```bash
cd ~/Hestia
./scripts/start_demo.sh
```

This will:

1. Copy the example config to `config.demo.py` if it does not exist.
2. Create the isolated `demo-data/` directories.
3. Run `scripts/seed_demo.py` to create a mock admin user, synthetic memories,
   a sample session, and a sample proposal.
4. Start the web server on `http://127.0.0.1:8766`.
5. Print a bearer token for the mock admin.

## Log in as the mock admin

Because `web.debug_login` is enabled **only** in `config.demo.py`, the web UI
shows a one-click debug login for the mock admin. No Telegram/Matrix/email code
is needed, and the real product auth paths are unchanged.

### Web UI

Open `http://127.0.0.1:8766`, click the **Demo Admin** card, and the UI will
log you in automatically.

### API / curl

If you need a bearer token for scripts, call the debug-login endpoint with the
demo admin user id (stored in `demo-data/demo-admin.json`):

```bash
USER_ID=$(python3 -c "import json; print(json.load(open('demo-data/demo-admin.json'))['user_id'])")
TOKEN=$(curl -s -X POST http://127.0.0.1:8766/api/auth/debug-login \
  -H "Content-Type: application/json" \
  -d "{\"user_id\":\"$USER_ID\"}" \
  | python3 -c 'import sys, json; print(json.load(sys.stdin)["token"])')

curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8766/api/auth/status
```

## Capture screenshots

Open `http://127.0.0.1:8766` in a browser, log in as Demo Admin, and navigate
to any page:

- **Dashboard** — shows only synthetic stats.
- **Context Lab** — assembles a system prompt from the generic demo SOUL.md and
  synthetic memories; no real operator data.
- **Sessions / Knowledge / Proposals / Admin Users** — show only the seeded
  demo rows.

All data is scoped to the demo identity (`platform="demo"`,
`platform_user="demo-admin@hestia.local"`), so real rows are never returned.

## Stop the demo instance

```bash
./scripts/stop_demo.sh
```

This kills only the demo server process and removes its PID file. The personal
`~/Hestia-runtime` service keeps running.

## Reset / clean up

To start completely fresh, stop the demo and delete the throwaway data:

```bash
./scripts/stop_demo.sh
rm -rf demo-data
```

The next `start_demo.sh` will re-create everything from the seed script.

## Important limits

- **Do not** edit `config.demo.example.py` to point at real secrets or the
  personal database.
- **Do not** commit `config.demo.py`, `demo-data/`, or the demo DB.
- The demo instance shares the same `~/Hestia` source code as the dev worktree,
  but it runs with its own config and data, so code changes are reflected
  immediately after a restart.
- If `http://127.0.0.1:8001` is not reachable, Context Lab preview will fail
  with a connection error; other pages are unaffected.
