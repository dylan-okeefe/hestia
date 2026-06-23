# Decisions — Persistence store split

This document records design choices in `docs/reviews/spec-persistence-store-split.md` that need a human call before implementation starts. It makes no code changes.

---

## 1. ORDERING CONFLICT: store split vs. concurrency vs. trust specs

**The conflict:**

- The store-split spec's Dependency section says it must land **after** the concurrency spec, because the concurrency spec adds a `correction` column that should be owned by the new `MessageStore`/`TurnStore`.
- The concurrency spec's Dependency section says the `correction` column migration should land **after** the store split, because it should be owned by the new `MessageStore`.

These cannot both be true.

### Options

**(a) Store split first, then concurrency adds `correction` to the split stores.**  
Do the split as a pure, behavior-preserving refactor with **no new columns**. The new `MessageStore` and `TurnStore` initially mirror the current schema. After the split lands, the concurrency spec adds the `correction` column (and any indexes) to the already-split stores.

**(b) Concurrency first, then split moves the new column.**  
Add `correction` to the monolithic `sessions.py` / schema, then split the file and carry the column into `MessageStore`.

**(c) Do both in one big supervised loop.**  
Combine the split and the `correction` column work into a single PR. This resolves the ordering problem by making it simultaneous, but it violates the spec's guidance to keep the split coherent and not mix other migrations into the same loop.

### Recommendation: **(a)**

The whole point of the split is to reduce risk by moving code without changing behavior. Adding a schema migration at the same time turns a refactor into a schema change, makes rollbacks harder, and couples two large specs. Split first, validate it, then let the concurrency spec add `correction` to the new `MessageStore` as a follow-up.

**Decision needed:** Confirm (a), or choose (b)/(c) and update both specs' dependency sections.

**Decision:** (a). Do the store split first as a pure behavior-preserving refactor that adds no new columns and no new behavior. The messages `correction` column is the concurrency spec's responsibility and will be added to the already-split `MessageStore` afterward. This breaks the inter-spec ordering conflict in favor of a clean structural base.

---

## 2. Transaction boundaries across stores

Several existing operations touch more than one table:

- `append_message` inserts a message **and** updates `sessions.last_active_at`.
- `create_session` may archive a previous session before creating a new one.
- `archive_session` updates the session state **and** may write a handoff summary message.
- `insert_turn` / `update_turn` are turn-only today, but finalization in the orchestrator may update the turn and the session slot fields close together.

After the split, these operations may span `MessageStore`, `SessionStore`, and `TurnStore`.

### Options

**(a) Add a unit-of-work / transaction helper in persistence.**  
Expose something like `async with persistence.transaction() as conn:` that stores can accept as an optional connection argument, so multiple store calls share one transaction. This keeps operations atomic but adds complexity and requires every store method to support an optional connection/transaction parameter.

**(b) Keep stores independent; accept multiple store calls.**  
The orchestrator calls `MessageStore.append_message()` then `SessionStore.touch_last_active_at()` as separate commits. This is simpler and matches the current split-connection design, but it creates small windows where the message exists and `last_active_at` is stale.

**(c) Keep multi-table operations in a small coordinator service.**  
Introduce a `SessionLifecycleService` (or similar) that owns the transaction and calls into the split stores. This hides transaction complexity from the orchestrator but re-introduces a layer between persistence and orchestrator.

### Recommendation: **(b) for the refactor, with (a) reserved for proven races.**

Start with independent stores and explicit call ordering. The current code already tolerates retry-on-collision for `idx` races, so the existing consistency model is "eventual within milliseconds," not strict serializability. If load tests or bug reports show that `last_active_at` staleness causes real problems, add a transactional helper only for those specific paths. Avoid premature transaction plumbing across the entire persistence layer.

**Decision needed:** Confirm (b), or mandate (a)/(c) up front.

** Decision:** Reject (b). Do NOT adopt (a)'s cross-store transaction helper or optional-connection parameters. For every operation that is atomic today (one connection, multiple writes, one commit — append_message and any similar multi-table method), keep it as a single self-contained method that preserves that one transaction. Do not decompose it into multiple store calls. Place it on the most relevant store (e.g. append_message on MessageStore, touching the sessions row as a documented exception) or a minimal coordinator. All single-table methods stay transaction-free with no shared-connection plumbing. Add as an implementation check for the build and review steps: enumerate every method in the current sessions.py that performs more than one write before a single commit, and confirm each one still commits exactly once after the split. That's the concrete test that the atomicity was actually preserved rather than quietly dropped.

