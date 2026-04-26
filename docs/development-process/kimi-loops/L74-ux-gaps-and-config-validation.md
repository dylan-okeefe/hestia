# L74 — UX Gaps & Config Validation

**Status:** Spec ready. Feature branch work — merge to `develop` when green.

**Branch:** `feature/l74-ux-gaps-and-config-validation` (from `develop`)

## Goal

Close two usability gaps identified in the evaluation: the inability to view conversation history from the CLI, and the lack of startup-time config validation that could catch misconfigurations before they cause cryptic runtime errors.

---

## Intent & Meaning

The evaluation notes two friction points for operators:

1. **`hestia ask` is ephemeral with no session:** A user who runs `hestia ask` for a quick question cannot continue that conversation. The gap between "quick one-shot" and "persistent session" is abrupt. A `hestia history` command would let users retrieve past conversations.

2. **No config validation on startup:** `HestiaConfig.from_file()` validates the model name but does not check that the database URL is reachable, that IMAP is resolvable if email is configured, or that the Telegram token is non-empty if Telegram is the chosen platform. `hestia doctor` covers this, but it is a separate invocation. Startup should fail helpfully, not mysteriously.

The intent is **reduce the gap between "I want to do something" and "I can do it."** Hestia emphasizes "your data stays local," but local data you cannot retrieve is not much better than data in the cloud. And a tool that starts up with a broken config, only to fail three turns later with a confusing timeout, wastes the operator's time.

---

## Scope

### §1 — Add `hestia history` command

**Files:** `src/hestia/cli.py`, `src/hestia/commands/history.py` (new)
**Evaluation:** `hestia chat has no conversation history display`. The CLI chat mode doesn't show previous messages on startup.

**Change:**
Add a `hestia history [session_id]` command:
- With no argument: list recent sessions (id, platform, start time, message count).
- With a session id: print the conversation in a readable format (Markdown-like, with user/assistant prefixes).
- Optional `--format json` for scripting.

Use `SessionStore` and `MessageStore` (or the existing session retrieval API) to fetch data.

**Intent:** The CLI should be a first-class interface, not just a REPL. Operators should be able to audit and retrieve their data without writing SQL.

**Commit:** `feat(cli): add hestia history command for session retrieval`

---

### §2 — Startup config validation

**File:** `src/hestia/app.py`
**Evaluation:** No config validation on startup. Startup could fail more helpfully.

**Change:**
Add a `_validate_config_at_startup(config)` phase in `make_app()`:
- If `platform == "telegram"`, assert `telegram.bot_token` is non-empty.
- If `email.enabled`, assert `email.imap_host` and `email.smtp_host` are resolvable (or at least non-empty and syntactically valid).
- If `storage.database_url` is a file path, assert the parent directory exists.
- If `inference.base_url` is set, attempt a lightweight `GET /health` (optional, with a short timeout, and warn — don't fail — if unreachable).

Raise `HestiaConfigError` with a clear message on any failure.

**Intent:** A bad config should be caught at the front door, not discovered during the first turn.

**Commit:** `feat(app): validate config at startup with helpful error messages`

---

## Quality gates

```bash
uv run pytest tests/unit/ tests/integration/ -q
uv run mypy src/hestia
uv run ruff check src/ tests/
```

## Acceptance (Spec-Based)

- `hestia history` lists sessions.
- `hestia history <id>` prints a conversation.
- `make_app()` raises `HestiaConfigError` on obviously broken config before creating subsystems.
- All tests pass.

## Acceptance (Intent-Based)

- **A user can find that conversation from yesterday.** Run `hestia history`, pick a session ID, and see the full turn-by-turn exchange.
- **A broken config is obvious in under 2 seconds.** Introduce a deliberate misconfig (empty bot token, bad database path) and verify the error message tells you exactly what is wrong and which config field to fix.
- **Validation does not block valid configs.** A correct config should start without spurious warnings.

## Handoff

- Write `docs/handoffs/L74-ux-gaps-and-config-validation-handoff.md`.
- Update `docs/development-process/kimi-loop-log.md`.
- Merge `feature/l74-ux-gaps-and-config-validation` to `develop`.

## Dependencies

L71 (app context flattening) should merge first to avoid conflicts in `make_app()`.
