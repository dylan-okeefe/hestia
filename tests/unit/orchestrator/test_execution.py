"""Unit tests for TurnExecution direct tool dispatch (L161)."""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hestia.core.types import (
    Message,
    Session,
    SessionState,
    SessionTemperature,
    StreamDelta,
    ToolCall,
)
from hestia.errors import MaxIterationsError
from hestia.orchestrator.execution import (
    TurnExecution,
    _normalize_tool_arguments,
)
from hestia.orchestrator.quality import Correction, DegeneratePattern
from hestia.orchestrator.types import Turn, TurnContext, TurnState
from hestia.tools.metadata import ToolMetadata
from hestia.tools.registry import ToolRegistry
from hestia.tools.types import ToolCallResult


def _make_session() -> Session:
    return Session(
        id="test-session",
        platform="test",
        platform_user="user",
        started_at=datetime.now(),
        last_active_at=datetime.now(),
        slot_id=None,
        slot_saved_path=None,
        state=SessionState.ACTIVE,
        temperature=SessionTemperature.HOT,
    )


def _make_turn() -> Turn:
    return Turn(
        id="turn-1",
        session_id="test-session",
        state=TurnState.RECEIVED,
        user_message=Message(role="user", content="hello"),
        started_at=datetime.now(),
    )


@pytest.mark.asyncio
async def test_direct_write_file_dispatch():
    """A direct write_file tool call is dispatched correctly."""
    registry = ToolRegistry(MagicMock())
    async def _write_file(**kwargs: object) -> str:
        return "Wrote file"

    registry._tools["write_file"] = ToolMetadata(
        name="write_file",
        public_description="Write a file",
        internal_description="",
        parameters_schema={},
        requires_confirmation=False,
        ordering="concurrent",
        handler=_write_file,
    )

    execution = TurnExecution(
        tool_registry=registry,
        inference_client=MagicMock(),
        policy=MagicMock(),
        context_builder=MagicMock(),
        session_store=MagicMock(),
    )

    tc = ToolCall(
        id="tc1", name="write_file", arguments={"path": "/tmp/test.txt", "content": "hi"}
    )
    result = await execution._dispatch_tool_call(_make_session(), tc)
    assert result.status == "ok"
    assert "Wrote file" in result.content


def test_call_tool_is_in_dispatch_table():
    """call_tool is present in the meta-tool dispatch table."""
    execution = TurnExecution(
        tool_registry=MagicMock(),
        inference_client=MagicMock(),
        policy=MagicMock(),
        context_builder=MagicMock(),
        session_store=MagicMock(),
    )
    assert hasattr(execution, "_meta_tools")
    assert "call_tool" in execution._meta_tools


@pytest.mark.asyncio
async def test_max_iterations_error_raised(make_chat_response):
    """Canned ChatResponse sequences that exceed max_iterations raise MaxIterationsError."""
    store = MagicMock()
    store.append_message = AsyncMock()

    builder = MagicMock()
    builder.build = AsyncMock(return_value=MagicMock(messages=[]))
    execution = TurnExecution(
        tool_registry=MagicMock(),
        inference_client=MagicMock(),
        policy=MagicMock(),
        context_builder=builder,
        session_store=store,
        max_iterations=2,
    )

    execution._inference.chat = AsyncMock(
        return_value=make_chat_response(
            finish_reason="tool_calls",
            tool_calls=[ToolCall(id="tc1", name="test_tool", arguments={})],
        )
    )

    ctx = TurnContext(
        turn=_make_turn(),
        user_message=Message(role="user", content="hello"),
        system_prompt="",
        respond_callback=AsyncMock(),
        session=_make_session(),
        build_result=MagicMock(messages=[]),
    )

    with patch.object(
        execution, "_handle_tool_calls", new_callable=AsyncMock
    ) as mock_handle:
        # _handle_tool_calls increments iterations and continues the loop
        async def _side_effect(*args, **kwargs):
            ctx.turn.iterations += 1
            return TurnState.BUILDING_CONTEXT

        mock_handle.side_effect = _side_effect

        with pytest.raises(MaxIterationsError) as exc_info:
            await execution.run(ctx, AsyncMock(), AsyncMock())

        assert exc_info.value.max_iterations == 2


