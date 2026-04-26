# L68 — Memory Store Precision & Maintainability Handoff

**Branch:** `feature/l68-memory-store-precision`
**Status:** Complete, ready for review

## Changes

### §1–§2 — Fix tag substring matching & simplify LIKE fallback
- Removed space-delimited legacy tag patterns (`s0`, `s1`, `s2`) from `list_memories`
- Only pipe-delimited exact-match patterns remain (`p0`, `p1`, `p2`)
- "work" no longer matches "homework|errands"

### §3 — Remove dead `hasattr` in `_row_to_memory`
- Direct field access instead of defensive `hasattr` checks

### §4 — Extract `_resolve_scope` helper
- Single method replaces 5 copies of the same ContextVar fallback boilerplate

### §5 — Complete FTS5 operator escaping
- `_sanitize_fts5_query` now escapes `*`, `^`, and `NOT` without space separation

## Quality gates

- `pytest tests/unit/test_memory_store.py` — 22 passed
- `mypy src/hestia/memory/store.py` — no issues
- `ruff check` — clean

## Intent verification

- **Tag search is trustworthy:** No substring false-positives on pipe-delimited tags.
- **Scope logic lives in one place:** `grep '_get_user_scope' src/hestia/memory/store.py` shows only `_resolve_scope` and `_get_user_scope` itself.
- **FTS5 is complete:** Queries with `*`, `^`, and `NOT` are escaped/quoted.

## Next

Ready to merge to `develop` and start L69.
