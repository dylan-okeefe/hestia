# Environment Variables Reference

Hestia reads configuration from three layers (highest precedence first):

1. **CLI flags** (e.g. `--config`, `--new-session`)
2. **Environment variables** (this document)
3. **`config.py`** fields

Most config classes support `from_env()` — fields are mapped automatically
using the pattern `HESTIA_{PREFIX}_{FIELD_NAME_UPPER}`.

## Special / Hand-picked Variables

These are handled explicitly in code and are **not** part of the auto-generated
mapping above.

| Variable | Purpose | Example |
|----------|---------|---------|
| `HESTIA_ALLOW_DUMMY_MODEL` | Set to `1` to allow the dummy model (`model_name="dummy"`) for testing without a real inference server. | `1` |
| `HESTIA_SOUL_PATH` | Override the path to `SOUL.md` (personality file). | `/opt/hestia/SOUL.md` |
| `HESTIA_CALIBRATION_PATH` | Override the path to `docs/calibration.json`. | `/opt/hestia/calibration.json` |
| `HESTIA_EXPERIMENTAL_SKILLS` | Set to `1` to enable the experimental skills subsystem. | `1` |

## Auto-generated Mappings

### Top-level (`HESTIA_*`)

Prefix: `HESTIA`

| Variable | Type | Default |
|----------|------|---------|
| `HESTIA_SYSTEM_PROMPT` | string | `"You are a helpful assistant."` |
| `HESTIA_MAX_ITERATIONS` | int | `10` |
| `HESTIA_VERBOSE` | bool | `false` |

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
| `HESTIA_INFERENCE_API_KEY` | string | *(empty)* |
| `HESTIA_INFERENCE_MAX_TOKENS` | int | `1024` |
| `HESTIA_INFERENCE_TEMPERATURE` | float | `0.7` |
| `HESTIA_INFERENCE_TOP_P` | float | `1.0` |
| `HESTIA_INFERENCE_DEFAULT_REASONING_BUDGET` | int | `2048` |
| `HESTIA_INFERENCE_CONNECT_TIMEOUT_SECONDS` | float | `10.0` |
| `HESTIA_INFERENCE_READ_TIMEOUT_SECONDS` | float | `60.0` |

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
| `HESTIA_SCHEDULER_MAX_CONCURRENT` | int | `3` |
| `HESTIA_SCHEDULER_RETRY_BACKOFF_BASE_SECONDS` | float | `5.0` |
| `HESTIA_SCHEDULER_RETRY_MAX_ATTEMPTS` | int | `3` |

### Storage (`HESTIA_STORAGE_*`)

Prefix: `STORAGE`

| Variable | Type | Default |
|----------|------|---------|
| `HESTIA_STORAGE_DATABASE_URL` | string | `sqlite+aiosqlite:///hestia.db` |
| `HESTIA_STORAGE_ARTIFACTS_DIR` | string | `artifacts` |
| `HESTIA_STORAGE_ALLOWED_ROOTS` | list | `.` |

### Telegram (`HESTIA_TELEGRAM_*`)

Prefix: `TELEGRAM`

| Variable | Type | Default |
|----------|------|---------|
| `HESTIA_TELEGRAM_BOT_TOKEN` | string | *(empty)* |
| `HESTIA_TELEGRAM_ALLOWED_USERS` | list | *(empty)* |
| `HESTIA_TELEGRAM_RATE_LIMIT_EDITS_SECONDS` | float | `1.5` |
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
| `HESTIA_TRUST_REQUIRE_CONFIRMATION` | bool | `true` |
| `HESTIA_TRUST_MAX_FILE_SIZE_MB` | int | `10` |
| `HESTIA_TRUST_ALLOW_REMOTE_EXECUTION` | bool | `false` |
| `HESTIA_TRUST_ALLOW_WEB_SEARCH` | bool | `false` |
| `HESTIA_TRUST_ALLOW_EMAIL_READ` | bool | `false` |
| `HESTIA_TRUST_ALLOW_EMAIL_SEND` | bool | `false` |
| `HESTIA_TRUST_ALLOW_SCHEDULER` | bool | `false` |

### Web Search (`HESTIA_WEB_SEARCH_*`)

Prefix: `WEB_SEARCH`

| Variable | Type | Default |
|----------|------|---------|
| `HESTIA_WEB_SEARCH_PROVIDER` | string | *(empty)* |
| `HESTIA_WEB_SEARCH_API_KEY` | string | *(empty)* |
| `HESTIA_WEB_SEARCH_MAX_RESULTS` | int | `5` |

### Handoff (`HESTIA_HANDOFF_*`)

Prefix: `HANDOFF`

| Variable | Type | Default |
|----------|------|---------|
| `HESTIA_HANDOFF_ENABLED` | bool | `false` |
| `HESTIA_HANDOFF_MIN_TURNS` | int | `5` |
| `HESTIA_HANDOFF_SUMMARY_MODEL` | string | *(empty)* |

### Compression (`HESTIA_COMPRESSION_*`)

Prefix: `COMPRESSION`

