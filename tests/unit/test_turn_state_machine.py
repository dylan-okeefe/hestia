"""Unit tests for Turn state machine."""

from datetime import datetime

import pytest

from hestia.errors import IllegalTransitionError
from hestia.orchestrator.transitions import ALLOWED_TRANSITIONS, assert_transition
from hestia.orchestrator.types import Turn, TurnState, TurnTransition


class TestAllowedTransitions:
    """Tests for the transition table."""

    def test_received_can_build_or_fail(self):
        """RECEIVED can transition to BUILDING_CONTEXT or FAILED."""
        assert TurnState.BUILDING_CONTEXT in ALLOWED_TRANSITIONS[TurnState.RECEIVED]
        assert TurnState.FAILED in ALLOWED_TRANSITIONS[TurnState.RECEIVED]

    def test_building_context_can_await_or_fail(self):
        """BUILDING_CONTEXT can transition to AWAITING_MODEL or FAILED."""
        assert TurnState.AWAITING_MODEL in ALLOWED_TRANSITIONS[TurnState.BUILDING_CONTEXT]
        assert TurnState.FAILED in ALLOWED_TRANSITIONS[TurnState.BUILDING_CONTEXT]

    def test_awaiting_model_multiple_outcomes(self):
        """AWAITING_MODEL has multiple valid outcomes."""
        allowed = ALLOWED_TRANSITIONS[TurnState.AWAITING_MODEL]
        assert TurnState.EXECUTING_TOOLS in allowed
        assert TurnState.DONE in allowed
        assert TurnState.RETRYING in allowed
        assert TurnState.FAILED in allowed

    def test_executing_tools_can_loop_or_fail(self):
        """EXECUTING_TOOLS can loop to BUILDING_CONTEXT or go to AWAITING_USER/FAILED."""
        allowed = ALLOWED_TRANSITIONS[TurnState.EXECUTING_TOOLS]
        assert TurnState.BUILDING_CONTEXT in allowed
        assert TurnState.AWAITING_USER in allowed
        assert TurnState.FAILED in allowed

    def test_retrying_can_await_or_fail(self):
        """RETRYING can go back to AWAITING_MODEL or to FAILED."""
        assert TurnState.AWAITING_MODEL in ALLOWED_TRANSITIONS[TurnState.RETRYING]
        assert TurnState.FAILED in ALLOWED_TRANSITIONS[TurnState.RETRYING]

    def test_terminal_states_have_no_outbound(self):
        """DONE and FAILED are terminal - no outbound transitions."""
        assert ALLOWED_TRANSITIONS[TurnState.DONE] == set()
        assert ALLOWED_TRANSITIONS[TurnState.FAILED] == set()

    def test_phase3_states_empty(self):
        """AWAITING_SUBAGENT and COMPRESSING are reserved for Phase 3."""
        assert ALLOWED_TRANSITIONS[TurnState.AWAITING_SUBAGENT] == set()
        assert ALLOWED_TRANSITIONS[TurnState.COMPRESSING] == set()


# Module-level tests for assert_transition (avoiding pytest-asyncio class issues)
def test_allowed_transition_passes():
    """Allowed transitions do not raise."""
    assert_transition(TurnState.RECEIVED, TurnState.BUILDING_CONTEXT)
    assert_transition(TurnState.AWAITING_MODEL, TurnState.DONE)
    assert_transition(TurnState.EXECUTING_TOOLS, TurnState.BUILDING_CONTEXT)


def test_disallowed_transition_raises():
    """Disallowed transitions raise IllegalTransitionError."""
    with pytest.raises(IllegalTransitionError):
        assert_transition(TurnState.DONE, TurnState.RECEIVED)

    with pytest.raises(IllegalTransitionError):
        assert_transition(TurnState.FAILED, TurnState.RETRYING)

    with pytest.raises(IllegalTransitionError):
        assert_transition(TurnState.RECEIVED, TurnState.DONE)


def test_error_message_contains_state_names():
    """Error message includes the state names for debugging."""
    with pytest.raises(IllegalTransitionError) as exc_info:
        assert_transition(TurnState.DONE, TurnState.RECEIVED)

    assert "done" in str(exc_info.value)
    assert "received" in str(exc_info.value)


class TestTurnDataclass:
    """Tests for Turn and TurnTransition dataclasses."""

    def test_turn_creation(self):
        """Turn can be created with required fields."""
        turn = Turn(
            id="turn_123",
            session_id="session_456",
            state=TurnState.RECEIVED,
            user_message=None,
            started_at=datetime.now(),
        )
        assert turn.id == "turn_123"
        assert turn.state == TurnState.RECEIVED
        assert turn.iterations == 0
        assert turn.transitions == []

    def test_turn_with_transitions(self):
        """Turn can have transitions added."""
        now = datetime.now()
        transition = TurnTransition(
            from_state=TurnState.RECEIVED,
            to_state=TurnState.BUILDING_CONTEXT,
            at=now,
            note="Starting build",
        )
        turn = Turn(
            id="turn_123",
            session_id="session_456",
            state=TurnState.BUILDING_CONTEXT,
            user_message=None,
            started_at=now,
            transitions=[transition],
        )
        assert len(turn.transitions) == 1
        assert turn.transitions[0].note == "Starting build"

    def test_turn_state_changes(self):
        """Turn state can be updated."""
        turn = Turn(
            id="turn_123",
            session_id="session_456",
            state=TurnState.RECEIVED,
            user_message=None,
            started_at=datetime.now(),
        )
        turn.state = TurnState.BUILDING_CONTEXT
        assert turn.state == TurnState.BUILDING_CONTEXT

    def test_turn_completion(self):
        """Turn tracks completion state."""
        turn = Turn(
            id="turn_123",
            session_id="session_456",
            state=TurnState.DONE,
            user_message=None,
            started_at=datetime.now(),
            completed_at=datetime.now(),
            final_response="Hello!",
        )
        assert turn.final_response == "Hello!"
        assert turn.completed_at is not None

    def test_turn_failure(self):
        """Turn tracks failure state."""
        turn = Turn(
            id="turn_123",
            session_id="session_456",
            state=TurnState.FAILED,
            user_message=None,
            started_at=datetime.now(),
            error="Something went wrong",
        )
        assert turn.error == "Something went wrong"
