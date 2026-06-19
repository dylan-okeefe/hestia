# Decisions — manual /compact command

**Status:** Resolved 2026-06-16. Implement against these.

1. **Persistence model.** Persistent + archive. `/compact` durably replaces the active session history with [task-aware summary + the last K turns verbatim] and archives the original messages (marked pre-compaction, recoverable, not deleted). The next turn rebuilds COLD from the smaller history.

2. **Verbatim window.** Keep the last K turns verbatim (configurable; default a token-aware tail of roughly the last 4-6 turns) and summarize everything older.

3. **Task-aware summary.** The compaction summary uses a structured task-state template, not a generic prose recap: goal, criteria, progress/what's done, what's pending, key findings, and artifact paths. This is the make-or-break for long agentic tasks (job search); a generic recap that loses criteria or the resume path is worse than useless.

4. **Memory flush (narrow).** Yes, but narrow and in the same summarization pass. Write only the structured task-state fields from #3 to the memory store, with dedup against existing entries. Do NOT do a general "extract any interesting fact" pass. Rationale: the compaction summary degrades over repeated compactions (summary-of-summary drift), so the handful of facts that matter need to live in durable memory; reusing the one summarization call avoids extra latency, and the narrow scope avoids the memory-pollution problem seen in the UX review.

5. **v1 scope.** Include the focus argument: `/compact <instruction>` (e.g. "keep the job criteria") steers what the summary preserves. Plain `/compact` uses the default task-aware behavior.

6. **Write-time memory filter (companion).** Add a sanitizer/validator at the shared memory-store write boundary that rejects or strips junk before it is stored: tool-call XML (`<tool_call>...`), unclosed tags, raw assistant/tool turn dumps, and trivially low-value content. This applies to ALL memory writes (the agent's `memory_write`, the reflection loop, and the compaction flush), and is the root-cause fix for the junk memories observed in the 2026-06-16 UX review. The compaction flush depends on it for quality.

7. **Correctness (baked in, not optional).** `/compact` takes the per-session lock (it mutates the session), erases the KV slot afterward so the next turn rebuilds COLD, and shows a "compacting..." loading state since it costs one LLM call on slow local hardware.

## Related, deferred to its own loop
- **Overnight memory dedupe / pruning.** Destructive, so it needs its own decision pass: dedup-by-merge vs delete, soft-delete/archive vs hard removal, never touching pinned/high-value memories, and an auditable/reversible run. Not part of this loop.