| Variable | Type | Default |
|----------|------|---------|
| `HESTIA_COMPRESSION_ENABLED` | bool | `false` |
| `HESTIA_COMPRESSION_THRESHOLD_TOKENS` | int | `6144` |

### Security (`HESTIA_SECURITY_*`)

Prefix: `SECURITY`

| Variable | Type | Default |
|----------|------|---------|
| `HESTIA_SECURITY_INJECTION_SCAN_ENABLED` | bool | `true` |
| `HESTIA_SECURITY_INJECTION_SCAN_THRESHOLD` | float | `0.7` |
| `HESTIA_SECURITY_SSRF_BLOCK_PRIVATE_IPS` | bool | `true` |
| `HESTIA_SECURITY_SSRF_ALLOWED_SCHEMES` | list | `http, https` |

### Email (`HESTIA_EMAIL_*`)

Prefix: `EMAIL`

| Variable | Type | Default |
|----------|------|---------|
| `HESTIA_EMAIL_IMAP_SERVER` | string | *(empty)* |
| `HESTIA_EMAIL_IMAP_PORT` | int | `993` |
| `HESTIA_EMAIL_IMAP_USERNAME` | string | *(empty)* |
| `HESTIA_EMAIL_IMAP_PASSWORD` | string | *(empty)* |
| `HESTIA_EMAIL_IMAP_PASSWORD_ENV` | string | *(empty)* |
| `HESTIA_EMAIL_IMAP_USE_SSL` | bool | `true` |
| `HESTIA_EMAIL_IMAP_FOLDER` | string | `INBOX` |
| `HESTIA_EMAIL_SMTP_SERVER` | string | *(empty)* |
| `HESTIA_EMAIL_SMTP_PORT` | int | `587` |
| `HESTIA_EMAIL_SMTP_USERNAME` | string | *(empty)* |
| `HESTIA_EMAIL_SMTP_PASSWORD` | string | *(empty)* |
| `HESTIA_EMAIL_SMTP_PASSWORD_ENV` | string | *(empty)* |
| `HESTIA_EMAIL_SMTP_USE_TLS` | bool | `true` |
| `HESTIA_EMAIL_SMTP_FROM` | string | *(empty)* |
| `HESTIA_EMAIL_SANITIZE_HTML` | bool | `true` |

### Reflection (`HESTIA_REFLECTION_*`)

Prefix: `REFLECTION`

| Variable | Type | Default |
|----------|------|---------|
| `HESTIA_REFLECTION_ENABLED` | bool | `false` |
| `HESTIA_REFLECTION_INTERVAL_HOURS` | int | `24` |
| `HESTIA_REFLECTION_MIN_TURNS` | int | `20` |
| `HESTIA_REFLECTION_MODEL` | string | *(empty)* |
| `HESTIA_REFLECTION_AUTO_ACCEPT` | bool | `false` |

### Style (`HESTIA_STYLE_*`)

Prefix: `STYLE`

| Variable | Type | Default |
|----------|------|---------|
| `HESTIA_STYLE_ENABLED` | bool | `false` |
| `HESTIA_STYLE_MIN_TURNS_TO_ACTIVATE` | int | `10` |
| `HESTIA_STYLE_MAX_AGE_DAYS` | int | `30` |
| `HESTIA_STYLE_UPDATE_INTERVAL_HOURS` | int | `24` |

### Policy (`HESTIA_POLICY_*`)

Prefix: `POLICY`

| Variable | Type | Default |
|----------|------|---------|
| `HESTIA_POLICY_DELEGATION_ENABLED` | bool | `true` |
| `HESTIA_POLICY_DELEGATION_THRESHOLD` | int | `3` |
| `HESTIA_POLICY_MAX_TOOL_CALLS_PER_TURN` | int | `5` |

### Voice (`HESTIA_VOICE_*`)

Prefix: `VOICE`

| Variable | Type | Default |
|----------|------|---------|
| `HESTIA_VOICE_ENABLED` | bool | `false` |
| `HESTIA_VOICE_STT_MODEL` | string | *(empty)* |
| `HESTIA_VOICE_TTS_MODEL` | string | *(empty)* |
| `HESTIA_VOICE_SAMPLE_RATE` | int | `24000` |
| `HESTIA_VOICE_INPUT_DEVICE` | int | `-1` |
| `HESTIA_VOICE_OUTPUT_DEVICE` | int | `-1` |

## Password Environment Variables

Email and Matrix passwords can be stored in dedicated env vars rather than
`config.py`:

```python
# config.py
email=EmailConfig(
    imap_password_env="EMAIL_IMAP_PASSWORD",
    smtp_password_env="EMAIL_SMTP_PASSWORD",
)
```

The actual password is then read from the named environment variable at
runtime. This keeps secrets out of version-controlled config files.

## Usage Tips

- **Booleans**: use `true`, `1`, `yes`, or `on` for true; anything else is false.
- **Lists**: comma-separated (e.g. `HESTIA_STORAGE_ALLOWED_ROOTS=".,/tmp"`).
- **Paths**: relative to the working directory where Hestia is launched.
