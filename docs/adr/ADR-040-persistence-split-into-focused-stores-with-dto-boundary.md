# ADR-040: Persistence split into focused stores with a DTO boundary

- **Status:** Accepted
- **Date:** 2026-06-16
- **Context:** `persistence/sessions.py` had grown to ~1044 lines and ~32 methods,
  owning sessions, messages, turns, transitions, handoffs, slot fields, and
  analytics. It also imported `hestia.orchestrator.types`, an upward dependency
  from the persistence layer into the domain layer. This was the clearest
  "split me" file in the codebase (L220).

- **Decision:**
  1. Split into `SessionStore`, `MessageStore`, and `TurnStore`
     (`session_store.py`, `message_store.py`, `turn_store.py`).
  2. Introduce persistence-local DTOs (`MessageDTO`, `TurnDTO`,
     `TurnTransitionDTO` in `persistence/dto.py`) that mirror the live table
     columns exactly. Stores accept and return DTOs only; domain objects never
     reach persistence.
  3. Map domain ↔ DTO in `orchestrator/mappers.py`. The persistence layer must
     not import `hestia.orchestrator`, enforced by
     `tests/unit/persistence/test_no_orchestrator_imports.py`.
  4. Move handoff business logic into `orchestrator/handoff_service.py`.
  5. Keep `persistence/sessions.py` as a deprecated re-export facade that emits
     a `DeprecationWarning`; remove it in v0.16.0.
  6. Operations that are atomic today (e.g. `append_message`: message insert +
     `last_active_at` update in one commit) stay as a single self-contained
     method on one store rather than being decomposed into multiple store calls.

- **Consequences:** The refactor is behavior-preserving; existing tests changed
  only for store wiring, not assertions. The `messages.correction` column was
  intentionally left to the concurrency work (ADR-041) so this loop added no new
  columns. Round-trip tests guard against DTO drift.

- **Related:** ADR-004; `persistence/session_store.py`, `message_store.py`,
  `turn_store.py`, `dto.py`, `orchestrator/mappers.py`, `handoff_service.py`.
