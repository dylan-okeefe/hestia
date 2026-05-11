# mypy: disable-error-code="no-untyped-def,import-not-found"
"""Integration tests for memory tools via mock inference.

Run with:
    uv run pytest tests/integration/test_memory_matrix_mock.py -q
"""

from datetime import datetime

import pytest
from helpers import FakeInferenceClient

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


def _make_session(session_id: str = "test_session") -> Session:
    return Session(
        id=session_id,
        platform="test",
        platform_user="user",
        started_at=datetime.now(),
        last_active_at=datetime.now(),
        slot_id=None,
        slot_saved_path=None,
        state=SessionState.ACTIVE,
        temperature=SessionTemperature.COLD,
    )


@pytest.mark.asyncio
async def test_save_memory(store, fake_policy, tool_registry, respond_callback):
    """save_memory via call_tool stores a note."""
    responses = [
        ChatResponse(
            content="",
            reasoning_content=None,
            tool_calls=[
                ToolCall(
                    id="c1",
                    name="call_tool",
                    arguments={
                        "name": "save_memory",
                        "arguments": {
                            "content": "Buy oat milk",
                            "tags": "e2e_hestia_l11 shopping",
                        },
                    },
                )
            ],
            finish_reason="tool_calls",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        ),
        ChatResponse(
            content="Saved.",
            reasoning_content=None,
            tool_calls=[],
            finish_reason="stop",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        ),
    ]
    inference = FakeInferenceClient(responses)
    builder = ContextBuilder(inference, fake_policy, body_factor=1.0)
    orchestrator = Orchestrator(
        inference=inference,
        session_store=store,
        context_builder=builder,
        tool_registry=tool_registry,
        policy=fake_policy,
    )
    session = _make_session("test_save_memory")
    turn = await orchestrator.process_turn(
        session=session,
        user_message=Message(role="user", content="Remember to buy oat milk."),
        respond_callback=respond_callback,
    )
    assert turn.state == TurnState.DONE
    messages = await store.get_messages(session.id)
    tool_msgs = [m.content for m in messages if m.role == "tool"]
    assert any("Saved memory mem_" in m for m in tool_msgs)


@pytest.mark.asyncio
async def test_list_memories_all(
    store, fake_policy, tool_registry, memory_store, respond_callback
):
    """list_memories returns all memories."""
    await memory_store.save("Alpha note", tags=["e2e_hestia_l11", "test"], platform="test", platform_user="user")
    await memory_store.save("Beta note", tags=["other"], platform="test", platform_user="user")

    responses = [
        ChatResponse(
            content="",
            reasoning_content=None,
            tool_calls=[
                ToolCall(
                    id="c1",
                    name="call_tool",
                    arguments={"name": "list_memories", "arguments": {}},
                )
            ],
            finish_reason="tool_calls",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        ),
        ChatResponse(
            content="Listed.",
            reasoning_content=None,
            tool_calls=[],
            finish_reason="stop",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        ),
    ]
    inference = FakeInferenceClient(responses)
    builder = ContextBuilder(inference, fake_policy, body_factor=1.0)
    orchestrator = Orchestrator(
        inference=inference,
        session_store=store,
        context_builder=builder,
        tool_registry=tool_registry,
        policy=fake_policy,
    )
    session = _make_session("test_list_all")
    turn = await orchestrator.process_turn(
        session=session,
        user_message=Message(role="user", content="List my memories."),
        respond_callback=respond_callback,
    )
    assert turn.state == TurnState.DONE
    messages = await store.get_messages(session.id)
    tool_msgs = [m.content for m in messages if m.role == "tool"]
    assert any("Alpha note" in m for m in tool_msgs)
    assert any("Beta note" in m for m in tool_msgs)


