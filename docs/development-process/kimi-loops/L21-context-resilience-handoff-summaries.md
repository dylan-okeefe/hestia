# Kimi loop L21 — context resilience + session handoff summaries

## Review carry-forward

From L20 review (trust config + web search):

- `uv.lock` was left uncommitted after Kimi's 0.3.0 bump; Cursor committed it
  manually. Kimi's end-of-loop checklist should include
  `git status --short` and an explicit "no stray untracked files" check.
- Ruff / mypy counts matched baseline (166 / 44) but nothing in the loop
  tightens them; see also L22.
- `hestia init` wizard, email/calendar adapters, and reflection loop remain on
  the roadmap but out of scope for L21 — see `design-artifacts/brainstorm-april-13.md`
  for priorities.
- From Dylan's runtime report: shared llama-server on Hermes+Hestia produced a
  ⚠️ "Context length exceeded (15,228 tokens). Cannot compress further." reply
  on the Silas side. Root cause is Hermes-internal compression logic; **the
  lesson for Hestia is that we silently truncate on overflow without any
  summarization or user-visible signal.** Full analysis:
  [`reviews/context-overflow-analysis-april-17.md`](../reviews/context-overflow-analysis-april-17.md).

**Branch:** `feature/l21-context-resilience-handoff` from **`develop`**.

---

## Goal

Close three gaps in how Hestia handles long-running sessions and per-slot
context pressure:

1. **No session handoff summaries** — every new session starts with only
   identity + memory epoch; yesterday's thread is lost unless the model
   `save_memory`'d something explicitly.
2. **No history compression** — when `ContextBuilder` drops oldest messages to
   fit the budget, they are silently discarded with no breadcrumb left in
   context. Quality degrades without the operator knowing why.
3. **No user-visible overflow signal** — if protected messages alone exceed
   budget, `ContextBuilder` returns a best-effort `[system, new_user]` pair and
   carries on. The operator never finds out.

Ship behind opt-in config flags; default behavior stays identical for existing
installs.

Target version: **0.4.0** (minor bump; new config fields and a new public
`HistoryCompressor` protocol).

---

## §-1 — Create branch and capture baseline

```bash
git checkout develop
git pull origin develop
git checkout -b feature/l21-context-resilience-handoff
uv run pytest tests/unit/ tests/integration/ -q
```

Record the baseline ("514 passed, 6 skipped" expected — matches v0.3.0).

---

## §0 — Cleanup carry-forward from L20

1. Confirm `uv.lock` at HEAD has `version = "0.3.0"` for the Hestia package
   entry and matches `pyproject.toml`. If not, regenerate with `uv lock` and
   commit in a standalone `chore(lockfile): …` commit.
2. Add a **"post-loop self-check"** checklist stanza at the end of this file
   (Kimi should tick it before writing `.kimi-done`):
   - `git status --short` shows no untracked or modified files.
   - `uv run pytest tests/unit/ tests/integration/ -q` green.
   - `uv run ruff check src/ tests/` ≤ baseline (current: 166).
   - `uv run mypy src/hestia` ≤ baseline (current: 44).

Commit: `chore: tighten Kimi end-of-loop checklist`.

---

## §1 — Session handoff summaries

### Problem

Session close → all raw history becomes cold rows in `messages`. The model
sees none of it next time unless the operator manually `save_memory`'d things
during the session. For a personal assistant, this breaks the "I was just
talking to you 10 minutes ago" expectation.

### Code sketch

**File:** `src/hestia/memory/handoff.py` (new)

