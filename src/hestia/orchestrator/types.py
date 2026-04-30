"""Turn and TurnState types for the orchestrator state machine."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from hestia.core.types import Message

if TYPE_CHECKING:
    from hestia.context.builder import BuildResult
    from hestia.core.types import Session, ToolSchema
    from hestia.platforms.base import Platform


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


# Callback types
ResponseCallback = Callable[[str], Awaitable[None]]
StreamCallback = Callable[[str], Awaitable[None]]
TransitionCallback = Callable[[Turn, TurnState, str], Awaitable[None]]


@dataclass
class TurnContext:
    """Mutable per-turn state passed through the orchestrator pipeline.

    Replaces the 7-tuple returned by ``_prepare_turn_context`` and the
    20-parameter signature of ``_run_inference_loop``.
    """

    # Immutable for this turn (set once)
    turn: Turn
    user_message: Message
    system_prompt: str
    respond_callback: ResponseCallback
    session: Session
    platform: Platform | None = None
    platform_user: str | None = None

    # Set by _prepare_turn_context
    build_result: BuildResult | None = None
    tools: list[ToolSchema] = field(default_factory=list)
    slot_id: int | None = None
    running_history: list[Message] = field(default_factory=list)
    style_prefix: str | None = None
    allowed_tools: list[str] | None = None

    # Per-turn delivery hint (set by platform adapter)
    voice_reply: bool = False

    # Streaming callback (called for each content chunk)
    stream_callback: StreamCallback | None = None

    # Accumulated during _run_inference_loop
    tool_chain: list[str] = field(default_factory=list)
    artifact_handles: list[str] = field(default_factory=list)
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_reasoning_tokens: int = 0
    delegated: bool = False
