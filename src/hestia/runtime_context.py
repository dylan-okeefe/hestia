"""Process-wide execution context (contextvars).

Used when policy must distinguish scheduler-driven turns from interactive CLI,
without changing the persisted session row.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hestia.persistence.trace_store import TraceStore

# True while Scheduler._fire_task is inside orchestrator.process_turn.
scheduler_tick_active: ContextVar[bool] = ContextVar("scheduler_tick_active", default=False)

# Caller identity set by Orchestrator.process_turn for downstream scoping.
current_platform: ContextVar[str | None] = ContextVar("current_platform", default=None)
current_platform_user: ContextVar[str | None] = ContextVar("current_platform_user", default=None)

# Current session ID set by Orchestrator.process_turn for tool egress logging
current_session_id: ContextVar[str | None] = ContextVar("current_session_id", default=None)

# Current TraceStore set by Orchestrator.process_turn for tool egress logging
current_trace_store: ContextVar[TraceStore | None] = ContextVar(
    "current_trace_store", default=None
)
