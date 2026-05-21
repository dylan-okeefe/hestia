# L162 — Cross-Session Conversation Continuity

**Status:** Spec only
**Branch:** `feature/l162-cross-session-conversation-continuity` (from `feature/workflow-builder`)
**Depends on:** L158 (auto-save memory), L159 (load memories into system prompt)

## Intent

Even with L158 and L159, new sessions only see *summaries* of past conversations. The user still loses the full thread context (e.g., specific job URLs, scraped artifact handles, intermediate reasoning). This loop adds a "session handoff" mechanism: when a new session starts for the same user/platform, load the most recent archived session's final messages into the new session's initial history.

## Review carry-forward

- *(none)*

## Scope

### §1 — Session handoff data model

Add to `src/hestia/persistence/sessions.py` (or new module):

```python
@dataclass
class SessionHandoff:
    """Data transferred from a previous session to a new one."""
    previous_session_id: str
    summary: str
    key_messages: list[Message]  # Last N user/assistant messages
    artifacts: list[str]  # Artifact handles referenced
    created_at: datetime
```

**Commit:** `feat(persistence): SessionHandoff dataclass for cross-session continuity`

### §2 — Handoff storage and retrieval

Modify `SessionStore`:

1. `save_handoff(session_id, handoff: SessionHandoff)` — stores handoff data as JSON in a new `session_handoffs` table or as a column on `sessions`.
2. `get_latest_handoff(platform, platform_user)` — returns the most recent handoff for that user, or None.

Schema addition:
```sql
CREATE TABLE session_handoffs (
    id TEXT PRIMARY KEY,
    previous_session_id TEXT NOT NULL,
    platform TEXT NOT NULL,
    platform_user TEXT NOT NULL,
    summary TEXT,
    key_messages TEXT,  -- JSON array of message dicts
    artifacts TEXT,  -- JSON array of artifact handles
    created_at DATETIME NOT NULL
);
```

**Commit:** `feat(persistence): session handoff storage and retrieval`

### §3 — Generate handoff on archival

In `SessionStore.archive_session()` (or wherever sessions end):

1. After generating the summary (from L158), also capture the last `_HANDOFF_MESSAGE_COUNT = 8` user/assistant messages.
2. Capture any artifact handles referenced in those messages.
3. Save a `SessionHandoff` record.

```python
async def _save_handoff(self, session_id: str, messages: list[Message]) -> None:
    key_messages = [
        m for m in messages[-_HANDOFF_MESSAGE_COUNT:]
        if m.role in ("user", "assistant")
    ]
    # ... extract artifact handles from tool results ...
    handoff = SessionHandoff(...)
    await self.save_handoff(session_id, handoff)
```

**Commit:** `feat(persistence): auto-generate handoff on session archival`

### §4 — Inject handoff into new sessions

Modify `src/hestia/platforms/telegram_adapter.py` (and matrix adapter) when creating a new session:

1. Before creating the session, check `session_store.get_latest_handoff(platform, platform_user)`.
2. If a handoff exists, prepend a synthetic system message or user message to the new session's initial history:

```python
handoff = await session_store.get_latest_handoff(platform, platform_user)
if handoff is not None:
    context_msg = Message(
        role="system",
        content=(
            f"Continuing from previous session ({handoff.previous_session_id}).\n"
            f"Summary: {handoff.summary}\n"
            f"Recent context:\n" +
            "\n".join(f"- [{m.role}] {m.content[:200]}" for m in handoff.key_messages)
        ),
    )
    # Append as first message in the new session
```

**Commit:** `feat(platforms): inject session handoff into new session history`

### §5 — Tests

In `tests/unit/persistence/test_session_handoff.py`:
1. Test `save_handoff` and `get_latest_handoff` round-trip.
2. Test `get_latest_handoff` returns None when no handoff exists.
3. Test handoff includes correct key messages.

In `tests/unit/platforms/test_telegram_adapter.py` (or integration):
1. Test that a new session for an existing user gets handoff messages prepended.
2. Test that a new session for a new user gets no handoff.

Run quality gates.

**Commit:** `test(persistence): session handoff storage and injection coverage`

## Acceptance

- `pytest tests/unit/ tests/integration/ -q` green
- `mypy src/hestia` reports 0 errors
- Starting a new Telegram session after a previous one was archived causes the system to include a "Continuing from previous session" message

## Handoff

- Write `docs/handoffs/L162-cross-session-conversation-continuity-handoff.md`
- Update `docs/development-process/kimi-loop-log.md`
