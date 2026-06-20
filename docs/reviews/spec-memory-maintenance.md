# Spec — overnight memory maintenance

**Status:** Spec ready. Decisions resolved in `docs/reviews/decisions-memory-maintenance.md`.
**Loop:** assign the next free L-number when queued (avoid collision with in-flight loops on the dev box).
**Branch:** off `develop`.

## Goal

Scheduled maintenance that keeps the memory store clean and accurate over time: dedup near-identical memories, remove junk and orphans, and resolve contradictions (newer fact supersedes older), without losing real facts. Reuses the scheduler (ADR-027), the memory store (ADR-029), the soft-delete pattern, and the digest surface from the blocked-actions work.

## Scope

### §1 — Deterministic pass (frequent)
- Dedup by normalized-text exact match and high-overlap FTS similarity; merge duplicates (keep richer/newer, fold unique tags, soft-delete loser) (decisions #1, #2).
- Remove clear junk that slipped the write-time filter and orphaned/unscoped memories that can never be recalled (decision #3).
- Deterministic only; no LLM call.

### §2 — LLM-assisted pass (infrequent)
- Near-duplicate (paraphrase) merge.
- Contradiction/supersession: detect same-attribute conflicts, newer wins, soft-delete the older with a "superseded by X" note. Confidence-gated; keep both when unsure it's the same attribute (decision #4). Record reasoning in the trace.

### §3 — Soft-delete + retention
- All removals are soft-delete (mark inactive, recoverable) with a retention window; never hard-delete on the unattended run (decision #6).

### §4 — Protected set
- Exempt user-authored memories (Profile Notes), pinned memories, and recently-recalled ones from any merge/prune/supersede (decision #6).

### §5 — Trace + digest
- Record every merge, prune, and supersession (what, why, recoverable-until).
- Emit a periodic maintenance digest reusing the blocked-actions digest surface, with supersessions surfaced prominently. Provide an undo path from the trace (decisions #5, #6).

### §6 — Schedule wiring
- Scheduler tasks for the two cadences (deterministic frequent, LLM-assisted infrequent), times/frequencies configurable (decision #7).

## Tests
- Exact and high-overlap duplicates merge (richer/newer kept, loser soft-deleted).
- Junk and orphaned/unscoped memories are removed; valid old facts are not.
- A same-attribute contradiction supersedes newer-wins, is recoverable, and is logged; two genuinely separate facts are both kept.
- Protected memories (user-authored, pinned, recently-recalled) are never touched.
- Every change is soft-delete, not hard-delete; the digest lists all actions with supersessions highlighted.

## Acceptance
- Gates green (pytest, mypy, ruff, web-ui build if touched).
- `.kimi-done` includes the assigned loop number.
- Manual: seed duplicate + contradictory + junk memories, run both passes, confirm correct merge/prune/supersede with a clean digest and working undo.

## Related
- Complements the `/compact` write-time memory filter (prevents new junk; this cleans existing memory).
- Warrants its own ADR (automated destructive memory maintenance), and parallels the `consolidate-memory` skill pattern.

## Critical rules
- Do not merge or push without Dylan's okay.
- Soft-delete only on the unattended run; everything recoverable within the retention window.
- Never touch protected memories.
- The trace/digest must be genuinely reviewable; supersessions front-and-center.