```python
"""Session handoff summaries: generate a 2-3 sentence summary on session close."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from hestia.core.inference import InferenceClient
from hestia.core.types import Message, Session
from hestia.memory.store import MemoryRecord, MemoryStore

logger = logging.getLogger(__name__)

HANDOFF_PROMPT = """You are producing a brief session handoff note.

Summarize the conversation in 2-3 sentences, focused on:
1. What was decided or accomplished.
2. What is still pending.
3. Any facts the operator will want to remember next session.

No pleasantries. No greetings. No bullet lists. Plain prose, <= 350 characters.
"""


@dataclass
class HandoffResult:
    summary: str
    memory_id: str
    token_cost: int


class SessionHandoffSummarizer:
    """Generates a short summary when a session closes and stores it as memory."""

    def __init__(
        self,
        inference: InferenceClient,
        memory_store: MemoryStore,
        *,
        max_chars: int = 350,
        min_messages: int = 4,
    ) -> None:
        self._inference = inference
        self._memory = memory_store
        self._max_chars = max_chars
        self._min_messages = min_messages

    async def summarize_and_store(
        self,
        session: Session,
        history: list[Message],
    ) -> HandoffResult | None:
        """Generate a handoff summary and persist it. Returns None on skip."""
        # Skip trivial sessions (greetings, single-turn).
        user_msgs = sum(1 for m in history if m.role == "user")
        if user_msgs < self._min_messages:
            return None

        request_msgs: list[Message] = [
            Message(role="system", content=HANDOFF_PROMPT),
            *(m for m in history if m.role in ("user", "assistant") and m.content),
        ]
        response = await self._inference.chat(
            messages=request_msgs,
            tools=[],
            slot_id=None,            # one-shot, no slot state
            reasoning_budget=0,
        )
        summary = (response.content or "").strip()
        if not summary:
            logger.warning("Session handoff produced empty summary for %s", session.id)
            return None
        if len(summary) > self._max_chars:
            summary = summary[: self._max_chars].rstrip() + "…"

        record = MemoryRecord(
            content=summary,
            type="session_handoff",
            tags=["handoff", session.platform],
            session_id=session.id,
        )
        memory_id = await self._memory.save(record)
        return HandoffResult(
            summary=summary,
            memory_id=memory_id,
            token_cost=(response.prompt_tokens or 0) + (response.completion_tokens or 0),
        )
```

### Wiring

- `HestiaConfig` gains a nested `handoff: HandoffConfig` with
  `enabled: bool = False`, `min_messages: int = 4`, `max_chars: int = 350`.
- `Orchestrator.close_session(session_id)` (or equivalent — audit existing
  CLI / scheduler code for the close path) picks up the summarizer when
  configured and fires it. If there is no single close hook today, this loop
  adds one.
- Scheduler's slot-eviction path (COLD transition) also triggers the
  summarizer **iff** `handoff.enabled and not already_summarized(session)`.

### Tests

- `tests/unit/test_handoff_summarizer.py`: happy path, skip-on-short-session,
  empty-response handling, oversize truncation, memory record shape.
- `tests/integration/test_handoff_flow.py`: full cycle — start session,
  record N turns, close, assert handoff memory exists and surfaces in
  `memory.search(tags=["handoff"])`.

### Commit

`feat(memory): session handoff summaries on close`

---

## §2 — History compression for overflow recovery

### Problem

When `ContextBuilder.build()` drops oldest history to fit, nothing replaces
the dropped content. The model loses continuity with no breadcrumb.

### Code sketch

**File:** `src/hestia/context/compressor.py` (new)

```python
"""History compression for context overflow recovery."""

from __future__ import annotations

import logging
from typing import Protocol

from hestia.core.inference import InferenceClient
from hestia.core.types import Message

logger = logging.getLogger(__name__)


class HistoryCompressor(Protocol):
    async def summarize(self, dropped: list[Message]) -> str: ...


class InferenceHistoryCompressor:
    """Default compressor that calls the same InferenceClient with a short prompt."""

    PROMPT = (
        "You are compressing older conversation history so the model can continue.\n"
        "Summarize the following exchanges in <= 400 characters, preserving:\n"
        "- User intent and any decisions made\n"
        "- Facts the assistant learned about the user\n"
        "- Open questions or pending actions\n"
        "Do not address the user. Output a single prose paragraph."
    )

    def __init__(self, inference: InferenceClient, *, max_chars: int = 400) -> None:
        self._inference = inference
        self._max_chars = max_chars

    async def summarize(self, dropped: list[Message]) -> str:
        if not dropped:
            return ""
        request = [
            Message(role="system", content=self.PROMPT),
            *(m for m in dropped if m.role in ("user", "assistant") and m.content),
        ]
        try:
            response = await self._inference.chat(
                messages=request, tools=[], slot_id=None, reasoning_budget=0
            )
        except Exception:   # noqa: BLE001 — compressor is best-effort
            logger.warning("History compressor failed; falling back to truncation", exc_info=True)
            return ""
        summary = (response.content or "").strip()
        return summary[: self._max_chars].rstrip()
```

