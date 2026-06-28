# Long-Term Memory

Hestia keeps a long-term memory of durable facts about you (preferences,
criteria, context) in a SQLite FTS5 store. Memories are compiled into a bounded
"memory epoch" that is injected into the system prompt, so the assistant carries
relevant facts across sessions. This guide covers how facts get captured, how
they are kept clean, and how to tune and operate the maintenance system.

## How facts are captured

Three paths write to memory, all through one sanitized boundary:

1. **Proactive capture (primary).** The assistant is instructed to call
   `save_memory` the moment you correct it, change a preference, or state a
   durable fact (location filters, scheduling rules, what to include or exclude).
   This is the main, fact-level path, and it is why corrections survive
   compaction and new sessions.
2. **Session-end fact extraction.** When a session is archived, Hestia extracts
   structured task-state facts (goal, criteria, progress, findings, artifact
   paths) via the compaction summarizer and stores them. It skips trivial
   sessions (below `min_messages`), dedupes against existing memories, and the
   same summary is reused for the next session's handoff, so there is exactly one
   summarization per archive. This is a backstop for whatever the proactive path
   missed, not a transcript dump.
3. **Manual `/compact`.** Compacting a session in place (see
   [chat commands](chat-commands.md)) flushes the same narrow task-state fields to
   memory.

### Write-time sanitizer

Every write passes a sanitizer at the store boundary that rejects junk before it
is stored: tool-call XML, unclosed tags, raw assistant/tool turn dumps, and
trivially low-value content. This prevents the noise that would otherwise
accumulate from automated writers.

## Overnight memory maintenance

A scheduled subsystem keeps memory clean and accurate over time. It is
reversible by construction: nothing is hard-deleted on the unattended run, every
removal is a soft-delete with a retention window, and every action is logged with
an undo deadline.

Two cadences:

- **Nightly deterministic pass** — merges exact and high-overlap duplicates
  (keeping the richer/newer copy) and prunes junk and orphaned/unscoped memories.
  Conservative: no age- or recall-based removal.
- **Weekly LLM-assisted pass** — merges paraphrase near-duplicates, and resolves
  contradictions by superseding the older fact with the newer one when it is
  confident they describe the same attribute (e.g. "I live in Houston" superseded
  by "I live in Dallas"). When unsure, it keeps both.

A **protected set** is never touched: user-authored memories (your Profile
notes), pinned memories, and recently-recalled ones. Each run produces an
operator digest (sharing the blocked-actions digest surface) that highlights
supersessions, since overwriting one fact with another is the riskiest decision.

### Operating it

```bash
# Register the nightly + weekly maintenance tasks for an identity
hestia memory maintenance ensure-tasks --platform telegram --user <id>

# Undo a maintenance action (within the undo retention window)
hestia memory maintenance undo <action-id>
```

Action ids and the reasoning behind each merge/prune/supersede appear in the
maintenance digest and trace.

## Tuning

See [environment variables](environment-variables.md) for the full reference. Key
knobs:

| Variable | Default | Purpose |
|----------|---------|---------|
| `HESTIA_MEMORY_RETENTION_DAYS` | `30` | How long soft-deleted memories are kept before hard-delete. |
| `HESTIA_MEMORY_RECENTLY_RECALLED_DAYS` | `7` | Protection window for recently-recalled memories. |
| `HESTIA_MEMORY_LLM_DEDUPE_CONFIDENCE_THRESHOLD` | `0.8` | Minimum confidence to merge near-duplicates. |
| `HESTIA_MEMORY_CONTRADICTION_CONFIDENCE_THRESHOLD` | `0.8` | Minimum confidence to supersede a contradicting fact. |
| `HESTIA_MEMORY_MAINTENANCE_DETERMINISTIC_CRON` | `0 3 * * *` | Nightly deterministic pass schedule. |
| `HESTIA_MEMORY_MAINTENANCE_LLM_CRON` | `0 4 * * 0` | Weekly LLM pass schedule. |
| `HESTIA_MEMORY_MAINTENANCE_UNDO_RETENTION_DAYS` | `7` | Window to undo a maintenance action. |

## Related

- [Chat commands](chat-commands.md) — `/compact` and other in-session commands.
- ADR-029 (FTS, not vectors), ADR-047 (compaction + sanitizer), ADR-048 (fact
  extraction), ADR-049 (memory maintenance).
