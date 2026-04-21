# ADR-0012: Turn state machine with platform-agnostic confirmation callback

- **Status:** Accepted
- **Date:** 2026-04-09
- **Context:** The orchestrator needs to run under multiple adapters (CLI
  today, Matrix and Telegram in Phase 2). Some tools require user
  confirmation before executing (e.g., `terminal`). Confirmation UX is
  adapter-specific — CLI uses a stdin prompt, Matrix uses a reply button,
  Telegram uses an inline keyboard. The orchestrator cannot know about
  any of this without coupling itself to every adapter.

  Separately, turn lifecycle needs to be observable and recoverable:
  debugging an agent that hangs mid-turn is impossible without a record
  of what state it was in and what transitions it took.

- **Decision:**
  1. Model the turn lifecycle as an explicit state machine with 10
     states (`RECEIVED`, `BUILDING_CONTEXT`, `AWAITING_MODEL`,
     `EXECUTING_TOOLS`, `AWAITING_USER`, `AWAITING_SUBAGENT`,
     `COMPRESSING`, `RETRYING`, `DONE`, `FAILED`) and a static
     `ALLOWED_TRANSITIONS` table. `assert_transition` raises
     `IllegalTransitionError` on any invalid move. Every transition is
     persisted as a `TurnTransition` row linked to the parent `Turn`.
  2. Tool confirmation is an injected `ConfirmCallback` on the
     `Orchestrator` constructor. The orchestrator never prompts the
     user directly. Adapters provide the callback: CLI calls
     `click.confirm`, Matrix sends a reply with accept/deny buttons,
     Telegram does the same with inline keyboards. If no callback is
     provided and a tool requires confirmation, the call fails closed
     with an error result.
  3. Response delivery uses the same pattern: a `ResponseCallback` the
     adapter provides, invoked when the turn reaches `DONE` or `FAILED`.

- **Consequences:**
  - Adding a new adapter is purely additive — implement two async
    callbacks, inject them into `Orchestrator`, no orchestrator changes.
  - Every turn has a complete transition audit trail in the database,
    which makes post-mortem debugging tractable.
  - Illegal transitions (e.g., skipping `BUILDING_CONTEXT`) fail loudly
    at the source rather than corrupt state silently.
  - The `AWAITING_SUBAGENT` and `COMPRESSING` states are reserved but
    have no transitions wired yet — they'll light up in Phase 3 without
    requiring a schema migration.
  - `requires_confirmation=True` is enforced in the orchestrator on both
    the `call_tool` meta-tool path (which is what models actually use)
    and the direct-tool dispatch path. If `confirm_callback` is `None`
    the orchestrator fails closed with an error result; if the callback
    returns `False` the tool is cancelled.