@pytest.mark.asyncio
async def test_per_turn_tool_call_cap_enforced():
    """Per-turn tool-call cap exceeded: cap enforced, excess calls get errors."""
    registry = MagicMock()
    registry.describe.return_value = MagicMock(
        requires_confirmation=False, ordering="concurrent"
    )

    policy = MagicMock()
    policy.tool_result_max_chars.return_value = 8000

    execution = TurnExecution(
        tool_registry=registry,
        inference_client=MagicMock(),
        policy=policy,
        context_builder=MagicMock(),
        session_store=MagicMock(),
        max_tool_calls_per_turn=2,
    )

    tool_calls = [
        ToolCall(id="tc1", name="tool_a", arguments={}),
        ToolCall(id="tc2", name="tool_b", arguments={}),
        ToolCall(id="tc3", name="tool_c", arguments={}),
        ToolCall(id="tc4", name="tool_d", arguments={}),
    ]

    with patch.object(
        execution, "_dispatch_tool_call", new_callable=AsyncMock
    ) as mock_dispatch:
        mock_dispatch.return_value = ToolCallResult(
            status="ok",
            content="ok",
            artifact_handle=None,
            truncated=False,
        )

        result_messages, artifact_handles = await execution._execute_tool_calls(
            _make_session(), tool_calls
        )

        # Only first 2 should have been dispatched
        assert mock_dispatch.call_count == 2
        dispatched_names = [call.args[1].name for call in mock_dispatch.call_args_list]
        assert dispatched_names == ["tool_a", "tool_b"]

        # 4 result messages total: 2 cap-rejection errors + 2 real results
        assert len(result_messages) == 4
        assert "too many tool calls" in result_messages[0].content
        assert "too many tool calls" in result_messages[1].content
        assert result_messages[0].tool_call_id == "tc3"
        assert result_messages[1].tool_call_id == "tc4"
        assert result_messages[2].content == "ok"
        assert result_messages[3].content == "ok"
        assert artifact_handles == []


@pytest.mark.asyncio
async def test_repeated_list_tools_blocked_after_first_call():
    """After the first list_tools in a turn, subsequent list_tools calls are
    replaced with a synthetic result instead of being re-executed."""
    registry = MagicMock()
    registry.describe.return_value = MagicMock(
        requires_confirmation=False, ordering="concurrent"
    )

    policy = MagicMock()
    policy.tool_result_max_chars.return_value = 8000

    execution = TurnExecution(
        tool_registry=registry,
        inference_client=MagicMock(),
        policy=policy,
        context_builder=MagicMock(),
        session_store=MagicMock(),
    )

    ctx = TurnContext(
        turn=_make_turn(),
        user_message=Message(role="user", content="hello"),
        system_prompt="",
        respond_callback=AsyncMock(),
        session=_make_session(),
        build_result=MagicMock(messages=[]),
    )
    # ctx.tool_chain has already been extended with the current batch by the
    # caller (_handle_tool_calls). We include a prior list_tools entry so that
    # the current batch's list_tools calls are treated as repeats.
    ctx.tool_chain = ["list_tools", "read_file", "read_file", "read_file"]

    tool_calls = [
        ToolCall(id="tc1", name="list_tools", arguments={}),
        ToolCall(id="tc2", name="read_file", arguments={"path": "/tmp/a.txt"}),
        ToolCall(id="tc3", name="list_tools", arguments={}),
    ]

    with patch.object(
        execution, "_dispatch_tool_call", new_callable=AsyncMock
    ) as mock_dispatch:
        mock_dispatch.return_value = ToolCallResult(
            status="ok",
            content="file contents",
            artifact_handle=None,
            truncated=False,
        )

        result_messages, _artifact_handles = await execution._execute_tool_calls(
            _make_session(), tool_calls, ctx=ctx
        )

        # Only read_file should have been dispatched; both list_tools calls are blocked.
        assert mock_dispatch.call_count == 1
        assert mock_dispatch.call_args[0][1].name == "read_file"

        assert len(result_messages) == 3
        assert result_messages[0].role == "tool"
        assert result_messages[0].tool_call_id == "tc1"
        assert "list_tools is now DISABLED" in result_messages[0].content
        assert result_messages[1].tool_call_id == "tc2"
        assert result_messages[1].content == "file contents"
        assert result_messages[2].tool_call_id == "tc3"
        assert "list_tools is now DISABLED" in result_messages[2].content
        # The context is flagged so the next prompt drops the list_tools schema.
        assert ctx._list_tools_blocked is True


