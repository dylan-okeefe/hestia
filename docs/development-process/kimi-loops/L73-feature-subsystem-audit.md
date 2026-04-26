# L73 — Feature Subsystem Audit

**Status:** Spec ready. Feature branch work — merge to `develop` when green.

**Branch:** `feature/l73-feature-subsystem-audit` (from `develop`)

## Goal

Audit the three largest feature subsystems — Reflection, Style Profile, and Skills — and decide for each: finish, slim, or remove. The evaluation is unambiguous: "Either finish it or remove it. Dead scaffolding that ships is worse than no scaffolding."

---

## Intent & Meaning

The evaluation devotes significant space to what it calls "feature infrastructure accreting faster than it's used." The numbers:

- **Reflection:** ~600 lines (runner, scheduler, store, types, prompts, CLI commands)
- **Style:** ~600 lines (builder, store, scheduler, vocab, context)
- **Skills:** ~500 lines (decorator, index, state, types, store)

That's ~1,700 lines of feature infrastructure for three features, two of which are off by default and one is gated behind an experimental flag. Each subsystem follows the same pattern (config, store, builder, scheduler, CLI), which is consistent but heavy.

The evaluation's verdict:
- **Skills:** Most concerning. "Scaffolding for a feature that doesn't work yet. Either finish it (build the run_skill meta-tool, ship a built-in skill library) or remove it."
- **Reflection and Style:** Functional but could each be "about half their current size without losing capability."

The intent is **rebalance the codebase's center of gravity**. Right now there is more code for features most users won't enable than for the core chat loop that everyone uses. This creates navigation friction, compile/test overhead, and cognitive load for contributors. The goal is not minimalism — it is **honesty about what is shipped**. A half-built feature behind a flag is not a feature; it is a promise that hasn't been kept.

---

## Scope

### §1 — Skills: decide and execute

**Files:** `src/hestia/skills/` (~500 lines)
**Evaluation:** "Either build the run_skill meta-tool and ship a useful built-in skill, or remove the entire subsystem and put it back when it's ready."

**Change:**
Audit the skills code. If the `run_skill` meta-tool and a minimal built-in skill library (even one skill) can be built in this loop, build them. If not, delete:
- `src/hestia/skills/`
- `SkillStore` references in `persistence/`
- `skills` config section
- CLI commands for skills
- Tests

**Do not leave dead scaffolding.** A git history preserves the code if we want it back.

**Intent:** The codebase should not contain 500 lines of code for a feature that does nothing when the flag is flipped.

**Commit:** `feat(skills): ship run_skill meta-tool + built-in skill library` OR `refactor: remove incomplete skills subsystem`

---

### §2 — Reflection: slim by half

**Files:** `src/hestia/reflection/` (~600 lines)
**Evaluation:** "Functional, but could be about half its current size without losing capability."

**Change:**
Audit for redundancy:
- Is `ReflectionScheduler` separate from the main scheduler for a real reason, or just pattern consistency?
- Can `ProposalStore` and `Observation` types be simplified?
- Are the three-pass pipeline (pattern mining → proposal generation → queue write) all necessary for the current value delivered?
- Can the CLI surface be reduced (e.g., merge `show`/`list` into one command)?

Target: reduce to ~300 lines without removing functionality.

**Intent:** A feature that is off by default should not dominate the codebase. If it is worth keeping, it should be tight.

**Commit:** `refactor(reflection): slim subsystem to core value`

---

### §3 — Style Profile: slim by half

**Files:** `src/hestia/style/` (~600 lines)
**Evaluation:** "Five files and ~600 lines for a feature that injects a short [STYLE] addendum into the system prompt. The signal-to-code ratio is low."

**Change:**
Audit for redundancy:
- `style/vocab.py` (299 lines of vocabulary classification) — is the classification depth necessary, or can a simpler heuristic suffice?
- `style/context.py` — can formatting be inlined?
- Can `StyleProfileBuilder` and `StyleProfileStore` be merged or simplified?

Target: reduce to ~300 lines without removing functionality.

**Intent:** The [STYLE] addendum is a nice touch, but it should not require 600 lines of infrastructure. Reduce to the minimal code that captures the user's style and injects it.

**Commit:** `refactor(style): slim subsystem to core value`

---

## Quality gates

```bash
uv run pytest tests/unit/ tests/integration/ -q
uv run mypy src/hestia
uv run ruff check src/ tests/
```

## Acceptance (Spec-Based)

- Skills is either functional (meta-tool works, at least one built-in skill runs) or fully removed.
- Reflection is ≤ 350 lines.
- Style is ≤ 350 lines.
- All tests pass.

## Acceptance (Intent-Based)

- **The core chat loop is the majority of the code.** After this loop, `src/hestia/` should have visibly more lines in `orchestrator/`, `tools/`, and `context/` than in `reflection/`, `style/`, and `skills/` combined.
- **A new contributor can ignore the optional features.** The optional subsystems should be small enough that a reader skimming the tree does not assume they are central.
- **Nothing is left in a zombie state.** If skills is removed, `grep -r "skills" src/hestia/config.py` should show nothing. If it is kept, `hestia chat` with skills enabled should demonstrably invoke a skill.

## Handoff

- Write `docs/handoffs/L73-feature-subsystem-audit-handoff.md`.
- Update `docs/development-process/kimi-loop-log.md`.
- Merge `feature/l73-feature-subsystem-audit` to `develop`.

## Dependencies

L71 (app context flattening) should merge first to avoid conflicts in config wiring.