### Wiring

- `ContextBuilder.__init__` gains `compressor: HistoryCompressor | None = None`
  and a constructor kwarg `compress_on_overflow: bool = False`.
- During `build()`, after `truncated_count` is finalized: if compressor is
  configured and `compress_on_overflow` is True, call it on the dropped slice,
  wrap the returned summary as:
  ```python
  Message(role="system", content=f"[PRIOR CONTEXT SUMMARY]\n{summary}")
  ```
  and insert it right after the last `effective_*_prefix` block (i.e. it
  becomes part of the effective system prompt for this turn only — it does
  NOT get persisted to the messages table).
- If the dropped slice is empty or the compressor returns empty, no splice.
- Count the summary's tokens; if it would push the final build back over
  budget, drop one more real message from the tail of included history and
  retry once. If still over, fall back to no-compression.

### Tests

- `tests/unit/test_context_compressor.py`: empty dropped list, happy path,
  inference error fallback, oversize truncation.
- `tests/unit/test_context_builder_compression.py`: ContextBuilder with and
  without compressor; assert summary appears in final messages when enabled
  and absent when disabled.

### Commit

`feat(context): optional history compressor for overflow recovery`

---

## §3 — Raise `ContextTooLargeError` on protected-block overflow

### Problem

Today when `protected_count > raw_budget`, `ContextBuilder.build` returns a
best-effort `[system, new_user]` with `truncated_count=len(history)` and no
error. The orchestrator and platform adapter carry on normally, so the
operator never finds out their context is broken.

### Code sketch

**File:** `src/hestia/context/builder.py`

Replace the current best-effort branch with:

```python
if protected_count > raw_budget:
    raise ContextTooLargeError(
        f"Protected context ({protected_count} tokens) exceeds per-slot budget "
        f"({raw_budget}). System+identity+memory_epoch+skill_index+new_user is "
        "too large to fit. Reduce identity, memory_epoch, or run /reset."
    )
```

Import from `hestia.errors`.

**File:** `src/hestia/orchestrator/engine.py`

Wrap the `await self._builder.build(...)` calls in `try/except
ContextTooLargeError as exc:` and:

1. Record a `FailureRecord` with `failure_class = CONTEXT_OVERFLOW`.
2. Transition the turn to `FAILED`.
3. Return a synthetic response to the platform adapter via `response_callback`
   with the user-visible message:
   ```
   ⚠️ This session has grown past my context budget
   ({raw_budget:,} tokens per slot). I've saved a summary of our conversation.
   Type /reset to start fresh, and I'll keep the summary for reference.
   ```
4. Kick off the handoff summarizer (§1) against the current history before the
   forced reset so no context is lost.

Also raise on "protected fits but absolutely nothing from history does AND
compression returned empty" — this is a subtler near-overflow the user can
act on.

### Tests

- `tests/unit/test_context_builder.py`: new test case
  `test_protected_overflow_raises`.
- `tests/integration/test_orchestrator_context_overflow.py`: end-to-end — force
  a session that triggers the error, assert the failure record lands, the
  response callback is called with the expected message, and the handoff
  summary exists in memory afterward.

### Commit

`feat(context): raise ContextTooLargeError and surface via platform adapters`

---

## §4 — Config: `HandoffConfig` + `CompressionConfig`, wiring through `TrustConfig`

### Code sketch

**File:** `src/hestia/config.py`

```python
@dataclass
class HandoffConfig:
    """Controls session-close summary generation."""
    enabled: bool = False
    min_messages: int = 4      # skip very short sessions
    max_chars: int = 350


@dataclass
class CompressionConfig:
    """Controls in-turn history compression on overflow."""
    enabled: bool = False
    max_chars: int = 400


@dataclass
class HestiaConfig:
    # … existing fields …
    handoff: HandoffConfig = field(default_factory=HandoffConfig)
    compression: CompressionConfig = field(default_factory=CompressionConfig)
```

**File:** `src/hestia/config.py` — also extend the preset constructors:

```python
TrustConfig.paranoid()    # handoff=False, compression=False (unchanged)
TrustConfig.household()   # handoff=True,  compression=True
TrustConfig.developer()   # handoff=True,  compression=True
```

