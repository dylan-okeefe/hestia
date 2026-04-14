# Credentials and where to put them (Hestia testing)

**Do not commit secrets.** Use environment variables, a **gitignored** `config.local.py`, or systemd `Environment=` / `EnvironmentFile=`.

---

## 1. Inference (always)

| Item | Example | Where |
|------|---------|--------|
| **llama.cpp** running locally | `http://127.0.0.1:8001` | `InferenceConfig.base_url` in config |
| **Model id string** | Must match server | `InferenceConfig.model_name` |

No secret; must be up for E2E and manual Matrix/Telegram runs.

---

## 2. Telegram (optional — personal bot)

| Item | Where |
|------|--------|
| **Bot token** (BotFather) | `HESTIA_TELEGRAM_BOT_TOKEN` → read by `~/Hestia-runtime/config.runtime.py` (or `TelegramConfig` in your config) |
| **Allowed numeric user ids** (comma-separated) | `HESTIA_TELEGRAM_ALLOWED_USERS` |

---

## 3. Matrix — **two** users (see `docs/design/matrix-integration.md` §5.0)

### 3.1 Bot (Hestia process: `hestia matrix`)

| Secret / value | Env names (after L10/L11 wiring; until then set in Python `MatrixConfig`) |
|----------------|-----------------------------------------------------------------------------|
| Homeserver URL | `HESTIA_MATRIX_HOMESERVER` (e.g. `https://matrix.org`) |
| Bot MXID | `HESTIA_MATRIX_USER_ID` (e.g. `@hestia-bot:matrix.org`) |
| Bot access token | `HESTIA_MATRIX_ACCESS_TOKEN` |
| Device id | `HESTIA_MATRIX_DEVICE_ID` (optional; default e.g. `hestia-bot`) |
| Allowed rooms (comma-separated room ids or aliases) | `HESTIA_MATRIX_ALLOWED_ROOMS` |

**Room:** Create a **test room**, invite the **bot** user, put its id (or alias) in `allowed_rooms`.

### 3.2 Tester (driver: `matrix-commander` or pytest)

| Secret / value | Typical location |
|----------------|------------------|
| Tester MXID | Own account (e.g. `@you-test:matrix.org`) |
| Tester access token | **`matrix-commander`** credentials file (e.g. `~/.local/share/matrix-commander/credentials.json`) **or** CI env vars such as `MATRIX_TEST_USER_ACCESS_TOKEN`, `MATRIX_TEST_USER_ID` once L12 adds them |
| Test room id | Same room as bot — tester must be a **member** who can post |

The tester must **not** reuse the bot token.

---

## 4. E2E / CI (optional env-gated pytest)

After L12/L13 land, tests may expect names like:

| Purpose | Examples |
|---------|----------|
| Bot | `MATRIX_BOT_ACCESS_TOKEN`, `MATRIX_BOT_USER_ID`, `MATRIX_HOMESERVER` |
| Tester | `MATRIX_TEST_USER_ACCESS_TOKEN`, `MATRIX_TEST_USER_ID` |
| Room | `MATRIX_TEST_ROOM_ID` |

Exact names: follow **`docs/orchestration/kimi-loops/L12-matrix-e2e-two-user.md`** (or test module docstrings) after Kimi implements them.

---

## 5. Disposable local state

| Item | Where |
|------|--------|
| SQLite DB for a test worktree | `runtime-data/hestia.db` inside that worktree (gitignored via `/runtime-data/`) |
| KV slots | Same tree’s `runtime-data/slots` |

Use a **dedicated** worktree or DB file for automation so you can `rm` it if teardown fails.

---

## 6. Checklist before telling Cursor to run Kimi

- [ ] llama-server healthy (`hestia health` or curl `/health`)
- [ ] Matrix: bot account registered, token obtained, room created, bot invited, `allowed_rooms` set
- [ ] Matrix: tester account registered, token in driver store or env
- [ ] Telegram (if used): token + allowed user ids exported
- [ ] No secrets in `git status` tracked files
