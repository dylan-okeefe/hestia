"""Tests for token usage display in chat and ask commands."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hestia.core.types import Session, SessionState, SessionTemperature
from hestia.persistence.trace_store import TraceRecord


@pytest.fixture
def sample_session():
    """Create a sample session."""
    return Session(
        id="test_session_123",
        platform="cli",
        platform_user="test_user",
        started_at=datetime.now(),
        last_active_at=datetime.now(),
        slot_id=None,
        slot_saved_path=None,
        state=SessionState.ACTIVE,
        temperature=SessionTemperature.COLD,
    )


@pytest.fixture
def mock_app(sample_session):
    """Create a mocked app context for chat commands."""
    app = MagicMock()
    app.config.inference.model_name = "test-model"
    app.verbose = True

    session_store = MagicMock()
    session_store.get_or_create_session = AsyncMock(return_value=sample_session)
    app.session_store = session_store

    trace = TraceRecord(
        id="trace-1",
        session_id=sample_session.id,
        turn_id="turn-1",
        started_at=datetime.now(),
        ended_at=datetime.now(),
        user_input_summary="hello",
        tools_called=[],
        tool_call_count=0,
        delegated=False,
        outcome="success",
        artifact_handles=[],
        prompt_tokens=1000,
        completion_tokens=200,
        reasoning_tokens=None,
        total_duration_ms=500,
    )
    trace_store = MagicMock()
    trace_store.get_by_turn = AsyncMock(return_value=trace)
    app.trace_store = trace_store

    app.epoch_compiler = None
    app.close = AsyncMock()
    context_builder = MagicMock()
    context_builder.warm_up = AsyncMock()
    app.context_builder = context_builder

    orchestrator = MagicMock()
    turn = MagicMock()
    turn.id = "turn-1"
    orchestrator.process_turn = AsyncMock(return_value=turn)
    orchestrator.recover_stale_turns = AsyncMock(return_value=0)
    app.make_orchestrator.return_value = orchestrator

    return app


@pytest.mark.asyncio
async def test_cmd_ask_shows_tokens_when_verbose(mock_app, capsys):
    """cmd_ask should display token usage when verbose=True."""
    from hestia.commands.chat import cmd_ask

    with patch("hestia.commands.chat.click.echo") as mock_echo:
        await cmd_ask(mock_app, "Hello world")

    # Find the token usage echo call
    token_calls = [
        call for call in mock_echo.call_args_list
        if "Tokens:" in str(call)
    ]
    assert len(token_calls) == 1
    assert "Tokens: 1,000 prompt + 200 completion = 1,200 total" in str(token_calls[0])


@pytest.mark.asyncio
async def test_cmd_ask_hides_tokens_when_not_verbose(mock_app, capsys):
    """cmd_ask should not display token usage when verbose=False."""
    from hestia.commands.chat import cmd_ask

    mock_app.verbose = False

    with patch("hestia.commands.chat.click.echo") as mock_echo:
        await cmd_ask(mock_app, "Hello world")

    token_calls = [
        call for call in mock_echo.call_args_list
        if "Tokens:" in str(call)
    ]
    assert len(token_calls) == 0


@pytest.mark.asyncio
async def test_cmd_ask_shows_reasoning_tokens(mock_app):
    """cmd_ask should include reasoning tokens when present."""
    from hestia.commands.chat import cmd_ask

    trace = TraceRecord(
        id="trace-1",
        session_id=mock_app.session_store.get_or_create_session.return_value.id,
        turn_id="turn-1",
        started_at=datetime.now(),
        ended_at=datetime.now(),
        user_input_summary="hello",
        tools_called=[],
        tool_call_count=0,
        delegated=False,
        outcome="success",
        artifact_handles=[],
        prompt_tokens=1000,
        completion_tokens=200,
        reasoning_tokens=50,
        total_duration_ms=500,
    )
    mock_app.trace_store.get_by_turn = AsyncMock(return_value=trace)

    with patch("hestia.commands.chat.click.echo") as mock_echo:
        await cmd_ask(mock_app, "Hello world")

    token_calls = [
        call for call in mock_echo.call_args_list
        if "Tokens:" in str(call)
    ]
    assert len(token_calls) == 1
    assert "(+ 50 reasoning)" in str(token_calls[0])
