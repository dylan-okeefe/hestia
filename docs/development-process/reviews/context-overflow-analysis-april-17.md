# Context-length overflow — findings & recommendations

**Date:** April 17, 2026
**Trigger:** Dylan ran a Matrix "post-merge check" and saw the bot reply:

> ⚠️ Context length exceeded (15,228 tokens). Cannot compress further.

This document separates what actually happened from what *would* happen in Hestia
today, and proposes the fix that belongs in the next loop (L21).

---

## 1. Where the error came from

That exact message is **not** produced anywhere in the Hestia codebase. A full-repo
grep for "Cannot compress further", "Context length exceeded", and related strings
returns zero matches in `src/hestia/`.

The message is produced by **Hermes / Silas** at
`~/.hermes/hermes-agent/run_agent.py:7833`:

```python
"error": f"Context length exceeded ({approx_tokens:,} tokens). Cannot compress further.",
```

Hermes's gateway log (`~/.hermes/logs/gateway.log.1`) shows the full pattern:

```
⚠️  Context length exceeded — stepping down: 28,672 → 16,000 tokens
⚠️  Context length exceeded — stepping down: 16,000 → 8,000 tokens
⚠️  Context length exceeded at minimum tier — attempting compression...
❌ Context length exceeded and cannot compress further.
```

So Silas has a multi-tier "shrink ctx → retry → compress → give up" loop, and
what Dylan saw was Silas exhausting it. Hestia and Silas share the same
`llama-server` instance (which runs `--ctx-size 49152 --parallel 3`, so
16 K per slot); when a Silas slot's conversation grows past ~15 K, Silas fails
with that message while Hestia is untouched.

**Bottom line: the reported error is a Hermes symptom, not a Hestia bug.** But
it exposes a real gap in Hestia's own design.

---

## 2. What Hestia does today when budget is tight

`src/hestia/context/builder.py` (`ContextBuilder.build`):

1. Compute `raw_budget = policy.turn_token_budget(session)` (default 8 K, bumped
   to 16 K in `config.runtime.py` per L19).
2. Assemble **protected top** (system + identity + memory epoch + skill index +
   first user message) and **protected bottom** (new user message).
3. If even those exceed budget, return a best-effort with *just* `[system,
   new_user]` and `truncated_count = len(history)`.
4. Otherwise walk history newest→oldest, adding messages until the next one
   would overflow, then stop and record `truncated_count`.

`src/hestia/core/inference.py::_strip_historical_reasoning` already removes
`reasoning_content` from every message before a request, so `<think>` blocks do
not re-accumulate across turns.

### What's missing

- No **compression** or **summarization** of dropped history. Once messages fall
  out of the window, the model has amnesia with no breadcrumb.
- No **user-visible signal** when `truncated_count > 0` or when the protected
  block itself doesn't fit. The platform adapters just send whatever the model
  produced under the reduced context.
- No **session handoff summary** (brainstorm §6). Each new session begins with
  only identity + memory epoch; anything the operator discussed yesterday that
  wasn't explicitly `save_memory`'d is gone.
- `ContextTooLargeError` is declared in `src/hestia/errors.py` but never raised
  or caught anywhere.

### What *would* happen if a single Hestia slot grew past its per-slot budget

If `identity + memory_epoch + skill_index + first_user + new_user` ≥ `raw_budget`,
`ContextBuilder.build` returns the best-effort `[system, new_user]` pair. The
inference call still happens — with no history, possibly degraded answers.
`llama-server` can also refuse the request independently if the server-side
tokenized prompt exceeds its slot `--ctx-size`, which returns a 4xx from
`/v1/chat/completions` and bubbles up as `InferenceServerError` in Hestia. In
that case the user sees `⚠️ Error: <raw error>` via the Matrix/Telegram adapter.
No graceful compression, no retry, no summary preserved.

---

## 3. Recommended fix (scoped for L21)

### 3a. Session handoff summaries (cheap, highest ROI)

At the end of each session (`/reset`, explicit close, or scheduler eviction to
`COLD`), run one inference call with a short system prompt:

> "Summarize this session in 2–3 sentences focused on decisions, outcomes, and
> anything still pending. No pleasantries."

Store the result as a `MemoryRecord` with `type="session_handoff"`,
`session_id=<closed session id>`, `tags=["handoff", <platform>]`. The context
builder's memory-epoch compilation already consumes the memory store, so these
summaries automatically seed future sessions without any new injection point.

**Cost:** 1 short inference per session close. **Impact:** cross-session
continuity without raw-history rehydration.

### 3b. History-window compression fallback

Extend `ContextBuilder` with an optional `compressor: HistoryCompressor | None`.
When `truncated_count > 0`, and before committing the best-effort result,
call `compressor.summarize(dropped_messages)` and splice the returned system
note in as a single protected message right after the memory epoch:

> `[PRIOR CONTEXT SUMMARY] <summary>`

Implementation detail: the compressor itself is a small inference call; guard
it with a timeout and fall back to pure truncation if it fails. The
`HistoryCompressor` protocol lives in `src/hestia/context/compressor.py`; the
default implementation reuses the existing `InferenceClient` with a dedicated
system prompt and a strict `max_tokens` cap (e.g. 400). Policy decides whether
to use it via a new `ctx.compress_on_overflow` flag (default True for
household/developer trust, False for paranoid).

### 3c. Loud overflow signal

When `ContextBuilder.build` drops even the protected block, raise
`ContextTooLargeError` instead of silently returning best-effort. `Orchestrator`
catches it, records a `FailureClass.CONTEXT_OVERFLOW` failure, and asks the
platform adapter to send a user-visible message:

> "⚠️ Your session is at the context limit (X tokens, budget Y). I've summarized
> the earlier part of the conversation and kept the last N turns. Type `/reset`
> to start fresh."

This puts the operator in control instead of hiding the degradation.

### 3d. Scheduled session cleanup

The scheduler already supports cron tasks. Add a default `session_compactor`
task (disabled by default; enabled by `trust.household()` or explicit config)
that runs nightly: for sessions inactive > N days, generate the handoff
summary (§3a) if not already present, then archive the raw history to a
separate `messages_archive` table and leave only the summary + last K messages
live. Keeps the active slot small without losing retrievable history.

---

## 4. Out of scope for L21 (future loops)

- **Multi-tier ctx stepping (à la Hermes):** Hestia uses one slot per session, so
  stepping slot ctx down dynamically would require `llama-server` support we
  don't have. Not worth copying.
- **Semantic memory recall on each turn:** lazy pre-loading of relevant memories
  into protected_top (MemPalace-style L2) is separately valuable but belongs in
  a memory-focused loop, not the context-resilience loop.
- **Prompt injection detection on tool results (brainstorm §2a):** also
  separate — tracked for L24.

---

## 5. Acceptance criteria for L21

1. Session handoff summaries are generated on session close and live in the
   memory store with retrievable tags.
2. `ContextBuilder` grows an optional compressor; when wired and triggered,
   dropped history appears as a single summary message in the next build.
3. `ContextTooLargeError` is raised when the protected block exceeds budget,
   and the Matrix/Telegram adapters send a user-visible warning including the
   numbers.
4. New unit tests: handoff summary creation, compressor splice, protected-block
   overflow error path, and the platform warning format.
5. Opt-in via `TrustConfig` / `InferenceConfig`, not forced on existing
   installs.
