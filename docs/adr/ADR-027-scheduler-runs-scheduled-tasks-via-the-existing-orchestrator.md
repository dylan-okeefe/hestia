# ADR-027: Scheduler runs scheduled tasks via the existing Orchestrator

- **Status:** Accepted
- **Date:** 2026-04-09
- **Context:** Hestia needs to fire LLM turns at user-defined times — both
  recurring ("every weekday at 9am, summarize my Matrix unread") and one-shot
  ("remind me at 3pm"). Without a dedicated scheduler, every adapter would
  end up reinventing this loop, and the natural place for it (cron + a
  daemon process) lives outside Hestia entirely, which loses session
  continuity and KV-cache reuse.

- **Decision:**
  1. Introduce a `Scheduler` class that owns a single asyncio loop. The loop
     wakes on a fixed tick interval, queries `SchedulerStore.list_due_tasks`,
     and fires each due task by invoking the existing `Orchestrator.process_turn`
     with the task's prompt as a synthetic user message.
  2. Scheduled tasks are persisted in a new `scheduled_tasks` table that
     stores either a `cron_expression` (recurring) or `fire_at` timestamp
     (one-shot), never both. `next_run_at` is computed eagerly with
     `croniter` and updated after every run.
  3. The Scheduler does not own its own `InferenceClient` or `SlotManager` —
     it receives an already-built `Orchestrator`. This guarantees scheduled
     turns share the same slot pool, calibration, and policy as
     interactive turns.
  4. Task results are delivered via a `response_callback` injected at
     construction. The CLI daemon prints to stdout. Future adapters
     (Matrix, Telegram) will route the response back to the originating
     channel.
  5. One-shot tasks auto-disable after firing because `_compute_next_run`
     returns `None` for them. Recurring tasks advance `next_run_at` to
     the next cron occurrence.
  6. The loop is cancellable via an `asyncio.Event`. `stop()` is fast and
     idempotent.

- **Consequences:**
  - Scheduled and interactive turns are indistinguishable from the
    Orchestrator's perspective, so all the Phase 1c invariants
    (transition validation, EmptyResponseError guard, confirmation
    enforcement) apply uniformly.
  - Scheduled turns benefit from KV-cache reuse: a recurring task that
    runs against the same session every morning will warm-restore the
    slot from disk on each fire.
  - Task firing is sequential within a tick. If a task takes 30 seconds
    and ten tasks are due at once, the tenth waits five minutes. This is
    fine for Phase 2b — the realistic load is single-digit tasks per day.
    A worker pool can be added later without changing the public API.
  - Cron expressions are evaluated in the process's local timezone, not
    UTC. This matches user intuition for "every weekday at 9am" but
    needs to be documented.
  - One-shot tasks scheduled in the past are silently disabled (their
    `next_run_at` is `None` from the start). The CLI rejects past
    `--at` values up front so the user gets a clear error.
  - Adding `croniter` is the first non-stdlib runtime dependency outside
    httpx/sqlalchemy/click. It's small, stable, and widely used; the
    alternative (hand-rolled cron parsing) is not worth the bug surface.
