# L74 — UX Gaps & Config Validation

## Intent & Meaning

This loop closes three friction points identified in the evaluation: the inability to view conversation history from the CLI, cryptic failures on broken configs, and unhelpful "Something went wrong" error messages.

The intent is **reduce the gap between "I want to do something" and "I can do it."** Local data you cannot retrieve is not much better than data in the cloud. And a tool that starts with a broken config, only to fail three turns later with a confusing timeout, wastes the operator's time.

## Changes Made

### §1 — `hestia history` command

**`src/hestia/commands/history.py`** (new)
- `cmd_history_list` — lists recent sessions with id, platform, user, last active, state
- `cmd_history_show` — prints conversation for a session with color-coded role labels
- Both support `--json` for scripting

**`src/hestia/persistence/sessions.py`**
- Added `SessionStore.list_sessions(limit=20)` — returns recent sessions ordered by `last_active_at desc`

**`src/hestia/cli.py`**
- Registered `history [session_id]` command

**`src/hestia/commands/__init__.py`**
- Exported `cmd_history_list`, `cmd_history_show`

### §2 — Startup config validation

**`src/hestia/errors.py`**
- Added `HestiaConfigError(ValueError)`

**`src/hestia/app.py`**
- Added `_validate_config_at_startup(cfg)` called from `make_app()` before subsystem creation:
  - If `telegram.allowed_users` is set but `bot_token` is empty → error
  - If either `email.imap_host` or `email.smtp_host` is set but the other is missing → error
  - If `storage.database_url` is a sqlite file path and parent directory does not exist → error

### §3 — Better user-facing error messages

**`src/hestia/orchestrator/finalization.py`**
- Expanded `sanitize_user_error` to map common failures to actionable messages:
  - `InferenceTimeoutError` → "The AI is taking longer than expected. Try again in a moment."
  - `ContextTooLargeError` → "Our conversation has grown very long. I'll summarize and continue..."
  - `ToolExecutionError` → "I tried to use the {tool} tool but it failed. You can retry..."
  - `MaxIterationsError` / `PolicyFailureError` → "I'm having trouble responding right now. Please try again."

## Verification

- `pytest tests/unit/ tests/integration/ -q` → **1057 passed, 6 skipped**
- `ruff check` on changed files → **all checks passed**
- `mypy` on changed files → **no issues**

## Commit

```
feat(cli,app,ux): history command, startup validation, better error messages
```

## Risks & Follow-ups

- **None.** All changes are additive with safe defaults.
- The `history` command relies on `SessionStore.list_sessions()` which does not filter by platform/user. In multi-tenant deployments this may need scoping.
- Startup validation does not attempt a live `GET /health` to the inference server (spec mentioned this as optional). It can be added later if operators find value in it.