@pytest.mark.asyncio
async def test_first_list_tools_in_batch_is_allowed():
    """When no prior list_tools exists in the turn, the first one executes."""
    registry = MagicMock()
    registry.describe.return_value = MagicMock(
        requires_confirmation=False, ordering="concurrent"
    )

    policy = MagicMock()
    policy.tool_result_max_chars.return_value = 8000

    execution = TurnExecution(
        tool_registry=registry,
        inference_client=MagicMock(),
        policy=policy,
        context_builder=MagicMock(),
        session_store=MagicMock(),
    )

    ctx = TurnContext(
        turn=_make_turn(),
        user_message=Message(role="user", content="hello"),
        system_prompt="",
        respond_callback=AsyncMock(),
        session=_make_session(),
        build_result=MagicMock(messages=[]),
    )
    # Prior tools in the turn, but no list_tools yet.
    ctx.tool_chain = ["read_file", "read_file"]

    tool_calls = [
        ToolCall(id="tc1", name="list_tools", arguments={}),
        ToolCall(id="tc2", name="list_tools", arguments={}),
    ]

    with patch.object(
        execution, "_dispatch_tool_call", new_callable=AsyncMock
    ) as mock_dispatch:
        mock_dispatch.return_value = ToolCallResult(
            status="ok",
            content="tool list",
            artifact_handle=None,
            truncated=False,
        )

        result_messages, _artifact_handles = await execution._execute_tool_calls(
            _make_session(), tool_calls, ctx=ctx
        )

        # First list_tools executes; second is blocked.
        assert mock_dispatch.call_count == 1
        assert mock_dispatch.call_args[0][1].id == "tc1"

        assert len(result_messages) == 2
        assert result_messages[0].tool_call_id == "tc1"
        assert result_messages[0].content == "tool list"
        assert result_messages[1].tool_call_id == "tc2"
        assert "list_tools is now DISABLED" in result_messages[1].content
        assert ctx._list_tools_blocked is True


@pytest.mark.asyncio
async def test_describe_tool_binge_is_blocked_after_three_unique_tools():
    """After describing 3 unique tools, further describe_tool calls are blocked."""
    registry = MagicMock()
    registry.describe.return_value = MagicMock(
        requires_confirmation=False, ordering="concurrent"
    )

    policy = MagicMock()
    policy.tool_result_max_chars.return_value = 8000

    execution = TurnExecution(
        tool_registry=registry,
        inference_client=MagicMock(),
        policy=policy,
        context_builder=MagicMock(),
        session_store=MagicMock(),
    )

    ctx = TurnContext(
        turn=_make_turn(),
        user_message=Message(role="user", content="hello"),
        system_prompt="",
        respond_callback=AsyncMock(),
        session=_make_session(),
        build_result=MagicMock(messages=[]),
    )
    # Prior turn already described read_file, list_dir, and grep.
    ctx.running_history = [
        Message(
            role="assistant",
            content=None,
            tool_calls=[
                ToolCall(
                    id="prev1",
                    name="describe_tool",
                    arguments={"names": ["read_file", "list_dir", "grep"]},
                )
            ],
        ),
        Message(role="tool", content="schemas", tool_call_id="prev1"),
    ]

    tool_calls = [
        ToolCall(id="tc1", name="describe_tool", arguments={"names": ["browser_get"]}),
        ToolCall(id="tc2", name="describe_tool", arguments={"names": "write_file"}),
    ]

    with patch.object(
        execution, "_dispatch_tool_call", new_callable=AsyncMock
    ) as mock_dispatch:
        mock_dispatch.return_value = ToolCallResult(
            status="ok",
            content="schema",
            artifact_handle=None,
            truncated=False,
        )

        result_messages, _artifact_handles = await execution._execute_tool_calls(
            _make_session(), tool_calls, ctx=ctx
        )

        # Both describe_tool calls are blocked; nothing is dispatched.
        assert mock_dispatch.call_count == 0
        assert len(result_messages) == 2
        assert result_messages[0].tool_call_id == "tc1"
        assert "describe_tool is now DISABLED" in result_messages[0].content
        assert result_messages[1].tool_call_id == "tc2"
        assert "describe_tool is now DISABLED" in result_messages[1].content
        assert ctx._describe_tool_blocked is True


@pytest.mark.asyncio
async def test_describe_tool_repeated_name_is_blocked():
    """A describe_tool call for an already-described tool is blocked."""
    registry = MagicMock()
    registry.describe.return_value = MagicMock(
        requires_confirmation=False, ordering="concurrent"
    )

    policy = MagicMock()
    policy.tool_result_max_chars.return_value = 8000

    execution = TurnExecution(
        tool_registry=registry,
        inference_client=MagicMock(),
        policy=policy,
        context_builder=MagicMock(),
        session_store=MagicMock(),
    )

    ctx = TurnContext(
        turn=_make_turn(),
        user_message=Message(role="user", content="hello"),
        system_prompt="",
        respond_callback=AsyncMock(),
        session=_make_session(),
        build_result=MagicMock(messages=[]),
    )
    ctx.running_history = [
        Message(
            role="assistant",
            content=None,
            tool_calls=[
                ToolCall(
                    id="prev1",
                    name="describe_tool",
                    arguments={"names": ["read_file"]},
                )
            ],
        ),
        Message(role="tool", content="schema", tool_call_id="prev1"),
    ]

    tool_calls = [
        ToolCall(id="tc1", name="describe_tool", arguments={"names": ["read_file"]}),
    ]

    with patch.object(
        execution, "_dispatch_tool_call", new_callable=AsyncMock
    ) as mock_dispatch:
        mock_dispatch.return_value = ToolCallResult(
            status="ok",
            content="schema",
            artifact_handle=None,
            truncated=False,
        )

        result_messages, _artifact_handles = await execution._execute_tool_calls(
            _make_session(), tool_calls, ctx=ctx
        )

        assert mock_dispatch.call_count == 0
        assert len(result_messages) == 1
        assert "describe_tool is now DISABLED" in result_messages[0].content
        assert ctx._describe_tool_blocked is True


