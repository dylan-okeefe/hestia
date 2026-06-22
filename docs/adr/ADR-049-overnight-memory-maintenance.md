# ADR-049: Overnight memory maintenance (dedupe, prune, supersede)

- **Status:** Accepted
- **Date:** 2026-06-22
- **Context:** Long-term memory accumulates duplicates, junk that slipped past
  capture, and stale or contradicted facts over time. It needs automated hygiene
  that keeps memory clean and accurate without losing real facts. Because the
  operation is destructive, it needs strong, reversible-by-construction safety
  (L226-L231).

- **Decision:** A scheduled `hestia.memory.maintenance` subsystem.
  1. **Two-tier cadence:** a frequent deterministic pass (exact-normalized and
     high-overlap FTS dedupe-merge, plus pruning of junk and orphaned/unscoped
     memories) and an infrequent LLM-assisted pass (paraphrase near-duplicate
     merge, and contradiction resolution).
  2. **Merge, not delete, on duplicates:** keep the richer/newer copy, fold in
     unique tags, soft-delete the loser. Pruning is conservative — junk,
     orphaned/unscoped, and superseded only. No age- or recall-based removal.
  3. **Contradiction/supersession (LLM tier):** when two memories conflict on the
     same attribute, the newer wins. It is confidence-gated (threshold 0.8) and
     keeps both when unsure it is the same attribute. The loser is soft-deleted
     with `superseded_by` set and the reasoning recorded.
  4. **Fully automatic, made safe by construction:** every removal is a
     soft-delete with a retention window (never a hard delete on the unattended
     run); a protected set exempts user-authored, pinned, and recently-recalled
     memories; a trace store records every action with an undo deadline; an
     operator digest (reusing the blocked-actions surface, ADR-044) highlights
     supersessions; and an undo CLI restores any action.
  5. **Scheduling:** scheduler-driven (nightly deterministic, weekly LLM),
     config-driven thresholds and cadences.

- **Consequences:**
  - Memory stays clean and accurate over time, and the run is reversible, which
    is what makes fully-automatic acceptable.
  - Complements the write-time sanitizer (ADR-047): the sanitizer prevents new
    junk, this cleans existing memory.
  - Respects ADR-029 (FTS, not vectors) by combining deterministic matching with
    a bounded LLM pass rather than introducing embeddings.

- **Related:** ADR-029, ADR-044, ADR-047, ADR-027;
  `memory/maintenance/*`, `persistence/maintenance_trace_store.py`,
  `memory/store.py`, `scheduler/engine.py`.
