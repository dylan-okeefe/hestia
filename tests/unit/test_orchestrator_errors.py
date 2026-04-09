"""Unit tests for Orchestrator error handling."""

from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from hestia.artifacts.store import ArtifactStore
from hestia.context.builder import ContextBuilder
from hestia.core.types import ChatResponse, Message, Session, SessionState, SessionTemperature, ToolCall
from hestia.orchestrator import Orchestrator, TurnState
from hestia.persistence.db import Database
from hestia.persistence.sessions import SessionStore
from hestia.tools.metadata import tool
from hestia.tools.registry import ToolRegistry


class FakeInferenceClient:
    """Fake inference client that returns canned responses."""

    def __init__(self, responses):
        self.responses = responses
        self.call_count = 0

    async def count_request(self, messages, tools):
        total = 0
        for msg in messages:
            total += 10 + len(msg.content) // 4
        for tool in tools:
            total += 50
        return total

    async def chat(self, messages, tools=None, slot_id=None, **kwargs):
        if self.call_count < len(self.responses):
            response = self.responses[self.call_count]
            self.call_count += 1
            return response
        raise RuntimeError("No more canned responses")


class FakePolicyEngine:
    """Fake policy engine."""

    def should_delegate(self, session, task_description):
        return False

    def should_compress(self, session, tokens_used, tokens_budget):
        return False

    def should_evict_slot(self, slot_id, pressure):
        return False

    def retry_after_error(self, error, attempt):
        from hestia.policy.engine import RetryAction, RetryDecision
        return RetryDecision(action=RetryAction.FAIL)

    def turn_token_budget(self, session):
        return 4000

    def tool_result_max_chars(self, tool_name):
        return 4000


@pytest.fixture
async def store(tmp_path):
    """Create a SessionStore with temp database."""
    db_url = f"sqlite+aiosqlite:///{tmp_path}/test.db"
    db = Database(db_url)
    await db.connect()
    await db.create_tables()
    store = SessionStore(db)
    yield store
    await db.close()


@pytest.fixture
def artifact_store(tmp_path):
    """Artifact store in temp directory."""
    return ArtifactStore(tmp_path / "artifacts")


@pytest.fixture
def tool_registry(artifact_store):
    """Tool registry with no tools."""
    return ToolRegistry(artifact_store)


@pytest.mark.asyncio
async def test_empty_response_error_on_stop_with_empty_content(store, tool_registry):
    """Empty content with finish_reason='stop' should fail the turn, not return blank."""
    fake_policy = FakePolicyEngine()
    
    # Create inference that returns empty content with stop
    empty_response = ChatResponse(
        content="",
        reasoning_content=None,
        tool_calls=[],
        finish_reason="stop",
        prompt_tokens=10,
        completion_tokens=0,
        total_tokens=10,
    )
    inference = FakeInferenceClient([empty_response])
    
    context_builder = ContextBuilder(inference, fake_policy, body_factor=1.0)
    
    session = Session(
        id="test_session_empty",
        platform="test",
        platform_user="user",
        started_at=datetime.now(),
        last_active_at=datetime.now(),
        slot_id=None,
        slot_saved_path=None,
        state=SessionState.ACTIVE,
        temperature=SessionTemperature.COLD,
    )
    
    orchestrator = Orchestrator(
        inference=inference,
        session_store=store,
        context_builder=context_builder,
        tool_registry=tool_registry,
        policy=fake_policy,
        max_iterations=10,
    )
    
    respond_callback = AsyncMock()
    user_message = Message(role="user", content="Hello")
    
    # Should not raise - exception is caught internally
    turn = await orchestrator.process_turn(
        session=session,
        user_message=user_message,
        respond_callback=respond_callback,
    )
    
    # Turn should be FAILED
    assert turn.state == TurnState.FAILED
    assert turn.error is not None
    assert "EmptyResponseError" in turn.error or "empty content" in turn.error
    
    # Response callback should have been called with error, not empty string
    respond_callback.assert_called_once()
    call_args = respond_callback.call_args[0][0]
    assert "Error:" in call_args
    assert call_args != ""


