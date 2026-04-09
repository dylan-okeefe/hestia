# Phase 1c: Orchestrator & CLI - Implementation Summary

## Overview
Phase 1c completes the core Hestia framework by adding the **Orchestrator engine** that manages turn execution through a state machine, and a **CLI adapter** for local testing and development.

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
- Tool confirmation callback support
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

**107 tests passing:**
- 15 turn state machine tests
- 7 turn persistence tests  
- 13 ContextBuilder tests (updated for two-number calibration)
- 3 orchestrator integration tests
- Plus existing Phase 1a/1b tests

**Integration Tests:**
- Simple turn completion (no tools)
- Turn with tool calls (meta-tools)
- Turn persistence verification

## Bug Fixes

1. **IllegalTransitionError duplication** - Fixed by importing from `hestia.errors` instead of redefining in transitions module

2. **ContextBuilder test updates** - Updated to use `body_factor` parameter instead of deprecated `calibration_factor`

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
- `docs/Phase-1c-Summary.md`

**Modified Files:**
- `pyproject.toml` - Added click dependency and hestia CLI entry point
- `src/hestia/errors.py` - Added IllegalTransitionError
- `src/hestia/persistence/sessions.py` - Added turn persistence methods
- `tests/unit/test_context_builder.py` - Updated for two-number calibration

## Next Steps (Phase 2)

With Phase 1 complete, the foundation is ready for:
- Matrix adapter (real-time messaging)
- Telegram adapter
- SlotManager (KV cache persistence)
- Scheduler (background task management)

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

You: exit
Goodbye!
```
