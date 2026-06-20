# Review — feature/l158-fact-extraction (changes required before merge)

**Reviewed:** the two feature commits (`c1e1f00` prompt rule, `a5f3b07` archive-time auto-save) directly, since local develop is stale.
**Verdict:** the prompt rule is good as-is; the archive-time auto-save needs three changes before merge. Failing test first per change, per-item handoff accounting, do not merge without Dylan's okay.

## Keep as-is

- **Prompt rule (`c1e1f00`).** Instructing the agent to `save_memory` on user corrections/preferences/durable facts is the right primary capture mechanism. Verified `save_memory` is the real tool name, so the instruction is valid. No change needed.
- **`b74e5a6`** (guard tool-call fallback parsers against list payloads) is the fix for the recurring `'list' object has no attribute 'get'` error from the 2026-06-16 UX review. Keep.

## Required changes (archive-time auto-save, `a5f3b07`)

### 1. Resolve the handoff / auto-save responsibility split (highest priority — regression risk)
`generate_handoff_summary` calls `archive_session`, which now runs `_auto_save_session_memory` and summarizes; `generate_handoff_summary` also has its own `summarize_and_store` path, currently gated off only because `engine.py` wires the handoff service with `summarizer=None`. Summarization-on-archive is now split between two places, decided by wiring.

Required end state:
- Exactly **one** summarization per archive (no double LLM call, no two near-duplicate memories).
- The **next-session handoff continuity must still work**: confirm the synthetic handoff summary that gets injected into the next session is still produced. The auto-save writes a recalled long-term memory, which is a different mechanism from the handoff message; make sure routing summarization into the auto-save did not silently disable handoff continuity.
- Make the responsibility explicit: one component owns summarization-on-archive and the other reuses its result. Do not leave two independent summarizers gated by which one happens to have a summarizer wired.
- Add a test asserting a single archive produces one summary, the handoff continuity artifact still exists, and there is no duplicate memory write.

### 2. Reshape the saved content to durable facts, gated on substance
Today the auto-save stores `summary + up to 10 raw user-message bullets` on every archived session. That is transcript, not fact; the sanitizer won't catch it (prose, not tool-call XML) and conservative memory-maintenance pruning won't remove it (not clear junk), so it will accumulate low-value entries that dilute recall.
- Drop the raw user-message bullets. Reuse the structured task-state extraction from `memory/compaction_summarizer.py` (goal, criteria, key findings, artifact paths) so what lands in memory is durable facts.
- Gate the save on session substance: skip trivial sessions (e.g. below a minimum message count, or when extraction yields nothing durable).
- Add tests: a substantive session saves structured facts; a trivial session saves nothing.

### 3. Make archive-save a fallback, not a redundant re-summary
With the agent now saving facts proactively during the session (the prompt rule), a full re-summary at archive is partly redundant.
- Dedup the archive-save against existing memories for the session/user so it does not duplicate what was already saved proactively.
- Treat it as a light backstop for what the proactive path missed, not a second full pass.

## Acceptance
- Gates green (pytest, mypy, ruff).
- Per-item handoff accounting: each of the three items mapped to done or explicitly deferred.
- Manual: archive a substantive session, confirm one summary, intact next-session handoff, structured (not transcript) memory, and no duplicate of a proactively-saved fact.
