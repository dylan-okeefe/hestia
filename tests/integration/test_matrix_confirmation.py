# mypy: disable-error-code="no-untyped-def,import-not-found"
"""Integration test for Matrix confirmation callback via mock inference.

Run with:
    uv run pytest tests/integration/test_matrix_confirmation.py -q
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from nio import RoomSendResponse

from hestia.config import MatrixConfig
from hestia.context.builder import ContextBuilder
from hestia.core.types import (
    ChatResponse,
    Message,
    Session,
    SessionState,
    SessionTemperature,
    ToolCall,
)
from hestia.orchestrator import Orchestrator, TurnState
from hestia.platforms.matrix_adapter import MatrixAdapter
from hestia.persistence.db import Database
from hestia.persistence.sessions import SessionStore
from hestia.tools.registry import ToolRegistry


def _make_session(session_id: str = "test_session") -> Session:
    return Session(
        id=session_id,
        platform="matrix",
        platform_user="!room:matrix.org",
        started_at=datetime.now(),
        last_active_at=datetime.now(),
        slot_id=None,
        slot_saved_path=None,
        state=SessionState.ACTIVE,
        temperature=SessionTemperature.COLD,
    )


class FakePolicy:
    """Minimal fake policy for confirmation tests."""

    def auto_approve(self, tool_name, session):
        return False

    def filter_tools(self, session, tool_names, registry):
        return tool_names

    def reasoning_budget(self, session, iteration):
        return 2048

    def turn_token_budget(self, session):
        return 4000

    def tool_result_max_chars(self, tool_name):
        return 4000

    def should_delegate(self, *args, **kwargs):
        return False

    def should_compress(self, *args, **kwargs):
        return False

    def retry_after_error(self, error, attempt):
        from hestia.policy.engine import RetryAction, RetryDecision

        return RetryDecision(action=RetryAction.FAIL)


class FakeInferenceClient:
    """Fake inference client for testing."""

    def __init__(self, responses):
        self.responses = responses
        self.call_count = 0

    async def chat(self, messages, tools=None, slot_id=None, **kwargs):
        response = self.responses[self.call_count]
        self.call_count += 1
        return response

    async def count_request(self, messages, tools):
        return 100

    async def close(self):
        pass


async def _make_orchestrator(approve: bool):
    """Build an orchestrator with a MatrixAdapter confirm callback."""
    db = Database("sqlite+aiosqlite:///:memory:")
    await db.connect()
    await db.create_tables()
    store = SessionStore(db)

    registry = ToolRegistry("/tmp/artifacts")
    from hestia.tools.builtin.write_file import make_write_file_tool

    import os

    sandbox = "/tmp/sandbox_matrix_confirm"
    os.makedirs(sandbox, exist_ok=True)
    registry.register(make_write_file_tool([sandbox]))

    adapter = MatrixAdapter(
        MatrixConfig(
            access_token="test_token",
            user_id="@bot:matrix.org",
            allowed_rooms=["!room:matrix.org"],
        )
    )
    mock_client = AsyncMock()
    mock_client.room_send.return_value = RoomSendResponse(
        event_id="$confirm_prompt", room_id="!room:matrix.org"
    )
    mock_client.sync = AsyncMock()
    adapter._client = mock_client

    policy = FakePolicy()

    async def confirm_callback(tool_name: str, arguments: dict) -> bool:
        return await adapter.request_confirmation(
            "!room:matrix.org", tool_name, arguments
        )

    responses = [
        ChatResponse(
            content="",
            reasoning_content=None,
            tool_calls=[
                ToolCall(
                    id="c1",
                    name="call_tool",
                    arguments={
                        "name": "write_file",
                        "arguments": {"path": "/tmp/sandbox_matrix_confirm/test.txt", "content": "hello"},
                    },
                )
            ],
            finish_reason="tool_calls",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        ),
        ChatResponse(
            content="Done.",
            reasoning_content=None,
            tool_calls=[],
            finish_reason="stop",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        ),
    ]
    inference = FakeInferenceClient(responses)
    builder = ContextBuilder(inference, policy, body_factor=1.0)
    orchestrator = Orchestrator(
        inference=inference,
        session_store=store,
        context_builder=builder,
        tool_registry=registry,
        policy=policy,
        confirm_callback=confirm_callback,
    )
    return orchestrator, adapter, store, db


@pytest.mark.asyncio
async def test_matrix_confirmation_approves_tool():
    """End-to-end: model calls write_file, Matrix reply 'yes' approves it."""
    orchestrator, adapter, store, db = await _make_orchestrator(approve=True)

    session = _make_session("test_matrix_confirm_yes")
    responses_list: list[str] = []

    async def respond(response_text: str) -> None:
        responses_list.append(response_text)

    turn_task = asyncio.create_task(
        orchestrator.process_turn(
            session=session,
            user_message=Message(role="user", content="Write a file."),
            respond_callback=respond,
        )
    )

    await asyncio.sleep(0.2)

    mock_event = MagicMock()
    mock_event.sender = "@user:matrix.org"
    mock_event.body = "yes"
    mock_event.source = {
        "content": {
            "m.relates_to": {
                "m.in_reply_to": {"event_id": "$confirm_prompt"}
            }
        }
    }
    mock_room = MagicMock()
    mock_room.room_id = "!room:matrix.org"
    await adapter._handle_room_message(mock_room, mock_event)

    turn = await asyncio.wait_for(turn_task, timeout=5)
    assert turn.state == TurnState.DONE
    messages = await store.get_messages(session.id)
    tool_msgs = [m.content for m in messages if m.role == "tool"]
    assert any("Wrote" in (m or "") for m in tool_msgs)
    await db.close()


@pytest.mark.asyncio
async def test_matrix_confirmation_denies_tool():
    """End-to-end: model calls write_file, Matrix reply 'no' denies it."""
    orchestrator, adapter, store, db = await _make_orchestrator(approve=False)

    session = _make_session("test_matrix_confirm_no")
    responses_list: list[str] = []

    async def respond(response_text: str) -> None:
        responses_list.append(response_text)

    turn_task = asyncio.create_task(
        orchestrator.process_turn(
            session=session,
            user_message=Message(role="user", content="Write a file."),
            respond_callback=respond,
        )
    )

    await asyncio.sleep(0.2)

    mock_event = MagicMock()
    mock_event.sender = "@user:matrix.org"
    mock_event.body = "no"
    mock_event.source = {
        "content": {
            "m.relates_to": {
                "m.in_reply_to": {"event_id": "$confirm_prompt"}
            }
        }
    }
    mock_room = MagicMock()
    mock_room.room_id = "!room:matrix.org"
    await adapter._handle_room_message(mock_room, mock_event)

    turn = await asyncio.wait_for(turn_task, timeout=5)
    assert turn.state == TurnState.DONE
    messages = await store.get_messages(session.id)
    tool_msgs = [m.content for m in messages if m.role == "tool"]
    assert any("cancelled by user" in (m or "").lower() for m in tool_msgs)
    await db.close()
