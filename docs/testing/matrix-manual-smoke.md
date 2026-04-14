# Matrix manual smoke test guide

Step-by-step manual validation of the Matrix platform path. No pytest required — just two Matrix accounts, a room, and the CLI.

---

## Prerequisites

- A running llama.cpp server (`curl http://localhost:8001/health` returns OK)
- Two Matrix accounts:
  - **Bot** — the Hestia process (`hestia matrix`)
  - **Tester** — you, or a separate account used to send messages
- A **test room** where both accounts are members
- Bot credentials in `.matrix.secrets.py` (or env vars) and wired into `config.py`

See [`CREDENTIALS_AND_SECRETS.md`](CREDENTIALS_AND_SECRETS.md) for exact env names.

---

## 1. Start the bot

From a feature worktree (not your stable runtime tree):

```bash
hestia --config config.py matrix
```

You should see logs showing:
- `MatrixAdapter` starts sync loop
- `Scheduler` starts (if enabled in config)
- No immediate errors from `matrix-nio`

---

## 2. Send a ping from the tester account

### Option A: Element web/desktop

Type `hello hestia` in the test room.

### Option B: `matrix-commander`

```bash
matrix-commander -r "!your-room:server" -m "hello hestia"
```

### Option C: `scripts/matrix_test_send.py`

```bash
export HESTIA_MATRIX_HOMESERVER=https://matrix.org
export HESTIA_MATRIX_USER_ID=@bot:matrix.org
export HESTIA_MATRIX_TESTER_USER_ID=@tester:matrix.org
export HESTIA_MATRIX_TESTER_ACCESS_TOKEN=syt_...
export HESTIA_MATRIX_TEST_ROOM_ID='!room:matrix.org'

python scripts/matrix_test_send.py "hello hestia"
```

**Expected:** Bot replies within ~30 seconds with an assistant message.

---

## 3. Per-tool smoke lines

Paste these one at a time. Assert the bot responds with something reasonable (exact wording depends on your model).

| Tool | Paste line | Expected behavior |
|------|-----------|-------------------|
| `current_time` | "What time is it?" | Bot answers with current date/time |
| `read_file` | "Read the file README.md" | Bot returns the first few lines |
| `list_dir` | "List the deploy directory" | Bot lists files in `deploy/` |
| `http_get` | "Fetch https://example.com and tell me the title" | Bot returns "Example Domain" or similar |
| `save_memory` | "Remember that my favorite color is blue" | Bot confirms memory saved |
| `search_memory` | "What is my favorite color?" | Bot answers "blue" |
| `list_memories` | "List my recent memories" | Bot shows recent memory entries |
| `write_file` | "Write 'hello' to /tmp/test_hestia.txt" | **Denied** — no confirmation UI in Matrix v1 |
| `terminal` | "Run the command 'uname -a'" | **Denied** — no confirmation UI in Matrix v1 |

---

## 4. Memory cleanup

If the smoke test inserted memories, clean them up so you do not pollute the database:

```bash
# List recent memories
hestia --config config.py memory list

# Remove by ID
hestia --config config.py memory remove <id>
```

For automated runs, prefer a **disposable** SQLite file (`runtime-data/hestia.db`) and delete it afterward.

---

## 5. Scheduler notes (L13+)

Since L13, you can bind scheduled tasks to a Matrix room:

```bash
# Bind to an existing Matrix session
hestia --config config.py schedule add \
  --session-id <matrix-session-id> \
  --prompt "Good morning" \
  --cron "0 8 * * *"

# Or create a task bound directly to a Matrix room
hestia --config config.py schedule add \
  --platform matrix \
  --platform-user '!room:server' \
  --prompt "Hourly ping" \
  --cron "0 * * * *"
```

List and remove:

```bash
hestia --config config.py schedule list
hestia --config config.py schedule remove <id>
```

---

## 6. Shutdown

Press **Ctrl-C** in the terminal running `hestia matrix`. The bot will cancel the sync loop and exit cleanly.

If running under systemd in the runtime tree, use:

```bash
sudo systemctl stop hestia-agent@$USER
```
