# ADR-0031: Capability labels and session-aware tool filtering

- **Status:** Accepted
- **Date:** 2026-04-10
- **Context:** Tools had informal `tags` but no security-oriented labels. All
  registered tools were visible to every session type, including subagents and
  scheduler-driven turns that run without a human at the keyboard.

- **Decision:**
  1. Add a `capabilities` list on `ToolMetadata` using a small fixed vocabulary
     (`read_local`, `write_local`, `shell_exec`, `network_egress`, `memory_read`,
     `memory_write`, `orchestration`).
  2. Extend `PolicyEngine` with `filter_tools(session, names, registry)`;
     `DefaultPolicyEngine` removes tools whose capabilities intersect a blocked set
     for `platform=subagent` and for scheduler execution.
  3. Scheduler turns use the same persisted session as interactive CLI, so
     scheduler mode is detected with `contextvars` (`scheduler_tick_active`)
     set for the duration of `Scheduler._fire_task` → `process_turn`.

- **Consequences:** Tool listings and `call_tool` dispatch must respect the
  filtered set. Subagents cannot run shell or arbitrary local writes by default.
