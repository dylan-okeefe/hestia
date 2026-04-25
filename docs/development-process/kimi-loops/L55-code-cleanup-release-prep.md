# L55 — Code Cleanup & Release Prep

**Status:** Spec only. Pre-release cleanup — **merge to `develop`.**

**Branch:** `feature/l55-code-cleanup-release-prep` (from `develop`)

## Goal

Clean up internal review-tracking comments, fix type-system papercuts, and
remove mechanical repetition so the codebase is release-ready.

## Scope

### §1 — Strip internal review-tracking comments

**Files:** Search entire `src/hestia/` for patterns:
- `# Copilot [A-Z]-\d+:`
- `# M-\d+ / \d{4}-\d{2}-\d{2}:`
- `# C-\d+`
- Any other internal code-review IDs embedded in comments

**What to do:**
- Delete the tracking comment.
- If the comment contained an actual engineering note (not just a tracker ID),
  rewrite it in plain language.
- If the comment is now obvious from the code, delete it entirely.

Example transformation:
```python
# Copilot H-9: We need to check bounds here because the model can hallucinate large numbers.
# ->
# Guard against hallucinated large values from the model.
```

### §2 — TurnContext.session should be non-optional

**File:** `src/hestia/orchestrator/types.py`

`TurnContext.session: Session | None` is initialized `None` in the dataclass,
but structurally it is always populated before the inference loop runs. Every
caller is forced to handle `None` with guard clauses.

Change to:
```python
@dataclass
class TurnContext:
    session: Session  # required
    ...
```

Remove all `if ctx.session is None: return` guard clauses in
`orchestrator/engine.py` and anywhere else they exist.

### §3 — SkillIndexBuilder divergence

**File:** `src/hestia/skills/builder.py`

`format_for_prompt()` and `build_index()` produce similar-but-not-identical
output for the same use case. They will silently diverge over time.

Pick one canonical format. Make the other a thin wrapper that calls the
canonical method and transforms the output (if a different shape is truly
needed). Add a docstring explaining which is the source of truth.

If they are truly redundant, delete one and update all callers.

### §4 — Tool factory return type cleanup

**Files:** All `make_*_tool` factories in `src/hestia/tools/builtin/`

Every factory ends with:
```python
return cast("Callable[..., Coroutine[Any, Any, str]]", x)
```

The `@tool` decorator should return a type that satisfies the factory return
type without `cast()`. Tighten the `@tool` decorator's return type annotation
so the `cast()` can be removed from all factories.

If mypy still complains, consider making the factory return type
`ToolHandler` (the alias) directly, since that's what `@tool` actually
returns.

### §5 — Meta-command handler relocation (prep work)

**File:** `src/hestia/app.py`

The `_handle_meta_command` function defines CLI-specific REPL commands
(`/help`, `/tools`, `/exit`) inside the app context module. This is the wrong
home — it belongs in `src/hestia/commands/`.

Move `_handle_meta_command` and its dispatch table to
`src/hestia/commands/meta.py` (new file). Update `app.py` to import and call
it. This is intentionally a small move — full app.py decomposition is L57.

## Quality gates

```bash
uv run pytest tests/unit/ tests/integration/ -q
uv run mypy src/hestia
uv run ruff check src/ tests/
```

## Acceptance

- No `# Copilot`, `# M-`, or `# C-` tracker comments remain in `src/`.
- `TurnContext.session` is `Session` (not `Session | None`).
- `SkillIndexBuilder` has one canonical formatting method.
- No `cast()` in tool factories.
- `_handle_meta_command` lives in `commands/meta.py`.

## Handoff

- Write `docs/handoffs/L55-code-cleanup-release-prep-handoff.md`.
- Update `docs/development-process/kimi-loop-log.md`.
- Merge `feature/l55-code-cleanup-release-prep` to `develop`.
- Advance `KIMI_CURRENT.md` to L56.

## Dependencies

- L54 should merge first (it touches overlapping files like `engine.py`).
