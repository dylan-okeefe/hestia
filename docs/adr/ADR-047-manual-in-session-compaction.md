# ADR-047: Manual in-session compaction with `/compact`

- **Status:** Accepted
- **Date:** 2026-06-19
- **Context:** Long-running agentic sessions (e.g., job-search assistance) accumulate hundreds of messages and large tool results. The existing context builder truncates history per turn, but the remaining prompt can still be large enough that the local model spends more than 120 seconds on prompt processing before emitting any token, causing streaming timeouts and turn failures. Handoff summaries already provide session-close compaction, but there is no way for a user to compact an active session without ending it.
- **Decision:** Add a user-invoked `/compact` meta-command that compacts the current session in place.
  1. **Persistence model:** `/compact` durably replaces the active session history with a task-aware summary plus the last K turns verbatim, and archives the original messages as a pre-compaction recoverable snapshot. It never hard-deletes history.
  2. **Verbatim window:** Keep a token-aware tail of roughly the last 4-6 turns verbatim so the immediate conversational context survives compaction.
  3. **Task-aware summary:** The compaction summary uses a structured task-state template (goal, criteria, progress/done, pending, key findings, artifact paths) rather than generic prose, so long agentic tasks retain their criteria and references.
  4. **Narrow memory flush:** In the same summarization pass, write the structured task-state fields to long-term memory with deduplication against existing entries. The flush is narrow: it does not perform a general "extract any interesting fact" pass.
  5. **Write-time memory filter:** A sanitizer at the shared memory-store write boundary rejects or strips junk before storage (tool-call XML, unclosed tags, raw assistant/tool turn dumps, trivially low-value content). This applies to all memory writes, including the compaction flush.
  6. **Safety:** `/compact` acquires the per-session lock, shows a "compacting..." in-flight state, and erases the session's KV slot afterward so the next turn rebuilds cold from the smaller history.
  7. **User steering:** `/compact <instruction>` (e.g., "keep the job criteria") steers what the summary preserves. Plain `/compact` uses the default task-aware behavior.
- **Consequences:**
  - **Recoverable:** Original messages are archived and recoverable, not destroyed.
  - **Slot cold-start:** The next turn after compaction pays a one-time KV-cache rebuild cost, but subsequent turns are faster because the history is smaller.
  - **Memory quality:** The write-time filter fixes the root cause of junk memories observed in the 2026-06-16 UX review and benefits all memory writers, not just compaction.
  - **Scope limitation:** Overnight memory deduplication/pruning is explicitly deferred to a separate loop because it is destructive and needs its own decision pass.
  - **Reuses existing machinery:** The implementation reuses the session summarizer / handoff service, the per-session lock, and the L221 non-DONE slot-erase path rather than building a parallel compactor.
