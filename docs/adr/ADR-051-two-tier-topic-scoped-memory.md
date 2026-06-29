# ADR-051: Two-tier topic-scoped memory

- **Status:** Accepted
- **Date:** 2026-06-29
- **Related:** Extends ADR-023 (memory epochs) and ADR-049 (overnight memory
  maintenance); builds on ADR-029 (SQLite FTS5 long-term memory).
- **Decisions:** `docs/reviews/decisions-thread-scoped-memory.md`.
  **Spec:** `docs/reviews/spec-thread-scoped-memory.md`. Implemented as loops
  L237 (backend), L238 (scope-aware maintenance), and L239 (memory UI).

## Context

Memory was keyed only by `(platform, platform_user)`, so every conversation a
person had shared one flat pool. A user who keeps deliberately separate topic
chats (for example a testing chat, a job-search chat, and a general chat with the
same assistant) had context bleed between them, while a flat per-thread pool would
have lost universal facts like identity and preferences. Two kinds of fact were
colliding: user-global facts that should be known everywhere, and thread-local
facts that are noise outside their thread.

## Decision

Give memory a two-tier scope: a global pool that is always injected, and a
topic-scoped pool keyed on user-named topics rather than rigid room ids.

**Data model (additive runtime migration, not Alembic).** A boolean `is_global`
column on the FTS `memory` table, plus three new tables: `topics` (user-named,
scoped to `platform`/`platform_user`), `conversation_topics`
(conversation to topic subscriptions), and `memory_topics` (memory to topic,
many-to-many). The implicit per-conversation pool is modeled as an auto per-room
topic named `room:<conversation_id>` so retrieval and migration share one code
path. A global memory carries `is_global = 1` and no topic rows; the two are
mutually exclusive.

**Capture scoping.** The only capture-time judgment is a coarse global-vs-topic
choice, driven by a prompt rule: identity and durable preferences are global,
everything else is topic-scoped. A topic-scoped save is associated with all of the
conversation's currently subscribed topics through a single shared resolver
(`TopicStore.resolve_capture_topic_ids`); if the conversation has no explicit
topics, the resolver creates and subscribes the implicit `room:<id>` topic so the
memory is still reachable. Scope is never assigned by the model's descriptive
tagging; topics are a separate, explicit retrieval layer from tags.

**Commands.** `/add-topic` subscribes a conversation to a topic and, on the first
add, migrates the conversation's implicit memories into it and drops the implicit
association so later adds do not re-migrate. `/remove-topic` unsubscribes without
un-associating existing memories. `/topic` lists subscriptions. `/remember-global`
forces a global save.

**Epoch composition.** Global memories are injected first up to a configurable
soft cap (default about 30 percent of the epoch token budget), then the subscribed
topics' memories by recency fill the remainder; slack flows down and the total
never exceeds the budget. In group chats the epoch is the active sender's global
memories plus the room's subscribed-topic memories. A sort-key seam is left for a
future per-memory importance score (recency for now).

**Maintenance (extends ADR-049).** Deduplication and supersession operate strictly
within scope: a global fact and a topic fact with identical content are not
duplicates, and cross-scope supersession does not occur. Scope is computed by a
shared key (global is one bucket; topic-scoped memories are keyed by their exact
sorted topic set). Protected set, retention, and undo all apply per scope.

**Migration.** On rollout all pre-existing memories become global, with no
automatic classification; nothing is dropped or re-scoped silently. Users curate
down to topics through the redesigned memory UI.

**Operator UI.** The Knowledge surface is a curation tool: memories grouped by
scope, per-memory edit, scope change, pin, and soft-delete with restore, plus
topic create/rename/delete. All scope and topic changes are explicit,
owner-authenticated user actions.

## Consequences

- Deliberately separate topic chats stay isolated while identity and preferences
  remain universal, matching real usage.
- The implicit per-room topic gives un-topic'd conversations a clean default and a
  single migration path when the user adds their first explicit topic.
- Scope changes only by explicit user action (or the deferred review-gated
  promotion pass), never as a side effect of model tagging, which keeps retrieval
  predictable.
- An all-global migration is safe and lossless, but it depends on the curation UI
  as the path back to an organized state.
- A scope-promotion pass (topic to global), review-gated through the Proposals
  system with optional ultra-high-confidence auto-promote plus digest and undo, is
  deferred to a future maintenance loop and is marked as such in
  `memory/maintenance/service.py`.
- A future per-memory importance score can slot into the epoch sort key without
  reworking composition.
