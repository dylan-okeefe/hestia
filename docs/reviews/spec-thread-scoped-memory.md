# Spec — thread/topic-scoped memory

**Status:** Spec ready. Decisions resolved in
`docs/reviews/decisions-thread-scoped-memory.md`.
**Loops:** assign L-numbers when queued. Likely an arc of three loops (backend,
maintenance, web UI); split further per the no-skip rule if a loop is too large.
**Branch:** off `develop`.

## Goal

Give memory a two-tier scope (global + user-named topics) so a person's deliberately
separate topic chats stay isolated while identity/preferences remain universal, and
expose topics to the user through chat commands and a redesigned memory UI. Reuses
the existing FTS memory store, epoch compiler, meta-command framework, and the
ADR-049 maintenance subsystem.

## Loop A — Topic model, capture, epoch, migration (backend)

### §1 Data model
- New tables: `topics` (user-named), `conversation_topics` (room→topic
  subscriptions), `memory_topics` (memory↔topic many-to-many). Additive runtime
  migration.
- A `global` flag/reserved scope on memory (always-inject). The implicit
  per-conversation pool is an auto per-room topic (`room:<id>`).

### §2 Capture scoping
- Prompt rule: identity and durable preferences → global; everything else → the
  conversation's subscribed topics (all of them). Session-end extraction is
  topic-scoped.
- A topic-scoped save writes `memory_topics` rows for every currently subscribed
  topic (deterministic, no per-topic LLM choice).

### §3 Commands (`commands/meta.py`)
- `/add-topic <name>`: subscribe; on the first add, migrate the conversation's
  implicit memories to the topic and drop the implicit association; later adds
  affect future saves only.
- `/remove-topic <name>`: unsubscribe; subscription only, do not un-associate
  existing memories.
- `/topic`: show subscriptions.
- `/remember-global <fact>`: force a global save.

### §4 Epoch composition
- Global-first up to a configurable soft cap (default ~30% of `epoch_max_tokens`),
  then subscribed-topic memories by recency, slack flows down, total ≤ budget.
- Group chats: active sender's global + room's subscribed-topic memories.
- Leave a sort-key seam for a future `importance` score (recency for now).

### §5 Migration
- All existing memories → global on rollout. No classification.

**Tests:** topic save lands in all subscribed topics; `/add-topic` migrates
implicit memories once and not retroactively on later adds; `/remove-topic`
leaves memory associations intact; epoch respects the global cap and slack;
group-chat epoch uses per-sender global; existing memories read as global after
migration.

## Loop B — Maintenance scope-awareness (extends ADR-049)

- Dedup and supersession operate within scope; protected set, retention, and undo
  apply per scope.
- **Deferred (future loop):** the scope-promotion pass (topic → global) is
  review-gated through the Proposals system, with optional ultra-high-confidence
  auto-promote + digest + undo. Do NOT build it in this loop; record it as the
  next maintenance extension.

**Tests:** a global and a topic memory with identical content are not merged; a
within-topic duplicate is merged; protected/retention behavior is per scope.

## Loop C — Memory UI redesign (web)

Redesign the Knowledge/memory surface into a curation tool:
- Grouped by scope (Global + per-topic).
- Per-memory: edit content, change scope (promote to global, demote, add/remove
  topics), pin/unpin, soft-delete + restore.
- Topic management: create/rename/delete, view subscriptions.
- Metadata: source session, created, last-recalled, descriptive tags shown as
  distinct from topics.
- Surface promotion proposals (once Loop B's future pass exists).

**Tests:** scope and topic edits persist and change retrieval; soft-deleted
memories restore; descriptive tags render separately from topics.

## Dependencies & notes
- Loop A is the foundation; B and C depend on it. The promotion pass depends on B.
- Warrants its own ADR (two-tier topic-scoped memory) once Loop A lands.
- Decision pass already complete; this spec is the implementation plan.

## Critical rules
- Do not merge or push without Dylan's okay.
- Scope changes only by explicit user action or the review-gated promotion pass —
  never as a side effect of LLM tagging.
- Migration is non-destructive: existing memories become global, nothing dropped.
