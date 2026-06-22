# ADR-048: Session-end fact extraction and proactive memory capture

- **Status:** Accepted
- **Date:** 2026-06-22
- **Context:** Durable facts a user states during a session (corrections,
  preferences, task criteria) need to survive compaction and new sessions.
  Previously, archiving a session only produced a handoff summary for the next
  session; nothing extracted durable facts into long-term memory, and after the
  store split (ADR-040) the summarization-on-archive responsibility was
  ambiguously split between `SessionStore` and `HandoffService` (L158).

- **Decision:**
  1. **Proactive capture (prompt rule):** a system-prompt rule instructs the
     agent to call `save_memory` immediately when the user corrects it, changes
     a preference, or states a durable fact. This is the primary, fact-level
     capture path during the session.
  2. **Archive-time extraction:** `SessionStore.archive_session` runs structured
     task-state extraction via `SessionCompactionSummarizer` (reusing the
     `/compact` summarizer from ADR-047), gated on `min_messages` to skip trivial
     sessions, and writing only structured fields (goal, criteria, progress,
     findings, artifacts). It is best-effort and never blocks archival.
  3. **Single summarization:** `archive_session` returns the summary, and
     `HandoffService` reuses it to build the next-session handoff message. So
     there is exactly one summarization per archive and the handoff-into-next-
     session continuity is preserved. The independent `SessionHandoffSummarizer`
     / `handoff_summarizer` path was removed.

- **Consequences:**
  - Corrections and durable facts survive compaction and new sessions.
  - One summarization per archive (no double LLM call), and the archive-save is a
    deduped fallback to the proactive saves rather than a second full pass.
  - Saved content is structured facts (not a transcript dump) and passes the
    write-time sanitizer (ADR-047).
  - The archive dedup is exact-content match, so semantic overlap between
    proactively-saved facts and archive-extracted facts is left for the overnight
    memory-maintenance pass (ADR-049) to reconcile.

- **Related:** ADR-040, ADR-047, ADR-049, ADR-022, ADR-023;
  `persistence/session_store.py`, `orchestrator/handoff_service.py`.
