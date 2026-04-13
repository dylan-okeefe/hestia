"""Core dataclasses for Hestia."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel


def _utc_now() -> datetime:
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


@dataclass
class ToolCall:
    """A tool call requested by the model."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class Message:
    """A chat message."""

    role: Literal["system", "user", "assistant", "tool"]
    content: str
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None
    reasoning_content: str | None = None
    created_at: datetime = field(default_factory=_utc_now)


@dataclass
class ToolResult:
    """Result of executing a tool."""

    tool_call_id: str
    name: str
    content: str
    artifact_id: str | None = None


class SessionState(Enum):
    """Session lifecycle states."""

    ACTIVE = "active"
    IDLE = "idle"
    ARCHIVED = "archived"


class SessionTemperature(Enum):
    """Session thermal states (slot availability)."""

    HOT = "hot"  # has a live slot attached
    WARM = "warm"  # slot saved to disk, can be restored
    COLD = "cold"  # no slot, no saved cache, must rebuild from messages


@dataclass
class Session:
    """A conversation session."""

    id: str
    platform: str
    platform_user: str
    started_at: datetime
    last_active_at: datetime
    slot_id: int | None
    slot_saved_path: str | None
    state: SessionState
    temperature: SessionTemperature


@dataclass
class ScheduledTask:
    """A scheduled task for autonomous execution."""

    id: str
    session_id: str
    prompt: str
    description: str | None
    cron_expression: str | None  # Exactly one of cron_expression or fire_at must be set
    fire_at: datetime | None
    enabled: bool
    created_at: datetime
    last_run_at: datetime | None
    next_run_at: datetime | None
    last_error: str | None


class TurnState(Enum):
    """Turn processing states."""

    RECEIVED = "received"
    BUILDING_CONTEXT = "building_context"
    AWAITING_MODEL = "awaiting_model"
    EXECUTING_TOOLS = "executing_tools"
    AWAITING_SUBAGENT = "awaiting_subagent"
    AWAITING_USER = "awaiting_user"
    RETRYING = "retrying"
    DONE = "done"
    FAILED = "failed"


TERMINAL_STATES = {TurnState.DONE, TurnState.FAILED}


@dataclass
class ChatResponse:
    """Response from the inference server."""

    content: str
    reasoning_content: str | None
    tool_calls: list[ToolCall]
    finish_reason: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class FunctionSchema(BaseModel):
    """JSON schema for a function."""

    name: str
    description: str
    parameters: dict  # JSON Schema


class ToolSchema(BaseModel):
    """OpenAI-compatible tool schema."""

    type: Literal["function"] = "function"
    function: FunctionSchema
