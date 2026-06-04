# Environment Variables Reference

Hestia configuration is loaded from **`config.py`** by default.  CLI flags
(`--config`, `--db-path`, `--inference-url`, etc.) override individual fields
after the file is loaded.

Most config classes also expose a `from_env()` classmethod that builds an
instance from environment variables using the pattern
`HESTIA_{PREFIX}_{FIELD_NAME_UPPER}`.  This is **not** called automatically
by the CLI startup path (`cli.py` uses `from_file()` / `default()`), so env
vars are only active when you explicitly invoke `from_env()` in your own
entry-point or wrapper script.

## Special / Hand-picked Variables

These are handled explicitly in code and are **not** part of the auto-generated
mapping above.

| Variable | Purpose | Example |
|----------|---------|---------|
| `HESTIA_ALLOW_DUMMY_MODEL` | Set to `1` to allow the dummy model (`model_name="dummy"`) for testing without a real inference server. | `1` |
| `HESTIA_SOUL_PATH` | Override the path to `SOUL.md` (personality file). | `/opt/hestia/SOUL.md` |
| `HESTIA_CALIBRATION_PATH` | Override the path to `docs/calibration.json`. | `/opt/hestia/calibration.json` |

## Auto-generated Mappings

### Top-level (`HESTIA_*`)

Prefix: `HESTIA`

| Variable | Type | Default |
|----------|------|---------|
| `HESTIA_SYSTEM_PROMPT` | string | `"You are a helpful assistant."` |
| `HESTIA_MAX_ITERATIONS` | int | `10` |
| `HESTIA_VERBOSE` | bool | `false` |
| `HESTIA_USE_CURL_CFFI_FALLBACK` | bool | `false` |

### Identity (`HESTIA_IDENTITY_*`)

Prefix: `IDENTITY`

| Variable | Type | Default |
|----------|------|---------|
| `HESTIA_IDENTITY_SOUL_PATH` | string | `SOUL.md` |
| `HESTIA_IDENTITY_COMPILED_CACHE_PATH` | string | `.hestia/compiled_identity.txt` |
| `HESTIA_IDENTITY_MAX_TOKENS` | int | `300` |
| `HESTIA_IDENTITY_RECOMPILE_ON_CHANGE` | bool | `true` |

### Inference (`HESTIA_INFERENCE_*`)

Prefix: `INFERENCE`

| Variable | Type | Default |
|----------|------|---------|
| `HESTIA_INFERENCE_BASE_URL` | string | `http://localhost:8001` |
| `HESTIA_INFERENCE_MODEL_NAME` | string | *(empty)* |
| `HESTIA_INFERENCE_CONTEXT_LENGTH` | int | `8192` |
| `HESTIA_INFERENCE_DEFAULT_REASONING_BUDGET` | int | `2048` |
| `HESTIA_INFERENCE_MAX_TOKENS` | int | `1024` |
| `HESTIA_INFERENCE_STREAM` | bool | `false` |

### Slots (`HESTIA_SLOT_*`)

Prefix: `SLOT`

| Variable | Type | Default |
|----------|------|---------|
| `HESTIA_SLOT_SLOT_DIR` | string | `slots` |
| `HESTIA_SLOT_POOL_SIZE` | int | `4` |

### Scheduler (`HESTIA_SCHEDULER_*`)

Prefix: `SCHEDULER`

| Variable | Type | Default |
|----------|------|---------|
| `HESTIA_SCHEDULER_TICK_INTERVAL_SECONDS` | float | `5.0` |

### Storage (`HESTIA_STORAGE_*`)

Prefix: `STORAGE`

| Variable | Type | Default |
|----------|------|---------|
| `HESTIA_STORAGE_DATABASE_URL` | string | `sqlite+aiosqlite:///hestia.db` |
| `HESTIA_STORAGE_ARTIFACTS_DIR` | string | `artifacts` |
| `HESTIA_STORAGE_ALLOWED_ROOTS` | list | *(empty)* |
| `HESTIA_STORAGE_CHECKPOINT_SCOPE` | list | *(empty)* |

### Telegram (`HESTIA_TELEGRAM_*`)

Prefix: `TELEGRAM`

| Variable | Type | Default |
|----------|------|---------|
| `HESTIA_TELEGRAM_BOT_TOKEN` | string | *(empty)* |
| `HESTIA_TELEGRAM_ALLOWED_USERS` | list | *(empty)* |
| `HESTIA_TELEGRAM_RATE_LIMIT_EDITS_SECONDS` | float | `1.5` |
| `HESTIA_TELEGRAM_HTTP_VERSION` | string | `1.1` |
| `HESTIA_TELEGRAM_FALLBACK_IPS` | list | `149.154.167.220` |
| `HESTIA_TELEGRAM_CONNECT_TIMEOUT_SECONDS` | float | `10.0` |
| `HESTIA_TELEGRAM_READ_TIMEOUT_SECONDS` | float | `30.0` |
| `HESTIA_TELEGRAM_LONG_POLL_TIMEOUT_SECONDS` | float | `30.0` |
| `HESTIA_TELEGRAM_VOICE_MESSAGES` | bool | `false` |