@pytest.mark.asyncio
async def test_list_memories_by_tag(
    store, fake_policy, tool_registry, memory_store, respond_callback
):
    """list_memories filtered by tag returns matching subset."""
    await memory_store.save("Tagged item", tags=["e2e_hestia_l11"], platform="test", platform_user="user")
    await memory_store.save("Untagged item", tags=["other"], platform="test", platform_user="user")

    responses = [
        ChatResponse(
            content="",
            reasoning_content=None,
            tool_calls=[
                ToolCall(
                    id="c1",
                    name="call_tool",
                    arguments={
                        "name": "list_memories",
                        "arguments": {"tag": "e2e_hestia_l11"},
                    },
                )
            ],
            finish_reason="tool_calls",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        ),
        ChatResponse(
            content="Listed.",
            reasoning_content=None,
            tool_calls=[],
            finish_reason="stop",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        ),
    ]
    inference = FakeInferenceClient(responses)
    builder = ContextBuilder(inference, fake_policy, body_factor=1.0)
    orchestrator = Orchestrator(
        inference=inference,
        session_store=store,
        context_builder=builder,
        tool_registry=tool_registry,
        policy=fake_policy,
    )
    session = _make_session("test_list_tag")
    turn = await orchestrator.process_turn(
        session=session,
        user_message=Message(role="user", content="List tagged memories."),
        respond_callback=respond_callback,
    )
    assert turn.state == TurnState.DONE
    messages = await store.get_messages(session.id)
    tool_msgs = [m.content for m in messages if m.role == "tool"]
    assert any("Tagged item" in m for m in tool_msgs)
    assert not any("Untagged item" in m for m in tool_msgs)


@pytest.mark.asyncio
async def test_search_memory(
    store, fake_policy, tool_registry, memory_store, respond_callback
):
    """search_memory returns relevant matches."""
    await memory_store.save("Project Phoenix roadmap", tags=["e2e_hestia_l11", "project"], platform="test", platform_user="user")
    await memory_store.save("Grocery list: eggs", tags=["e2e_hestia_l11", "personal"], platform="test", platform_user="user")

    responses = [
        ChatResponse(
            content="",
            reasoning_content=None,
            tool_calls=[
                ToolCall(
                    id="c1",
                    name="call_tool",
                    arguments={
                        "name": "search_memory",
                        "arguments": {"query": "Phoenix", "limit": 5},
                    },
                )
            ],
            finish_reason="tool_calls",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        ),
        ChatResponse(
            content="Found it.",
            reasoning_content=None,
            tool_calls=[],
            finish_reason="stop",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        ),
    ]
    inference = FakeInferenceClient(responses)
    builder = ContextBuilder(inference, fake_policy, body_factor=1.0)
    orchestrator = Orchestrator(
        inference=inference,
        session_store=store,
        context_builder=builder,
        tool_registry=tool_registry,
        policy=fake_policy,
    )
    session = _make_session("test_search")
    turn = await orchestrator.process_turn(
        session=session,
        user_message=Message(role="user", content="Search for Phoenix."),
        respond_callback=respond_callback,
    )
    assert turn.state == TurnState.DONE
    messages = await store.get_messages(session.id)
    tool_msgs = [m.content for m in messages if m.role == "tool"]
    assert any("Phoenix" in m for m in tool_msgs)
    assert not any("eggs" in m for m in tool_msgs)


@pytest.mark.asyncio
async def test_search_memory_no_results(
    store, fake_policy, tool_registry, memory_store, respond_callback
):
    """search_memory returns no-results message when query misses."""
    responses = [
        ChatResponse(
            content="",
            reasoning_content=None,
            tool_calls=[
                ToolCall(
                    id="c1",
                    name="call_tool",
                    arguments={
                        "name": "search_memory",
                        "arguments": {"query": "xyznonexistent"},
                    },
                )
            ],
            finish_reason="tool_calls",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        ),
        ChatResponse(
            content="Nothing found.",
            reasoning_content=None,
            tool_calls=[],
            finish_reason="stop",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        ),
    ]
    inference = FakeInferenceClient(responses)
    builder = ContextBuilder(inference, fake_policy, body_factor=1.0)
    orchestrator = Orchestrator(
        inference=inference,
        session_store=store,
        context_builder=builder,
        tool_registry=tool_registry,
        policy=fake_policy,
    )
    session = _make_session("test_search_empty")
    turn = await orchestrator.process_turn(
        session=session,
        user_message=Message(role="user", content="Search for xyznonexistent."),
        respond_callback=respond_callback,
    )
    assert turn.state == TurnState.DONE
    messages = await store.get_messages(session.id)
    tool_msgs = [m.content for m in messages if m.role == "tool"]
    assert any("No memories found" in m for m in tool_msgs)
