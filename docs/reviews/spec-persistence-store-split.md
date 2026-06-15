# Spec — Split `persistence/sessions.py`

**Status:** HOLD-FOR-REVIEW  
**Review source:** docs/reviews/develop-review-2026-06-12.md (Architecture section)  
**Scope:** One coherent spec for the store split. Do NOT refactor other persistence files in the same loop.

## Problem statement

`src/hestia/persistence/sessions.py` is 1044 lines with ~32 methods and is responsible for:

- Sessions
- Messages
- Turns
- Transitions
- Handoffs
- Slot fields
- Analytics/aggregations

It also imports `orchestrator.types`, creating an upward dependency from the persistence layer to the domain layer. This is the clearest "split me" file in the codebase.

## Goal

- Split into focused stores: `SessionStore`, `MessageStore`, `TurnStore`.
- Introduce persistence-local DTOs; map to/from `Turn` only at the orchestrator boundary.
- Move handoff business logic into a `HandoffService`.
- Remove the upward `orchestrator.types` import from persistence.

## Design

### 1. New module layout

```
src/hestia/persistence/
  sessions.py              # Deprecated compatibility re-exports (temporary)
  session_store.py         # SessionStore
  message_store.py         # MessageStore + MessageDTO
  turn_store.py            # TurnStore + TurnDTO
  handoff_service.py       # HandoffService
```

### 2. DTOs

`MessageDTO` and `TurnDTO` are plain dataclasses with only primitive/SQLAlchemy-friendly types:

```python
@dataclass
class MessageDTO:
    id: str
    session_id: str
    role: str
    content: str
    created_at: datetime
    tool_calls: str | None   # JSON string
    tool_results: str | None # JSON string
    correction: bool
    metadata: str | None     # JSON string
```

`TurnDTO` similarly contains primitive fields only. The orchestrator layer maps these to/from `Turn`, `Message`, and `ToolCall` domain objects.

### 3. Store responsibilities

**`SessionStore`**
- CRUD for sessions.
- List active/archived sessions.
- Update session state, title, temperature, slot fields.
- No message/turn operations.

**`MessageStore`**
- Append, get, list, update messages for a session.
- Load messages for context building (returns `MessageDTO`).
- Correction column read/write.

**`TurnStore`**
- Create, update, finalize turns.
- Load turns for a session.
- Transition recording.

### 4. `HandoffService`

Move handoff-related business logic out of the store:

- `generate_handoff_summary(session_id)` — orchestrates summarization and writes the result.
- `get_recent_handoffs(session_id, limit)` — reads handoff summaries for context injection.

The service may use `MessageStore` and an inference client, but it lives in `orchestrator/` or a new `services/` layer, not in persistence.

### 5. Boundary mapping

In `orchestrator/engine.py` or a new `orchestrator/mappers.py`:

```python
def message_dto_to_domain(dto: MessageDTO) -> Message:
    ...

def message_domain_to_dto(msg: Message) -> MessageDTO:
    ...
```

Mapping handles JSON serialization of `tool_calls`, `tool_results`, and metadata.

### 6. Migration path

1. Create new modules alongside `sessions.py`.
2. Move methods from `sessions.py` to the appropriate new store, preserving method signatures where possible.
3. Update `AppContext` to instantiate the new stores and pass them to the orchestrator.
4. Keep `sessions.py` as thin re-exports that delegate to the new stores for one release, then delete.
5. Update all imports in `src/hestia/` to use the new stores.

## Tests that must pass before merging

1. `persistence/` has no imports from `orchestrator/`.
2. All existing persistence tests pass without modification (except import updates).
3. A full turn lifecycle (create session → append message → process turn → finalize) works end-to-end.
4. Handoff summaries still generate and load correctly.

## Files likely to change

- New: `src/hestia/persistence/session_store.py`, `src/hestia/persistence/message_store.py`, `src/hestia/persistence/turn_store.py`, `src/hestia/persistence/handoff_service.py` (or `src/hestia/services/handoff.py`)
- Modify: `src/hestia/persistence/sessions.py`, `src/hestia/app.py`, `src/hestia/orchestrator/engine.py`, all callers of `SessionStore`
- Tests: existing persistence tests updated to import from new modules; new `tests/unit/persistence/test_store_split.py`

## Risks & open questions

- **Blast radius.**  `SessionStore` is used by almost every subsystem. The temporary re-export layer limits risk.
- **DTO drift.**  If `MessageDTO` does not capture a field the orchestrator needs, mapping bugs will be subtle.
- **Transaction boundaries.**  Some current operations update sessions + messages + turns in one method. Decide whether to expose explicit transactions or accept multiple store calls.
- **Performance.**  Splitting stores may add mapping overhead; measure on a warm session.

## Dependency

- Must land **after** the `error_resolutions` bootstrap fix and the messages `correction` column migration (part of the concurrency spec), because those migrations should be owned by the new `MessageStore`/`TurnStore`.
- Should land **after** the trust-boundary spec if the trust spec adds new user/session indexes, but can be mostly independent.
