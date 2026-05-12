# L165 — Session Handoff Hardening

**Status:** Spec only  
**Branch:** `feature/l165-session-handoff-hardening` (from `feature/workflow-builder-runtime`)  
**Depends on:** L162 (cross-session conversation continuity)

## Intent

The runtime branch review (CRIT-2) identified that session handoff injects a `role="system"` message into the new session's history. While `ContextBuilder` filters system messages from history (preventing a Qwen template crash), this means the handoff content is silently discarded after the first turn. If the orchestrator ever pre-builds context before the first user message, the handoff would be stripped before it's ever seen.

## Review carry-forward

- *(none)*

## Scope

### §1 — Change handoff message role from "system" to "user"

In `src/hestia/persistence/sessions.py` (or wherever handoff injection happens), change the synthetic message role:

Before:
```python
context_msg = Message(
    role="system",
    content=(...),
)
```

After:
```python
context_msg = Message(
    role="user",
    content=(
        "[Previous session context]\n"
        f"Continuing from previous session ({handoff.previous_session_id}).\n"
        f"Summary: {handoff.summary}\n"
        f"Recent context:\n" +
        "\n".join(f"- [{m.role}] {m.content[:200]}" for m in handoff.key_messages)
    ),
)
```

The `[Previous session context]` prefix signals to the model (and to human readers) that this is synthetic context, not a real user message.

**Commit:** `fix(persistence): use role="user" for handoff injection`

### §2 — Update ContextBuilder to handle handoff user messages

Since the handoff message now has `role="user"`, it will survive the builder's filtering. However, it should still be treated specially:

1. In `ContextBuilder.build()`, identify handoff messages by the `[Previous session context]` prefix.
2. Ensure handoff messages are placed at the very beginning of the history (before any real user messages).
3. Do not include handoff messages in token budget calculations as normal user messages — they should be treated as part of the system context.

**Commit:** `feat(context): treat handoff user messages as context prefix`

### §3 — Verify handoff survives past the first turn

Write an integration test:

1. Create a session with a handoff record.
2. Process a turn (user message → assistant response).
3. Verify the handoff content is still present in the session's message history after the turn completes.
4. Process a second turn.
5. Verify the handoff content is still present.

**Commit:** `test(persistence): verify handoff survives multiple turns`

### §4 — Quality gates

```bash
uv run pytest tests/unit/ tests/integration/ -q
uv run mypy src/hestia
uv run ruff check src/ tests/
```

## Acceptance

- Handoff messages use `role="user"` with `[Previous session context]` prefix
- Handoff content survives past the first turn
- ContextBuilder places handoff messages at the beginning of history
- Qwen template does not crash when handoff is present
- All quality gates pass

## Handoff

- Write `docs/handoffs/L165-session-handoff-hardening-handoff.md`
- Update `docs/development-process/kimi-loop-log.md`
