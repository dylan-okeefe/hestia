---
name: hestia-orchestration
description: Orchestrate multi-loop development builds for the Hestia personal assistant project. Use when working in the Hestia repository to plan, spec, build, review, and merge feature work. Triggers on any task involving hestia source code, tests, docs, releases, or the kimi loop queue.
---

# Hestia Orchestration

Execute the Hestia build workflow: plan from high-level docs, write specs, implement, self-review, and land changes. This skill replaces Cursor's orchestration role.

## Role

You are both **builder and reviewer**. There is no separate Cursor instance. You:
1. Plan work from high-level docs or user direction
2. Write `L*.md` specs when the work spans multiple commits or themes
3. Implement specs sequentially in one session
4. Self-review between logical chunks
5. Commit, write handoffs, and leave the repo in a clean state

Dylan (the user) handles: final approval, `git push`, secrets, and release tags.

## Workflow modes

### Mode A — Single item (default)
For one bug, one refactor, or one small feature.
- Skip spec files. Just build, test, commit.
- Example: "Do H-5 from the v0.9.1 backlog."

### Mode B — Spec-driven arc
For multi-commit or multi-theme work.
1. Read the high-level doc (e.g., `v0.9.1-copilot-backlog.md`)
2. Break into logical `L*.md` specs. Name them sequentially (L46, L47, etc.).
3. For **each spec** in the arc:
   a. Read the spec
   b. Implement all sections
   c. Run quality gates
   d. Self-review using the checklist
   e. Fix issues immediately (do not defer unless user says so)
   f. Commit with conventional commit messages
   g. Write/update the handoff file
4. After the arc completes, update `docs/development-process/kimi-loop-log.md` with a summary entry at the top.

## Quality gates (run after every logical chunk)

```bash
uv run pytest tests/unit/ tests/integration/ -q
uv run mypy src/hestia
uv run ruff check src/ tests/
```

All three must pass before advancing. If ruff has pre-existing baseline issues, note the count and ensure no new issues were introduced.

## Self-review checklist

Before declaring a chunk done, verify:

1. **§0 cleanup items are addressed** — If the spec has a `## Review carry-forward` section, every bullet must be checked off or fixed.
2. **Config fields are wired** — Every new config field is read somewhere (CLI, adapter, or runner).
3. **Import changes don't break downstream** — When `__init__.py` exports change, grep for test files that import from that package.
4. **Migrations match schema** — If schema changed, Alembic migration exists and table count matches.
5. **Store methods reach the CLI** — If a store gains a new method, the CLI command that should call it actually does.
6. **In-memory state has a DB fallback** — Any dict cache needs persistence on restart.
7. **Tests cover the change** — New code has tests; existing tests still pass.
8. **Type safety** — `mypy` reports 0 errors in changed files.
9. **No sync I/O in async paths** — Wrap sync calls with `asyncio.to_thread` or use async-native APIs.
10. **No bare excepts** — Narrow exception clauses; log unexpected ones.

See `references/review-checklist.md` for the detailed version with examples.

## Git flow

- Branch from `develop`: `git checkout -b feature/l<NN>-<slug>`
- Conventional commits: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`
- One commit per logical section
- Do **not** merge to `develop` unless Dylan explicitly authorizes it
- Push feature branch to origin when done: `git push -u origin feature/l<NN>-<slug>`

## Release discipline

After a release tag is placed on `develop` (and especially after push), **no feature branch merges to develop** until a release-prep document exists that names every `feature/*` branch by exact name.

Allowed exceptions (no prep doc needed):
- Pre-tag hotfixes that are part of the in-flight release
- Pure planning/spec docs under `docs/development-process/`
- `.cursorrules` and `AGENTS.md` policy updates

See `references/release-discipline.md` for full rules and examples.

## Prompt format for specs

When writing `L*.md` specs, follow the format in `references/prompt-format.md`:
- §-1: Merge previous phase into develop
- §0: Cleanup bugs from previous phase review
- §1-N: New work sections with code sketches, tests, and commit messages
- Final section: Handoff report
- Critical Rules Recap at the end

## Project structure

```
src/hestia/
  cli.py              # CLI entry point
  config.py           # HestiaConfig dataclass
  core/               # Types + inference client
  context/            # Context builder
  orchestrator/       # Turn state machine
  inference/          # SlotManager
  scheduler/          # Background task loop
  tools/              # Tool registry + built-ins
  artifacts/          # Artifact storage
  persistence/        # Database layer
  platforms/          # Platform ABC + adapters
  policy/             # Policy engine
```

## When to ask Dylan vs. proceed

**Proceed without asking:**
- Trivial fixes (typos, single-line type corrections, test gaps)
- Refactoring that preserves behavior and passes all gates
- Moving a TODO comment or updating a docstring

**Ask Dylan:**
- New dependencies or version bumps
- Changes to trust/security policy behavior
- Schema migrations that alter existing data
- Removing or changing public API surfaces
- Anything that costs money (API keys, new services)
- When a spec is ambiguous or contradictory

## Handoff files

After completing a spec arc, write or update:
- `docs/handoffs/L<NN>-<slug>-handoff.md` — technical summary
- `docs/development-process/kimi-loop-log.md` — narrative entry at top
- `docs/development-process/prompts/KIMI_CURRENT.md` — advance pointer or set idle
