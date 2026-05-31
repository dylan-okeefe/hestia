# L202 — JSON Repair + Search Tools — Handoff

**Branch:** `feature/l202-json-repair-and-search-tools`  
**Status:** Complete  
**Commits:** 2

---

## Commits

1. `feat(core): add repair_json utility for malformed tool-call arguments`
   - `src/hestia/core/json_repair.py` — new pure function repairing trailing commas, single quotes, unquoted keys, missing braces, fenced blocks, literal newlines/tabs
   - `tests/unit/core/test_json_repair.py` — tests for all repair cases + unrecoverable garbage

2. `fix(inference): use repair_json before giving up on tool-call arguments`
   - `src/hestia/core/inference.py` — wired `repair_json` into `_parse_json_tool_calls`, added `_parse_bare_json_tool_calls`, updated `_extract_tool_calls_from_text`
   - `src/hestia/orchestrator/execution.py` — applied `repair_json` in streaming accumulator path

---

## Quality gates

- `pytest tests/unit/core/test_json_repair.py tests/unit/test_inference_client.py tests/unit/orchestrator/test_execution.py` — 26 passed, 1 pre-existing failure ✅
- `mypy` on modified files — 0 errors ✅
- `ruff check` on modified files — 0 new issues ✅

---

## Verification notes

- Trailing comma / single quotes / missing braces are repaired
- ` ```json ` fenced blocks are extracted
- XML `<tool_call>` tags still work
- Streaming and non-streaming paths both use repair_json

---

## Next loop

L203 — Quality Monitor (T1.4)