---

## 3. HandoffService location

The spec says the service can live in `orchestrator/` or a new `services/` layer.

### Options

**(a) `src/hestia/orchestrator/handoff_service.py`.**  
Put it next to the code that already consumes handoffs (context building, session lifecycle). This is the least invasive: no new top-level package, and the orchestrator can import it directly.

**(b) `src/hestia/services/handoff.py`.**  
Create a new top-level `services/` layer for business logic that is neither pure persistence nor pure orchestration. This makes the dependency graph cleaner (orchestrator → services → persistence), but it adds a new abstraction to the project and may feel empty until more services are moved there.

**(c) `src/hestia/persistence/handoff_service.py`.**  
Keep it in persistence because handoffs are stored as messages. This is the weakest option: the whole point is to move handoff *business logic* out of persistence.

### Recommendation: **(a) for now, with a migration path to (b).**

The project does not currently have a `services/` package. Creating one in this loop adds scope and raises questions about what else belongs there. Placing `HandoffService` in `orchestrator/` keeps the refactor focused. If a second or third service later justifies a dedicated layer, promote it to `services/` at that point.

**Decision needed:** Confirm (a), or commit to creating `services/` now.

**Decision:** (a). Place `HandoffService` in `src/hestia/orchestrator/handoff_service.py` for now; promote to a `services/` layer later only if a second or third service justifies it. Enforce direction: the orchestrator may import the service and the stores, but persistence must never import `HandoffService` or any orchestrator module. Test #1 ("persistence has no orchestrator imports") must cover this.

---

## 4. Temporary `sessions.py` re-export facade

The spec proposes keeping `src/hestia/persistence/sessions.py` as thin re-exports that delegate to the new stores for "one release, then delete."

### Options

**(a) Keep the facade for exactly one release cycle.**  
- v0.15.0 ships the split; `sessions.py` re-exports remain and are marked deprecated in release notes.
- v0.16.0 removes `sessions.py` and updates any remaining imports.
- Internal imports are updated during the v0.15.0 PR, but the facade is a safety net for external scripts / plugins.

**(b) Delete `sessions.py` immediately in the same PR.**  
All imports across `src/` and `tests/` are updated in one go. No deprecated facade, no second pass. Riskier but leaves no dead code.

**(c) Keep the facade indefinitely.**  
Treat `sessions.py` as a stable, backward-compatible public API. This is appealing for plugins but defeats the architectural goal of removing the upward `orchestrator.types` import and the oversized store.

### Recommendation: **(a) with a concrete definition.**

The facade is valuable insurance because `SessionStore` is used by almost every subsystem. Define "one release" concretely:

> `sessions.py` re-exports ship in the release that first contains the split. The following release removes them. If the split lands in v0.15.0, `sessions.py` is deleted before v0.16.0 ships.

This gives one full release for integration tests and user scripts to adapt without leaving dead code forever.

**Decision needed:** Confirm (a) and the concrete release rule, or choose (b)/(c).

**Decision:** (a) with a concrete rule. Keep `sessions.py` as thin deprecated re-exports in the release that first ships the split, and delete it in the following release (split lands in v0.15.0, `sessions.py` removed before v0.16.0). Update all internal `src/` and `tests/` imports to the new stores in the split PR; the facade exists only as a safety net for external scripts/plugins. The facade must emit a `DeprecationWarning` on import, not just a release-note mention, so anyone still importing it is warned before removal.

---

## 5. Guarding against DTO drift

`MessageDTO` and `TurnDTO` are intended to be persistence-local, but the orchestrator maps through them. If a field is dropped or mis-serialized, the bug will be subtle.

### Options

**(a) Round-trip property tests.**  
Add tests that take a rich domain `Message`/`Turn`, convert to DTO, persist and reload, convert back to domain, and assert the result equals the original. This catches missing fields and serialization mistakes.

**(b) Manual mapping table + review.**  
Maintain a documented table of every domain field and its DTO/DB representation. The table is reviewed at implementation time and for every later schema change. Cheap but does not prevent regressions.

