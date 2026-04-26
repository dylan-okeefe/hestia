# L70 — Telegram Markdown & Code Hygiene

**Status:** Spec ready. Feature branch work — merge to `develop` when green.

**Branch:** `feature/l70-telegram-markdown-and-hygiene` (from `develop`)

## Goal

Clean up the Telegram markdown-to-HTML converter: remove dead code, simplify the regex chain, and eliminate the duplicate test file leftover from an earlier refactor.

---

## Intent & Meaning

The evaluation identified three issues in `telegram_adapter.py`:

1. **`_italic_repl` dead code:** A check for `"*" in inner` and `"<b>" in inner` can never trigger given the regex pattern `r"\*([^*\n]+)\*"`. The `[^*\n]+` already excludes `*`, and bold tags are replaced before italic replacement runs. The dead code confuses readers into thinking there is an edge case they are missing.
2. **`_md_to_tg_html` regex soup:** A chain of regex substitutions converts Markdown to Telegram HTML. It is fragile for nested formatting and has no test coverage for edge cases. The evaluation does not demand a full rewrite (the personal-assistant use case is controlled), but it does ask for cleanup of known dead code.
3. **`test_builtin_tools_new.py`:** A duplicate test file from an in-progress refactor.

The intent is **make the code obviously correct**. Dead code, duplicate files, and untested regex chains are all forms of "noise" that make the codebase harder to trust. We are not building a general-purpose Markdown parser — we are making sure the one we have does not contain lies.

---

## Scope

### §1 — Remove dead code from `_italic_repl`

**File:** `src/hestia/platforms/telegram_adapter.py`
**Evaluation:** The inner check is dead code (lines 70-71).

**Change:**
```python
# Before
def _italic_repl(match: re.Match) -> str:
    inner = match.group(1)
    if "*" in inner or "<b>" in inner or "</b>" in inner:
        return match.group(0)
    return f"<i>{inner}</i>"

# After
def _italic_repl(match: re.Match) -> str:
    return f"<i>{match.group(1)}</i>"
```

**Intent:** The function should do what it says — wrap the capture in `<i>` — without phantom edge-case guards.

**Commit:** `fix(telegram): remove dead code from _italic_repl`

---

### §2 — Simplify `_md_to_tg_html`

**File:** `src/hestia/platforms/telegram_adapter.py`
**Evaluation:** `_md_to_tg_html` is regex soup. The `_italic_repl` closure is more complex than necessary given the dead code.

**Change:**
- Inline or simplify the replacement chain.
- Ensure the order is documented: code blocks → bold → italic → links. The order matters; document why.
- If the closure can be replaced with a simple `re.sub(..., r"<i>\1</i>", text)`, do so.

**Intent:** A 40-line regex chain should explain its ordering and not contain nested closures for logic that fits on one line.

**Commit:** `refactor(telegram): simplify markdown-to-HTML regex chain`

---

### §3 — Merge or delete `test_builtin_tools_new.py`

**Files:** `tests/unit/tools/`
**Evaluation:** `test_builtin_tools.py` and `test_builtin_tools_new.py` coexist. Suggests a refactor in progress.

**Change:**
- Verify which file is current.
- If `test_builtin_tools_new.py` supersedes the old one, delete the old and rename.
- If the old one still has unique tests, merge them into the new file and delete the old.
- If neither is authoritative, audit both and consolidate.

**Intent:** Two files with similar names is a trap for contributors. There should be exactly one test module per source module.

**Commit:** `test: consolidate duplicate builtin-tools test files`

---

## Quality gates

```bash
uv run pytest tests/unit/ tests/integration/ -q
uv run mypy src/hestia
uv run ruff check src/ tests/
```

## Acceptance (Spec-Based)

- `_italic_repl` has no inner-check branch.
- `_md_to_tg_html` ordering is documented.
- Only one `test_builtin_tools*.py` file exists in `tests/unit/tools/`.
- All tests pass.

## Acceptance (Intent-Based)

- **The markdown converter is readable in one pass.** A new contributor should read `_md_to_tg_html` and understand the transformation order without scrolling back and forth.
- **There is no dead code to wonder about.** Grepping `_italic_repl` should show a 2-line function, not a 6-line function with a mystery branch.
- **Test discovery is unambiguous.** `pytest tests/unit/tools/test_builtin_tools.py` should run exactly one test module.

## Handoff

- Write `docs/handoffs/L70-telegram-markdown-and-hygiene-handoff.md`.
- Update `docs/development-process/kimi-loop-log.md`.
- Merge `feature/l70-telegram-markdown-and-hygiene` to `develop`.

## Dependencies

None. Can start immediately from `develop` tip.
