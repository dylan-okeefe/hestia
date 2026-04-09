# Hestia Phase 1c Report — Orchestrator & CLI

**Date:** 2026-04-09

## Overview

Phase 1c completes the core Hestia framework by adding the **Orchestrator engine** that manages turn execution through a state machine, and a **CLI adapter** for local testing and development.

## Known Issues Found In Review

The following bugs were discovered during review and fixed in the Phase 1c cleanup cycle:

1. **User message double-counted on first model call** - CLI was persisting user messages before calling `process_turn()`, causing the message to appear twice (once in history, once in `protected_bottom`). Fixed by moving `append_message` into the orchestrator.

2. **EmptyResponseError guard missing** - Model returning `finish_reason="stop"` with empty content would silently complete the turn. Fixed by adding `EmptyResponseError` and failing the turn when content is empty.

3. **confirm_callback fails open** - Tools with `requires_confirmation=True` would execute without confirmation if no callback was injected. Fixed to fail closed with an error.

4. **CLI missing REPL meta-commands** - Phase 1c §5 specified `/quit`, `/reset`, `/history`, `/session`, `/help` commands. Added in cleanup.

5. **Missing ADR-012** - Forgot to document the state machine + confirmation callback pattern. Added in cleanup.

6. **Confirmation enforcement bypassed in meta-tool path** - The fail-closed check from fix #3 only ran in the direct-tool branch, which is never exercised in production. Models invoke tools through `call_tool` meta-tool, completely bypassing confirmation. **Fixed in cleanup-2.**

## Cleanup Cycle Changes

### §1. Orchestrator Owns User Message Persistence
- Moved `append_message` from CLI adapter into `process_turn()`
- Fixes first-turn double-count bug

### §2. EmptyResponseError Guard
- Added `EmptyResponseError` exception class
- Guard in `stop`/`length` branch fails turn if content is empty
- Unit tests verify the guard

### §3. Confirm Callback Fails Closed
- Changed `requires_confirmation` check to fail if callback is missing
- Returns error `ToolCallResult` instead of executing tool
- Security fix for future adapters

### §4. CLI REPL Meta-Commands
- Added `/quit`, `/exit` - exit REPL
- Added `/reset` - start fresh session
- Added `/history` - print message history
- Added `/session` - print session metadata
- Added `/help` - list commands

### §5. Two-Tool Chain Integration Test
- Added test: "What time is it in Tokyo, and how many files are in /tmp?"
- Verifies multi-iteration tool chains work end-to-end

### §6. Handoff Document Renamed
- Moved from `docs/Phase-1c-Summary.md` to `docs/handoffs/HESTIA_PHASE_1C_REPORT_20260409.md`
- Per ADR-010 naming convention

### §7. ADR-012 Added
- Documents state machine + confirmation callback pattern
- Explains adapter contract for Phase 2

## Cleanup-2 Cycle (Post-Review Fixes)

After the initial cleanup cycle, review found one critical bug and three nits:

### §1. Fix: Confirmation Enforcement in Meta-Tool Path (Blocker)
- **Bug:** The fail-closed check only ran in the direct-tool branch, never in production.
- **Fix:** Moved confirmation enforcement into the `call_tool` meta-tool branch in orchestrator.
- **Tests:** Added 2 new tests for meta-tool confirmation (fail closed, user denial).
- **Commit:** `c15a61f`

### §2. Nit: Hoist EmptyResponseError Import
- Moved import from inline to module top for consistency.
- **Commit:** `7040f15`

### §3. Fix: /reset Keeps Same User
- **Bug:** `/reset` created a new user identity each time, accumulating orphans.
- **Fix:** Added `SessionStore.create_session()` and updated `/reset` to use same user.
- **Tests:** Added 2 tests for `create_session` behavior.
- **Commit:** `1254147`

### §4. Nit: Fix ADR-012 Indentation
- Re-indented sub-bullets to match ADR-011 format for proper GitHub rendering.
- Updated confirmation enforcement wording to reflect meta-tool fix.
- **Commit:** `874ff6c`

## Components Delivered

### 1. Turn State Machine (`src/hestia/orchestrator/`)

