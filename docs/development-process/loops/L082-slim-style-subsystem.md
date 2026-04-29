# L82 — Slim Style Subsystem

**Status:** Spec only  
**Branch:** `feature/l82-slim-style-subsystem` (from `develop`)

## Goal

Cut the style subsystem from ~899 lines to ≤350 lines without losing capability. Like reflection, this is an opt-in feature that currently outweighs its utility.

## Review carry-forward

- *(none — this is a clean-up loop)*

## Scope

### §1 — Audit and identify cuts

Current style files:
- `vocab.py` (299 lines) — Vocabulary classification system. Almost certainly over-engineered for appending a short `[STYLE]` prefix to the system prompt.
- `builder.py` (231 lines) — StyleProfileBuilder. May have redundant persistence logic.
- `store.py` (179 lines) — StyleProfileStore with CRUD.
- `scheduler.py` (123 lines) — StyleScheduler wiring.
- `context.py` (54 lines) — `format_style_prefix_from_data()` helper.
- `__init__.py` (13 lines)

**Audit questions:**
- Does `vocab.py` need 299 lines of word-classification logic? Can the same effect be achieved with a simpler heuristic or a smaller lookup table?
- Are all StyleProfileBuilder phases used, or can the builder be simplified?
- Does the store need full CRUD, or just get/update?

**Commit:** `docs(style): audit findings and cut list`

### §2 — Slash vocab.py

`vocab.py` is the biggest target. Evaluate whether the classification logic (word lists, POS tagging, sentiment scoring) produces measurably better style prefixes than a simpler approach. Options:
1. Replace with a 50-line heuristic based on message length and punctuation density.
2. Keep the core idea but cut the word lists and external dependencies.
3. If evaluation shows no quality difference, replace entirely with a minimal prefix formatter.

**Target:** `vocab.py` ≤60 lines (or delete if replaced by heuristic).

**Commit:** `refactor(style): replace 299-line vocab classifier with minimal heuristic`

### §3 — Simplify builder and store

Collapse `StyleProfileBuilder` to the essential phases: collect samples → compute stats → write profile. Remove intermediate abstractions. Slim `StyleProfileStore` to get/update only.

**Target:** `builder.py` ≤100 lines, `store.py` ≤80 lines.

**Commit:** `refactor(style): slim builder and store to essential CRUD`

### §4 — Consolidate scheduler and context

Merge `context.py` into `builder.py` if the helper is only used there. Simplify `scheduler.py` wiring.

**Target:** `scheduler.py` ≤60 lines.

**Commit:** `refactor(style): merge context helper into builder, slim scheduler`

## Tests

- Keep `tests/unit/test_style*.py` green.
- If the vocab approach changes, update or remove vocab-specific tests.

## Acceptance

- `pytest tests/unit/ tests/integration/ -q` green
- `mypy src/hestia` reports 0 errors
- `find src/hestia/style/ -name "*.py" | xargs wc -l` total ≤ 350
- `.kimi-done` includes `LOOP=L82`

## Handoff

- Write `docs/handoffs/L82-slim-style-subsystem-handoff.md`
- Update `docs/development-process/kimi-loop-log.md`
- Advance `KIMI_CURRENT.md` to next queued item (or idle)
