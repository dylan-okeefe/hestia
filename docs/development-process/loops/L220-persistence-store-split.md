# L220 — Split `persistence/sessions.py` into focused stores

**Status:** Spec only. Feature branch work; do not merge to develop until release-prep merge sequence.  
**Branch:** `feature/l220-persistence-store-split` (from `develop`)  
**Spec source:** `docs/reviews/spec-persistence-store-split.md`  

## Goal

Split the monolithic `SessionStore` in `src/hestia/persistence/sessions.py` into `SessionStore`, `MessageStore`, and `TurnStore`; introduce persistence-local DTOs with orchestrator-side mapping; move handoff business logic into `src/hestia/orchestrator/handoff_service.py`; and leave a deprecated `sessions.py` re-export facade for one release.

## Review carry-forward

- *(none — this is a new spec-driven arc)*

## Scope

### §1 — DTOs and mappers

Create the persistence-local DTOs and the orchestrator-side mapper functions.

**Files:**
- `src/hestia/persistence/dto.py` — new home for `MessageDTO` and `TurnDTO` (imported by `message_store.py`, `turn_store.py`, and `mappers.py`).
- `src/hestia/orchestrator/mappers.py` — `message_domain_to_dto`, `message_dto_to_domain`, `turn_domain_to_dto`, `turn_dto_to_domain`.

