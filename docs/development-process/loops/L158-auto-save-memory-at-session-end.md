# L158 — Auto-Save Memory at Session End

**Status:** Spec only
**Branch:** `feature/l158-auto-save-memory-at-session-end` (from `feature/workflow-builder`)
**Depends on:** L157 (browser session persistence — already landed)

## Intent

The model currently has zero recollection of cross-session context because nothing is ever saved to the memory store. When a Telegram session ends (user stops messaging, session is archived), any job search results, preferences, or facts discussed are lost forever. This loop adds automatic session summarization and memory persistence at session archival time.

## Review carry-forward

- *(none)*

## Scope

### §1 — Session summary generation

Add `src/hestia/memory/session_summarizer.py`:

```python
"""Summarize a completed session for memory storage."""

import logging
from typing import TYPE_CHECKING

from hestia.core.types import Message

if TYPE_CHECKING:
    from hestia.inference import InferenceClient

logger = logging.getLogger(__name__)

_SUMMARY_PROMPT = """\
Summarize the following conversation in 2-3 sentences. Focus on:
1. What the user asked for or discussed
2. Any key facts, preferences, or decisions
3. Any unfinished tasks or next steps

Be concise. Output only the summary, no preamble."""


class SessionSummarizer:
    """Generates a text summary of a session's messages."""

    def __init__(self, inference: "InferenceClient") -> None:
        self._inference = inference

    async def summarize(self, messages: list[Message]) -> str:
        """Return a summary string or empty string if nothing to summarize."""
        if not messages:
            return ""

        # Filter to user/assistant roles with actual content
        dialogue = []
        for m in messages:
            if m.role in ("user", "assistant") and (m.content or "").strip():
                dialogue.append(f"{m.role}: {m.content.strip()}")

        if len(dialogue) < 2:
            return ""

        text = "\n".join(dialogue)
        prompt_messages = [
            Message(role="system", content=_SUMMARY_PROMPT),
            Message(role="user", content=text),
        ]

        try:
            response = await self._inference.chat(
                messages=prompt_messages,
                tools=[],
                reasoning_budget=0,
            )
            return (response.content or "").strip()
        except Exception as exc:
            logger.warning("Session summarization failed: %s", exc)
            return ""
```

**Commit:** `feat(memory): SessionSummarizer for turn dialogue compression`

### §2 — Auto-save on session archival

Modify `src/hestia/persistence/sessions.py` — in `SessionStore.archive_session()` (or wherever session state transitions to `archived`):

1. After updating the session state to `archived`, fetch all messages for that session.
2. If a `SessionSummarizer` is configured, generate a summary.
3. If the summary is non-empty, save it to the memory store with:
   - `tags`: `["session-summary", <platform>, <session_topic_tag>]`
   - `session_id`: the archived session's ID
   - `content`: the summary text + a bullet list of key user messages (for searchability)

Add auto-tag inference: scan user messages for keywords to derive a topic tag:
- Contains "job", "resume", "hiring", "role" → tag `"job-search"`
- Contains "weather" → tag `"weather"`
- Contains "memory", "remember" → tag `"memory-config"`
- Default → tag `"general"`

```python
async def _auto_save_session_memory(
    self,
    session_id: str,
    summarizer: SessionSummarizer | None,
) -> None:
    """Generate summary and save to memory store when a session ends."""
    if summarizer is None:
        return
    messages = await self.get_messages(session_id)
    summary = await summarizer.summarize(messages)
    if not summary:
        return
    # ... save to memory store via MemoryStore.save()
```

**Commit:** `feat(memory): auto-save session summary on archival`

### §3 — Wire summarizer into app context

In `src/hestia/app.py` `AppContext`:
1. Add a lazy `session_summarizer` property.
2. Pass it to `SessionStore` or the orchestrator so it can be invoked at archival time.

**Commit:** `feat(app): wire SessionSummarizer into AppContext`

### §4 — Tests

In `tests/unit/memory/test_session_summarizer.py`:
1. Test `summarize` returns empty string for empty messages.
2. Test `summarize` returns empty string for single message.
3. Mock `InferenceClient.chat` and assert the prompt contains the dialogue.
4. Test that a failed inference call returns `""` (no crash).

In `tests/unit/persistence/test_sessions.py` (or integration):
1. Archive a session with messages. Assert a memory row is created.
2. Archive a session with no messages. Assert no memory row.

Run quality gates:
```bash
uv run pytest tests/unit/ tests/integration/ -q
uv run mypy src/hestia
uv run ruff check src/ tests/
```

**Commit:** `test(memory): session summarizer and auto-save coverage`

## Acceptance

- `pytest tests/unit/ tests/integration/ -q` green
- `mypy src/hestia` reports 0 errors
- `ruff check src/` remains at baseline or better
- Archiving a session with 3+ user/assistant messages creates a memory entry

## Handoff

- Write `docs/handoffs/L158-auto-save-memory-at-session-end-handoff.md`
- Update `docs/development-process/kimi-loop-log.md`
