"""Core dataclasses for Hestia."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel

from hestia.core.clock import utcnow


def _utc_now() -> datetime:
    """Return timezone-aware UTC now."""
    return utcnow()


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
    notify: bool = False

    def __post_init__(self) -> None:
        if bool(self.cron_expression) and bool(self.fire_at):
            raise ValueError("Exactly one of cron_expression or fire_at must be set")
        if not (bool(self.cron_expression) or bool(self.fire_at)):
            raise ValueError("Exactly one of cron_expression or fire_at must be set")


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


@dataclass
class StreamDelta:
    """A single chunk from a streaming inference response."""

    content: str
    finish_reason: str | None = None


class FunctionSchema(BaseModel):
    """JSON schema for a function."""

    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema


class ToolSchema(BaseModel):
    """OpenAI-compatible tool schema."""

    type: Literal["function"] = "function"
    function: FunctionSchema