@pytest.mark.asyncio
async def test_empty_response_error_on_length_with_empty_content(store, tool_registry):
    """Empty content with finish_reason='length' should also fail the turn."""
    fake_policy = FakePolicyEngine()
    
    empty_response = ChatResponse(
        content="   ",  # whitespace-only counts as empty
        reasoning_content=None,
        tool_calls=[],
        finish_reason="length",
        prompt_tokens=10,
        completion_tokens=0,
        total_tokens=10,
    )
    inference = FakeInferenceClient([empty_response])
    
    context_builder = ContextBuilder(inference, fake_policy, body_factor=1.0)
    
    session = Session(
        id="test_session_length",
        platform="test",
        platform_user="user",
        started_at=datetime.now(),
        last_active_at=datetime.now(),
        slot_id=None,
        slot_saved_path=None,
        state=SessionState.ACTIVE,
        temperature=SessionTemperature.COLD,
    )
    
    orchestrator = Orchestrator(
        inference=inference,
        session_store=store,
        context_builder=context_builder,
        tool_registry=tool_registry,
        policy=fake_policy,
        max_iterations=10,
    )
    
    respond_callback = AsyncMock()
    user_message = Message(role="user", content="Hello")
    
    turn = await orchestrator.process_turn(
        session=session,
        user_message=user_message,
        respond_callback=respond_callback,
    )
    
    assert turn.state == TurnState.FAILED
    assert turn.error is not None
    respond_callback.assert_called_once()


# Tool requiring confirmation for testing
@tool(
    name="dangerous_tool",
    public_description="A tool that requires confirmation.",
    parameters_schema={"type": "object", "properties": {}},
    requires_confirmation=True,
)
async def dangerous_tool() -> str:
    return "Executed dangerous operation"


@pytest.mark.asyncio
async def test_confirm_callback_missing_fails_closed_direct_path(store, artifact_store):
    """Direct tool path: requires_confirmation should error if no confirm_callback."""
    fake_policy = FakePolicyEngine()
    
    # Register a tool that requires confirmation
    registry = ToolRegistry(artifact_store)
    registry.register(dangerous_tool)
    
    # Create inference that triggers the dangerous tool via DIRECT call
    tool_call_response = ChatResponse(
        content="",
        reasoning_content=None,
        tool_calls=[
            ToolCall(id="call_1", name="dangerous_tool", arguments={})
        ],
        finish_reason="tool_calls",
        prompt_tokens=20,
        completion_tokens=10,
        total_tokens=30,
    )
    final_response = ChatResponse(
        content="Done.",
        reasoning_content=None,
        tool_calls=[],
        finish_reason="stop",
        prompt_tokens=30,
        completion_tokens=5,
        total_tokens=35,
    )
    inference = FakeInferenceClient([tool_call_response, final_response])
    
    context_builder = ContextBuilder(inference, fake_policy, body_factor=1.0)
    
    session = Session(
        id="test_session_confirm_direct",
        platform="test",
        platform_user="user",
        started_at=datetime.now(),
        last_active_at=datetime.now(),
        slot_id=None,
        slot_saved_path=None,
        state=SessionState.ACTIVE,
        temperature=SessionTemperature.COLD,
    )
    
    # Create orchestrator WITHOUT confirm_callback
    orchestrator = Orchestrator(
        inference=inference,
        session_store=store,
        context_builder=context_builder,
        tool_registry=registry,
        policy=fake_policy,
        confirm_callback=None,  # No callback!
        max_iterations=10,
    )
    
    respond_callback = AsyncMock()
    user_message = Message(role="user", content="Run dangerous tool")
    
    turn = await orchestrator.process_turn(
        session=session,
        user_message=user_message,
        respond_callback=respond_callback,
    )
    
    # Turn should complete (not fail) but the tool result should be an error
    assert turn.state == TurnState.DONE
    
    # Verify the tool message in history shows the error
    messages = await store.get_messages(session.id)
    tool_messages = [m for m in messages if m.role == "tool"]
    assert len(tool_messages) == 1
    assert tool_messages[0].content == (
        "Tool 'dangerous_tool' requires user confirmation but no "
        "confirm_callback is configured on this orchestrator."
    )


