# Spec — Split `persistence/sessions.py`

**Status:** HOLD-FOR-REVIEW  
**Review source:** `docs/reviews/develop-review-2026-06-12.md` (Architecture section)  
**Scope:** One coherent spec for the store split. Do NOT refactor other persistence files in the same loop.  

## Decisions incorporated

This spec has been updated to reflect the choices recorded in `docs/reviews/decisions-store-split.md`:

1. **Ordering:** the split lands first as a behavior-preserving refactor with **no new columns**. The concurrency spec's `correction` column will be added to the already-split `MessageStore` afterward.
2. **Transaction boundaries:** multi-write methods that are atomic today stay single self-contained methods. The only cross-table write kept inside a method is `MessageStore.append_message`, which updates `sessions.last_active_at` as a documented exception.
3. **HandoffService:** lives in `src/hestia/orchestrator/handoff_service.py` (not persistence).
4. **Facade:** `src/hestia/persistence/sessions.py` becomes thin deprecated re-exports for one release, then is deleted.
5. **DTOs:** `MessageDTO` and `TurnDTO` mirror the live DB columns exactly; mapping lives in `src/hestia/orchestrator/mappers.py`.
6. **Handoff storage:** handoff summaries are stored as messages (`is_handoff=True`) in the session being archived. No schema change.
7. **Store inputs:** store methods accept and return DTOs only; the orchestrator maps at the boundary.

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
- Introduce persistence-local DTOs; map to/from `Message`/`Turn` only at the orchestrator boundary.
- Move handoff business logic into `HandoffService`.
- Remove the upward `orchestrator.types` import from persistence.

## Design

### 1. New module layout

```
src/hestia/persistence/
  sessions.py              # Deprecated compatibility re-exports (temporary)
  session_store.py         # SessionStore + session CRUD + handoff persistence
  message_store.py         # MessageStore + MessageDTO
  turn_store.py            # TurnStore + TurnDTO
src/hestia/orchestrator/
  handoff_service.py       # HandoffService
  mappers.py               # domain <-> DTO conversion
```

### 2. DTOs

`MessageDTO` and `TurnDTO` are plain dataclasses with only primitive/SQLAlchemy-friendly types. They are built from the **live** schema, not from the orchestrator's domain objects.

```python
@dataclass
class MessageDTO:
    session_id: str
    idx: int
    role: str
    content: str
    created_at: datetime
    tool_calls: str | None   # JSON string
    tool_call_id: str | None
    reasoning_content: str | None
    is_handoff: bool
```

```python
@dataclass
class TurnDTO:
    id: str
    session_id: str
    state: str               # TurnState.value
    started_at: datetime
    last_transition_at: datetime
    iteration: int
    reasoning_budget: int
    status_msg_id: str | None
    slot_id: int | None
    error: str | None
```

Notes:

