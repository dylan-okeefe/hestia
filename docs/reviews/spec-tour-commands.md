# Spec — /tour and /commands

**Status:** Spec ready. Decisions: `docs/reviews/decisions-tour-commands.md`.
**Loops:** an arc of three. Loop A is the foundation; B and C depend on it.
Split further per the no-skip rule if a loop is too large.
**Branch:** off `develop`.

## Goal

Give the chat surface a generated command reference (`/commands`) and a narrated,
non-interactive capability walkthrough (`/tour`), both driven from a single
docstring-based command registry so they cannot drift from the real commands.

## Loop A — Command registry (foundation)

Introduce the registry and migrate existing meta-commands onto it. No new
user-facing command behavior beyond what already exists.

### Scope
- A lightweight registration per command: name, aliases, one-line summary, and the
  longer help read from the handler's docstring (`func.__doc__`). A `@command`
  decorator or an explicit registry object, whichever fits the existing dispatch.
- Migrate the current meta-commands (`/compact`, `/reset`, `/history`, `/session`,
  `/refresh`, `/tokens`, `/help`, `/quit`, `/exit`, and the memory commands
  `/add-topic`, `/remove-topic`, `/topic`, `/remember-global` if present) to register
  through it, preserving behavior exactly.
- The registry must be reachable from the cross-platform command path, not only the
  CLI REPL handler.

### Invariants and tests (write first)
- Every existing meta-command resolves through the registry and behaves identically
  (dispatch test per command, or a parametrized table).
- The registry exposes, for each command: name, aliases, summary, long help (from the
  docstring). A command missing a summary or docstring fails a registry-completeness
  test.
- Unknown command still falls through to normal handling unchanged.

## Loop B — /commands reference (+ /help alias)

### Scope
- `/commands` renders the registry catalog: each command's name, aliases, and summary,
  grouped readably.
- `/help` aliases to `/commands`. Remove the hardcoded help list in `meta.py`.
- Works on CLI, Telegram, and Matrix.

### Invariants and tests (write first)
- `/commands` output contains every registered command (the drift guard).
- `/help` produces the same output as `/commands`.
- Output renders on each platform path without platform-specific formatting errors.

## Loop C — /tour walkthrough

### Scope
- `/tour` starts; `/continue` advances; `/endtour` ends. Pure narration, progression
  never gated on user action.
- Ephemeral cursor keyed to (conversation, user); a fresh `/tour` restarts from the
  top; `/endtour` clears it.
- DM / single-user only: in a group room `/tour` replies that it is DM-only and does
  not start.
- `/continue` and `/endtour` outside an active tour no-op with a "no tour running"
  message.
- Fast-path: each step returns static curated prose with no inference turn. Steps are
  sourced from / consistent with the registry's longer descriptions.

### Invariants and tests (write first)
- `/tour` then repeated `/continue` walks every step in order and terminates cleanly
  at the end without requiring any user action between steps.
- `/endtour` mid-tour clears the cursor; a subsequent `/continue` reports no active
  tour.
- A second `/tour` after finishing restarts from step one.
- In a multi-user room, `/tour` does not start and returns the DM-only message.
- Drift guard: every major command/capability appears in at least one tour step.

## Dependencies and notes
- Loop A is the foundation; B and C both depend on A landing first.
- Warrants a short ADR (docstring-driven command registry) once Loop A lands, since it
  changes how commands are defined and discovered.
- Cursor state for `/tour`: reuse existing per-session/per-conversation state storage;
  do not add a new persistence table for an ephemeral cursor.

## Critical rules
- Do not merge or push without Dylan's okay.
- Tests assert the invariants first, then implement.
- No silent skips; per-item handoff accounting; if a loop is too big, split it and
  flag the split rather than dropping scope.