**Implementation notes:**
- DTOs must mirror the live schema exactly (decision #6):
  - `MessageDTO`: `session_id`, `idx`, `role`, `content`, `tool_calls` (JSON string), `tool_call_id`, `reasoning_content`, `is_handoff`, `created_at`.
  - `TurnDTO`: `id`, `session_id`, `state`, `started_at`, `last_transition_at`, `iteration`, `reasoning_budget`, `status_msg_id`, `slot_id`, `error`.
- `message_domain_to_dto` needs `session_id` and `idx` because the domain `Message` does not carry them.
- `turn_dto_to_domain` reconstructs non-persisted fields (`completed_at=None`, `tool_calls_made=0`, `final_response=None`, `thinking_aborted=False`, `artifact_handles=[]`).

**Tests:**
- `tests/unit/persistence/test_message_dto_roundtrip.py`: build a rich `Message`, map to `MessageDTO`, persist via `MessageStore`, reload, map back, assert equality over persisted fields.
- `tests/unit/persistence/test_turn_dto_roundtrip.py`: same for `Turn`/`TurnDTO`.

**Commit:** `refactor(persistence): add MessageDTO/TurnDTO and orchestrator mappers`

### §2 — `MessageStore`

Create `src/hestia/persistence/message_store.py`.

**Move from `sessions.py`:**
- `append_message(session_id, msg: MessageDTO) -> None`
- `get_messages(session_id) -> list[MessageDTO]`
- `get_turn_messages(turn_id) -> dict[str, str] | None` (uses `turns` table; acceptable convenience method on `TurnStore`, but keep it where callers expect it for now).

**Implementation notes:**
- `append_message` must remain a single self-contained method that inserts the message row **and** updates `sessions.last_active_at` in one connection/commit (decision #2).
- Preserve the retry-on-`IntegrityError` behavior for `idx` collisions.
- Convert `Message` → `MessageDTO` before inserting; return `MessageDTO` from queries.

**Tests:**
- Move/adapt message-related tests from `tests/unit/persistence/test_sessions.py` and `tests/unit/test_session_store_turns.py` into `tests/unit/persistence/test_message_store.py`.
- Ensure `append_message` still bumps `last_active_at`.

**Commit:** `refactor(persistence): add MessageStore with atomic append and DTO interface`

### §3 — `TurnStore`

Create `src/hestia/persistence/turn_store.py`.

**Move from `sessions.py`:**
- `insert_turn(dto: TurnDTO) -> None`
- `update_turn(dto: TurnDTO) -> None`
- `get_turn(turn_id) -> TurnDTO | None`
- `list_turns_for_session(session_id, limit=50) -> list[TurnDTO]`
- `list_stale_turns() -> list[TurnDTO]`
- `list_turns_with_errors(limit=50) -> list[TurnDTO]`
- `count_turns_for_session(session_id) -> int`
- `count_turns_for_sessions(session_ids) -> dict[str, int]`
- `turn_stats_since(since) -> dict[str, int]`
- `fail_turn(turn_id, error) -> None`
- `append_transition(turn_id, transition: TurnTransition) -> None` — accepts `TurnTransition` domain object? Decision #9 says stores accept DTOs only. Define a small `TurnTransitionDTO` in `dto.py` and convert in the mapper.
- `get_turn_messages(turn_id)` may live here or in `MessageStore`; pick one and update callers consistently.

**Implementation notes:**
- `insert_turn` / `update_turn` no longer accept domain `Turn`; they accept `TurnDTO`.
- `append_transition` keeps retry-on-collision.

**Tests:**
- Move/adapt turn-related tests into `tests/unit/persistence/test_turn_store.py`.

**Commit:** `refactor(persistence): add TurnStore with DTO interface and transition retry`

### §4 — `SessionStore` (trimmed)

Create `src/hestia/persistence/session_store.py` with only session-related methods.

**Move from `sessions.py`:**
- `get_or_create_session`, `create_session`, `get_session`, `get_active_session`, `get_sessions_batch`, `list_sessions`
- `archive_session`, `end_session`
- `assign_slot`, `release_slot`, `update_saved_path`
- `update_session_title`
- `count_sessions_by_state`
- EventBus publishing on `session_started`.

**Remove from `SessionStore`:**
- All message/turn methods (moved to new stores).
- `_row_to_message`, `_extract_artifact_handles`, `_generate_and_save_handoff`, `save_handoff`, `get_latest_handoff`, `list_handoffs_for_identities`, `_format_handoff_message`.
- `get_or_create_session_with_handoff` moves to `HandoffService`.

**Implementation notes:**
- `archive_session` becomes a single write: update the session row to `ARCHIVED`. Handoff generation is handled by `HandoffService`.
- `create_session` may still accept `archive_previous: Session | None` and call `archive_session` before inserting; keep behavior but it is no longer responsible for handoff generation beyond archiving.
- `SessionStore` must remain event-bus-aware; do not pass the event bus to `MessageStore` or `TurnStore`.

**Tests:**
- Trim `tests/unit/persistence/test_sessions.py` to session-only coverage.
- Verify `SessionStore` no longer imports from `orchestrator`.

**Commit:** `refactor(persistence): trim SessionStore to session-only responsibilities`

### §5 — `HandoffService`

Create `src/hestia/orchestrator/handoff_service.py`.

**Responsibilities moved from `SessionStore`:**
- `generate_handoff_summary(session_id)` — archives the session, optionally summarizes via `SessionHandoffSummarizer`, and writes a handoff message with `is_handoff=True`.
- `get_recent_handoffs(platform, platform_user, limit=1)` — returns recent handoff summaries by reading `is_handoff=True` messages from archived sessions.
- `get_or_create_session_with_handoff(platform, platform_user, title=None)` — delegates to `SessionStore.get_or_create_session`, checks for existing messages via `MessageStore`, and prepends a synthetic handoff message if the session is new.

**Implementation notes:**
- Handoff summaries are stored as messages (`is_handoff=True`) with no schema change (decision #8).
- `HandoffService` lives in `orchestrator/` and imports persistence; persistence must not import it (decision #3).
- Synthetic handoff message format should match the current `_format_handoff_message` behavior.

**Tests:**
- `tests/unit/orchestrator/test_handoff_service.py`: archive generates handoff message; get_recent_handoffs returns latest; get_or_create_session_with_handoff injects handoff for new sessions only.

**Commit:** `refactor(orchestrator): add HandoffService for handoff business logic`

### §6 — Update callers and `AppContext`

Update every internal caller to import from the new modules and use the appropriate store/service.

**Files to touch (list is indicative; grep to verify):**
- `src/hestia/app.py` — instantiate `MessageStore`, `TurnStore`, `HandoffService`; pass them where needed.
- `src/hestia/orchestrator/engine.py` — accept `MessageStore`, `TurnStore`, `HandoffService`; map `Message`/`Turn` at boundaries.
- `src/hestia/orchestrator/assembly.py` — use `MessageStore` for history and appends.
- `src/hestia/orchestrator/execution.py` — use `MessageStore` for appends.
- `src/hestia/orchestrator/finalization.py` — use `TurnStore` for `update_turn`/`fail_turn`.
- `src/hestia/inference/slot_manager.py` — use `SessionStore`.
- `src/hestia/platforms/runners.py`, `telegram_adapter.py` — use `HandoffService.get_or_create_session_with_handoff` and `HandoffService.generate_handoff_summary`.
- `src/hestia/scheduler/engine.py` — use `SessionStore`.
- `src/hestia/style/scheduler.py`, `reflection/scheduler.py` — keep using `SessionStore._db` or switch to injected `Database`.
- `src/hestia/commands/meta.py` — split `get_messages`/`create_session` usage across stores/service.
- `src/hestia/tools/builtin/delegate_task.py`, `scheduler_tools.py` — use `SessionStore`/`HandoffService` as appropriate.
- `src/hestia/web/context.py` — add `message_store` and `turn_store` fields.
- `src/hestia/commands/serve.py` — pass new stores into `WebContext`.
- `src/hestia/web/routes/sessions.py`, `errors.py`, `users.py`, `traces.py`, `egress.py` — use the correct store for each call.

**Implementation notes:**
- Where a function today receives one `session_store` and calls both session and message methods, split the dependencies (e.g. `Orchestrator` takes `session_store`, `message_store`, `turn_store`, `handoff_service`).
- The orchestrator maps domain objects to DTOs before calling `MessageStore`/`TurnStore`.
- Keep signatures as stable as possible to minimize test churn.

**Tests:**
- Update existing test imports from `hestia.persistence.sessions` to the new modules.
- `tests/integration/test_handoff_flow.py` must pass after handoff logic move.
- `tests/integration/test_orchestrator.py` M-2 invariant (single `get_messages` call per turn) still holds.

**Commit:** `refactor(orchestrator): wire MessageStore, TurnStore, and HandoffService into callers`

### §7 — Deprecated `sessions.py` facade

Replace `src/hestia/persistence/sessions.py` with thin re-exports.

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

**Tests:**
- `tests/unit/persistence/test_sessions_facade.py`: importing from `hestia.persistence.sessions` emits `DeprecationWarning` and yields the same classes.

**Commit:** `refactor(persistence): add deprecated sessions.py re-export facade`

### §8 — Import-lint guard

Add a lightweight test that fails if any persistence module imports orchestrator modules.

**File:** `tests/unit/persistence/test_no_orchestrator_imports.py`

**Implementation:**
- Use `importlib` and `sys.modules` or static AST parsing to assert that no module under `hestia.persistence` imports from `hestia.orchestrator`.
- Exclude `TYPE_CHECKING` blocks.

**Commit:** `test(persistence): enforce no upward orchestrator imports in persistence layer`

## Tests

- New unit tests:
  - `tests/unit/persistence/test_message_dto_roundtrip.py`
  - `tests/unit/persistence/test_turn_dto_roundtrip.py`
  - `tests/unit/persistence/test_message_store.py`
  - `tests/unit/persistence/test_turn_store.py`
  - `tests/unit/persistence/test_sessions_facade.py`
  - `tests/unit/persistence/test_no_orchestrator_imports.py`
  - `tests/unit/orchestrator/test_handoff_service.py`
- Updated tests: all existing persistence/orchestrator/integration tests that imported `SessionStore` from `hestia.persistence.sessions`.
- Keep existing tests green.

## Acceptance

- `uv run pytest tests/unit/ tests/integration/ -q` green
- `uv run mypy src/hestia` reports 0 errors
- `uv run ruff check src/ tests/` remains at baseline or better (project line-length is 120)
- `.kimi-done` includes `LOOP=L220`
- `git diff --stat` shows `sessions.py` reduced to a deprecation facade and new store modules carrying the logic.

## Handoff

- Write `docs/handoffs/L220-persistence-store-split-handoff.md`
- Update `docs/development-process/kimi-loop-log.md`
- Advance `KIMI_CURRENT.md` to the concurrency loop (L221)

## Critical rules recap

- Do not merge or push without Dylan's okay.
- No new schema columns in this loop.
- Persistence must never import `hestia.orchestrator` modules.
- Keep `append_message` atomic (message insert + `last_active_at` update in one commit).
- Update internal imports to the new modules; the facade is only for external scripts.