@pytest.mark.asyncio
async def test_meta_tool_confirm_callback_missing_fails_closed(store, artifact_store):
    """Meta-tool path (call_tool): requires_confirmation should error if no confirm_callback."""
    fake_policy = FakePolicyEngine()
    
    # Register a tool that requires confirmation
    registry = ToolRegistry(artifact_store)
    registry.register(dangerous_tool)
    
    # Create inference that triggers the dangerous tool via META-TOOL call
    tool_call_response = ChatResponse(
        content="",
        reasoning_content=None,
        tool_calls=[
            ToolCall(
                id="call_1",
                name="call_tool",  # Meta-tool pattern!
                arguments={"name": "dangerous_tool", "arguments": {}}
            )
        ],
        finish_reason="tool_calls",
        prompt_tokens=20,
        completion_tokens=10,
        total_tokens=30,
    )
    final_response = ChatResponse(
        content="Done.",
        reasoning_content=None,
        tool_calls=[],
        finish_reason="stop",
        prompt_tokens=30,
        completion_tokens=5,
        total_tokens=35,
    )
    inference = FakeInferenceClient([tool_call_response, final_response])
    
    context_builder = ContextBuilder(inference, fake_policy, body_factor=1.0)
    
    session = Session(
        id="test_session_confirm_meta",
        platform="test",
        platform_user="user",
        started_at=datetime.now(),
        last_active_at=datetime.now(),
        slot_id=None,
        slot_saved_path=None,
        state=SessionState.ACTIVE,
        temperature=SessionTemperature.COLD,
    )
    
    # Create orchestrator WITHOUT confirm_callback
    orchestrator = Orchestrator(
        inference=inference,
        session_store=store,
        context_builder=context_builder,
        tool_registry=registry,
        policy=fake_policy,
        confirm_callback=None,  # No callback!
        max_iterations=10,
    )
    
    respond_callback = AsyncMock()
    user_message = Message(role="user", content="Run dangerous tool")
    
    turn = await orchestrator.process_turn(
        session=session,
        user_message=user_message,
        respond_callback=respond_callback,
    )
    
    # Turn should complete (not fail) but the tool result should be an error
    assert turn.state == TurnState.DONE
    
    # Verify the tool message in history shows the error (not the tool's success message)
    messages = await store.get_messages(session.id)
    tool_messages = [m for m in messages if m.role == "tool"]
    assert len(tool_messages) == 1
    assert "requires user confirmation" in tool_messages[0].content
    assert "Executed dangerous operation" not in tool_messages[0].content  # Tool did NOT run


@pytest.mark.asyncio
async def test_meta_tool_confirm_callback_denial_respected(store, artifact_store):
    """Meta-tool path: user denial should cancel the tool."""
    fake_policy = FakePolicyEngine()
    
    # Register a tool that requires confirmation
    registry = ToolRegistry(artifact_store)
    registry.register(dangerous_tool)
    
    # Create inference that triggers the dangerous tool via META-TOOL call
    tool_call_response = ChatResponse(
        content="",
        reasoning_content=None,
        tool_calls=[
            ToolCall(
                id="call_1",
                name="call_tool",
                arguments={"name": "dangerous_tool", "arguments": {}}
            )
        ],
        finish_reason="tool_calls",
        prompt_tokens=20,
        completion_tokens=10,
        total_tokens=30,
    )
    final_response = ChatResponse(
        content="Done.",
        reasoning_content=None,
        tool_calls=[],
        finish_reason="stop",
        prompt_tokens=30,
        completion_tokens=5,
        total_tokens=35,
    )
    inference = FakeInferenceClient([tool_call_response, final_response])
    
    context_builder = ContextBuilder(inference, fake_policy, body_factor=1.0)
    
    session = Session(
        id="test_session_confirm_denied",
        platform="test",
        platform_user="user",
        started_at=datetime.now(),
        last_active_at=datetime.now(),
        slot_id=None,
        slot_saved_path=None,
        state=SessionState.ACTIVE,
        temperature=SessionTemperature.COLD,
    )
    
    # Create orchestrator with a callback that DENIES confirmation
    async def deny_callback(tool_name: str, arguments: dict) -> bool:
        return False
    
    orchestrator = Orchestrator(
        inference=inference,
        session_store=store,
        context_builder=context_builder,
        tool_registry=registry,
        policy=fake_policy,
        confirm_callback=deny_callback,  # Always denies
        max_iterations=10,
    )
    
    respond_callback = AsyncMock()
    user_message = Message(role="user", content="Run dangerous tool")
    
    turn = await orchestrator.process_turn(
        session=session,
        user_message=user_message,
        respond_callback=respond_callback,
    )
    
    # Turn should complete but tool was cancelled
    assert turn.state == TurnState.DONE
    
    # Verify the tool message shows cancellation (not the tool's success message)
    messages = await store.get_messages(session.id)
    tool_messages = [m for m in messages if m.role == "tool"]
    assert len(tool_messages) == 1
    assert tool_messages[0].content == "Tool execution was cancelled by user."
    assert "Executed dangerous operation" not in tool_messages[0].content  # Tool did NOT run