### Matrix (`HESTIA_MATRIX_*`)

Prefix: `MATRIX`

| Variable | Type | Default |
|----------|------|---------|
| `HESTIA_MATRIX_HOMESERVER` | string | `https://matrix.org` |
| `HESTIA_MATRIX_USER_ID` | string | *(empty)* |
| `HESTIA_MATRIX_DEVICE_ID` | string | `hestia-bot` |
| `HESTIA_MATRIX_ACCESS_TOKEN` | string | *(empty)* |
| `HESTIA_MATRIX_ALLOWED_ROOMS` | list | *(empty)* |
| `HESTIA_MATRIX_RATE_LIMIT_EDITS_SECONDS` | float | `1.5` |
| `HESTIA_MATRIX_SYNC_TIMEOUT_MS` | int | `30000` |

### Trust (`HESTIA_TRUST_*`)

Prefix: `TRUST`

| Variable | Type | Default |
|----------|------|---------|
| `HESTIA_TRUST_AUTO_APPROVE_TOOLS` | list | `[]` |
| `HESTIA_TRUST_SCHEDULER_SHELL_EXEC` | bool | `false` |
| `HESTIA_TRUST_SCHEDULER_WRITE_LOCAL` | bool | `false` |
| `HESTIA_TRUST_SUBAGENT_SHELL_EXEC` | bool | `false` |
| `HESTIA_TRUST_SUBAGENT_WRITE_LOCAL` | bool | `false` |
| `HESTIA_TRUST_SUBAGENT_EMAIL_SEND` | bool | `false` |
| `HESTIA_TRUST_SCHEDULER_EMAIL_SEND` | bool | `false` |
| `HESTIA_TRUST_SELF_MANAGEMENT` | bool | `false` |
| `HESTIA_TRUST_BLOCKED_SHELL_PATTERNS` | list | `[]` |
| `HESTIA_TRUST_WRITE_GUARD_ENABLED` | bool | `true` |
| `HESTIA_TRUST_PRESET` | string | `null` |
| `HESTIA_TRUST_CHECKPOINT_ON_EDIT` | bool | `true` |
| `HESTIA_TRUST_AUTO_ROLLBACK_ON_FAILURE` | bool | `false` |

### Web Search (`HESTIA_WEB_SEARCH_*`)

Prefix: `WEB_SEARCH`

| Variable | Type | Default |
|----------|------|---------|
| `HESTIA_WEB_SEARCH_PROVIDER` | string | *(empty)* |
| `HESTIA_WEB_SEARCH_API_KEY` | string | *(empty)* |
| `HESTIA_WEB_SEARCH_MAX_RESULTS` | int | `5` |
| `HESTIA_WEB_SEARCH_INCLUDE_RAW_CONTENT` | bool | `false` |
| `HESTIA_WEB_SEARCH_SEARCH_DEPTH` | string | `basic` |
| `HESTIA_WEB_SEARCH_TIME_RANGE` | string | `null` |

### Handoff (`HESTIA_HANDOFF_*`)

Prefix: `HANDOFF`

| Variable | Type | Default |
|----------|------|---------|
| `HESTIA_HANDOFF_ENABLED` | bool | `false` |
| `HESTIA_HANDOFF_MIN_MESSAGES` | int | `4` |
| `HESTIA_HANDOFF_MAX_CHARS` | int | `350` |

### Compression (`HESTIA_COMPRESSION_*`)

Prefix: `COMPRESSION`

| Variable | Type | Default |
|----------|------|---------|
| `HESTIA_COMPRESSION_ENABLED` | bool | `false` |
| `HESTIA_COMPRESSION_MAX_CHARS` | int | `400` |

### Security (`HESTIA_SECURITY_*`)

Prefix: `SECURITY`

| Variable | Type | Default |
|----------|------|---------|
| `HESTIA_SECURITY_INJECTION_SCANNER_ENABLED` | bool | `true` |
| `HESTIA_SECURITY_INJECTION_ENTROPY_THRESHOLD` | float | `5.5` |
| `HESTIA_SECURITY_INJECTION_SKIP_FILTERS_FOR_STRUCTURED` | bool | `true` |
| `HESTIA_SECURITY_EGRESS_AUDIT_ENABLED` | bool | `true` |

### Email (`HESTIA_EMAIL_*`)

Prefix: `EMAIL`

| Variable | Type | Default |
|----------|------|---------|
| `HESTIA_EMAIL_IMAP_HOST` | string | *(empty)* |
| `HESTIA_EMAIL_IMAP_PORT` | int | `993` |
| `HESTIA_EMAIL_SMTP_HOST` | string | *(empty)* |
| `HESTIA_EMAIL_SMTP_PORT` | int | `587` |
| `HESTIA_EMAIL_USERNAME` | string | *(empty)* |
| `HESTIA_EMAIL_PASSWORD` | string | *(empty)* |
| `HESTIA_EMAIL_PASSWORD_ENV` | string | `null` |
| `HESTIA_EMAIL_DEFAULT_FOLDER` | string | `INBOX` |
| `HESTIA_EMAIL_DRAFTS_FOLDER` | string | `Drafts` |
| `HESTIA_EMAIL_SENT_FOLDER` | string | `Sent` |
| `HESTIA_EMAIL_MAX_FETCH` | int | `50` |
| `HESTIA_EMAIL_SANITIZE_HTML` | bool | `true` |
| `HESTIA_EMAIL_INJECTION_SCAN` | bool | `true` |

