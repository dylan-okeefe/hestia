# mypy: disable-error-code="no-untyped-def,import-not-found"
"""Integration tests for the full built-in + meta tool matrix via mock inference.

Run with:
    uv run pytest tests/integration/test_tool_matrix_mock_inference.py -q
"""

from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

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
from hestia.tools.builtin.delegate_task import make_delegate_task_tool


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
async def test_meta_list_tools(
    store, fake_policy, context_builder, tool_registry, respond_callback
):
    """list_tools meta-tool returns the registered tool list."""
    responses = [
        ChatResponse(
            content="",
            reasoning_content=None,
            tool_calls=[ToolCall(id="c1", name="list_tools", arguments={"tag": None})],
            finish_reason="tool_calls",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        ),
        ChatResponse(
            content="Here are your tools.",
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
    session = _make_session("test_meta_list")
    turn = await orchestrator.process_turn(
        session=session,
        user_message=Message(role="user", content="What tools do you have?"),
        respond_callback=respond_callback,
    )
    assert turn.state == TurnState.DONE
    messages = await store.get_messages(session.id)
    tool_msgs = [m for m in messages if m.role == "tool"]
    assert len(tool_msgs) == 1
    assert "current_time" in tool_msgs[0].content


@pytest.mark.asyncio
async def test_meta_call_tool_current_time(
    store, fake_policy, context_builder, tool_registry, respond_callback
):
    """call_tool meta-tool can invoke current_time."""
    responses = [
        ChatResponse(
            content="",
            reasoning_content=None,
            tool_calls=[
                ToolCall(
                    id="c1",
                    name="call_tool",
                    arguments={"name": "current_time", "arguments": {"timezone": "UTC"}},
                )
            ],
            finish_reason="tool_calls",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        ),
        ChatResponse(
            content="The time is now.",
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
    session = _make_session("test_current_time")
    turn = await orchestrator.process_turn(
        session=session,
        user_message=Message(role="user", content="What time is it?"),
        respond_callback=respond_callback,
    )
    assert turn.state == TurnState.DONE
    messages = await store.get_messages(session.id)
    tool_msgs = [m for m in messages if m.role == "tool"]
    assert any("UTC" in (m.content or "") for m in tool_msgs)


@pytest.mark.asyncio
async def test_read_file_and_list_dir(
    store, fake_policy, tool_registry, file_sandbox, respond_callback, responses
):
    """read_file and list_dir via call_tool."""
    sandbox = Path(file_sandbox)
    (sandbox / "hello.txt").write_text("Hello, world!")

    responses_seq = [
        ChatResponse(
            content="",
            reasoning_content=None,
            tool_calls=[
                ToolCall(
                    id="c1",
                    name="call_tool",
                    arguments={
                        "name": "read_file",
                        "arguments": {"path": str(sandbox / "hello.txt")},
                    },
                )
            ],
            finish_reason="tool_calls",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        ),
        ChatResponse(
            content="",
            reasoning_content=None,
            tool_calls=[
                ToolCall(
                    id="c2",
                    name="call_tool",
                    arguments={
                        "name": "list_dir",
                        "arguments": {"path": str(sandbox)},
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
    inference = FakeInferenceClient(responses_seq)
    builder = ContextBuilder(inference, fake_policy, body_factor=1.0)
    orchestrator = Orchestrator(
        inference=inference,
        session_store=store,
        context_builder=builder,
        tool_registry=tool_registry,
        policy=fake_policy,
    )
    session = _make_session("test_read_list")
    turn = await orchestrator.process_turn(
        session=session,
        user_message=Message(role="user", content="Read the file and list the dir."),
        respond_callback=respond_callback,
    )
    assert turn.state == TurnState.DONE
    messages = await store.get_messages(session.id)
    tool_msgs = [m.content for m in messages if m.role == "tool"]
    assert any("Hello, world!" in m for m in tool_msgs)
    assert any("hello.txt" in m for m in tool_msgs)


@pytest.mark.asyncio
async def test_denied_write_file_without_confirm_callback(
    store, fake_policy, context_builder, tool_registry, file_sandbox, respond_callback
):
    """write_file is denied when confirm_callback is None."""
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
                        "arguments": {"path": str(Path(file_sandbox) / "out.txt"), "content": "x"},
                    },
                )
            ],
            finish_reason="tool_calls",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        ),
        ChatResponse(
            content="Cannot write.",
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
        confirm_callback=None,
    )
    session = _make_session("test_denied_write")
    turn = await orchestrator.process_turn(
        session=session,
        user_message=Message(role="user", content="Write a file."),
        respond_callback=respond_callback,
    )
    assert turn.state == TurnState.DONE
    messages = await store.get_messages(session.id)
    tool_msgs = [m.content for m in messages if m.role == "tool"]
    assert any("no confirm_callback is configured" in m for m in tool_msgs)


@pytest.mark.asyncio
async def test_denied_terminal_without_confirm_callback(
    store, fake_policy, context_builder, tool_registry, respond_callback
):
    """terminal is denied when confirm_callback is None."""
    responses = [
        ChatResponse(
            content="",
            reasoning_content=None,
            tool_calls=[
                ToolCall(
                    id="c1",
                    name="call_tool",
                    arguments={
                        "name": "terminal",
                        "arguments": {"command": "echo hello"},
                    },
                )
            ],
            finish_reason="tool_calls",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        ),
        ChatResponse(
            content="Cannot run shell.",
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
        confirm_callback=None,
    )
    session = _make_session("test_denied_terminal")
    turn = await orchestrator.process_turn(
        session=session,
        user_message=Message(role="user", content="Run a command."),
        respond_callback=respond_callback,
    )
    assert turn.state == TurnState.DONE
    messages = await store.get_messages(session.id)
    tool_msgs = [m.content for m in messages if m.role == "tool"]
    assert any("no confirm_callback is configured" in m for m in tool_msgs)


@pytest.mark.asyncio
async def test_http_get_public_url(
    store, fake_policy, context_builder, tool_registry, respond_callback
):
    """http_get fetches a public URL via call_tool (httpx patched for speed)."""
    mock_response = AsyncMock()
    mock_response.text = "Public page content"
    mock_response.raise_for_status = lambda: None

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_response)

    responses = [
        ChatResponse(
            content="",
            reasoning_content=None,
            tool_calls=[
                ToolCall(
                    id="c1",
                    name="call_tool",
                    arguments={
                        "name": "http_get",
                        "arguments": {"url": "http://1.1.1.1/test"},
                    },
                )
            ],
            finish_reason="tool_calls",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        ),
        ChatResponse(
            content="Fetched.",
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
    session = _make_session("test_http_get")
    with patch("httpx.AsyncClient", return_value=mock_client):
        turn = await orchestrator.process_turn(
            session=session,
            user_message=Message(role="user", content="Fetch a page."),
            respond_callback=respond_callback,
        )
    assert turn.state == TurnState.DONE
    messages = await store.get_messages(session.id)
    tool_msgs = [m.content for m in messages if m.role == "tool"]
    assert any("Public page content" in m for m in tool_msgs)


@pytest.mark.asyncio
async def test_artifact_overflow_and_read_artifact(
    store,
    fake_policy,
    context_builder,
    tool_registry,
    artifact_store,
    file_sandbox,
    respond_callback,
):
    """Large read_file result overflows to artifact; read_artifact retrieves it."""
    sandbox = Path(file_sandbox)
    large_content = "A" * 5000
    target = sandbox / "large.txt"
    target.write_text(large_content)

    known_handle = "art_l11_overflow01"

    responses = [
        ChatResponse(
            content="",
            reasoning_content=None,
            tool_calls=[
                ToolCall(
                    id="c1",
                    name="call_tool",
                    arguments={
                        "name": "read_file",
                        "arguments": {"path": str(target)},
                    },
                )
            ],
            finish_reason="tool_calls",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        ),
        ChatResponse(
            content="",
            reasoning_content=None,
            tool_calls=[
                ToolCall(
                    id="c2",
                    name="call_tool",
                    arguments={
                        "name": "read_artifact",
                        "arguments": {"handle": known_handle},
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
    builder = ContextBuilder(inference, fake_policy, body_factor=1.0)
    orchestrator = Orchestrator(
        inference=inference,
        session_store=store,
        context_builder=builder,
        tool_registry=tool_registry,
        policy=fake_policy,
    )
    session = _make_session("test_artifact_overflow")

    # Pin artifact handle so the mock can predict it for read_artifact
    with patch.object(artifact_store, "_generate_handle", return_value=known_handle):
        turn = await orchestrator.process_turn(
            session=session,
            user_message=Message(role="user", content="Read the big file."),
            respond_callback=respond_callback,
        )

    assert turn.state == TurnState.DONE
    messages = await store.get_messages(session.id)
    tool_msgs = [m.content for m in messages if m.role == "tool"]

    # First tool result should mention the artifact
    assert any(known_handle in m for m in tool_msgs)
    # Second tool result should contain the full content
    assert any("A" * 100 in m for m in tool_msgs)


@pytest.mark.asyncio
async def test_delegate_task_minimal(
    store, fake_policy, context_builder, artifact_store, file_sandbox, respond_callback
):
    """delegate_task spawns a subagent and returns a summary."""
    from hestia.tools.builtin import current_time
    from hestia.tools.registry import ToolRegistry

    # Subagent registry: simple tools only (no delegation to avoid recursion)
    sub_registry = ToolRegistry(artifact_store)
    sub_registry.register(current_time)

    # Subagent inference: just return a stop response
    sub_inference = FakeInferenceClient([
        ChatResponse(
            content="Subagent completed the task.",
            reasoning_content=None,
            tool_calls=[],
            finish_reason="stop",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        ),
    ])
    sub_builder = ContextBuilder(sub_inference, fake_policy, body_factor=1.0)

    def sub_orchestrator_factory():
        return Orchestrator(
            inference=sub_inference,
            session_store=store,
            context_builder=sub_builder,
            tool_registry=sub_registry,
            policy=fake_policy,
        )

    delegate_tool = make_delegate_task_tool(store, sub_orchestrator_factory)

    # Parent registry includes delegate_task
    from hestia.tools.builtin import http_get, terminal
    from hestia.tools.builtin.list_dir import make_list_dir_tool
    from hestia.tools.builtin.read_file import make_read_file_tool

    parent_registry = ToolRegistry(artifact_store)
    parent_registry.register(current_time)
    parent_registry.register(http_get)
    parent_registry.register(terminal)
    parent_registry.register(make_read_file_tool([file_sandbox]))
    parent_registry.register(make_list_dir_tool([file_sandbox]))
    parent_registry.register(delegate_tool)

    responses = [
        ChatResponse(
            content="",
            reasoning_content=None,
            tool_calls=[
                ToolCall(
                    id="c1",
                    name="call_tool",
                    arguments={
                        "name": "delegate_task",
                        "arguments": {"task": "Say hello", "context": "minimal test"},
                    },
                )
            ],
            finish_reason="tool_calls",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        ),
        ChatResponse(
            content="Delegation finished.",
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
        tool_registry=parent_registry,
        policy=fake_policy,
    )
    session = _make_session("test_delegate")
    turn = await orchestrator.process_turn(
        session=session,
        user_message=Message(role="user", content="Delegate a task."),
        respond_callback=respond_callback,
    )
    assert turn.state == TurnState.DONE
    messages = await store.get_messages(session.id)
    tool_msgs = [m.content for m in messages if m.role == "tool"]
    assert any("Subagent result: complete" in m for m in tool_msgs)
    assert any("Subagent completed the task" in m for m in tool_msgs)