- `tool_results` are not a separate column; they are persisted as `role="tool"` messages.
- `correction` is intentionally omitted; it is added by the concurrency spec later (decision #1).
- `id` is omitted because the messages primary key is composite `(session_id, idx)`.

### 3. Store responsibilities

**`SessionStore`**
- CRUD for sessions (`get_or_create_session`, `get_session`, `get_active_session`, `create_session`, `end_session`, `archive_session`).
- List active/archived sessions (`list_sessions`).
- Update session state, title, temperature, slot fields (`update_session_title`, `assign_slot`, `release_slot`, `update_saved_path`).
- `get_or_create_session_with_handoff` moves to `HandoffService`.
- Handoff table persistence (`save_handoff`, `get_latest_handoff`, `list_handoffs_for_identities`) is **removed**; handoff data is now stored as messages.
- No message/turn operations.

**`MessageStore`**
- Append, get, list messages for a session (`append_message`, `get_messages`).
- `append_message` is a single self-contained method that both inserts the message row and bumps `sessions.last_active_at` in one connection/commit.
- Returns `MessageDTO`.

**`TurnStore`**
- Create, update, finalize turns (`insert_turn`, `update_turn`, `fail_turn`).
- Load turns for a session (`get_turn`, `list_turns_for_session`, `list_stale_turns`, `list_turns_with_errors`).
- Transition recording (`append_transition`).
- Turn analytics (`count_turns_for_session`, `count_turns_for_sessions`, `turn_stats_since`, `get_turn_messages`).
- Accepts and returns `TurnDTO` only.

### 4. `HandoffService`

Located at `src/hestia/orchestrator/handoff_service.py`. It owns handoff business logic and depends on persistence, but persistence never depends on it.

```python
class HandoffService:
    def __init__(
        self,
        session_store: SessionStore,
        message_store: MessageStore,
        summarizer: SessionHandoffSummarizer | None = None,
    ) -> None: ...

    async def generate_handoff_summary(self, session_id: str) -> None:
        """Archive the session, summarize if enabled, and write the handoff as a message."""

    async def get_recent_handoffs(
        self, platform: str, platform_user: str, limit: int = 1
    ) -> list[dict[str, Any]]:
        """Return recent handoff summaries for a user across archived sessions."""

    async def get_or_create_session_with_handoff(
        self, platform: str, platform_user: str, title: str | None = None
    ) -> Session:
        """Get or create a session; if new and empty, prepend a synthetic handoff message."""
```

Implementation notes:

- `generate_handoff_summary` archives the session via `SessionStore.archive_session`, optionally generates an inference summary via `SessionHandoffSummarizer`, and writes a handoff message via `MessageStore.append_message` with `is_handoff=True`.
- The handoff message content follows the existing `_format_handoff_message` format.
- `get_recent_handoffs` finds the most recent archived session(s) for the user and returns the latest `is_handoff=True` message from each.
- `get_or_create_session_with_handoff` is the old `SessionStore` method moved here; it uses `SessionStore.get_or_create_session`, `MessageStore.get_messages`, and `MessageStore.append_message`.

### 5. Boundary mapping

`src/hestia/orchestrator/mappers.py`:

```python
def message_domain_to_dto(msg: Message, session_id: str, idx: int) -> MessageDTO: ...
def message_dto_to_domain(dto: MessageDTO) -> Message: ...
def turn_domain_to_dto(turn: Turn) -> TurnDTO: ...
def turn_dto_to_domain(
    dto: TurnDTO,
    transitions: list[TurnTransition] | None = None,
    user_message: Message | None = None,
) -> Turn: ...
```

- Mapping handles JSON serialization of `tool_calls`.
- Non-persisted `Turn` fields (`completed_at`, `tool_calls_made`, `final_response`, `thinking_aborted`, `artifact_handles`) are reconstructed with defaults.

### 6. Transaction boundaries

The split keeps the current per-connection commit model. Methods that today perform multiple writes before a single commit stay single self-contained methods:

| Method | Writes | Owner |
|---|---|---|
| `MessageStore.append_message` | `messages` insert + `sessions.last_active_at` update | `MessageStore` |
| `SessionStore.get_or_create_session` | upsert + conflict fallback update | `SessionStore` |
| `TurnStore.append_transition` | `turn_transitions` insert (retry on collision) | `TurnStore` |

Operations that are already separate commits in the current code (e.g. archive session then write handoff message) remain separate; `HandoffService` sequences them explicitly.

### 7. Migration path

1. Create new modules alongside `sessions.py`.
2. Move methods from `sessions.py` to the appropriate new store, preserving signatures where possible (but changing turn/message methods to accept DTOs).
3. Add `src/hestia/orchestrator/mappers.py` and `src/hestia/orchestrator/handoff_service.py`.
4. Update `AppContext` to instantiate the new stores and `HandoffService`, and wire them into callers.
5. Update internal `src/` and `tests/` imports to use the new stores / service.
6. Keep `sessions.py` as thin deprecated re-exports that delegate to the new stores for one release, then delete.

### 8. Deprecated facade

`src/hestia/persistence/sessions.py`:

```python
import warnings
warnings.warn(
    "hestia.persistence.sessions is deprecated; import SessionStore from "
    "hestia.persistence.session_store, MessageStore from hestia.persistence.message_store, "
    "and TurnStore from hestia.persistence.turn_store. This module will be removed in v0.16.0.",
    DeprecationWarning,
    stacklevel=2,
)

from hestia.persistence.session_store import SessionStore
from hestia.persistence.message_store import MessageStore
from hestia.persistence.turn_store import TurnStore

__all__ = ["SessionStore", "MessageStore", "TurnStore"]
```

- Internal imports are updated in the same PR; the facade is a safety net for external scripts/plugins.
- The facade is removed before v0.16.0.

## Tests that must pass before merging

1. `persistence/` has no imports from `orchestrator/`.
2. All existing persistence tests pass without modification (except import updates).
3. A full turn lifecycle (create session → append message → process turn → finalize) works end-to-end.
4. Handoff summaries still generate and load correctly.
5. DTO round-trip tests pass for `MessageDTO` and `TurnDTO` over a real database.
6. `sessions.py` emits a `DeprecationWarning` on import.

## Files likely to change

- New: `src/hestia/persistence/session_store.py`, `src/hestia/persistence/message_store.py`, `src/hestia/persistence/turn_store.py`, `src/hestia/orchestrator/handoff_service.py`, `src/hestia/orchestrator/mappers.py`
- Modify: `src/hestia/persistence/sessions.py`, `src/hestia/app.py`, `src/hestia/orchestrator/engine.py`, `src/hestia/orchestrator/assembly.py`, `src/hestia/orchestrator/execution.py`, `src/hestia/orchestrator/finalization.py`, all callers of `SessionStore`
- Tests: existing persistence tests updated to import from new modules; new `tests/unit/persistence/test_message_dto_roundtrip.py`, `tests/unit/persistence/test_turn_dto_roundtrip.py`, `tests/unit/persistence/test_store_split.py`

## Risks & open questions

- **Blast radius.** `SessionStore` is used by almost every subsystem. The temporary re-export layer limits risk.
- **DTO drift.** Round-trip tests are the primary guard.
- **Handoff format change.** Moving handoff storage from `session_handoffs` table to messages is behavior-preserving at the user level but changes the persistence contract; tests that assert on `session_handoffs` rows need updating.
- **Performance.** Splitting stores may add mapping overhead; measure on a warm session.

## Dependency

- Must land **after** the `error_resolutions` bootstrap fix.
- Must land **before** the concurrency spec's `correction` column migration, because that migration belongs in the already-split `MessageStore`.
- Can be mostly independent of the trust-boundary spec.
