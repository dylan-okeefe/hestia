# ADR-0014: Context resilience — compression, handoff summaries, and overflow signals

## Status

Accepted

## Context

Three gaps in Hestia's context handling were identified during the L21 review:

1. **No session handoff summaries:** Every new session starts with only identity +
   memory epoch; yesterday's thread is lost unless the model explicitly saved it.
2. **No history compression:** When `ContextBuilder` drops oldest messages to fit
   the budget, they are silently discarded with no breadcrumb.
3. **No user-visible overflow signal:** If protected messages alone exceed budget,
   `ContextBuilder` returns a best-effort `[system, new_user]` pair and carries on.
   The operator never finds out.

## Decision

### 1. Compression is per-turn, not global

`HistoryCompressor` is called on the dropped slice during `ContextBuilder.build()`
and the summary is spliced into the effective system prompt for that turn only.
It is **not** persisted to the messages table.

Rationale: Global compression would mutate history, making it hard to reason about
what the model actually saw. Per-turn compression is a transient optimization —
if the summary is bad, the next turn gets a fresh chance.

### 2. Handoff is a memory entry, not a separate table

`SessionHandoffSummarizer` generates a 2-3 sentence summary on session close and
stores it via `MemoryStore.save()` with tags `["handoff", <platform>]`.

Rationale: Re-using the existing memory system means handoff summaries are
automatically searchable, tagged, and subject to the same TTL/gc policies as
other memories. A separate table would require new indexing, new search logic,
and new cleanup.

### 3. `ContextTooLargeError` is raised instead of best-efforting

When `protected_count > raw_budget`, `ContextBuilder.build()` now raises
`ContextTooLargeError`. The orchestrator catches it, records a failure bundle,
transitions the turn to `FAILED`, and sends a warning via the platform's
`send_system_warning` channel.

Rationale: Best-efforting silently degraded quality. Raising makes the failure
visible to operators, gives them an actionable message (`/reset`), and triggers
the handoff summarizer so no context is lost.

## Consequences

### Positive

- **Operator visibility:** Context overflow is no longer silent.
- **Continuity:** Handoff summaries let new sessions pick up where old ones left off.
- **Quality:** Compression preserves a breadcrumb of dropped history.

### Negative

- **Extra inference calls:** Both compression and handoff call the model, adding
  latency and token cost.
- **Config complexity:** Two new config sections (`HandoffConfig`,
  `CompressionConfig`) and trust-preset implications.

## Related

- `src/hestia/context/compressor.py`
- `src/hestia/memory/handoff.py`
- `src/hestia/context/builder.py`
- `src/hestia/orchestrator/engine.py`
- `src/hestia/config.py`
