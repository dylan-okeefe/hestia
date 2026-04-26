# L66 — Meta-Tool Extensibility & Serialization Hygiene

**Status:** Spec ready. Feature branch work — merge to `develop` when green.

**Branch:** `feature/l66-meta-tool-extensibility` (from `develop`)

## Goal

Fix two extensibility traps in the orchestrator: an open-coded type switch for meta-tool dispatch that grows linearly with each new meta-tool, and a serialization function living in the wrong module that forces circular imports.

---

## Intent & Meaning

The evaluation calls `_dispatch_tool_call` in `execution.py` an "open-coded type switch." Each meta-tool (`list_tools`, `describe_tool`, `call_tool`) has its own `if tc.name == "..."` branch. Adding a fourth meta-tool means editing an 80-line function that will become 120 lines. The intent is not just "make it shorter" — it is **make meta-tools as easy to add as regular tools**. The `@tool` decorator gives regular tools a clean registration pattern; meta-tools deserve the same.

`_message_to_dict` lives in `core/inference.py` but is imported by `context/builder.py`. The evaluation calls this a "circular import smell" and notes that `_message_to_dict` is a serialization concern, not an inference concern. The intent is **module boundary integrity**: `core/inference.py` should talk to llama-server; `core/types.py` (or a serialization module) should own the data-to-JSON mapping. Clean boundaries mean fewer local imports and clearer navigation.

---

## Scope

### §1 — Meta-tool dispatch table

**File:** `src/hestia/orchestrator/execution.py`
**Evaluation:** `_dispatch_tool_call` meta-tool dispatch is an open-coded type switch (lines 336-420). Each meta-tool has its own inline branch.

**Change:**
Create a `MetaToolRegistry` or a simple dict of handlers inside `TurnExecution`:

```python
self._meta_tools: dict[str, Callable[[ToolCall], Awaitable[ToolCallResult]]] = {
    "list_tools": self._meta_list_tools,
    "describe_tool": self._meta_describe_tool,
    "call_tool": self._meta_call_tool,
}
```

Extract each branch into a private async method (`_meta_list_tools`, etc.). `_dispatch_tool_call` becomes:

```python
async def _dispatch_tool_call(self, tc: ToolCall, ...) -> ToolCallResult:
    handler = self._meta_tools.get(tc.name)
    if handler:
        return await handler(tc)
    # ... fall through to regular tool dispatch
```

**Intent:** Adding a meta-tool should be one line (registering a handler), not a new `if` block inside a growing function.

**Commit:** `refactor(execution): replace meta-tool type switch with dispatch table`

---

### §2 — Move `_message_to_dict` to serialization module

**File:** `src/hestia/core/inference.py` → new or existing serialization home
**Evaluation:** `_message_to_dict` belongs in `core/types.py` or a serialization module, not `core/inference.py`.

**Change:**
- Move `_message_to_dict` to `src/hestia/core/serialization.py` (create if needed) or `src/hestia/core/types.py`.
- Update all imports:
  - `core/inference.py` — import and use it
  - `context/builder.py` — import from new location
- Remove the local import workaround in `persistence/db.py` if related (separate concern, but note if it simplifies).

**Intent:** A reader looking for "how do I serialize a Message?" should find the answer in a module whose name implies serialization, not inside an HTTP client wrapper.

**Commit:** `refactor(core): move _message_to_dict to serialization module`

---

## Quality gates

```bash
uv run pytest tests/unit/ tests/integration/ -q
uv run mypy src/hestia
uv run ruff check src/ tests/
```

## Acceptance (Spec-Based)

- `_dispatch_tool_call` has no `if tc.name == "..."` branches for meta-tools.
- `_message_to_dict` is importable from its new module; old import paths removed.
- All tests pass.

## Acceptance (Intent-Based)

- **A new meta-tool requires zero changes to `_dispatch_tool_call`.** Verify by imagining (or prototyping) a `abort_tool` meta-tool — it should only need a new handler method and a dict entry.
- **No file imports `_message_to_dict` from `core/inference.py`.** Verify with `grep -r "_message_to_dict" src/` — only the new home and `core/inference.py` (re-export or internal use) should appear.
- **The module graph is acyclic.** Verify that `context/builder.py` no longer imports from `core/inference.py` just for serialization.

## Handoff

- Write `docs/handoffs/L66-meta-tool-extensibility-handoff.md`.
- Update `docs/development-process/kimi-loop-log.md`.
- Merge `feature/l66-meta-tool-extensibility` to `develop`.

## Dependencies

None. Can start immediately from `develop` tip.