@pytest.mark.asyncio
async def test_repeated_identical_call_is_blocked_and_schema_dropped():
    """A tool call identical to the previous assistant message is blocked."""
    registry = MagicMock()
    registry.describe.return_value = MagicMock(
        requires_confirmation=False, ordering="concurrent"
    )

    policy = MagicMock()
    policy.tool_result_max_chars.return_value = 8000

    execution = TurnExecution(
        tool_registry=registry,
        inference_client=MagicMock(),
        policy=policy,
        context_builder=MagicMock(),
        session_store=MagicMock(),
    )

    ctx = TurnContext(
        turn=_make_turn(),
        user_message=Message(role="user", content="hello"),
        system_prompt="",
        respond_callback=AsyncMock(),
        session=_make_session(),
        build_result=MagicMock(messages=[]),
    )
    # Previous assistant message issued the exact same search_memory call.
    ctx.running_history = [
        Message(role="user", content="find jobs"),
        Message(
            role="assistant",
            content=None,
            tool_calls=[
                ToolCall(
                    id="prev1",
                    name="search_memory",
                    arguments={"query": "job search job title target role"},
                )
            ],
        ),
        Message(role="tool", content="no results", tool_call_id="prev1"),
    ]

    tool_calls = [
        ToolCall(
            id="tc1",
            name="search_memory",
            arguments={"query": "job search job title target role"},
        ),
    ]

    with patch.object(
        execution, "_dispatch_tool_call", new_callable=AsyncMock
    ) as mock_dispatch:
        mock_dispatch.return_value = ToolCallResult(
            status="ok",
            content="results",
            artifact_handle=None,
            truncated=False,
        )

        result_messages, _artifact_handles = await execution._execute_tool_calls(
            _make_session(), tool_calls, ctx=ctx
        )

        # The repeated call is not dispatched.
        assert mock_dispatch.call_count == 0
        assert len(result_messages) == 1
        assert result_messages[0].tool_call_id == "tc1"
        assert "search_memory" in result_messages[0].content
        assert "DISABLED" in result_messages[0].content
        assert ctx._repeated_tools_blocked == {"search_memory"}


@pytest.mark.asyncio
async def test_repeated_identical_call_allows_different_arguments():
    """A tool call with different arguments from the previous turn executes."""
    registry = MagicMock()
    registry.describe.return_value = MagicMock(
        requires_confirmation=False, ordering="concurrent"
    )

    policy = MagicMock()
    policy.tool_result_max_chars.return_value = 8000

    execution = TurnExecution(
        tool_registry=registry,
        inference_client=MagicMock(),
        policy=policy,
        context_builder=MagicMock(),
        session_store=MagicMock(),
    )

    ctx = TurnContext(
        turn=_make_turn(),
        user_message=Message(role="user", content="hello"),
        system_prompt="",
        respond_callback=AsyncMock(),
        session=_make_session(),
        build_result=MagicMock(messages=[]),
    )
    ctx.running_history = [
        Message(role="user", content="find jobs"),
        Message(
            role="assistant",
            content=None,
            tool_calls=[
                ToolCall(
                    id="prev1",
                    name="search_memory",
                    arguments={"query": "old query"},
                )
            ],
        ),
        Message(role="tool", content="no results", tool_call_id="prev1"),
    ]

    tool_calls = [
        ToolCall(
            id="tc1",
            name="search_memory",
            arguments={"query": "new query"},
        ),
    ]

    with patch.object(
        execution, "_dispatch_tool_call", new_callable=AsyncMock
    ) as mock_dispatch:
        mock_dispatch.return_value = ToolCallResult(
            status="ok",
            content="results",
            artifact_handle=None,
            truncated=False,
        )

        result_messages, _artifact_handles = await execution._execute_tool_calls(
            _make_session(), tool_calls, ctx=ctx
        )

        assert mock_dispatch.call_count == 1
        assert len(result_messages) == 1
        assert result_messages[0].content == "results"
        assert not getattr(ctx, "_repeated_tools_blocked", None)


