"""Mapping between domain objects and persistence-local DTOs."""

from __future__ import annotations

import json
from typing import Any, Literal, cast

from hestia.core.types import Message, ToolCall
from hestia.orchestrator.types import Turn, TurnState, TurnTransition
from hestia.persistence.dto import MessageDTO, TurnDTO, TurnTransitionDTO


def message_domain_to_dto(msg: Message, session_id: str, idx: int) -> MessageDTO:
    """Convert a domain ``Message`` to a persistence ``MessageDTO``."""
    tool_calls_json: str | None = None
    if msg.tool_calls:
        tool_calls_json = json.dumps(
            [
                {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                for tc in msg.tool_calls
            ]
        )
    return MessageDTO(
        session_id=session_id,
        idx=idx,
        role=msg.role,
        content=msg.content,
        created_at=msg.created_at,
        tool_calls=tool_calls_json,
        tool_call_id=msg.tool_call_id,
        reasoning_content=msg.reasoning_content,
        is_handoff=msg.is_handoff,
    )


def message_dto_to_domain(dto: MessageDTO) -> Message:
    """Convert a persistence ``MessageDTO`` to a domain ``Message``."""
    tool_calls: list[ToolCall] | None = None
    if dto.tool_calls:
        try:
            data = json.loads(dto.tool_calls)
            normalized: list[ToolCall] = []
            for tc in data:
                raw_args = tc.get("arguments")
                if isinstance(raw_args, dict):
                    args = raw_args
                else:
                    # Legacy/corrupt arguments that are not dicts become {}.
                    args = {}
                normalized.append(
                    ToolCall(
                        id=tc["id"],
                        name=tc["name"],
                        arguments=args,
                    )
                )
            tool_calls = normalized
        except (json.JSONDecodeError, KeyError) as e:
            raise ValueError(f"Failed to parse tool_calls JSON: {e}") from e
    return Message(
        role=cast(Literal["system", "user", "assistant", "tool"], dto.role),
        content=dto.content,
        tool_calls=tool_calls,
        tool_call_id=dto.tool_call_id,
        reasoning_content=dto.reasoning_content,
        is_handoff=dto.is_handoff,
    )


def turn_domain_to_dto(turn: Turn) -> TurnDTO:
    """Convert a domain ``Turn`` to a persistence ``TurnDTO``."""
    return TurnDTO(
        id=turn.id,
        session_id=turn.session_id,
        state=turn.state.value,
        started_at=turn.started_at,
        last_transition_at=turn.last_transition_at,
        iteration=turn.iterations,
        reasoning_budget=turn.reasoning_budget,
        status_msg_id=turn.status_msg_id,
        slot_id=turn.slot_id,
        error=turn.error,
    )


def turn_dto_to_domain(
    dto: TurnDTO,
    transitions: list[TurnTransition] | None = None,
    user_message: Message | None = None,
) -> Turn:
    """Convert a persistence ``TurnDTO`` to a domain ``Turn``."""
    return Turn(
        id=dto.id,
        session_id=dto.session_id,
        state=TurnState(dto.state),
        user_message=user_message,
        started_at=dto.started_at,
        completed_at=None,
        iterations=dto.iteration,
        tool_calls_made=0,
        final_response=None,
        error=dto.error,
        reasoning_budget=dto.reasoning_budget,
        status_msg_id=dto.status_msg_id,
        slot_id=dto.slot_id,
        thinking_aborted=False,
        artifact_handles=[],
        transitions=transitions or [],
        last_transition_at=dto.last_transition_at,
    )


def turn_transition_domain_to_dto(
    turn_id: str, transition: TurnTransition
) -> TurnTransitionDTO:
    """Convert a domain ``TurnTransition`` to a persistence DTO."""
    return TurnTransitionDTO(
        turn_id=turn_id,
        from_state=transition.from_state.value,
        to_state=transition.to_state.value,
        at=transition.at,
        reason=transition.note,
    )


def turn_transition_dto_to_domain(dto: TurnTransitionDTO) -> TurnTransition:
    """Convert a persistence ``TurnTransitionDTO`` to a domain object."""
    return TurnTransition(
        from_state=TurnState(dto.from_state),
        to_state=TurnState(dto.to_state),
        at=dto.at,
        note=dto.reason or "",
    )
