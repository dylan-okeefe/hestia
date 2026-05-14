# L165 — Session Handoff Hardening

## Outcome

Fixed the CRIT-2 issue where session handoff content was silently discarded after the first turn because it was injected as a `role="system"` message (which `ContextBuilder` filters out to prevent Qwen template crashes). Changed the synthetic handoff message to `role="user"` with a `[Previous session context]` prefix, and updated `ContextBuilder` to treat handoff user messages as protected context placed at the beginning of history.

## Changes

### §1 — Change handoff message role from "system" to "user"
- `src/hestia/persistence/sessions.py`
  - `get_or_create_session_with_handoff`: changed `synthetic` message `role` from `"system"` to `"user"`
  - `_format_handoff_message`: changed prefix from `"[Session handoff from previous conversation]"` to `"[Previous session context]"`

### §2 — Update ContextBuilder to handle handoff user messages
- `src/hestia/context/builder.py`
  - In `build()`, extract handoff messages (identified by `role="user"` + content starting with `[Previous session context]`)
  - Remove them from the history pool that goes through `HistoryWindowSelector` token budgeting
  - Place them in `protected_top` immediately after the system message and before any real user messages
  - First real user message is still found from non-handoff history and protected as before

### §3 — Verify handoff survives past the first turn
- `tests/unit/test_context_builder.py`
  - Added `TestHandoffMessages` with 4 tests:
    - `test_handoff_placed_after_system` — verifies ordering (system → handoff → real users)
    - `test_handoff_survives_past_first_turn` — simulates two turns, asserts handoff present in both built contexts
    - `test_handoff_not_counted_in_history_budget` — verifies handoff survives while normal history is truncated
    - `test_first_user_protected_when_handoff_present` — verifies first real user message is still protected
- `tests/unit/test_session_store_turns.py`
  - Updated `test_get_or_create_session_with_handoff_injects_message` to expect `role="user"` and `[Previous session context]` prefix

## Commits

1. `fix(persistence): use role="user" for handoff injection`
2. `feat(context): treat handoff user messages as context prefix`
3. `test(persistence): verify handoff survives multiple turns`

## Quality Gates

- **pytest `tests/unit/test_context_builder.py` + `tests/unit/test_session_store_turns.py`**: 38 passed
- **pytest `tests/integration/test_handoff_flow.py`**: 1 passed
- **mypy `src/hestia`**: 2 pre-existing errors in `src/hestia/tools/builtin/browser_get.py` and `src/hestia/core/inference.py`. Changed files are clean.
- **ruff `src/hestia/persistence/sessions.py` + `src/hestia/context/builder.py` + `tests/unit/test_context_builder.py` + `tests/unit/test_session_store_turns.py`**: all clean

## Notes

- The Qwen "System message must be at the beginning" error is avoided because handoff messages are now `role="user"`. The only `role="system"` message in built context is the builder's own system prompt at index 0.
- Pre-existing test failures and collection errors in the broader suite (`test_search_web_duckduckgo.py`, `test_orchestrator_errors.py`, `test_web_auth.py`, etc.) were not introduced by this change.
