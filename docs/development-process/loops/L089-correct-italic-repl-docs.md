# L89 — Correct `_italic_repl` Documentation

**Status:** Spec only
**Branch:** `feature/l89-correct-italic-repl-docs` (from `develop`)

## Intent

The post-cleanup evaluation (`docs/development-process/reviews/post-cleanup-evaluation-april-26.md`) incorrectly calls `_italic_repl` in `telegram_adapter.py` dead code and includes a checklist item to delete it. The April 29 code review proved this is wrong: the `<b>` guard IS reachable when bold conversion runs before italic conversion (e.g., `*text **bold** more*` → `*text <b>bold</b> more*`). Leaving the incorrect checklist item risks a future contributor deleting correct code.

## Scope

### §1 — Update post-cleanup evaluation

In `docs/development-process/reviews/post-cleanup-evaluation-april-26.md`:

1. Find line 59: `1. **_italic_repl dead code still present.**` — replace the full paragraph with a correction note:
   ```
   1. ~~**`_italic_repl` dead code still present.**~~ Resolved: the `"*" in inner` clause was removed in L70. The remaining `<b>` guard is NOT dead code — it is reachable when bold conversion (`**text**` → `<b>text</b>`) runs before italic conversion, producing `<b>` tags inside the italic match group. See `code-review-develop-april-29.md` §_italic_repl for the full trace.
   ```

2. Find line 138: `- [ ] Remove _italic_repl dead code...` — replace with:
   ```
   - [x] `_italic_repl` — resolved. The `"*" in inner` clause was removed; the `<b>` guard is correct and reachable. No further action needed.
   ```

3. Find line 111 and line 119 — update the references to `_italic_repl` dead code with correction notes in the same style.

**Commit:** `docs: correct _italic_repl dead-code mischaracterization in post-cleanup eval`

## Evaluation

- **Spec check:** All four references to `_italic_repl` as "dead code" in `post-cleanup-evaluation-april-26.md` are corrected.
- **Intent check:** A future reader of the post-cleanup evaluation will NOT be led to delete `_italic_repl`. The correction cross-references the April 29 review for the full reasoning.
- **Regression check:** No code changes. `pytest tests/ -q` still passes. `grep -rn "italic_repl.*dead" docs/` returns zero hits.

## Acceptance

- `grep -rn "italic_repl.*dead" docs/` returns 0 results
- All checklist items referencing `_italic_repl` are marked resolved
- `.kimi-done` includes `LOOP=L89`

## Handoff

- Update `docs/development-process/kimi-loop-log.md`
- Advance `KIMI_CURRENT.md`
