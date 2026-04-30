# L056a: Orchestrator TurnContext Refactor

**Status:** Complete — merged to `feature/v0.10.1-pre-publication-prep`  
**Branch:** `feature/v0.10.1-pre-publication-prep`  
**Scope:** Collapse 7-tuple return and 20-parameter method signatures into a single TurnContext dataclass.

---

## Changes

### New: `TurnContext` dataclass (`orchestrator/types.py`)

Holds all mutable per-turn state that was previously passed as individual parameters:
- `session`, `turn`, `user_message`
- `build_result`, `tools`, `slot_id`
- `running_history`, `style_prefix`, `allowed_tools`
- `tool_chain`, `artifact_handles`
- `total_prompt_tokens`, `total_completion_tokens`, `total_reasoning_tokens`
- `delegated`
- `system_prompt`, `respond_callback`
- `platform`, `platform_user`

### Refactored methods (`orchestrator/engine.py`)

| Method | Before | After |
|--------|--------|-------|
| `_prepare_turn_context` | Returns 7-tuple | Mutates `TurnContext` in place |
| `_run_inference_loop` | 20 params, returns 7-tuple | Takes `TurnContext`, mutates in place, returns `str` (content) |
| `_handle_context_too_large` | 10 params | Takes `TurnContext` + `exc` + `trace_record_id` |
| `_handle_unexpected_error` | 10 params | Takes `TurnContext` + `error` + `trace_record_id` |
| `_finalize_turn` | 11 params | Takes `TurnContext` + `turn_start_time` + `trace_record_id` |

---

## Test Plan

- `uv run pytest tests/ -q` — no regressions
- `uv run mypy src/hestia/orchestrator/engine.py` — type clean
