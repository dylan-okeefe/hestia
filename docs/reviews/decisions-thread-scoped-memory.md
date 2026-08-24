# Decisions — thread/topic-scoped memory

**Status:** Resolved 2026-06-22. Implement against these. Brainstorm:
`docs/proposals/thread-scoped-memory-brainstorm.md`.

## 1. Scope architecture
Two-tier: a **global** pool and a **topic-scoped** pool. The scoped tier is keyed
on user-named **topics**, not rigid room ids. A room with no explicit topics
behaves as its own isolated pool (an implicit per-room topic). Topics generalize
the room model and let memory be shared across conversations.

## 2. Topics are first-class, separate from tags
Topics are NOT the existing descriptive tags. Tags stay the LLM's descriptive
layer; topics are explicit retrieval scopes changed only by user action. New
tables, not a reuse of tags. Rationale: scope must never change as a side effect
of the model's tagging judgment.

## 3. Data model
- `topics` — user-named (id, platform, platform_user, name).
- `conversation_topics` — subscriptions (room/session → topic), managed by the
  commands below.
- `memory_topics` — many-to-many (memory ↔ topic).
- `global` is a distinct flag/reserved scope on a memory (always-inject
  semantics), not a user topic.
- The implicit per-conversation pool is modeled as an auto per-room topic
  (e.g. `room:<id>`) so retrieval and migration have one code path.

## 4. Multi-topic per memory
A topic-scoped memory belongs to **all** of the conversation's currently
subscribed topics at save time (deterministic, no LLM "which topic" decision).

## 5. Commands
- `/add-topic <name>` — subscribe the conversation to a topic. On the FIRST add
  (implicit → explicit), migrate the conversation's implicit memories into the
  topic and drop their implicit association. Later adds only route future saves.
- `/remove-topic <name>` — unsubscribe. Changes retrieval and future-save routing
  only; does NOT un-associate existing memories from the topic.
- `/topic` — show the conversation's current topic subscriptions.
- `/remember-global <fact>` — explicit override: save a fact to global regardless
  of the conversation's topics.

## 6. Capture scoping (global vs topic)
The only capture-time judgment is coarse global-vs-topic, driven by the prompt
rule: identity and durable preferences → global; everything else → the
conversation's subscribed topics (all of them). Explicit topics override the
implicit pool for new saves. `/remember-global` forces global. Session-end task
extraction is topic-scoped by default.

## 7. Epoch composition (retrieval)
Global-first with a **soft cap**, topics fill the rest:
- Include global memories first, up to a configurable cap (default ~30% of
  `epoch_max_tokens`, e.g. 150 of 500), ordered by recency.
- Fill the remainder with the subscribed topics' memories, merged, by recency.
- Slack flows down: a small global pool leaves more for topics; total never
  exceeds `epoch_max_tokens`.
- A future per-memory **importance** score slots in as the within-bucket sort key
  (and could later override the cap). Deferred for now.

## 8. Group chats
A turn's epoch = the **active sender's** global + the **room's** subscribed-topic
memories. Global captures are per-sender; topic captures are shared room context.

## 9. Maintenance interaction (extends ADR-049)
Dedup and supersession operate **within scope** (a global fact and a topic fact
are not treated as duplicates). Protected set, retention, and undo apply per
scope. Cross-scope supersession is deferred/gated. A **scope-promotion pass**
(topic → global) is a FUTURE addition to the LLM maintenance tier and is
**review-gated**: promotions are filed through the existing Proposals system for
operator approval (ultra-high-confidence identity facts may auto-promote with a
prominent digest entry and undo).

## 10. Migration of existing memories
All existing memories become **global** on rollout. No auto-classification. Users
curate down to topics via the redesigned memory UI.

## 11. Memory UI redesign
Redesign the Knowledge/memory surface into a curation tool: grouped by scope
(Global + per-topic), per-memory edit / scope-change / pin / soft-delete +
restore, topic management (CRUD + view subscriptions), metadata (source session,
created, last-recalled, descriptive tags shown as distinct from topics), and
surfacing of promotion proposals. This is load-bearing for decision #10 — without
it the all-global migration has no path back to organized.
