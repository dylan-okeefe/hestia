# L228 — Memory Maintenance: Deterministic Prune

**Goal:** Implement the frequent deterministic prune pass: remove clear junk and orphaned/unscoped memories that can never be recalled, while keeping valid old facts.

**Branch:** `feature/l228-memory-deterministic-prune`

## §0 — Depends on

Merge `feature/l227-memory-deterministic-dedupe` into `develop` first.

## §1 — Prune engine

Create `src/hestia/memory/maintenance/prune.py`.

Class `DeterministicPruner`:

- `__init__(memory_store: MemoryStore, sanitizer: MemorySanitizer | None = None)`
- `async def run(platform: str | None = None, platform_user: str | None = None) -> PruneResult`

Behavior:

1. Load active memories scoped to the identity if provided; otherwise load all active memories.
2. Skip protected memories.
3. For each candidate, check two deterministic rules:
   - **Junk:** content would be rejected by `MemorySanitizer.sanitize()` (e.g., raw turn dumps, multiple role markers). If rejected, soft-delete with reason="junk".
   - **Orphan / unscoped:** `platform` is NULL OR `platform_user` is NULL OR content is empty after stripping whitespace. Soft-delete with reason="orphan".
4. Return `PruneResult(junk_count, orphan_count)`.

## §2 — MemoryMaintenance service

File: `src/hestia/memory/maintenance/service.py`

Add `async def run_deterministic_prune(self, platform=None, platform_user=None) -> PruneResult`.

## §3 — Tests

File: `tests/unit/memory/maintenance/test_deterministic_prune.py` (create)

- `test_junk_memory_is_pruned`
- `test_unscoped_memory_is_pruned`
- `test_valid_old_fact_is_not_pruned`
- `test_protected_junk_memory_is_not_pruned`
- `test_prune_scopes_to_identity`

## Quality Gates

```bash
uv run pytest tests/unit/memory/ -q
uv run mypy src/hestia
uv run ruff check src/ tests/
```

## Handoff

Write `docs/handoffs/L228-memory-deterministic-prune-handoff.md` and update `docs/development-process/kimi-loop-log.md`.

## Critical Rules
- Conservative: only remove clear junk and unscoped/orphaned memories.
- Soft-delete only; never hard-delete on the unattended run.
- Protected memories are exempt.