@pytest.mark.asyncio
async def test_repeated_identical_call_blocked_across_non_consecutive_steps():
    """A repeat of an earlier-turn tool call is blocked even if not consecutive."""
    registry = MagicMock()
    registry.describe.return_value = MagicMock(
        requires_confirmation=False, ordering="concurrent"
    )

    policy = MagicMock()
    policy.tool_result_max_chars.return_value = 8000

    execution = TurnExecution(
        tool_registry=registry,
        inference_client=MagicMock(),
        policy=policy,
        context_builder=MagicMock(),
        session_store=MagicMock(),
    )

    ctx = TurnContext(
        turn=_make_turn(),
        user_message=Message(role="user", content="hello"),
        system_prompt="",
        respond_callback=AsyncMock(),
        session=_make_session(),
        build_result=MagicMock(messages=[]),
    )
    ctx.running_history = [
        Message(role="user", content="find jobs"),
        Message(
            role="assistant",
            content=None,
            tool_calls=[
                ToolCall(
                    id="prev1",
                    name="search_memory",
                    arguments={"query": "old query"},
                )
            ],
        ),
        Message(role="tool", content="no results", tool_call_id="prev1"),
        # A different tool call in between does not reset the repeat guard.
        Message(
            role="assistant",
            content=None,
            tool_calls=[ToolCall(id="prev2", name="list_dir", arguments={"path": "/"})],
        ),
        Message(role="tool", content="files", tool_call_id="prev2"),
    ]

    tool_calls = [
        ToolCall(
            id="tc1",
            name="search_memory",
            arguments={"query": "old query"},
        ),
    ]

    with patch.object(
        execution, "_dispatch_tool_call", new_callable=AsyncMock
    ) as mock_dispatch:
        mock_dispatch.return_value = ToolCallResult(
            status="ok",
            content="results",
            artifact_handle=None,
            truncated=False,
        )

        result_messages, _artifact_handles = await execution._execute_tool_calls(
            _make_session(), tool_calls, ctx=ctx
        )

        assert mock_dispatch.call_count == 0
        assert len(result_messages) == 1
        assert "DISABLED" in result_messages[0].content
        assert ctx._repeated_tools_blocked == {"search_memory"}


@pytest.mark.asyncio
async def test_repeated_identical_call_deduped_within_batch():
    """The same tool call twice in one batch is blocked the second time."""
    registry = MagicMock()
    registry.describe.return_value = MagicMock(
        requires_confirmation=False, ordering="concurrent"
    )

    policy = MagicMock()
    policy.tool_result_max_chars.return_value = 8000

    execution = TurnExecution(
        tool_registry=registry,
        inference_client=MagicMock(),
        policy=policy,
        context_builder=MagicMock(),
        session_store=MagicMock(),
    )

    ctx = TurnContext(
        turn=_make_turn(),
        user_message=Message(role="user", content="hello"),
        system_prompt="",
        respond_callback=AsyncMock(),
        session=_make_session(),
        build_result=MagicMock(messages=[]),
    )

    tool_calls = [
        ToolCall(id="tc1", name="read_file", arguments={"path": "/tmp/a.txt"}),
        ToolCall(id="tc2", name="read_file", arguments={"path": "/tmp/a.txt"}),
    ]

    with patch.object(
        execution, "_dispatch_tool_call", new_callable=AsyncMock
    ) as mock_dispatch:
        mock_dispatch.return_value = ToolCallResult(
            status="ok",
            content="contents",
            artifact_handle=None,
            truncated=False,
        )

        result_messages, _artifact_handles = await execution._execute_tool_calls(
            _make_session(), tool_calls, ctx=ctx
        )

        # First executes, second is blocked as a duplicate within the batch.
        assert mock_dispatch.call_count == 1
        assert len(result_messages) == 2
        assert result_messages[0].content == "contents"
        assert "DISABLED" in result_messages[1].content
        assert ctx._repeated_tools_blocked == {"read_file"}


@pytest.mark.asyncio
async def test_repeated_identical_call_correction_not_duplicated():
    """A repeated-identical-call correction is injected once per tool."""
    store = MagicMock()
    store.append_message = AsyncMock()

    builder = MagicMock()
    builder.build = AsyncMock(return_value=MagicMock(messages=[]))

    execution = TurnExecution(
        tool_registry=MagicMock(),
        inference_client=MagicMock(),
        policy=MagicMock(),
        context_builder=builder,
        session_store=store,
    )

    ctx = TurnContext(
        turn=_make_turn(),
        user_message=Message(role="user", content="hello"),
        system_prompt="",
        respond_callback=AsyncMock(),
        session=_make_session(),
        build_result=MagicMock(messages=[]),
    )

    assistant_msg = Message(
        role="assistant",
        content=None,
        tool_calls=[
            ToolCall(id="tc1", name="read_file", arguments={"path": "/tmp/a.txt"})
        ],
    )

    # First repeated-identical-call correction is injected.
    with patch(
        "hestia.orchestrator.execution.classify_turn",
        return_value=Correction(
            pattern=DegeneratePattern.REPEATED_IDENTICAL_CALL,
            message="stop repeating",
        ),
    ):
        assert await execution._classify_and_maybe_correct(
            ctx, _make_turn(), assistant_msg
        ) is True
        assert ctx.correction_count == 1

    # Second identical call does not get another correction.
    with patch(
        "hestia.orchestrator.execution.classify_turn",
        return_value=Correction(
            pattern=DegeneratePattern.REPEATED_IDENTICAL_CALL,
            message="stop repeating",
        ),
    ):
        assert await execution._classify_and_maybe_correct(
            ctx, _make_turn(), assistant_msg
        ) is False
        assert ctx.correction_count == 1