**(c) Runtime debug assertions.**  
In the mapper, assert that the domain object has no attributes not present in the DTO, and vice versa. This catches drift during development but adds runtime overhead and must be disabled or relaxed in production.

### Recommendation: **(a) as the primary guard, plus a one-time (b).**

A round-trip test is the only option that catches regressions automatically. Add `tests/unit/persistence/test_message_dto_roundtrip.py` and a similar test for `TurnDTO`. Do a one-time manual audit of the mapping table during implementation to make sure the test starts with complete coverage.

**Decision needed:** Confirm (a), or prefer (b)/(c).

**Decision:** (a). Add round-trip tests (`tests/unit/persistence/test_message_dto_roundtrip.py` and a `TurnDTO` equivalent) that take a rich domain object, convert to DTO, persist, reload, convert back, and assert equality over the persisted fields. Do a one-time manual audit of the field mapping during implementation so the test starts with complete coverage. This is the primary automatic guard against DTO drift.

---

## 6. DTO field completeness (additional to #5)

The current draft `MessageDTO` includes `id`, `session_id`, `role`, `content`, `created_at`, `tool_calls`, `tool_results`, `correction`, and `metadata`. The domain `Message` dataclass also has `tool_call_id`, `reasoning_content`, and `is_handoff`.

### Options

**(a) DTO mirrors the database columns exactly.**  
Include every column that exists in the `messages` table, even if the orchestrator does not currently use it. This is the safest long-term choice.

**(b) DTO carries only the subset the orchestrator currently uses.**  
Omit `reasoning_content`, `is_handoff`, etc. if they are not actively consumed. Simpler DTOs, but any future use of those fields requires a DTO change.

**(c) DTO carries a superset plus an extensible metadata bag.**  
Map known fields explicitly and stuff anything else into `metadata` as JSON. Flexible but loses type safety.

### Recommendation: **(a).**

There is no benefit to omitting columns that already exist in the schema. A 1:1 DTO-to-table mapping makes the round-trip test in decision #5 trivial and prevents the exact drift the spec flags as a risk.

**Decision needed:** Confirm (a), or justify omitting specific fields.

