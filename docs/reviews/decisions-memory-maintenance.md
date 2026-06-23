# Decisions — overnight memory maintenance (dedupe / prune / supersede)

**Status:** Resolved 2026-06-16. Implement against these.

1. **Two-tier detection cadence.** A frequent, cheap deterministic pass plus a less-frequent LLM-assisted pass.
   - Deterministic (frequent): normalized-text exact match and high-overlap FTS dedup; junk and orphaned/unscoped removal. No new dependencies; respects ADR-029 (FTS, no vectors).
   - LLM-assisted (infrequent): near-duplicate merge and contradiction/supersession resolution.

2. **Dedup action: merge.** Combine duplicates into one memory, keeping the richer/newer content, folding in unique tags, and soft-deleting the loser. No information loss.

3. **Pruning: conservative.** Remove only clear junk that slipped the write-time filter, orphaned/unscoped memories that can never be recalled, and superseded duplicates. No age- or recall-based pruning, so still-valid old facts (resume path, criteria) stay.

4. **Contradiction / supersession (LLM tier).** Detect when two memories conflict on the same attribute and the newer should win (e.g. "I live in Houston" superseded by "I live in Dallas"). Soft-delete the older with a "superseded by X" note. Only act when confident it is an update to the same attribute, not two genuinely separate facts (e.g. two homes); when unsure, keep both.

5. **Autonomy: fully automatic.** Safe because every change is soft-delete + retention + a reviewable trace, so "automatic" is not irreversible. Not gated behind proposals; the digest plus an easy undo is sufficient.

6. **Safety (baked in).**
   - Soft-delete with a retention window; never hard-delete on the unattended run.
   - Exempt user-authored memories (Profile Notes), pinned memories, and recently-recalled ones.
   - Emit a periodic maintenance digest (same surface as blocked-actions) recording every merge, prune, and supersession, with supersessions surfaced prominently since overwriting a fact is the riskiest auto-decision. Provide an easy undo from the trace.

7. **Schedule.** Run via the scheduler (ADR-027) at quiet overnight hours, configurable. Deterministic pass frequent (e.g. nightly); LLM-assisted pass less frequent (e.g. weekly).

## Dependency
- The write-time memory filter from the `/compact` loop is the complement: that prevents new junk at write time, this cleans existing memory. This loop can assume the filter exists or include a minimal fallback.
