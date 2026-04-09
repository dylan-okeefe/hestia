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