**Decision:** (a), but build the DTOs from the LIVE schema, not the draft block in this spec (the draft is inaccurate). For `MessageDTO`, mirror the real `messages` columns exactly: `session_id`, `idx`, `role`, `content`, `tool_calls` (JSON string), `tool_call_id`, `reasoning_content`, `is_handoff`, `created_at`. Do NOT include `id`, `tool_results`, `metadata`, or `correction`: those are not columns (the PK is composite `(session_id, idx)`; tool results are separate `role="tool"` messages; `correction` is the concurrency spec's later addition per decision #1). `tool_call_id`, `is_handoff`, and `reasoning_content` are persisted today and load-bearing (tool-result correlation, handoff filtering, and reasoning that is stored-but-stripped-on-send), so they must round-trip. Build `TurnDTO` the same way from the live `turns` columns: `id`, `session_id`, `state`, `started_at`, `last_transition_at`, `iteration`, `reasoning_budget`, `status_msg_id`, `slot_id`, `error`. The #5 round-trip test asserts over exactly these persisted fields.

---

## 7. Where domain/DTO mapping lives

The spec suggests mapping in `orchestrator/engine.py` or a new `orchestrator/mappers.py`.

### Options

**(a) `src/hestia/orchestrator/mappers.py`.**  
Dedicated module for domain↔DTO conversion. Keeps `engine.py` focused and makes the mapping testable in isolation.

**(b) Inline in `orchestrator/engine.py`.**  
No new module. Fine if the mapping is small, but `engine.py` is already large.

**(c) Methods on the DTO itself (`MessageDTO.to_domain()`).**  
Convenient, but it pulls domain imports into the persistence layer, re-creating the upward dependency the split is meant to remove.

### Recommendation: **(a).**

A small `mappers.py` is the cleanest boundary and keeps the persistence layer free of `Message`/`Turn`/`ToolCall` imports.

**Decision needed:** Confirm (a), or prefer (b)/(c).

**Decision:** (a). Put domain↔DTO conversion in `src/hestia/orchestrator/mappers.py`. Keeps `engine.py` lean, makes mapping testable in isolation, and keeps the persistence layer free of `Message`/`Turn`/`ToolCall` imports.

---

## 8. Handoff storage format

Handoffs are currently written as messages (likely `is_handoff=True`). The spec moves handoff logic into `HandoffService` but does not say whether the storage format changes.

### Options

**(a) Keep handoffs as messages.**  
`HandoffService` writes a handoff summary as a message with `role="assistant"` or a system note and `is_handoff=True`. No schema change. Simplest.

**(b) Create a dedicated `handoffs` table.**  
Cleaner separation, but adds a new table, migration, and queries.

**(c) Handoff metadata in messages + separate content storage.**  
Over-engineered for the current scope.

### Recommendation: **(a).**

The split is already a large change. Changing the handoff storage format at the same time adds risk without a clear payoff. Keep handoffs as messages; revisit a dedicated table only if query performance or handoff features later justify it.

**Decision needed:** Confirm (a), or choose (b).

**Decision:** (a). Keep handoffs stored as messages (`is_handoff=True`); no schema or storage-format change in this loop. `HandoffService` owns the business logic only. Revisit a dedicated `handoffs` table later only if query performance or new handoff features justify it.

---

## 9. What the split stores accept as input

`insert_turn` currently accepts a domain `Turn`. After the split, persistence should not import `Turn`.

### Options

**(a) Stores accept DTOs only.**  
The orchestrator maps `Turn` → `TurnDTO` before calling `TurnStore.insert()`. This fully removes the upward import.

**(b) Stores accept primitive dictionaries / keyword arguments.**  
Even more decoupled but verbose and loses type safety.

**(c) Stores continue to accept domain objects.**  
Easiest port, but perpetuates the upward `orchestrator.types` import the spec wants to eliminate.

### Recommendation: **(a).**

This is the logical consequence of introducing DTOs. Domain objects stay in the orchestrator; persistence deals only with primitive-friendly DTOs.

**Decision needed:** Confirm (a), or accept (c) for an initial pass.

**Decision:** (a). Stores accept and return DTOs only; the orchestrator maps `Turn`/`Message`/`ToolCall` to/from DTOs at the boundary. This is what actually removes the upward `orchestrator.types` import from persistence, so no store method may accept a domain object.

---

## 10. EventBus ownership

`SessionStore` currently accepts an `EventBus`. After the split, messages and turns may also need to emit events.

### Options

**(a) Pass `EventBus` to all stores.**  
Uniform but encourages stores to publish events liberally.

**(b) Pass `EventBus` only to the stores that actually publish.**  
More precise. Today that is likely only `SessionStore`.

**(c) Move event publication out of persistence entirely.**  
Stores return results; the orchestrator or a service publishes events. Cleanest architecturally but requires more orchestrator changes.

### Recommendation: **(b) for the refactor, with a note to evaluate (c).**

Keep the current pattern: pass the event bus only where it is already used. Do not expand event publishing during the split. After the split is stable, audit whether event publication should move out of persistence entirely.

**Decision needed:** Confirm (b), or move to (c) now.

**Decision:** (b). Pass the `EventBus` only to the stores that already publish events (today that is `SessionStore`); do not expand event publishing during the split. After the split is stable, separately evaluate moving event publication out of persistence entirely (option (c)).

---

## Summary of recommendations

| # | Decision | Recommended option |
|---|---|---|
| 1 | Ordering conflict | **(a)** Split first, no new columns; concurrency adds `correction` afterward. |
| 2 | Transaction boundaries | **(b)** Independent stores with explicit call ordering; add transactions only for proven races. |
| 3 | HandoffService location | **(a)** `orchestrator/handoff_service.py` now; promote to `services/` later if warranted. |
| 4 | Re-export facade | **(a)** Keep `sessions.py` re-exports for one release, then delete. |
| 5 | DTO drift guard | **(a)** Round-trip tests plus one-time manual mapping audit. |
| 6 | DTO field completeness | **(a)** Mirror DB columns exactly. |
| 7 | Mapper location | **(a)** `orchestrator/mappers.py`. |
| 8 | Handoff storage | **(a)** Keep handoffs as messages. |
| 9 | Store input | **(a)** Accept DTOs only. |
| 10 | EventBus | **(b)** Pass only to stores that already publish events. |

**Next step:** Dylan reviews and confirms/rejects each option, then implementation can begin.
