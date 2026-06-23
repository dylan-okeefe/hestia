# Kimi — current task (orchestration pointer)

**Orchestrator:** Kimi (self-orchestrating via subagents)
**Last set by:** Kimi — 2026-06-19

---

## Current task

**Status:** Complete pending Dylan review — overnight memory maintenance (dedupe / prune / supersede)
**Overarching branch:** `feature/memory-maintenance`
**Decisions:** `docs/reviews/decisions-memory-maintenance.md`
**High-level spec:** `docs/reviews/spec-memory-maintenance.md`

### Completed loops

| Loop | Branch | Status | Focus | Spec |
|------|--------|--------|-------|------|
| **L226** | `feature/l226-memory-soft-delete-protected` | ✅ Merged into `feature/memory-maintenance` | Add soft-delete + retention columns and protected-set flags to `MemoryStore`. | `docs/development-process/loops/L226-memory-maintenance-soft-delete-protected-set.md` |
| **L227** | `feature/l227-memory-deterministic-dedupe` | ✅ Merged into `feature/memory-maintenance` | Deterministic dedupe: exact normalized match + high-overlap FTS merge. | `docs/development-process/loops/L227-memory-maintenance-deterministic-dedupe.md` |
| **L228** | `feature/l228-memory-deterministic-prune` | ✅ Merged into `feature/memory-maintenance` | Deterministic prune: junk and orphaned/unscoped removal. | `docs/development-process/loops/L228-memory-maintenance-deterministic-prune.md` |
| **L229** | `feature/l229-memory-llm-near-duplicate-merge` | ✅ Merged into `feature/memory-maintenance` | LLM-assisted paraphrase/near-duplicate merge. | `docs/development-process/loops/L229-memory-maintenance-llm-near-duplicate-merge.md` |
| **L230** | `feature/l230-memory-contradiction-supersession` | ✅ Merged into `feature/memory-maintenance` | LLM-assisted contradiction detection + supersession. | `docs/development-process/loops/L230-memory-maintenance-contradiction-supersession.md` |
| **L231** | `feature/l231-memory-trace-digest-scheduler` | ✅ Merged into `feature/memory-maintenance` | Trace every action, emit digest, wire cadences to scheduler. | `docs/development-process/loops/L231-memory-maintenance-trace-digest-scheduler.md` |

### Quality gates on `feature/memory-maintenance`

- `uv run pytest tests/unit/ -q`: **1969 passed, 1 pre-existing failure** (`test_fetch_url_allows_public_url`)
- `uv run mypy src/hestia`: **0 errors**
- `uv run ruff check src/ tests/`: **61 pre-existing issues**; no new issues introduced by memory-maintenance work

### Next step

Dylan review of `feature/memory-maintenance`; merge into `develop` when approved. Do not merge without Dylan's okay.
