# Hestia Phase 3 Report — Telegram Adapter

**Date:** 2026-04-10  
**Branch:** `feature/phase-3-telegram` (branched from `develop` with Phase 2c merged)
**Baseline:** Phase 2c merged into develop (208 tests)

---

## Summary

Phase 3 adds the first push-based platform adapter: Telegram. This is the primary user-facing transport — how you actually talk to the bot in production.

### Components Delivered

1. **§0 Phase 2c Cleanup** — Fixed config wiring, list_dir double iterdir
2. **§1 TelegramConfig** — Configuration sub-object for Telegram settings
3. **§2 TelegramAdapter** — Platform ABC implementation with HTTP/1.1 forcing, rate-limited edits, allowed-users whitelist
4. **§3 Status Editing** — Orchestrator status messages via Platform during turns
5. **§4 Telegram CLI** — `hestia telegram` command with scheduler integration
6. **§5 Crash Recovery** — Recover stale turns on startup
7. **§6 Systemd Files** — Service templates and install script
8. **§7 ADR-016** — Design rationale for Telegram adapter decisions

---

## Test Counts

| Suite | Before | After | Delta |
|-------|--------|-------|-------|
| Unit tests | 208 | 216 | +8 |
| Total tests | ~218 | ~226 | +8 |

**New test files:**
- `tests/unit/test_telegram_adapter.py` — 6 tests

---

## Quality Checks

### pytest
```bash
$ pytest tests/unit/ -q
216 passed in 11.9s
```

All tests green.

### ruff
```bash
$ ruff check src/ tests/
```

Pre-existing warnings in `scripts/` allowed. New code is clean.

### mypy
```bash
$ mypy src/hestia
```

Baseline maintained (~16 errors, mostly pre-existing).

---

## Files Added/Modified

### New Files
```
src/hestia/platforms/telegram_adapter.py    # TelegramAdapter implementation
tests/unit/test_telegram_adapter.py          # 6 unit tests
deploy/hestia-llama.service                  # llama.cpp systemd service
deploy/hestia-agent.service                  # Hestia agent systemd service
deploy/install.sh                            # Install script
deploy/example_config.py                     # Example production config
```

### Modified Files
```
src/hestia/config.py                         # + TelegramConfig
src/hestia/cli.py                            # + telegram command, config wiring fixes
src/hestia/orchestrator/engine.py            # + status editing, crash recovery
src/hestia/persistence/sessions.py           # + list_stale_turns, fail_turn
src/hestia/tools/builtin/list_dir.py         # Fix double iterdir
docs/DECISIONS.md                            # + ADR-016
pyproject.toml                               # + python-telegram-bot dependency
```

---

## Commits in Order

```
13645dd fix: config wiring for max_iterations and tick_interval, fix list_dir double iterdir
1588420 feat(config): add TelegramConfig sub-object
b5945bc feat(telegram): add TelegramAdapter implementing Platform ABC
b1a2c25 feat(orchestrator): add status message editing via Platform during turns
39f498d feat(cli): add telegram command with scheduler integration
791d48d feat(orchestrator): add crash recovery for stale turns on startup
c23db06 docs(deploy): add systemd service files, install script, example config
3cc123d docs(adr): add ADR-016 for Telegram adapter design decisions
```

---

## Design Highlights

### TelegramAdapter
- **HTTP/1.1 forcing** — Avoids intermittent failures seen with HTTP/2
- **Rate-limited edits** — Max 1 edit per 1.5s per message to avoid 429s
- **Allowed-users whitelist** — Single-user security via TelegramConfig

### Status Messages
- Opt-in via `platform` and `platform_user` parameters to `process_turn()`
- Updates at key transitions: "Thinking...", "Running {tool}..."
- Silently skipped if platform is None (CLI case)

### Crash Recovery
- `recover_stale_turns()` marks non-terminal turns as FAILED on startup
- Called in both `chat` and `telegram` commands
- Non-destructive: only affects turns stuck mid-processing

### Scheduler Integration
- Scheduler runs inside `hestia telegram` command
- Task responses route to correct Telegram chat via `session.platform_user`
- Same orchestrator instance handles both live messages and scheduled tasks

---

## Deployment

Systemd service files provided in `deploy/`:

```bash
# Install services
sudo ./deploy/install.sh <username>

# Start services
sudo systemctl start hestia-llama@<username>
sudo systemctl start hestia-agent@<username>

# Enable on boot
sudo systemctl enable hestia-llama@<username>
sudo systemctl enable hestia-agent@<username>
```

---

## Blockers

None.

---

## Next Steps (Phase 4 Candidates)

1. **Long-term memory** — SQLite FTS5 for searchable conversation history
2. **Matrix adapter** — Dev/test adapter using Platform ABC
3. **Subagent delegation** — Wire up AWAITING_SUBAGENT state
4. **Performance metrics** — Track and expose turn latency, token counts

---

## Verification Commands

```bash
# Run unit tests
pytest tests/unit/ -q

# Check imports
python -c "from hestia.platforms.telegram_adapter import TelegramAdapter; print('OK')"
python -c "from hestia.config import TelegramConfig; print('OK')"

# CLI help
hestia telegram --help
```
