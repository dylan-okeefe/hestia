# Spec — manual /compact command

**Status:** Spec ready. Decisions resolved in `docs/reviews/decisions-compact-command.md`.
**Loop:** assign the next free L-number when queued (avoid collision with the in-flight read_artifact and UX loops on the dev box).
**Branch:** off `develop`.

## Goal

A user-invoked `/compact` meta-command that compacts the current session in place, without starting a new session, to free context and speed up subsequent turns on the local model. Reuses existing machinery (session summarizer, slot lifecycle, meta-command framework) rather than building a parallel compactor.

## Scope

### §1 — Meta-command
- Add `/compact` (optionally `/compact <instruction>`) to `commands/meta.py`, available on all surfaces (CLI, Telegram, Matrix).
- Acquire the per-session lock for the duration (it mutates the session); do not compact while a turn is running.
- Show a "compacting..." in-flight state; it costs one LLM call.

### §2 — Task-aware summarization
- Reuse the session summarizer / handoff machinery, but with a compaction-specific prompt that emits a structured task-state summary: goal, criteria, progress/done, pending, key findings, artifact paths (decision #3). This is the same operation as new-session-with-handoff, except the result folds back into the SAME session id.
- `/compact <instruction>` passes the instruction into the summary prompt to steer what is preserved (decision #5).

### §3 — Persist + archive + slot lifecycle
- Replace the active message history with [summary message + last K turns verbatim], K configurable, default a token-aware tail (~4-6 turns) (decisions #1, #2).
- Archive the original messages (mark pre-compaction, recoverable); do not delete.
- Erase the session's KV slot so the next turn rebuilds COLD from the smaller history (reuse the L221 non-DONE slot-erase path) (decision #7).

### §4 — Narrow memory flush
- In the same summarization call, write only the structured task-state fields to the memory store, with dedup against existing entries (decision #4). No general fact extraction.

### §5 — Write-time memory filter (companion)
- Add a sanitizer/validator at the shared memory-store write boundary that rejects/strips tool-call XML, unclosed tags, raw assistant/tool turn dumps, and trivially low-value content (decision #6). Applies to all memory writes, not just compaction.

## Tests
- `/compact` on a long session replaces history with [summary + last K verbatim], archives originals (recoverable), and erases the slot.
- The summary preserves task-state fields (goal, criteria, artifact paths) on a job-search-style transcript.
- `/compact <instruction>` biases the summary toward the instruction.
- The narrow flush writes the task-state fields to memory and dedups a repeat.
- The write-time filter rejects a tool-call-XML memory write and a raw-turn-dump write; accepts a clean fact.
- Compaction takes the session lock and does not run concurrently with a turn.

## Acceptance
- Gates green (pytest, mypy, ruff, web-ui build).
- `.kimi-done` includes the assigned loop number.
- Manual: compact a long session, confirm the next turn is smaller/faster and task state survived.

## Related, deferred
- Overnight memory dedupe/pruning is a separate loop and needs its own decision pass (destructive operation; see `decisions-compact-command.md`).
- Warrants its own ADR (manual in-session compaction changes how session history is persisted); reuses ADR-013 (slots), ADR-022/023 (identity/memory epochs), and the handoff service.

## Critical rules
- Do not merge or push without Dylan's okay.
- Compaction must be recoverable: archive originals, never hard-delete.
- Reuse the summarizer and slot-erase paths; do not build a parallel compactor.
