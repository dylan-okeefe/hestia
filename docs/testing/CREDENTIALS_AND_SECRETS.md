# Credentials and where to put them (Hestia testing)

**Do not commit secrets.** Prefer the repo-root **Matrix** file below; or environment variables, a **gitignored** `config.local.py`, or systemd `Environment=` / `EnvironmentFile=`.

---

## Matrix (recommended): `.matrix.secrets.py`

1. Copy the scaffold (tracked in git):

   ```bash
   cp .matrix.secrets.example.py .matrix.secrets.py
   ```

2. Edit **`.matrix.secrets.py`** (gitignored): set `HOMESERVER`, `USER_ID`, `DEVICE_ID`, `ACCESS_TOKEN`, `ALLOWED_ROOMS`. For E2E, fill **tester** fields and `TEST_ROOM_ID` if you keep both identities in one place.

3. **Token rotation:** Access tokens can expire or be rotated. Optional **`LOGIN_PASSWORD`** (same account as `USER_ID`) is there for a **Hermes-style** workflow: re-login with **`matrix-nio`** password login when you need a fresh token — paste the new token into `ACCESS_TOKEN`. Hestia does **not** yet read the password automatically; it is for your scripts or a future auto-refresh feature.

4. Wire secrets into **`MatrixConfig`** from your `config.py` using `importlib` (see comments at the top of **`.matrix.secrets.example.py`**) or merge values by hand.

**Two-user model:** Bot fields drive **`hestia matrix`**. Tester fields are for **`matrix-commander`** / pytest; you can instead keep tester tokens only in the commander credentials file — the example file just offers one optional place.

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

| Secret / value | Where |
|----------------|--------|
| Homeserver, MXID, device, token, rooms | **`.matrix.secrets.py`** (from example) **or** env vars below |
| Optional password (token refresh workflow) | **`LOGIN_PASSWORD`** in **`.matrix.secrets.py`** only — not auto-used by Hestia yet |

Env alternative (when wired in config / L10): `HESTIA_MATRIX_HOMESERVER`, `HESTIA_MATRIX_USER_ID`, `HESTIA_MATRIX_ACCESS_TOKEN`, `HESTIA_MATRIX_DEVICE_ID`, `HESTIA_MATRIX_ALLOWED_ROOMS`.

**Room:** Create a **test room**, invite the **bot** user, put its id (or alias) in `ALLOWED_ROOMS`.

### 3.2 Tester (driver: `matrix-commander` or pytest)

| Secret / value | Typical location |
|----------------|------------------|
| Tester MXID / token | **`TESTER_*`** in **`.matrix.secrets.py`** **or** `~/.local/share/matrix-commander/credentials.json` **or** CI env vars once L12 standardizes names |

The tester must **not** reuse the bot token.

---

## 4. E2E / CI (optional env-gated pytest)

After L12 lands, tests may still read **`.matrix.secrets.py`** locally or expect env vars. Exact names: follow **`docs/orchestration/kimi-loops/L12-matrix-e2e-two-user.md`**.

---

## 5. Disposable local state

| Item | Where |
|------|--------|
| SQLite DB for a test worktree | `runtime-data/hestia.db` inside that worktree (gitignored via `/runtime-data/`) |
| KV slots | Same tree’s `runtime-data/slots` |

Use a **dedicated** worktree or DB file for automation so you can `rm` if teardown fails.

---

## 6. Checklist before telling Cursor to run Kimi

- [ ] llama-server healthy (`hestia health` or curl `/health`)
- [ ] Matrix: **`.matrix.secrets.py`** filled (or env vars), room created, bot invited
- [ ] Matrix: tester credentials for E2E (file or commander)
- [ ] Telegram (if used): token + allowed user ids exported
- [ ] `git status` shows **no** `.matrix.secrets.py` (ignored) and no other secret files tracked
