# Review — L237 thread/topic-scoped memory backend (Loop A)

**Branch:** `feature/l237-thread-scoped-memory-backend`
**Verdict:** Storage primitives are correct, but the capture path is unwired, which
is a blocking recall regression. Do not merge, and do not start Loop B or C, until
the items below land. Card #21 stays in In Review, not Done.
**Spec:** `docs/reviews/spec-thread-scoped-memory.md` (§2 capture scoping).
**Decisions:** `docs/reviews/decisions-thread-scoped-memory.md`.

## The blocker: new memories orphan from the epoch

`MemoryStore.get_for_epoch` returns a memory only if `is_global = 1`, or it has a
`memory_topics` row for a subscribed topic. But the real capture paths call
`MemoryStore.save()` with no `topic_ids` and no `is_global`, so every newly
captured memory lands `is_global = 0` with zero topic associations and is
retrieved by neither branch. It is stored but never injected into any future
epoch.

Pre-migration memories still inject (they are now `is_global = 1`), so old memory
survives, but everything captured going forward silently stops appearing in
context. This is a functional regression in passive recall and a silent skip of
spec §2 (capture scoping). The store primitives to scope a save exist; nothing
calls them.

Unwired callers (all currently scope-blind):

- `src/hestia/tools/builtin/memory_tools.py` — `save_memory`, the model's tool.
- `src/hestia/memory/compaction_summarizer.py` — session-end fact extraction.
- `src/hestia/memory/handoff.py` — handoff save.
- `src/hestia/cli.py` — manual `memory add`.

The only writer that sets scope correctly is `/remember-global` (`save_global`).

## Why the gates stayed green

The 541-line `tests/unit/memory/test_topic_scoped_memory.py` exercises the
primitives directly: every test calls `memory_store.save(..., topic_ids=[...])`
or `save_global(...)` and asserts on `get_for_epoch`. None of them save through
the `save_memory` tool or the extraction path and check that the memory lands in
the epoch. The building blocks are proven; the integration is not. The missing
test is the regression guard.

## Required fix

### 1. One shared capture-topic resolver

Add a single resolver so all non-global capture paths scope consistently. Put it
on `TopicStore` (`src/hestia/memory/topics.py`):

```
async def resolve_capture_topic_ids(conversation_id, platform, platform_user) -> list[str]
```

Behavior: return the conversation's subscribed topic ids
(`get_conversation_topic_ids`). If empty, `get_or_create_implicit_topic(...)`,
`subscribe_conversation(conversation_id, implicit.id)`, and return
`[implicit.id]`. Subscribing to the implicit topic is required so the read path
(`get_conversation_topic_ids` in `persistence/memory_epochs.py`) picks these
memories up, and so the first `/add-topic` `migrate_implicit_memories` finds the
implicit associations to migrate.

### 2. Wire the callers

- `save_memory` tool: inject `topic_store`; resolve topic ids for the current
  session and pass `topic_ids` to `save()`. Add an optional global flag to the
  tool (`scope = "global" | "topic"`, default `"topic"`) so the model can route
  identity and durable preferences to global per decision #6; when set, call
  `save_global()`. Add a concise capture rule to the memory section of the system
  prompt: identity and durable preferences are global, everything else is
  topic-scoped.
- `compaction_summarizer` (session-end extraction): topic-scoped by default,
  associate via the resolver for that session.
- `handoff`: topic-scoped via the resolver for that session.
- `cli.py` `memory add`: no conversation context, so `save_global()` (operator
  asserted durable fact). Confirm this reading in the handoff.

Keep `is_global` and topic association mutually exclusive (already true in
`save()`: `topic_ids` is ignored when `is_global=True`). Do not associate a global
memory with topics.

## Secondary fix (lower severity): non-FTS5 migration

The FTS5 recreate path correctly sets existing rows to `is_global = 1`, but the
non-FTS5 `_add_memory_column` path adds `is_global` with `DEFAULT 0`, and
`_migrate_existing_to_global` only updates `WHERE is_global IS NULL`, so on a
regular-table (non-FTS5) database existing memories stay non-global, violating §5.
Fix so legacy rows become global on the ALTER path too (default the column to 1
for the add-column case, or explicitly `UPDATE` existing rows at ALTER time).

## Tests to add

- **Integration (the regression guard):** save through the `save_memory` *tool* in
  a conversation with no explicit topics, then compile the epoch for that
  conversation and assert the memory is present. This must fail before the fix.
- `save_memory` in a conversation subscribed to two explicit topics associates the
  memory with both, and it appears in the epoch.
- A global capture (`scope="global"`) is `is_global=1` and appears in the epoch
  regardless of topics.
- Session-end extraction associates its memory with the conversation's topics and
  it appears in the epoch.
- Non-FTS5 migration: a pre-existing memory reads as global after migration.

## What is correct (for the record)

- Schema: the three tables (`topics`, `conversation_topics`, `memory_topics`) are
  clean and additive; no column changes to the FTS `memory` table beyond
  `is_global`.
- Migration on the FTS5 path (the one this database uses) is correct and
  idempotent: the recreate sets existing rows to `is_global = 1`.
- `TopicStore` and the first-add `migrate_implicit_memories` (copy then drop the
  implicit association so later adds do not re-migrate) are well built.
- `get_for_epoch`'s global-vs-topic split matches decisions #7/#8, including
  per-sender global in group chats.
- Commits are cleanly per-step; the `/add-topic` family is correctly registered
  through the ADR-050 command registry.

## Acceptance

- Gates green (pytest, mypy, ruff).
- The integration regression test above is present and passes.
- Per-item handoff accounting: each spec §2 item mapped to done.
- No merge/push without Dylan's okay; card #21 stays In Review until reviewed.
