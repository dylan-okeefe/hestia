"""Turn and TurnState types for the orchestrator state machine."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from hestia.core.types import Message


class TurnState(Enum):
    """Turn processing states."""

    RECEIVED = "received"  # user input captured, nothing run yet
    BUILDING_CONTEXT = "building_context"  # ContextBuilder is assembling
    AWAITING_MODEL = "awaiting_model"  # chat() in flight
    EXECUTING_TOOLS = "executing_tools"  # dispatching tool calls
    AWAITING_USER = "awaiting_user"  # paused for confirmation
    AWAITING_SUBAGENT = "awaiting_subagent"  # reserved for Phase 3
    RETRYING = "retrying"  # transient error, backing off
    DONE = "done"  # final answer produced
    FAILED = "failed"  # terminal error, no recovery


@dataclass
class TurnTransition:
    """A single state transition for a Turn."""

    from_state: TurnState
    to_state: TurnState
    at: datetime
    note: str = ""  # optional human-readable context


@dataclass
class Turn:
    """A single turn through the state machine."""

    id: str  # UUID
    session_id: str
    state: TurnState
    user_message: Message | None  # None for system-initiated turns (future)
    started_at: datetime
    completed_at: datetime | None = None
    iterations: int = 0  # how many model calls so far
    tool_calls_made: int = 0  # cumulative count
    final_response: str | None = None  # populated on DONE
    error: str | None = None  # populated on FAILED
    reasoning_budget: int = 2048  # reasoning tokens budgeted for this turn
    transitions: list[TurnTransition] = field(default_factory=list)
    # Artifact handles produced by tool calls during this turn. Populated by
    # the orchestrator engine; consumed by the delegate_task tool so a
    # subagent can surface the artifacts it produced back to its caller.
    artifact_handles: list[str] = field(default_factory=list)