**States:**
- `RECEIVED` - User input captured
- `BUILDING_CONTEXT` - Assembling message list within budget
- `AWAITING_MODEL` - LLM inference in progress
- `EXECUTING_TOOLS` - Dispatching tool calls
- `AWAITING_USER` - Paused for confirmation (reserved)
- `AWAITING_SUBAGENT` - Delegated to subagent (Phase 3)
- `COMPRESSING` - Context compression (Phase 3)
- `RETRYING` - Transient error, backing off
- `DONE` - Terminal success
- `FAILED` - Terminal error

**Key Classes:**
- `Turn` - Dataclass representing a single turn with full transition history
- `TurnTransition` - Records each state change with timestamp and note
- `IllegalTransitionError` - Raised on invalid state transitions

### 2. Orchestrator Engine (`src/hestia/orchestrator/engine.py`)

The `Orchestrator` class manages the turn lifecycle:

```python
orchestrator = Orchestrator(
    inference=inference_client,
    session_store=session_store,
    context_builder=context_builder,
    tool_registry=tool_registry,
    policy=policy_engine,
    confirm_callback=optional_confirmation_handler,
    max_iterations=10,
)

turn = await orchestrator.process_turn(
    session=session,
    user_message=user_message,
    respond_callback=response_handler,
)
```

**Features:**
- State machine with validated transitions
- Meta-tool dispatch (`list_tools`, `call_tool`)
- Tool confirmation callback support (fails closed if missing)
- Empty response guard (fails turn instead of silent blank)
- Automatic context rebuilding after tool execution
- Persistent turn logging with full transition audit trail
- Max iteration limit to prevent infinite loops

**State Flow:**
```
RECEIVED → BUILDING_CONTEXT → AWAITING_MODEL
                ↑                    ↓
                └──────────── EXECUTING_TOOLS (loop back)
                                    ↓
                              DONE or FAILED
```

### 3. CLI Adapter (`src/hestia/cli.py`)

Platform-agnostic command-line interface:

```bash
# Initialize
hestia init

# Interactive chat
hestia chat

# Single message
hestia ask "What time is it?"

# Health check
hestia health
```

**REPL Meta-Commands:**
- `/quit`, `/exit` - Exit the REPL
- `/reset` - Start a new session
- `/history` - Print the current session message history
- `/session` - Print the current session metadata
- `/help` - List all commands