@pytest.mark.asyncio
async def test_tool_result_truncated_before_reprompting():
    """A 50 KB tool result is clipped before being added to result messages."""
    registry = MagicMock()
    registry.describe.return_value = MagicMock(
        requires_confirmation=False, ordering="concurrent"
    )

    policy = MagicMock()
    policy.tool_result_max_chars.return_value = 100

    execution = TurnExecution(
        tool_registry=registry,
        inference_client=MagicMock(),
        policy=policy,
        context_builder=MagicMock(),
        session_store=MagicMock(),
    )

    huge_content = "x" * 50_000
    tool_calls = [
        ToolCall(id="tc1", name="big_tool", arguments={}),
    ]

    with patch.object(
        execution, "_dispatch_tool_call", new_callable=AsyncMock
    ) as mock_dispatch:
        mock_dispatch.return_value = ToolCallResult(
            status="ok",
            content=huge_content,
            artifact_handle=None,
            truncated=False,
        )

        result_messages, _artifact_handles = await execution._execute_tool_calls(
            _make_session(), tool_calls
        )

        assert len(result_messages) == 1
        msg = result_messages[0]
        assert len(msg.content) < len(huge_content)
        assert msg.content.endswith("\n... [truncated]")
        assert msg.content.startswith("x" * 100)
        policy.tool_result_max_chars.assert_called_once_with("big_tool")


@pytest.mark.asyncio
async def test_finish_reason_stop_with_tool_calls_routes_to_tools(make_chat_response):
    """finish_reason='stop' alongside tool_calls executes tools and continues loop."""
    store = MagicMock()
    store.append_message = AsyncMock()

    builder = MagicMock()
    builder.build = AsyncMock(return_value=MagicMock(messages=[]))

    execution = TurnExecution(
        tool_registry=MagicMock(),
        inference_client=MagicMock(),
        policy=MagicMock(),
        context_builder=builder,
        session_store=store,
        max_iterations=1,
    )

    execution._inference.chat = AsyncMock(
        return_value=make_chat_response(
            finish_reason="stop",
            tool_calls=[ToolCall(id="tc1", name="test_tool", arguments={})],
            content="",
        )
    )

    ctx = TurnContext(
        turn=_make_turn(),
        user_message=Message(role="user", content="hello"),
        system_prompt="",
        respond_callback=AsyncMock(),
        session=_make_session(),
        build_result=MagicMock(messages=[]),
    )

    with patch.object(
        execution, "_handle_tool_calls", new_callable=AsyncMock
    ) as mock_handle:
        async def _side_effect(*args, **kwargs):
            ctx.turn.iterations += 1
            return TurnState.BUILDING_CONTEXT

        mock_handle.side_effect = _side_effect
        with pytest.raises(MaxIterationsError):
            await execution.run(ctx, AsyncMock(), AsyncMock())

    mock_handle.assert_awaited_once()


@pytest.mark.asyncio
async def test_reasoning_guardrail_nudge(make_chat_response):
    """When model reasons >1500 chars without acting, nudge is sent and loop continues."""
    store = MagicMock()
    store.append_message = AsyncMock()

    builder = MagicMock()
    builder.build = AsyncMock(return_value=MagicMock(messages=[]))

    execution = TurnExecution(
        tool_registry=MagicMock(),
        inference_client=MagicMock(),
        policy=MagicMock(),
        context_builder=builder,
        session_store=store,
        max_iterations=3,
    )

    execution._inference.chat = AsyncMock(
        return_value=make_chat_response(
            finish_reason="stop",
            reasoning_content="x" * 1600,
            content="",
        )
    )

    respond_callback = AsyncMock()
    ctx = TurnContext(
        turn=_make_turn(),
        user_message=Message(role="user", content="hello"),
        system_prompt="",
        respond_callback=respond_callback,
        session=_make_session(),
        build_result=MagicMock(messages=[]),
    )

    with pytest.raises(MaxIterationsError):
        await execution.run(ctx, AsyncMock(), AsyncMock())

    # Should have sent the reasoning guardrail nudge at least once
    assert respond_callback.await_count >= 1
    nudge_text = respond_callback.await_args_list[0][0][0]
    assert "reasoning extensively" in nudge_text
    # Iterations should have advanced
    assert ctx.turn.iterations >= 1


