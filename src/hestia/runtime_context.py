"""Process-wide execution context (contextvars).

Used when policy must distinguish scheduler-driven turns from interactive CLI,
without changing the persisted session row.
"""

from contextvars import ContextVar

# True while Scheduler._fire_task is inside orchestrator.process_turn.
scheduler_tick_active: ContextVar[bool] = ContextVar("scheduler_tick_active", default=False)
