# L224 — Manual `/compact` command — Handoff

**Status:** Implementation complete. Branch `feature/l224-manual-compact-command`.
**Date:** 2026-06-19
**Depends on:** L225 (memory-write sanitizer) — already merged into this branch.

## What changed

### Core compaction service
- `src/hestia/orchestrator/compaction.py`
  - New `SessionCompactor` service orchestrates the entire `/compact` lifecycle.
  - Acquires the per-session lock via `SessionLockManager`; refuses to run concurrently with a turn.
  - Loads the session, generates a task-aware structured summary, archives every original message to `compaction_archive`, replaces active history with `[summary + last K verbatim turns]`, erases the KV slot, and flushes narrow task-state fields to memory.

### Task-aware summarizer
- `src/hestia/memory/compaction_summarizer.py`
  - New `SessionCompactionSummarizer` prompts the model for JSON with fields: `goal`, `criteria`, `progress_done`, `pending`, `key_findings`, `artifact_paths`, `summary`.
  - `/compact <instruction>` passes the instruction into the prompt to steer preservation.
  - Falls back gracefully to plain prose if JSON parsing fails.
  - Writes only the structured task-state fields to `MemoryStore.save()` so the L225 sanitizer filters junk automatically.
  - Exact-match dedupes against existing memories for the identity.

### Persistence
- `src/hestia/persistence/schema.py` — added `compaction_archive` table.
- `src/hestia/persistence/migrations/__init__.py` — added additive runtime migration `m008_compaction_archive`.
- `src/hestia/persistence/message_store.py` — added `archive_and_replace_messages(session_id, replacements, compacted_at)` which archives originals, deletes them, and inserts the replacement sequence in one transaction.

### Configuration
- `src/hestia/config.py` — added `CompactionConfig` with `enabled`, `verbatim_turns` (default 5), `summary_max_chars` (default 1500), `min_messages` (default 4). Placed under `features.compaction`.

### App wiring
- `src/hestia/app.py` — added shared `SessionLockManager`, `compaction_summarizer`, and `compactor` to `AppContext`; passes the shared lock manager into `Orchestrator`.

### Surface handlers
- `src/hestia/commands/meta.py` — added `/compact` and `/compact <instruction>` handling for CLI; shows "Compacting session..." in-flight state.
- `src/hestia/platforms/telegram_adapter.py` — added `/compact` command handler with status reply + edit on completion.
- `src/hestia/platforms/matrix_adapter.py` — added `/compact` command detection in room message handler.
- `src/hestia/platforms/runners.py` — injects `app.compactor` into Telegram and Matrix adapters.

### Tests
- `tests/unit/orchestrator/test_compaction.py` — 9 unit tests covering summary+tail replacement, archive recoverability, slot erase, lock refusal, disabled config, memory flush, dedup, instruction steering, and too-short refusal.
- `tests/integration/test_compaction_command.py` — 2 integration tests covering end-to-end `/compact` via `AppContext.compactor` and the CLI meta-command path.

## Quality gates

- `uv run pytest tests/unit/orchestrator/test_compaction.py tests/integration/test_compaction_command.py -q` → **11 passed**.
- `uv run pytest tests/unit/ -q` → **1915 passed**.
- `uv run pytest tests/integration/ -q` → **88 passed, 6 skipped**.
- `uv run mypy src/hestia` → **Success: no issues found in 208 source files**.
- `uv run ruff check src/ tests/` → **64 pre-existing errors**; no new errors introduced by L224 files.
- **Note:** Running `uv run pytest tests/unit/ tests/integration/ -q` in a single process exceeded the 300-second shell tool limit in this environment, but the same tests pass reliably when run separately. This appears to be an environment timeout, not a test failure.

## Secret scan

Ran the AGENTS.md secret scan; no credential-like strings were added:

```bash
git diff --cached -p | grep -iE "(api[_-]?key|token|secret|password|bearer)\s*[:=]\s*[\"'][a-zA-Z0-9_-]{20,}"
git diff --cached --name-only | xargs grep -iE "[0-9]+:[A-Za-z0-9_-]{35}" 2>/dev/null
```

No matches.

## Recovery / operational notes

- Original messages are **never hard-deleted**; they are copied to `compaction_archive` before replacement.
- The active history after `/compact` is `[synthetic handoff summary + last K verbatim turns]`.
- The KV slot is erased and the session demoted to `COLD` so the next turn rebuilds from the smaller history.
- The narrow memory flush reuses `MemoryStore.save()` and therefore the L225 sanitizer.

## Open / deferred

- Overnight memory dedupe/pruning remains explicitly deferred (see ADR-047 and decisions doc).
- Recovering a previous compaction from `compaction_archive` back into `messages` is not exposed via a command; the archive is for manual recovery/auditing only in v1.

## Next steps for orchestrator / Dylan

1. Review the branch diff.
2. Optional: run a live `/compact` on a long session to confirm the next turn is smaller/faster and task state survives.
3. Merge to `develop` when ready (do not merge without Dylan's okay).
4. Update `~/Hestia-runtime` with merged `develop` and restart services.