@pytest.mark.asyncio
async def test_streaming_repair_json():
    """Streaming path repairs malformed JSON tool call arguments via repair_json."""
    from hestia.core.types import StreamDelta

    execution = TurnExecution(
        tool_registry=MagicMock(),
        inference_client=MagicMock(),
        policy=MagicMock(),
        context_builder=MagicMock(),
        session_store=MagicMock(),
        stream=True,
    )

    delta = StreamDelta(
        content="",
        tool_call_chunks=[
            {
                "index": 0,
                "id": "tc1",
                "function": {
                    "name": "test_tool",
                    "arguments": '{"key": "value",}',  # trailing comma
                },
            }
        ],
        finish_reason="tool_calls",
    )

    async def _async_iter():
        yield delta

    async def _mock_chat_stream(*args, **kwargs):
        yield delta

    execution._inference.chat_stream = _mock_chat_stream

    ctx = TurnContext(
        turn=_make_turn(),
        user_message=Message(role="user", content="hello"),
        system_prompt="",
        respond_callback=AsyncMock(),
        session=_make_session(),
        build_result=MagicMock(messages=[]),
        stream_callback=AsyncMock(),
    )

    result = await execution._run_inference_streaming(ctx, ctx.turn)

    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].arguments == {"key": "value"}


@pytest.mark.asyncio
async def test_scan_tool_result_wiring():
    """Tool results are passed through _scan_tool_result during reassembly."""
    registry = MagicMock()
    registry.describe.return_value = MagicMock(
        requires_confirmation=False, ordering="concurrent"
    )

    policy = MagicMock()
    policy.tool_result_max_chars.return_value = 8000

    scanner = MagicMock()
    scanner.scan.return_value = MagicMock(triggered=True, reasons=["test reason"])
    scanner.wrap.return_value = "[SCANNED] wrapped content"

    execution = TurnExecution(
        tool_registry=registry,
        inference_client=MagicMock(),
        policy=policy,
        context_builder=MagicMock(),
        session_store=MagicMock(),
        injection_scanner=scanner,
    )

    tool_calls = [ToolCall(id="tc1", name="tool_a", arguments={})]

    with patch.object(
        execution, "_dispatch_tool_call", new_callable=AsyncMock
    ) as mock_dispatch:
        mock_dispatch.return_value = ToolCallResult(
            status="ok",
            content="suspicious content",
            artifact_handle=None,
            truncated=False,
        )

        result_messages, _ = await execution._execute_tool_calls(
            _make_session(), tool_calls
        )

        assert len(result_messages) == 1
        assert result_messages[0].content == "[SCANNED] wrapped content"
        scanner.scan.assert_called_once_with("suspicious content")
        scanner.wrap.assert_called_once()


@pytest.mark.asyncio
async def test_max_tokens_default_passed_to_chat(make_chat_response):
    """TurnExecution passes its default max_tokens to the inference client."""
    store = MagicMock()
    store.append_message = AsyncMock()

    builder = MagicMock()
    builder.build = AsyncMock(return_value=MagicMock(messages=[]))

    inference_client = MagicMock()
    inference_client.chat = AsyncMock(
        return_value=make_chat_response(finish_reason="stop", content="ok")
    )

    execution = TurnExecution(
        tool_registry=MagicMock(),
        inference_client=inference_client,
        policy=MagicMock(),
        context_builder=builder,
        session_store=store,
    )

    ctx = TurnContext(
        turn=_make_turn(),
        user_message=Message(role="user", content="hello"),
        system_prompt="",
        respond_callback=AsyncMock(),
        session=_make_session(),
        build_result=MagicMock(messages=[]),
    )

    await execution.run(ctx, AsyncMock(), AsyncMock())

    call_kwargs = inference_client.chat.call_args.kwargs
    assert call_kwargs["max_tokens"] == 1024


@pytest.mark.asyncio
async def test_max_tokens_override_passed_to_chat(make_chat_response):
    """A custom max_tokens value is forwarded to the inference client."""
    store = MagicMock()
    store.append_message = AsyncMock()

    builder = MagicMock()
    builder.build = AsyncMock(return_value=MagicMock(messages=[]))

    inference_client = MagicMock()
    inference_client.chat = AsyncMock(
        return_value=make_chat_response(finish_reason="stop", content="ok")
    )

    execution = TurnExecution(
        tool_registry=MagicMock(),
        inference_client=inference_client,
        policy=MagicMock(),
        context_builder=builder,
        session_store=store,
        max_tokens=4096,
    )

    ctx = TurnContext(
        turn=_make_turn(),
        user_message=Message(role="user", content="hello"),
        system_prompt="",
        respond_callback=AsyncMock(),
        session=_make_session(),
        build_result=MagicMock(messages=[]),
    )

    await execution.run(ctx, AsyncMock(), AsyncMock())

    call_kwargs = inference_client.chat.call_args.kwargs
    assert call_kwargs["max_tokens"] == 4096