**Configuration Options:**
- `--db-path` - Database location (default: hestia.db)
- `--artifacts-path` - Artifact storage (default: artifacts/)
- `--inference-url` - LLM server URL (default: http://localhost:8001)
- `--model` - Model name (default: Qwen3.5-9B-UD-Q4_K_XL.gguf)
- `-v/--verbose` - Debug output

### 4. SessionStore Turn Persistence (`src/hestia/persistence/sessions.py`)

Extended SessionStore with turn tracking:

- `insert_turn(turn)` - Create new turn record
- `update_turn(turn)` - Update turn state/completion
- `append_transition(turn_id, transition)` - Log state change
- `get_turn(turn_id)` - Retrieve turn by ID
- `list_turns_for_session(session_id, limit)` - List session history

## Test Coverage

**118 tests passing:**
- 15 turn state machine tests
- 7 turn persistence tests  
- 13 ContextBuilder tests (updated for two-number calibration)
- 4 orchestrator integration tests (including 2-tool chain)
- 3 orchestrator error handling tests
- 8 CLI meta-command tests
- Plus existing Phase 1a/1b tests

**Integration Tests:**
- Simple turn completion (no tools)
- Turn with tool calls (meta-tools)
- Turn persistence verification
- Two-tool chain (Tokyo time + /tmp file count)

**Error Handling Tests:**
- EmptyResponseError on empty stop/length
- Confirm callback fails closed when missing

## Files Added/Modified

**New Files:**
- `src/hestia/orchestrator/__init__.py`
- `src/hestia/orchestrator/types.py`
- `src/hestia/orchestrator/transitions.py`
- `src/hestia/orchestrator/engine.py`
- `src/hestia/cli.py`
- `tests/unit/test_turn_state_machine.py`
- `tests/unit/test_session_store_turns.py`
- `tests/integration/test_orchestrator.py`
- `tests/unit/test_orchestrator_errors.py`
- `tests/unit/test_cli_meta_commands.py`
- `docs/handoffs/HESTIA_PHASE_1C_REPORT_20260409.md`

**Modified Files:**
- `pyproject.toml` - Added click dependency and hestia CLI entry point
- `src/hestia/errors.py` - Added IllegalTransitionError, EmptyResponseError
- `src/hestia/persistence/sessions.py` - Added turn persistence methods
- `tests/unit/test_context_builder.py` - Updated for two-number calibration

## Architecture Decision Records

- **ADR-011**: Two-number calibration (body_factor + meta_tool_overhead)
- **ADR-012**: Turn state machine with platform-agnostic confirmation callback

## Next Steps (Phase 2)

Phase 1 is complete. The foundation is ready for:
- Matrix adapter (real-time messaging)
- Telegram adapter
- SlotManager (KV cache persistence)
- Scheduler (background task management)

**v0.1.0 is ready to tag** after this cleanup merges to `develop`.

## Usage Example

```bash
# Start llama-server
llama-server -m models/Qwen3.5-9B-UD-Q4_K_XL.gguf --port 8001 &

# Initialize Hestia
hestia init

# Chat
hestia chat
You: What time is it?
Assistant: The current time is 2026-04-09 12:45:00 UTC.

You: /help
Meta-commands:
  /quit, /exit     Exit the REPL
  /reset           Start a new session
  /history         Print the current session message history
  /session         Print the current session metadata
  /help            Show this help

You: /quit
Goodbye!
```

---

## Handoff Report

**Completed:** 2026-04-09
**Final Test Count:** 122 passing (15 new tests added in both cleanup cycles)
**Branch:** `feature/phase-1c-orchestrator-cli`

### Cleanup-1 Cycle Commits (7 commits)

1. `f2be4c8` - fix(orchestrator): own user message persistence to eliminate first-turn double-count
2. `406349c` - fix(orchestrator): raise EmptyResponseError on empty stop/length response
3. `b5d044e` - fix(orchestrator): fail closed when confirm_callback missing
4. `b7e4247` - feat(cli): add /quit /reset /history /session /help REPL meta-commands
5. `229d782` - test(integration): add two-tool chain test for Tokyo time + /tmp file count
6. `cf30445` - docs(handoffs): move Phase 1c report to docs/handoffs/ and conform to naming
7. `d3d9230` - docs(adr): add ADR-012 for turn state machine and confirmation callback

### Cleanup-2 Cycle Commits (5 commits)

8. `c15a61f` - fix(orchestrator): enforce confirmation in meta-tool path, not just direct calls
9. `7040f15` - style(orchestrator): hoist EmptyResponseError import to module top
10. `1254147` - fix(cli): /reset creates a new session for the same user, not a new user
11. `874ff6c` - docs(adr): fix ADR-012 indentation and update confirmation enforcement wording
12. `XXXXXXX` - docs(handoffs): add cleanup-2 cycle summary and update test count

### Quality Checks

- **pytest:** 122 passed (was 119 at cleanup-1, was 107 at baseline)
- **ruff:** Pre-existing warnings in scripts/calibrate_token_count.py only
- **mypy:** 9 errors, all pre-existing (forward refs in sessions.py, Database.init pattern)

### Deviations

None. All 11 sections implemented as specified across both cleanup cycles.

### Blockers

**Cleanup-2 complete.** Branch ready for Dylan to review, push, merge to develop, and tag v0.1.0.

### Git Log (feature/phase-1c-orchestrator-cli ^develop)

```
d3d9230 docs(adr): add ADR-012 for turn state machine and confirmation callback
cf30445 docs(handoffs): move Phase 1c report to docs/handoffs/ and conform to naming
229d782 test(integration): add two-tool chain test for Tokyo time + /tmp file count
b7e4247 feat(cli): add /quit /reset /history /session /help REPL meta-commands
b5d044e fix(orchestrator): fail closed when confirm_callback missing
406349c fix(orchestrator): raise EmptyResponseError on empty stop/length response
f2be4c8 fix(orchestrator): own user message persistence to eliminate first-turn double-count
74b837b feat(phase-1c): Orchestrator engine and CLI adapter
7601e0e refactor(tools): collapse auto_artifact_above and max_result_chars into max_inline_chars
aa7d863 fix(inference): recalibrate count_request as body factor plus meta-tool overhead
8dd8a9f Merge Phase 1b work into Phase 1c branch
c862fcd docs(handoffs): Phase 1b progress report
...
```

All commits authored by Dylan O'Keefe <dylanokeefedev@gmail.com>.
