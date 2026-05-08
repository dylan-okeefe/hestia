# L160 — Subagent Parent Context Inheritance

**Status:** Spec only
**Branch:** `feature/l160-subagent-parent-context-inheritance` (from `feature/workflow-builder`)
**Depends on:** None (can land independently)

## Intent

When the model delegates to a subagent, the subagent receives only the raw task text (e.g., "write an MD file with that info") with zero context about what was discussed in the parent session. The subagent then asks the user for clarification, wasting turns and frustrating the user. This loop passes the parent session's recent message history into the subagent's initial context.

## Review carry-forward

- *(none)*

## Scope

### §1 — Capture parent context at delegation time

Modify `src/hestia/orchestrator/execution.py` `_execute_policy_delegation()`:

1. Before creating the subagent turn, extract the last N messages from the parent session's running history.
2. Serialize them into a "context" string that the subagent can see.

```python
_PARENT_CONTEXT_MESSAGE_COUNT = 10
_PARENT_CONTEXT_MAX_CHARS = 4000

async def _execute_policy_delegation(
    self,
    user_message: Message,
    tool_calls: list[ToolCall],
) -> tuple[list[Message], list[str]]:
    ...
    # Build parent context for subagent
    parent_context = self._build_parent_context(ctx.running_history)
    ...

def _build_parent_context(self, history: list[Message]) -> str:
    """Serialize recent parent history for subagent consumption."""
    recent = history[-_PARENT_CONTEXT_MESSAGE_COUNT:]
    lines = ["## Parent session context (most recent messages):"]
    for msg in recent:
        if msg.role == "tool":
            # Truncate long tool results
            content = (msg.content or "")[:500]
            lines.append(f"[{msg.role}] {content}...")
        elif msg.role in ("user", "assistant"):
            content = (msg.content or "")[:1000]
            lines.append(f"[{msg.role}] {content}")
    text = "\n".join(lines)
    if len(text) > _PARENT_CONTEXT_MAX_CHARS:
        text = text[:_PARENT_CONTEXT_MAX_CHARS] + "\n... (truncated)"
    return text
```

**Commit:** `feat(orchestrator): capture parent context for subagent delegation`

### §2 — Inject parent context into subagent session

Modify `src/hestia/tools/builtin/delegate_task.py` (or wherever `delegate_task` is implemented):

1. Accept an optional `parent_context: str` parameter in the tool signature.
2. When creating the subagent's initial user message, prepend the parent context:

```python
context_prefix = f"""\
You are a subagent working on a delegated task. Here is the recent conversation context from the parent session:

{parent_context}

---
Delegated task:"""

full_task = f"{context_prefix}\n\n{task}"
```

3. Pass `full_task` as the subagent's initial user message instead of the bare task text.

**Commit:** `feat(tools): inject parent context into delegate_task subagent message`

### §3 — Wire delegation to pass parent context

In `src/hestia/orchestrator/execution.py` `_execute_policy_delegation()`, pass `parent_context` to the `delegate_task` tool call:

```python
result = await self._tools.call(
    "delegate_task",
    {
        "task": task,
        "context": context,
        "parent_context": parent_context,
    },
)
```

**Commit:** `feat(orchestrator): wire parent_context through policy delegation`

### §4 — Tests

In `tests/unit/orchestrator/test_delegation.py` (or create):
1. Test `_build_parent_context` returns empty string for empty history.
2. Test `_build_parent_context` includes only last N messages.
3. Test `_build_parent_context` truncates long tool results.
4. Test that `delegate_task` receives `parent_context` in its arguments when delegation triggers.

Run quality gates.

**Commit:** `test(orchestrator): subagent parent context inheritance coverage`

## Acceptance

- `pytest tests/unit/ tests/integration/ -q` green
- `mypy src/hestia` reports 0 errors
- Delegating a task from a session with history causes the subagent to receive the recent parent messages

## Handoff

- Write `docs/handoffs/L160-subagent-parent-context-inheritance-handoff.md`
- Update `docs/development-process/kimi-loop-log.md`
