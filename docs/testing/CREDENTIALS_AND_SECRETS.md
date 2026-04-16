# Credentials and where to put them (Hestia testing)

**Do not commit secrets.** Prefer the repo-root **Matrix** file below; or environment variables, a **gitignored** `config.local.py`, or systemd `Environment=` / `EnvironmentFile=`.

---

## Matrix (recommended): `.matrix.secrets.py`

1. Copy the scaffold (tracked in git):

   ```bash
   cp .matrix.secrets.example.py .matrix.secrets.py
   ```

2. Edit **`.matrix.secrets.py`** (gitignored). Fill bot fields (`HOMESERVER`, `USER_ID`, `DEVICE_ID`, `ACCESS_TOKEN`, `ALLOWED_ROOMS`). For E2E, also fill tester fields and `TEST_ROOM_ID`.

3. Wire it into **`MatrixConfig`** from your `config.py` using `importlib` (see the comment block at the top of `.matrix.secrets.example.py`) or set env vars instead.

4. **Token rotation:** Access tokens can expire. Optional **`LOGIN_PASSWORD`** (same account as `USER_ID`) is there for a manual token-refresh workflow with `matrix-nio` password login. Hestia does **not** auto-refresh from password yet.

**Two-user model:** Bot fields drive `hestia matrix`. Tester fields are used by `matrix-commander`, `scripts/matrix_test_send.py`, or pytest E2E.

---

## 1. Inference (always)

| Item | Example | Where |
|------|---------|--------|
| **llama.cpp** running locally | `http://127.0.0.1:8001` | `InferenceConfig.base_url` in config |
| **Model id string** | Must match server | `InferenceConfig.model_name` |

No secret; must be up for E2E and manual Matrix/Telegram runs.

---

## 2. Telegram (optional — personal bot)

| Item | Env variable | Where consumed |
|------|--------------|----------------|
| **Bot token** (BotFather) | `HESTIA_TELEGRAM_BOT_TOKEN` | Hardcoded in `config.py` or a custom runtime config file |
| **Allowed numeric user ids** (comma-separated) | `HESTIA_TELEGRAM_ALLOWED_USERS` | Same |

---

## 3. Matrix — bot credentials

### 3.1 Bot (`hestia matrix`)

| Secret / value | Env variable | `MatrixConfig` field | Required |
|----------------|--------------|----------------------|----------|
| Homeserver URL | `HESTIA_MATRIX_HOMESERVER` | `homeserver` | Yes (default: `https://matrix.org`) |
| Bot MXID | `HESTIA_MATRIX_USER_ID` | `user_id` | Yes |
| Device ID | `HESTIA_MATRIX_DEVICE_ID` | `device_id` | No (default: `hestia-bot`) |
| Access token | `HESTIA_MATRIX_ACCESS_TOKEN` | `access_token` | Yes |
| Allowed rooms | `HESTIA_MATRIX_ALLOWED_ROOMS` | `allowed_rooms` | Yes (comma-separated room IDs or aliases) |

**Room setup:** Create a **test room**, invite the **bot** user, put its ID (or alias) in `ALLOWED_ROOMS`.

**Optional password (manual refresh only):** `LOGIN_PASSWORD` in `.matrix.secrets.py` — not read by Hestia automatically.

### 3.2 Tester (driver / E2E)

| Secret / value | Env variable | Required |
|----------------|--------------|----------|
| Tester MXID | `HESTIA_MATRIX_TESTER_USER_ID` | Yes (for E2E) |
| Tester access token | `HESTIA_MATRIX_TESTER_ACCESS_TOKEN` | Yes (for E2E) |
| Tester device ID | `HESTIA_MATRIX_TESTER_DEVICE_ID` | No (default: `hestia-e2e-tester`) |
| Test room ID | `HESTIA_MATRIX_TEST_ROOM_ID` | Yes (for E2E) |

The tester **must not** reuse the bot token.

---

## 4. E2E / CI (env-gated pytest)

L12 standardizes the environment variable names above. Tests marked `@pytest.mark.matrix_e2e` **skip cleanly** when any required variable is missing.

Required for E2E:
- `HESTIA_MATRIX_HOMESERVER`
- `HESTIA_MATRIX_USER_ID`
- `HESTIA_MATRIX_ACCESS_TOKEN`
- `HESTIA_MATRIX_TESTER_USER_ID`
- `HESTIA_MATRIX_TESTER_ACCESS_TOKEN`
- `HESTIA_MATRIX_TEST_ROOM_ID`

Optional:
- `HESTIA_MATRIX_DEVICE_ID` (bot)
- `HESTIA_MATRIX_TESTER_DEVICE_ID` (tester)
- `HESTIA_MATRIX_ALLOWED_ROOMS` (if omitted, E2E tests typically infer it from `TEST_ROOM_ID`)

---

## 5. Disposable local state

| Item | Where |
|------|--------|
| SQLite DB for a test worktree | `runtime-data/hestia.db` inside that worktree (gitignored via `/runtime-data/`) |
| KV slots | Same tree’s `runtime-data/slots` |
| Artifacts | Same tree’s `runtime-data/artifacts` |

Use a **dedicated** worktree or DB file for automation so you can `rm -rf runtime-data/` if teardown fails. See [`docs/runtime-feature-testing.md`](../runtime-feature-testing.md).

---

## 6. Checklist before running Matrix tests

- [ ] llama-server healthy (`hestia health` or curl `/health`)
- [ ] Matrix: **`.matrix.secrets.py`** filled (or env vars), room created, bot invited
- [ ] Matrix: tester credentials for E2E (file or commander)
- [ ] Telegram (if used): token + allowed user ids exported
- [ ] `git status` shows **no** `.matrix.secrets.py` (ignored) and no other secret files tracked
