# L68 — Memory Store Precision & Maintainability

**Status:** Spec ready. Feature branch work — merge to `develop` when green.

**Branch:** `feature/l68-memory-store-precision` (from `develop`)

## Goal

Fix the latent tag-matching correctness bug, simplify the overcreative LIKE fallback, remove defensive dead code, and extract a shared SQL scope helper to reduce duplication across `MemoryStore` methods.

---

## Intent & Meaning

The evaluation found four issues in `memory/store.py`:

1. **Tag substring matching bug:** The space-delimited legacy patterns (`"tag %"`, `"% tag %"`, `"% tag"`) match tags that are substrings of other words. `"work"` matches `"homework|errands"`.
2. **Six LIKE clauses:** The fallback uses `p0, p1, p2, s0, s1, s2` — creative but hard to maintain.
3. **Defensive `hasattr` in `_row_to_memory`:** The columns are always selected; the check is never needed and obscures intent.
4. **Raw SQL duplication:** The user-scope conditional (`platform is None or platform_user is None → read from ContextVar`) appears in five methods.

The intent is **make memory search precise and the store readable**. A personal assistant's memory is its most user-visible feature. If a user says "forget what you know about work," and the system silently matches "homework," the user loses trust. The SQL duplication is a maintainability tax — every schema change requires editing the same conditional in five places.

---

## Scope

### §1 — Fix tag-matching substring bug

**File:** `src/hestia/memory/store.py`
**Evaluation:** `list_memories` tag-matching LIKE fallback uses patterns that match substrings.

**Change:**
Use a canonical delimiter (e.g., `|`) and match the exact tag with boundary checks:

```python
# Instead of:
s0 = "tag %", s1 = "% tag %", s2 = "% tag"

# Use exact match on the pipe-delimited tag column:
WHERE tags LIKE ? OR tags LIKE ? OR tags LIKE ?
# with:
f"%{tag}%"  # still substring...

# Better: store and query with canonical delimiter
WHERE tags = ? OR tags LIKE ? OR tags LIKE ? OR tags LIKE ?
# with exact and delimited patterns:
tag, f"{tag}|%", f"%|{tag}|%", f"%|{tag}"
```

**Intent:** A tag query for "work" should only match "work", "work|personal", or "personal|work", never "homework".

**Commit:** `fix(memory): prevent substring false-positives in tag matching`

---

### §2 — Simplify LIKE fallback to single pattern

**File:** `src/hestia/memory/store.py`
**Evaluation:** Six LIKE clauses (`p0, p1, p2, s0, s1, s2`) is creative but hard to maintain.

**Change:**
If the tags column uses a canonical pipe delimiter, a single `LIKE` or `=` check suffices. If FTS5 is available, prefer it exclusively for tag queries and drop the LIKE fallback for tags. If FTS5 is unavailable, use the delimited exact-match approach from §1.

Remove the `p0/p1/p2/s0/s1/s2` variable names and comments. The code should read like normal SQL.

**Intent:** SQL that looks like SQL. Future maintainers should not need a diagram to understand tag matching.

**Commit:** `refactor(memory): simplify tag fallback to canonical delimiter patterns`

---

### §3 — Remove dead `hasattr` check in `_row_to_memory`

**File:** `src/hestia/memory/store.py`
**Evaluation:** `hasattr` check on line 503 is never needed — columns are always selected.

**Change:**
Remove the `hasattr` branch. Access the row fields directly. If a test breaks, the test is wrong (it's not selecting the columns the real code selects).

**Intent:** Defensive coding should defend against real threats. A check that can never fail makes readers wonder what edge case they're missing.

**Commit:** `refactor(memory): remove unnecessary hasattr guard in _row_to_memory`

---

### §4 — Extract user-scope resolution helper

**File:** `src/hestia/memory/store.py`
**Evaluation:** The user-scope conditional appears in `save`, `search`, `list_memories`, `delete`, and `count`.

**Change:**
Extract `_resolve_scope(platform, platform_user) -> tuple[str | None, str | None]` and use it in all five methods. The helper should handle the ContextVar fallback.

```python
def _resolve_scope(
    self, platform: str | None, platform_user: str | None
) -> tuple[str | None, str | None]:
    if platform is None or platform_user is None:
        return current_platform.get(), current_platform_user.get()
    return platform, platform_user
```

**Intent:** One place to change scope logic. One place to verify it is correct.

**Commit:** `refactor(memory): extract _resolve_scope helper to deduplicate SQL conditionals`

---

## Quality gates

```bash
uv run pytest tests/unit/ tests/integration/ -q
uv run mypy src/hestia
uv run ruff check src/ tests/
```

## Acceptance (Spec-Based)

- Tag "work" does not match "homework|errands".
- `_row_to_memory` has no `hasattr` checks.
- `_resolve_scope` exists and is used in all CRUD methods.
- All tests pass.

## Acceptance (Intent-Based)

- **Memory search is trustworthy.** A test explicitly asserts that querying tag "work" against a memory with tags "homework|errands" returns zero results.
- **A schema change to scope logic edits one method.** Verify by grepping — the ContextVar fallback should appear only in `_resolve_scope`.
- **`_row_to_memory` is obviously correct.** A reader should see direct field access and understand the mapping without defensive distractions.

## Handoff

- Write `docs/handoffs/L68-memory-store-precision-handoff.md`.
- Update `docs/development-process/kimi-loop-log.md`.
- Merge `feature/l68-memory-store-precision` to `develop`.

## Dependencies

None. Can start immediately from `develop` tip.
