# ADR-018: Reflection loop architecture

## Status

Accepted

## Context

Hestia accumulates structured traces (turns, tool chains, outcomes) in `TraceStore` and long-term notes in `MemoryStore`. This data is valuable for identifying patterns that could improve the assistant's behavior, but until now it has been entirely passive — useful only if an operator manually reviews it.

The question is: how can Hestia turn this passive data into actionable, review-gated improvements without violating the operator-trust boundary?

## Decision

Implement a **three-pass reflection pipeline** that runs during idle hours, generates structured proposals, and queues them for explicit operator review. Proposals are **never auto-applied**.

### Three-pass design

1. **Pattern mining** (`ReflectionRunner._mine_patterns`)
   - Reads the last N traces from `TraceStore`.
   - Sends them to the inference model with a specialized system prompt focused on analysis.
   - Extracts structured observations under categories: `frustration | correction | slow_turn | repeated_chain | tool_failure`.

2. **Proposal generation** (`ReflectionRunner._generate_proposals`)
   - Feeds observations back to the model with a proposal-focused system prompt.
   - Output is a list of structured proposals, each with `type`, `summary`, `evidence` (turn IDs), `action` payload, and `confidence`.

3. **Queue write** (`ReflectionRunner.run`)
   - Persists each proposal to `ProposalStore` with `status="pending"` and an expiry timestamp.
   - Prunes expired proposals as a side effect.

### Proposal lifecycle

```
pending → accepted | rejected | deferred
   ↓
expired (after expire_days, auto-pruned)
```

- `accepted`: Operator agrees; action may be applied manually (dry-run first).
- `rejected`: Operator disagrees; review note is stored for future learning.
- `deferred`: Operator wants to revisit later.
- `expired`: Auto-pruned after `expire_days` if still pending.

### Storage

A dedicated `proposals` table (raw SQLite DDL, consistent with `TraceStore` and `FailureStore`) rather than abusing the FTS5 memory table. This gives us:
- Typed columns for filtering by status, type, and expiry.
- Indexed queries for `pending_count()` and `list_by_status()`.
- No FTS5 schema-migration headaches.

### Scheduler integration

`ReflectionScheduler` is a lightweight checker (not a full scheduler engine) that:
- Evaluates the configured cron expression.
- Checks whether any session was active within `idle_minutes`.
- Calls `ReflectionRunner.run()` only when both conditions pass.

It is invoked from the main scheduler daemon loop (`schedule_daemon` in `cli.py`).

### Session-start hook

When `Orchestrator.process_turn()` detects that a session has no prior history (first turn) and `ProposalStore.pending_count() > 0`, it prepends a system note to the effective system prompt. The note instructs the model to summarize the top 3 pending proposals and ask the user whether to accept/reject/defer. The note is only injected once per session.

### Guardrails

- `enabled: False` by default (opt-in).
- `proposals_per_run: 5` cap to avoid overwhelming the operator.
- Reflection system prompt explicitly instructs conservative proposals backed by multi-turn evidence.
- No proposal action is ever executed automatically; all require explicit CLI acceptance.

## Consequences

### Positive

- Hestia can improve between sessions without being told how.
- Proposals are grounded in actual conversation traces, not hallucinated improvements.
- Operator retains full control over what changes are applied.
- The architecture is extensible: new observation categories and proposal types can be added without changing the storage schema.

### Negative

- Each reflection run costs 2–3 inference calls during idle time (negligible on consumer GPUs, but not zero).
- False positives are possible; the model may propose changes that aren't genuinely useful. The `expire_days` limit and operator review gate mitigate this.
- The session-start note consumes a small amount of the context budget on the first turn when pending proposals exist.

## Related

- `src/hestia/reflection/runner.py`
- `src/hestia/reflection/store.py`
- `src/hestia/reflection/scheduler.py`
- `src/hestia/reflection/types.py`
- `docs/guides/reflection-tuning.md`
