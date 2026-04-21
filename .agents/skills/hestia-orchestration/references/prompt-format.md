# Prompt Format for L*.md Specs

## Structure

```markdown
# L<NN> — <Title>

**Status:** Spec only. Feature branch work; do not merge to develop until release-prep merge sequence.

**Branch:** `feature/l<NN>-<slug>` (from `develop`)

## Goal

One-sentence summary.

## Review carry-forward

- *(none)*
- OR: list every issue from the previous loop's review

## Scope

### §1 — <First theme>

What to change, where, and why. Include:
- File paths
- Function signatures
- Key implementation notes
- Test requirements
- Commit message: `type(scope): description`

### §2 — <Second theme>

... repeat as needed ...

## Tests

- New unit tests: list them
- Integration tests: list them
- Keep existing tests green

## Acceptance

- `pytest tests/unit/ tests/integration/ -q` green
- `mypy src/hestia` reports 0 errors
- `ruff check src/` remains at baseline or better
- `.kimi-done` includes `LOOP=L<NN>`

## Handoff

- Write `docs/handoffs/L<NN>-<slug>-handoff.md`
- Update `docs/development-process/kimi-loop-log.md`
- Advance `KIMI_CURRENT.md` to next queued item (or idle)
```

## Commit message format

Use conventional commits:
- `feat(scope): description`
- `fix(scope): description`
- `refactor(scope): description`
- `test(scope): description`
- `docs(scope): description`

One commit per logical section (§1, §2, etc.).

## Example: §0 cleanup section

```markdown
### §0 — Review carry-forward fixes

From L<NN-1> review:
- [ ] Fix A: description and file
- [ ] Fix B: description and file

Commit: `fix(scope): address L<NN-1> review carry-forward (A, B)`
```
