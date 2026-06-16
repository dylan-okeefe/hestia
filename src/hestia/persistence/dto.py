"""Persistence-local DTOs for messages, turns, and transitions.

These dataclasses contain only primitive/SQLAlchemy-friendly types. Domain
objects from ``hestia.orchestrator.types`` and ``hestia.core.types`` must be
mapped to/from these DTOs at the orchestrator boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class MessageDTO:
    """Database-facing representation of a chat message.

    Mirrors the ``messages`` table columns exactly (no ``correction`` column
    yet; that is added by the concurrency loop).
    """

    session_id: str
    idx: int
    role: str
    content: str
    created_at: datetime
    tool_calls: str | None = None
    tool_call_id: str | None = None
    reasoning_content: str | None = None
    is_handoff: bool = False


@dataclass
class TurnDTO:
    """Database-facing representation of a turn.

    Mirrors the ``turns`` table columns exactly.
    """

    id: str
    session_id: str
    state: str
    started_at: datetime
    last_transition_at: datetime
    iteration: int = 0
    reasoning_budget: int = 0
    status_msg_id: str | None = None
    slot_id: int | None = None
    error: str | None = None


@dataclass
class TurnTransitionDTO:
    """Database-facing representation of a turn state transition.

    The database column is ``reason``; the domain object calls it ``note``.
    """

    turn_id: str
    from_state: str
    to_state: str
    at: datetime
    reason: str | None = None
