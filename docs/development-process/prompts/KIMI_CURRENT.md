# Kimi — current task (orchestration pointer)

**Orchestrator:** Kimi (self-orchestrating via subagents)
**Last set by:** Kimi — 2026-06-19

---

## Current task

**Status:** In progress — overnight memory maintenance (dedupe / prune / supersede)
**Decisions:** `docs/reviews/decisions-memory-maintenance.md`
**High-level spec:** `docs/reviews/spec-memory-maintenance.md`

### Queued loops

| Loop | Branch | Status | Focus | Spec |
|------|--------|--------|-------|------|
| **L226** | `feature/l226-memory-soft-delete-protected` | **Pending** | Add soft-delete + retention columns and protected-set flags to `MemoryStore`. | `docs/development-process/loops/L226-memory-maintenance-soft-delete-protected-set.md` |
| **L227** | `feature/l227-memory-deterministic-dedupe` | **Pending** | Deterministic dedupe: exact normalized match + high-overlap FTS merge. | `docs/development-process/loops/L227-memory-maintenance-deterministic-dedupe.md` |
| **L228** | `feature/l228-memory-deterministic-prune` | **Pending** | Deterministic prune: junk and orphaned/unscoped removal. | `docs/development-process/loops/L228-memory-maintenance-deterministic-prune.md` |
| **L229** | `feature/l229-memory-llm-near-duplicate-merge` | **Pending** | LLM-assisted paraphrase/near-duplicate merge. | `docs/development-process/loops/L229-memory-maintenance-llm-near-duplicate-merge.md` |
| **L230** | `feature/l230-memory-contradiction-supersession` | **Pending** | LLM-assisted contradiction detection + supersession. | `docs/development-process/loops/L230-memory-maintenance-contradiction-supersession.md` |
| **L231** | `feature/l231-memory-trace-digest-scheduler` | **Pending** | Trace every action, emit digest, wire cadences to scheduler. | `docs/development-process/loops/L231-memory-maintenance-trace-digest-scheduler.md` |

### Execution order

1. **L226** — foundation: soft-delete + protected set.
2. **L227** — deterministic dedupe (depends on L226).
3. **L228** — deterministic prune (depends on L226).
4. **L229** — LLM near-duplicate merge (depends on L226–L228).
5. **L230** — contradiction/supersession (depends on L226–L228).
6. **L231** — trace + digest + scheduler wiring (depends on L226–L230).

### Acceptance for the arc

- Gates green after every loop.
- Manual: seed duplicate + contradictory + junk memories, run both passes, confirm correct merge/prune/supersede with a clean digest and working undo.
- `.kimi-done` includes all loop numbers.
- Do not merge without Dylan's okay.