### Reflection (`HESTIA_REFLECTION_*`)

Prefix: `REFLECTION`

| Variable | Type | Default |
|----------|------|---------|
| `HESTIA_REFLECTION_ENABLED` | bool | `true` |
| `HESTIA_REFLECTION_CRON` | string | `0 3 * * *` |
| `HESTIA_REFLECTION_IDLE_MINUTES` | int | `15` |
| `HESTIA_REFLECTION_LOOKBACK_TURNS` | int | `100` |
| `HESTIA_REFLECTION_PROPOSALS_PER_RUN` | int | `5` |
| `HESTIA_REFLECTION_EXPIRE_DAYS` | int | `14` |
| `HESTIA_REFLECTION_MODEL_OVERRIDE` | string | `null` |

### Style (`HESTIA_STYLE_*`)

Prefix: `STYLE`

| Variable | Type | Default |
|----------|------|---------|
| `HESTIA_STYLE_ENABLED` | bool | `true` |
| `HESTIA_STYLE_MIN_TURNS_TO_ACTIVATE` | int | `20` |
| `HESTIA_STYLE_LOOKBACK_DAYS` | int | `30` |
| `HESTIA_STYLE_CRON` | string | `15 3 * * *` |

### Policy (`HESTIA_POLICY_*`)

Prefix: `POLICY`

| Variable | Type | Default |
|----------|------|---------|
| `HESTIA_POLICY_DELEGATION_KEYWORDS` | tuple | `null` |
| `HESTIA_POLICY_RESEARCH_KEYWORDS` | tuple | `null` |
| `HESTIA_POLICY_MAX_TOOL_CALLS_PER_TURN` | int | `10` |

### Voice (`HESTIA_VOICE_*`)

Prefix: `VOICE`

| Variable | Type | Default |
|----------|------|---------|
| `HESTIA_VOICE_STT_MODEL` | string | `faster-whisper/large-v3-turbo` |
| `HESTIA_VOICE_STT_DEVICE` | string | `cuda` |
| `HESTIA_VOICE_STT_COMPUTE_TYPE` | string | `int8` |
| `HESTIA_VOICE_TTS_ENGINE` | string | `piper` |
| `HESTIA_VOICE_TTS_VOICE` | string | `en_US-amy-medium` |
| `HESTIA_VOICE_TTS_SPEED` | float | `1.0` |
| `HESTIA_VOICE_MODEL_CACHE_DIR` | string | `~/.cache/hestia/voice` |

### Web (`HESTIA_WEB_*`)

Prefix: `WEB`

| Variable | Type | Default |
|----------|------|---------|
| `HESTIA_WEB_ENABLED` | bool | `false` |
| `HESTIA_WEB_HOST` | string | `127.0.0.1` |
| `HESTIA_WEB_PORT` | int | `8765` |
| `HESTIA_WEB_AUTH_ENABLED` | bool | `true` |
| `HESTIA_WEB_SESSION_LIFETIME_HOURS` | int | `72` |
| `HESTIA_WEB_CODE_EXPIRY_SECONDS` | int | `300` |
| `HESTIA_WEB_CODE_LENGTH` | int | `6` |

### Browser (`HESTIA_BROWSER_*`)

Prefix: `BROWSER`

| Variable | Type | Default |
|----------|------|---------|
| `HESTIA_BROWSER_ENABLED` | bool | `false` |
| `HESTIA_BROWSER_SESSION_DIR` | string | `~/.hestia/browser-sessions` |
| `HESTIA_BROWSER_HEADLESS` | bool | `true` |
| `HESTIA_BROWSER_DEFAULT_TIMEOUT_SECONDS` | int | `30` |

### Rate Limit (`HESTIA_RATE_LIMIT_*`)

Prefix: `RATE_LIMIT`

| Variable | Type | Default |
|----------|------|---------|
| `HESTIA_RATE_LIMIT_ENABLED` | bool | `false` |
| `HESTIA_RATE_LIMIT_REQUESTS_PER_MINUTE` | float | `30.0` |
| `HESTIA_RATE_LIMIT_BURST_SIZE` | int | `5` |
| `HESTIA_RATE_LIMIT_MAX_BUCKETS` | int | `10000` |

## Password Environment Variables

Email and Matrix passwords can be stored in dedicated env vars rather than
`config.py`:

```python
# config.py
email=EmailConfig(
    password_env="EMAIL_PASSWORD",
)
```

The actual password is then read from the named environment variable at
runtime. This keeps secrets out of version-controlled config files.

## Usage Tips

- **Booleans**: use `true`, `1`, `yes`, or `on` for true; anything else is false.
- **Lists**: comma-separated (e.g. `HESTIA_STORAGE_ALLOWED_ROOTS=".,/tmp"`).
- **Paths**: relative to the working directory where Hestia is launched.
