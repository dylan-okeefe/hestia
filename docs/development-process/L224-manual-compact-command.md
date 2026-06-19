# L224 — Manual `/compact` command

**Status:** Spec ready. Implement after L225 merges (shared memory-write sanitizer).
**Branch:** `feature/l224-manual-compact-command` (from `develop` after L225 merges)
**Depends on:** L225 (shared memory-write sanitizer — the narrow compaction flush must pass through the sanitized boundary)
**ADR:** `docs/adr/ADR-047-manual-in-session-compaction.md`

## Goal

Deliver a user-invoked `/compact` meta-command that compacts the current session in place, without starting a new session, to free context and speed up subsequent turns on the local model. Reuses the session summarizer / handoff machinery, the per-session lock, and the existing non-DONE slot-erase path.

## Review carry-forward

- *(none — new spec-driven arc)*

## Scope

### §1 — Meta-command

- Add `/compact` and `/compact <instruction>` to `commands/meta.py`, available on all surfaces (CLI, Telegram, Matrix).
- Acquire the per-session lock for the duration; refuse to compact while a turn is running.
- Show a "compacting..." in-flight state; the operation costs one LLM call.

**Commit:** `feat(commands): add /compact meta-command with session lock and in-flight state`

### §2 — Task-aware summarization

- Reuse `HandoffService` / session summarizer with a compaction-specific prompt that emits a structured task-state summary: goal, criteria, progress/done, pending, key findings, artifact paths.
- `/compact <instruction>` passes the instruction into the summary prompt to steer what is preserved.
- The summary is emitted as a single synthetic `user` message with `is_handoff=True` so the context builder treats it as a protected prefix.

**Commit:** `feat(orchestrator): task-aware compaction summarizer with user instruction steering`

### §3 — Persist + archive + slot lifecycle

- Replace the active message history with `[summary message + last K turns verbatim]`, where K is configurable and defaults to a token-aware tail of roughly the last 4-6 turns.
- Archive the original messages: copy them to a recoverable store/table marked `pre_compaction` for the session. Do not delete originals until compaction is confirmed successful; better, never delete and instead mark them archived.
- Erase the session's KV slot after compaction so the next turn rebuilds COLD from the smaller history (reuse the L221 non-DONE slot-erase path).

**Commit:** `feat(persistence): compact session history, archive originals, erase slot`

### §4 — Narrow memory flush

- In the same summarization call, write only the structured task-state fields (goal, criteria, key findings, artifact paths) to the memory store, with deduplication against existing entries.
- The flush goes through the shared memory-write sanitizer added in L225.
- No general "extract any interesting fact" pass.

**Commit:** `feat(memory): narrow task-state flush from compaction via shared sanitizer`

## Tests

- `/compact` on a long session replaces history with `[summary + last K verbatim]`, archives originals (recoverable), and erases the slot.
- The summary preserves task-state fields (goal, criteria, artifact paths) on a job-search-style transcript.
- `/compact <instruction>` biases the summary toward the instruction.
- The narrow flush writes the task-state fields to memory and dedups a repeat.
- Compaction takes the session lock and does not run concurrently with a turn.

## Acceptance

- `uv run pytest tests/unit/ tests/integration/ -q` green
- `uv run mypy src/hestia` reports 0 errors
- `uv run ruff check src/ tests/` at baseline or better (line-length 120)
- `.kimi-done` includes `LOOP=L224`
- Manual: compact a long session, confirm the next turn is smaller/faster and task state survived.

## Handoff

- Write `docs/handoffs/L224-manual-compact-command-handoff.md`
- Update `docs/development-process/kimi-loop-log.md`
- Advance `docs/development-process/prompts/KIMI_CURRENT.md` to the next queued item (or idle)

## Critical rules recap

- Do not merge or push without Dylan's okay.
- Compaction must be recoverable: archive originals, never hard-delete.
- Reuse the summarizer, session lock, and slot-erase paths; do not build a parallel compactor.
- The memory flush must pass through the L225 sanitizer.
