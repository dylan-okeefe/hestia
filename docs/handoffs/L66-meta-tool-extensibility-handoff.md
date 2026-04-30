# L66 — Meta-Tool Extensibility & Serialization Hygiene Handoff

**Branch:** `feature/l66-meta-tool-extensibility`
**Status:** Complete, ready for review

## Changes

### §1 — Meta-tool dispatch table
- Extracted `list_tools`, `describe_tool`, `call_tool` handlers into `_meta_list_tools`, `_meta_describe_tool`, `_meta_call_tool`
- Registered in `self._meta_tools` dict in `TurnExecution.__init__`
- `_dispatch_tool_call` now does a dict lookup instead of an if/elif chain

### §2 — Move `_message_to_dict` to serialization module
- Created `src/hestia/core/serialization.py` with `message_to_dict()`
- Updated `core/inference.py` and `context/builder.py` imports
- No other file imported `_message_to_dict` from inference

### §3 — Document tool construction patterns
- Added module docstring to `tools/builtin/__init__.py` explaining plain `@tool` vs `make_*_tool` factory patterns

## Quality gates

- `pytest tests/integration/test_orchestrator.py tests/unit/test_inference_client.py` — 7 passed
- `mypy src/hestia/orchestrator/execution.py src/hestia/core/serialization.py src/hestia/core/inference.py src/hestia/context/builder.py` — no issues
- `ruff check` — clean

## Intent verification

- **Adding a meta-tool requires zero changes to `_dispatch_tool_call`:** Verified — only need a new handler method and a dict entry.
- **No cyclic import through inference for serialization:** `context/builder.py` now imports from `core/serialization.py`.

## Next

Ready to merge to `develop` and start L67.
