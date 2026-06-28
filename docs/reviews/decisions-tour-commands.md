# Decisions — /tour and /commands

**Status:** Resolved 2026-06-27. Implement against these. Spec:
`docs/reviews/spec-tour-commands.md`.

## Context

Add two chat-surface features: a narrated capability walkthrough (`/tour`) and a
generated command reference (`/commands`). Today `/help` is a hardcoded, already
stale list inside the CLI REPL handler (`src/hestia/commands/meta.py`); it never
gained `/add-topic`, `/remove-topic`, `/topic`, or `/remember-global`, and
meta-commands have no registry. Rather than add more hand-maintained lists, this
work introduces a docstring-driven command registry so the reference and the tour
both generate from one source.

## 1. Commands and interaction

- `/tour` starts the walkthrough; `/continue` advances one step; `/endtour` ends it.
- Pure narration. Progression NEVER depends on the user doing anything: `/continue`
  always advances, `/endtour` always ends. There is no "try it to proceed" gating.
- Do NOT overload `/exit`. It already means quit-the-REPL in `meta.py` (`/quit` and
  `/exit` are treated identically). The bail command is `/endtour`.

## 2. /tour state

- Ephemeral cursor keyed to (conversation, user). Not persisted across sessions; a
  fresh `/tour` restarts from the top.
- DM / single-user only for v1. In a multi-user room `/tour` is disabled and replies
  that it is DM-only, so there is no shared cursor in group chats.
- `/continue` and `/endtour` are only meaningful while a tour is active. Outside an
  active tour they no-op with a gentle "no tour running" message.
- `/tour` is a fast-path: it returns the next step's text without an inference turn
  (the way `/compact` short-circuits). Steps are static curated prose; the model
  never improvises them.

## 3. /commands reference

- `/commands` prints the generated command catalog: name, aliases, one-line summary.
- `/help` becomes an alias to `/commands`. Remove the hardcoded help list.
- Scope for v1: meta-commands only. Tools already carry `public_description` via the
  `@tool` decorator; surfacing them in `/commands` is a later option, not v1.

## 4. The command registry (foundation)

- Introduce a lightweight per-command registration (a `@command` decorator or a
  registry object) capturing: name, aliases, a one-line summary, and the longer help
  taken from the handler's docstring (`func.__doc__`). This is the JSDoc-style idea
  but runtime-introspectable and unit-testable; NO source-comment parsing.
- Single source of truth: `/commands` renders the summaries; `/tour` narrates from
  the longer descriptions (or a curated step list that references the same registry).
  The two cannot drift.
- Served on the cross-platform command path (CLI REPL, Telegram, Matrix), not just
  the CLI REPL handler. `/compact` already works across platforms, so follow that
  path, not the click/echo REPL-only branch.
- Migrating the existing meta-commands onto the registry must preserve their current
  behavior exactly.

## 5. Drift guard

- A test asserts every registered command appears in `/commands`, and every major
  command/capability appears somewhere in `/tour`. Adding a command without catalog
  coverage fails the test.

## Critical rules

- No merge/push without Dylan's okay.
- Tests assert the invariants first (see spec), then implement.
- No silent skips; per-item handoff accounting per the orchestration SKILL.