@pytest.mark.asyncio
async def test_max_tokens_passed_to_chat_stream(make_chat_response):
    """TurnExecution passes max_tokens to the streaming inference client."""
    store = MagicMock()
    store.append_message = AsyncMock()

    builder = MagicMock()
    builder.build = AsyncMock(return_value=MagicMock(messages=[]))

    inference_client = MagicMock()

    async def _mock_chat_stream(*args, **kwargs):
        yield StreamDelta(content="ok", finish_reason="stop")

    inference_client.chat_stream = MagicMock(wraps=_mock_chat_stream)

    execution = TurnExecution(
        tool_registry=MagicMock(),
        inference_client=inference_client,
        policy=MagicMock(),
        context_builder=builder,
        session_store=store,
        stream=True,
        max_tokens=2048,
    )

    ctx = TurnContext(
        turn=_make_turn(),
        user_message=Message(role="user", content="hello"),
        system_prompt="",
        respond_callback=AsyncMock(),
        session=_make_session(),
        build_result=MagicMock(messages=[]),
        stream_callback=AsyncMock(),
    )

    await execution.run(ctx, AsyncMock(), AsyncMock())

    call_kwargs = inference_client.chat_stream.call_args.kwargs
    assert call_kwargs["max_tokens"] == 2048


@pytest.mark.asyncio
async def test_streaming_inactivity_timeout_returns_partial_content():
    """If the stream stalls, _run_inference_streaming returns accumulated content."""
    execution = TurnExecution(
        tool_registry=MagicMock(),
        inference_client=MagicMock(),
        policy=MagicMock(),
        context_builder=MagicMock(),
        session_store=MagicMock(),
        stream=True,
    )

    async def _stalled_stream(*args, **kwargs):
        yield StreamDelta(content="partial ")
        yield StreamDelta(content="content")
        # Never yield another item; the wait_for should time out.
        await asyncio.Event().wait()

    execution._inference.chat_stream = _stalled_stream

    stream_callback = AsyncMock()
    ctx = TurnContext(
        turn=_make_turn(),
        user_message=Message(role="user", content="hello"),
        system_prompt="",
        respond_callback=AsyncMock(),
        session=_make_session(),
        build_result=MagicMock(messages=[]),
        stream_callback=stream_callback,
    )

    with patch(
        "hestia.orchestrator.execution._STREAM_INACTIVITY_TIMEOUT", 0.05
    ):
        result = await execution._run_inference_streaming(ctx, ctx.turn)

    assert result.content == "partial content"
    assert result.finish_reason == "stop"
    assert stream_callback.await_count == 2


def test_normalize_tool_arguments_coerces_non_dict_values():
    """Non-dict tool-call arguments are coerced to an empty dict."""
    assert _normalize_tool_arguments({"x": 1}) == {"x": 1}
    assert _normalize_tool_arguments(None) == {}
    assert _normalize_tool_arguments("") == {}
    assert _normalize_tool_arguments(["a"]) == {}
    assert _normalize_tool_arguments("not a dict") == {}


@pytest.mark.asyncio
async def test_execute_tool_calls_normalizes_non_dict_arguments():
    """_execute_tool_calls tolerates tool calls whose arguments are not dicts."""
    registry = MagicMock()
    registry.describe.return_value = MagicMock(
        requires_confirmation=False, ordering="concurrent"
    )

    policy = MagicMock()
    policy.tool_result_max_chars.return_value = 8000

    execution = TurnExecution(
        tool_registry=registry,
        inference_client=MagicMock(),
        policy=policy,
        context_builder=MagicMock(),
        session_store=MagicMock(),
    )

    tool_calls = [
        ToolCall(id="tc1", name="write_file", arguments="not-a-dict"),
        ToolCall(id="tc2", name="read_file", arguments=None),
    ]

    with patch.object(
        execution, "_dispatch_tool_call", new_callable=AsyncMock
    ) as mock_dispatch:
        mock_dispatch.return_value = ToolCallResult(
            status="ok",
            content="ok",
            artifact_handle=None,
            truncated=False,
        )

        result_messages, _ = await execution._execute_tool_calls(
            _make_session(), tool_calls
        )

    # Both calls should have been normalized to {} and dispatched.
    assert mock_dispatch.call_count == 2
    for call in mock_dispatch.call_args_list:
        assert call.args[1].arguments == {}
    assert len(result_messages) == 2