Note: TrustConfig stays as-is (it's capability-focused); the presets only
*imply* handoff/compression. Implementation: `HestiaConfig.for_trust(trust)`
helper that populates handoff / compression from the trust preset if the
operator hasn't explicitly set them.

### Tests

- `tests/unit/test_handoff_config.py`, `test_compression_config.py`
- Extend `test_trust_config.py` to verify the preset→config mapping.

### Commit

`feat(config): HandoffConfig and CompressionConfig with trust presets`

---

## §5 — Platform adapter: overflow warning formatting

### Code sketch

**File:** `src/hestia/platforms/base.py`

Add an abstract `send_system_warning(self, text: str) -> Awaitable[None]`.
Default impl in each adapter just prepends ⚠️.

**Files:** `src/hestia/platforms/telegram_adapter.py`,
`src/hestia/platforms/matrix_adapter.py`, `src/hestia/platforms/cli_adapter.py`.

The overflow path in §3 calls `await platform.send_system_warning(msg)`
instead of routing through the normal response path, so it's visibly distinct.

### Tests

Adapter-level unit tests for each platform: assert the warning is dispatched
with the expected prefix and formatting.

### Commit

`feat(platforms): system-warning channel for context overflow`

---

## §6 — Docs

- Add a new section to `README.md` → "Context budget and long sessions"
  explaining the three tiers (per-slot ctx, protected block, history), how
  compression and handoff interact, and how to enable them.
- Update `docs/runtime-feature-testing.md` with a scripted test:
  force a long session via `scripts/force_long_session.py` (new) and verify
  the warning fires at the right token threshold.
- Add an ADR: `docs/development-process/decisions/ADR-0014-context-resilience.md`
  documenting the design choices — why compression is per-turn not global, why
  handoff is a memory entry not a separate table, why `ContextTooLargeError`
  is now raised.

### Commit

`docs: context resilience & handoff summaries`

---

## §7 — Version bump and changelog

1. Bump `pyproject.toml` version from `0.3.0` → `0.4.0`.
2. Run `uv lock` and commit the resulting `uv.lock` in the **same commit** as
   the version bump (not a follow-up).
3. Update `CHANGELOG.md` under `## [Unreleased]` → move to `## [0.4.0]`:

```
### Added
- `HandoffConfig` controls automatic session-close summaries.
- `CompressionConfig` enables `HistoryCompressor` to splice summaries of
  dropped history into context when the budget is tight.
- `send_system_warning` on `Platform` ABC for out-of-band operator messaging.

### Changed
- `ContextBuilder.build` raises `ContextTooLargeError` when protected context
  exceeds budget instead of silently best-efforting.
- `TrustConfig.household()` / `developer()` now imply handoff and compression.

### Fixed
- (none — no prior regressions)
```

### Commit

`chore: bump version to 0.4.0`

---

## §8 — Handoff report

Create `docs/handoffs/L21-context-resilience-handoff.md`:

- What shipped (§1-§7).
- Test counts before and after.
- Any blockers or deferred items.
- Confirmation that the four post-loop checks (§0) passed.

### Commit

`docs: L21 handoff report`

---

## Critical rules recap

- Branch off `develop`, never `main`.
- One commit per section (except §7 where version bump + `uv.lock` is one).
- No new `ruff` or `mypy` regressions — diff both against baseline before
  claiming done. L22 will drive the count to zero; L21 just must not grow it.
- `.kimi-done` must contain `HESTIA_KIMI_DONE=1` and `LOOP=L21`.
- All new public APIs (`HistoryCompressor`, `SessionHandoffSummarizer`,
  `HandoffConfig`, `CompressionConfig`) get docstrings with example usage.
- Keep the default behavior identical to v0.3.0 for installs that don't opt in.

## Post-loop self-check

Before writing `.kimi-done`, Kimi must verify:

- [ ] `git status --short` is empty.
- [ ] `uv run pytest tests/unit/ tests/integration/ -q` is green.
- [ ] `uv run ruff check src/ tests/` count ≤ 166.
- [ ] `uv run mypy src/hestia` count ≤ 44.
- [ ] New unit tests cover §1, §2, §3, §4, §5.
- [ ] `CHANGELOG.md`, `pyproject.toml`, `uv.lock` all bumped to 0.4.0.
- [ ] Handoff report written.
