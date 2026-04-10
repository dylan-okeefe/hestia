"""Turn state machine transition table and validation."""

from hestia.errors import IllegalTransitionError
from hestia.orchestrator.types import TurnState

# Allowed transitions: from_state -> set of valid to_states
ALLOWED_TRANSITIONS: dict[TurnState, set[TurnState]] = {
    TurnState.RECEIVED: {TurnState.BUILDING_CONTEXT, TurnState.FAILED},
    TurnState.BUILDING_CONTEXT: {TurnState.AWAITING_MODEL, TurnState.FAILED},
    TurnState.AWAITING_MODEL: {
        TurnState.EXECUTING_TOOLS,
        TurnState.DONE,
        TurnState.RETRYING,
        TurnState.FAILED,
    },
    TurnState.EXECUTING_TOOLS: {
        TurnState.AWAITING_USER,
        TurnState.BUILDING_CONTEXT,  # loop back for next model call
        TurnState.FAILED,
    },
    TurnState.AWAITING_USER: {TurnState.EXECUTING_TOOLS, TurnState.FAILED},
    TurnState.RETRYING: {TurnState.AWAITING_MODEL, TurnState.FAILED},
    TurnState.AWAITING_SUBAGENT: set(),  # Phase 3
    TurnState.COMPRESSING: set(),  # Phase 3
    TurnState.DONE: set(),
    TurnState.FAILED: set(),
}


def assert_transition(from_state: TurnState, to_state: TurnState) -> None:
    """Validate that a transition is allowed.

    Args:
        from_state: Current state
        to_state: Desired next state

    Raises:
        IllegalTransitionError: If the transition is not allowed
    """
    allowed = ALLOWED_TRANSITIONS.get(from_state, set())
    if to_state not in allowed:
        raise IllegalTransitionError(
            f"Cannot transition from {from_state.value} to {to_state.value}"
        )
