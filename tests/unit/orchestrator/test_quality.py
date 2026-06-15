"""Unit tests for the quality monitor degenerate-pattern classifier."""

from datetime import datetime
from pathlib import Path

import pytest

from hestia.core.types import Message, Session, SessionState, SessionTemperature, ToolCall
from hestia.errors import EmptyResponseError, MaxIterationsError, PolicyFailureError
from hestia.orchestrator.quality import (
    DegeneratePattern,
    classify_turn,
)
from hestia.orchestrator.types import Turn


@pytest.fixture
def session() -> Session:
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


def _make_turn(iterations: int = 0) -> Turn:
    return Turn(
        id="turn-1",
        session_id="test-session",
        state="received",  # type: ignore[arg-type]
        user_message=None,
        started_at=datetime.now(),
        iterations=iterations,
    )


async def test_empty_response_detected(session: Session) -> None:
    """A message with no content and no tool calls is EMPTY_RESPONSE."""
    turn = _make_turn()
    msg = Message(role="assistant", content="", tool_calls=None)
    result = await classify_turn(turn, msg, [msg], ["list_tools"])
    assert result is not None
    assert result.pattern == DegeneratePattern.EMPTY_RESPONSE
    assert "Respond with text or a tool call." in result.message


async def test_empty_response_with_reasoning_not_detected(session: Session) -> None:
    """Reasoning-only content should not be flagged as empty."""
    turn = _make_turn()
    msg = Message(role="assistant", content="", tool_calls=None, reasoning_content="thinking...")
    result = await classify_turn(turn, msg, [msg], ["list_tools"])
    assert result is None


async def test_hallucinated_tool_detected(session: Session) -> None:
    """A tool call not in the allowed list is HALLUCINATED_TOOL."""
    turn = _make_turn()
    msg = Message(
        role="assistant",
        content="",
        tool_calls=[ToolCall(id="c1", name="fake_tool", arguments={})],
    )
    result = await classify_turn(turn, msg, [msg], ["list_tools", "write_file"])
    assert result is not None
    assert result.pattern == DegeneratePattern.HALLUCINATED_TOOL
    assert "fake_tool" not in result.message  # message lists valid tools
    assert "list_tools" in result.message


async def test_meta_tools_not_hallucinated(session: Session) -> None:
    """Meta-tools are always permitted and should not be flagged."""
    turn = _make_turn()
    msg = Message(
        role="assistant",
        content="",
        tool_calls=[ToolCall(id="c1", name="list_tools", arguments={})],
    )
    result = await classify_turn(turn, msg, [msg], ["write_file"])
    assert result is None


async def test_repeated_identical_call_detected(session: Session) -> None:
    """Two consecutive assistant messages with identical tool calls trigger the pattern."""
    turn = _make_turn(iterations=1)
    prev = Message(
        role="assistant",
        content="",
        tool_calls=[ToolCall(id="c1", name="read_file", arguments={"path": "/tmp/a.txt"})],
    )
    current = Message(
        role="assistant",
        content="",
        tool_calls=[ToolCall(id="c2", name="read_file", arguments={"path": "/tmp/a.txt"})],
    )
    result = await classify_turn(turn, current, [prev, current], ["read_file"])
    assert result is not None
    assert result.pattern == DegeneratePattern.REPEATED_IDENTICAL_CALL
    assert "repeatedly" in result.message.lower()


async def test_repeated_list_tools_call_correction_is_specific(session: Session) -> None:
    """A repeated list_tools call gets a forceful, specific correction."""
    turn = _make_turn(iterations=1)
    prev = Message(
        role="assistant",
        content="",
        tool_calls=[ToolCall(id="c1", name="list_tools", arguments={})],
    )
    current = Message(
        role="assistant",
        content="",
        tool_calls=[ToolCall(id="c2", name="list_tools", arguments={})],
    )
    result = await classify_turn(turn, current, [prev, current], ["list_tools"])
    assert result is not None
    assert result.pattern == DegeneratePattern.REPEATED_IDENTICAL_CALL
    assert "list_tools" in result.message
    assert "STOP calling list_tools" in result.message


async def test_repeated_call_with_different_args_not_detected(session: Session) -> None:
    """Tool calls with different arguments are not a repeat."""
    turn = _make_turn(iterations=1)
    prev = Message(
        role="assistant",
        content="",
        tool_calls=[ToolCall(id="c1", name="read_file", arguments={"path": "/tmp/a.txt"})],
    )
    current = Message(
        role="assistant",
        content="",
        tool_calls=[ToolCall(id="c2", name="read_file", arguments={"path": "/tmp/b.txt"})],
    )
    result = await classify_turn(turn, current, [prev, current], ["read_file"])
    assert result is None


async def test_patch_failed_detected(session: Session) -> None:
    """Three write_file errors on the same file trigger PATCH_FAILED."""
    turn = _make_turn(iterations=3)
    history: list[Message] = []
    for i in range(3):
        assistant = Message(
            role="assistant",
            content="",
            tool_calls=[
                ToolCall(id=f"call-{i}", name="write_file", arguments={"path": "/tmp/x.txt"})
            ],
        )
        tool_result = Message(
            role="tool",
            content="Error: permission denied",
            tool_call_id=f"call-{i}",
        )
        history.extend([assistant, tool_result])

    current = Message(role="assistant", content="done", tool_calls=None)
    result = await classify_turn(turn, current, history + [current], ["write_file"])
    assert result is not None
    assert result.pattern == DegeneratePattern.PATCH_FAILED
    assert "rewrite from scratch" in result.message


async def test_patch_failed_not_triggered_with_only_two_errors(session: Session) -> None:
    """Two errors on the same file are below the threshold."""
    turn = _make_turn(iterations=2)
    history: list[Message] = []
    for i in range(2):
        assistant = Message(
            role="assistant",
            content="",
            tool_calls=[
                ToolCall(id=f"call-{i}", name="write_file", arguments={"path": "/tmp/x.txt"})
            ],
        )
        tool_result = Message(
            role="tool",
            content="Error: permission denied",
            tool_call_id=f"call-{i}",
        )
        history.extend([assistant, tool_result])

    current = Message(role="assistant", content="done", tool_calls=None)
    result = await classify_turn(turn, current, history + [current], ["write_file"])
    assert result is None


async def test_read_only_streak_detected(session: Session) -> None:
    """Eight consecutive read-only tools trigger READ_ONLY_STREAK."""
    turn = _make_turn(iterations=8)
    history: list[Message] = []
    for i in range(8):
        assistant = Message(
            role="assistant",
            content="",
            tool_calls=[
                ToolCall(id=f"call-{i}", name="read_file", arguments={"path": "/tmp/a.txt"})
            ],
        )
        tool_result = Message(
            role="tool",
            content="file contents...",
            tool_call_id=f"call-{i}",
        )
        history.extend([assistant, tool_result])

    current = Message(role="assistant", content="done", tool_calls=None)
    result = await classify_turn(turn, current, history + [current], ["read_file", "write_file"])
    assert result is not None
    assert result.pattern == DegeneratePattern.READ_ONLY_STREAK
    assert "write your answer" in result.message


async def test_read_only_streak_broken_by_write_tool(session: Session) -> None:
    """A write tool in the chain breaks the streak."""
    turn = _make_turn(iterations=3)
    history: list[Message] = []
    for i in range(4):
        name = "write_file" if i == 2 else "read_file"
        assistant = Message(
            role="assistant",
            content="",
            tool_calls=[ToolCall(id=f"call-{i}", name=name, arguments={"path": "/tmp/a.txt"})],
        )
        tool_result = Message(
            role="tool",
            content="ok" if name == "write_file" else "contents...",
            tool_call_id=f"call-{i}",
        )
        history.extend([assistant, tool_result])

    current = Message(role="assistant", content="done", tool_calls=None)
    result = await classify_turn(turn, current, history + [current], ["read_file", "write_file"])
    assert result is None


async def test_meta_inspect_tools_do_not_count_toward_read_only_streak(session: Session) -> None:
    """list_tools and describe_tool don't count toward read-only streaks."""
    turn = _make_turn(iterations=5)
    history: list[Message] = []
    for i in range(5):
        name = ["list_tools", "describe_tool", "read_file", "list_memories", "search_memory"][i]
        assistant = Message(
            role="assistant",
            content="",
            tool_calls=[ToolCall(id=f"call-{i}", name=name, arguments={})],
        )
        tool_result = Message(
            role="tool",
            content="ok",
            tool_call_id=f"call-{i}",
        )
        history.extend([assistant, tool_result])

    current = Message(role="assistant", content="done", tool_calls=None)
    result = await classify_turn(turn, current, history + [current], ["read_file", "list_memories", "search_memory"])
    assert result is None


async def test_greeting_mid_task_detected(session: Session) -> None:
    """A greeting after iteration 2 triggers GREETING_MID_TASK."""
    turn = _make_turn(iterations=3)
    msg = Message(role="assistant", content="Hello! How can I help?")
    result = await classify_turn(turn, msg, [msg], ["list_tools"])
    assert result is not None
    assert result.pattern == DegeneratePattern.GREETING_MID_TASK
    assert "continue where you left off" in result.message


async def test_greeting_early_turn_not_detected(session: Session) -> None:
    """Greetings in the first few iterations are not flagged."""
    turn = _make_turn(iterations=1)
    msg = Message(role="assistant", content="Hello! How can I help?")
    result = await classify_turn(turn, msg, [msg], ["list_tools"])
    assert result is None


async def test_no_degenerate_pattern(session: Session) -> None:
    """A normal response returns None."""
    turn = _make_turn(iterations=1)
    msg = Message(role="assistant", content="Here is the answer.")
    result = await classify_turn(turn, msg, [msg], ["list_tools"])
    assert result is None


@pytest.mark.asyncio
async def test_execution_loop_quality_monitor_injection() -> None:
    """Integration: a degenerate response triggers correction injection in the loop."""
    from unittest.mock import AsyncMock, MagicMock

    from hestia.orchestrator.execution import TurnExecution
    from hestia.orchestrator.types import TurnContext

    session = Session(
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

    turn = _make_turn(iterations=1)
    ctx = TurnContext(
        turn=turn,
        user_message=Message(role="user", content="hi"),
        system_prompt="You are a test assistant.",
        respond_callback=AsyncMock(),
        session=session,
    )
    ctx.build_result = MagicMock()
    ctx.build_result.messages = []
    ctx.allowed_tools = ["list_tools"]

    # First model call returns empty, second returns normal text
    inference_client = MagicMock()
    inference_client.chat = AsyncMock()
    inference_client.chat.side_effect = [
        MagicMock(
            content="",
            reasoning_content=None,
            tool_calls=[],
            finish_reason="stop",
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
        ),
        MagicMock(
            content="All good now.",
            reasoning_content=None,
            tool_calls=[],
            finish_reason="stop",
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
        ),
    ]

    policy = MagicMock()
    policy.reasoning_budget = MagicMock(return_value=2048)

    builder = MagicMock()
    builder.build = AsyncMock(return_value=MagicMock(messages=[]))

    store = MagicMock()
    store.append_message = AsyncMock()

    execution = TurnExecution(
        tool_registry=MagicMock(),
        inference_client=inference_client,
        policy=policy,
        context_builder=builder,
        session_store=store,
    )

    transition = AsyncMock()
    set_typing = AsyncMock()

    result = await execution.run(ctx, transition, set_typing)

    # The loop should have called inference twice:
    # 1. First call returns empty
    # 2. Quality monitor injects correction
    # 3. Second call returns text
    assert inference_client.chat.call_count == 2

    # Correction should have been appended to store
    assert store.append_message.call_count >= 2
    # The last call should be the correction message
    correction_msg = store.append_message.call_args_list[-2][0][1]
    assert correction_msg.role == "user"
    assert "Respond with text or a tool call." in correction_msg.content

    assert result == "All good now."


@pytest.mark.asyncio
async def test_correction_count_capped_at_three() -> None:
    """After 3 corrections, the loop stops injecting and lets normal retry/fail logic run."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from hestia.orchestrator.execution import TurnExecution
    from hestia.orchestrator.types import TurnContext

    session = Session(
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

    turn = _make_turn(iterations=1)
    ctx = TurnContext(
        turn=turn,
        user_message=Message(role="user", content="hi"),
        system_prompt="You are a test assistant.",
        respond_callback=AsyncMock(),
        session=session,
    )
    ctx.build_result = MagicMock()
    ctx.build_result.messages = []
    ctx.allowed_tools = ["list_tools"]

    # Model always returns empty response
    inference_client = MagicMock()
    inference_client.chat = AsyncMock(
        return_value=MagicMock(
            content="",
            reasoning_content=None,
            tool_calls=[],
            finish_reason="stop",
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
        )
    )

    policy = MagicMock()
    policy.reasoning_budget = MagicMock(return_value=2048)
    policy.retry_after_error = MagicMock(
        return_value=MagicMock(action="retry", reason="retrying")
    )

    builder = MagicMock()
    builder.build = AsyncMock(return_value=MagicMock(messages=[]))

    store = MagicMock()
    store.append_message = AsyncMock()

    execution = TurnExecution(
        tool_registry=MagicMock(),
        inference_client=inference_client,
        policy=policy,
        context_builder=builder,
        session_store=store,
    )

    transition = AsyncMock()
    set_typing = AsyncMock()

    with patch.object(execution, "_max_iterations", 10), pytest.raises(
        (EmptyResponseError, MaxIterationsError, PolicyFailureError)
    ):
        await execution.run(ctx, transition, set_typing)

    # correction_count should have been capped at 3
    assert ctx.correction_count == 3

    # After the first 3 corrections, retry_after_error should be called for empty responses
    assert policy.retry_after_error.call_count > 0


@pytest.mark.asyncio
async def test_truncated_write_file_is_detected_and_recovered(session: Session) -> None:
    """A truncated write_file XML is classified as TRUNCATED_WRITE_FILE and recovered."""
    turn = _make_turn()
    body = (
        '<tool_call>\n<function=write_file>\n<parameter=arguments>\n'
        '{"path": "/tmp/recovered.md", "content": "# Part 1\n'
        + "a" * 1600
    )
    msg = Message(role="assistant", content=body)
    calls: list[tuple[str, str]] = []

    async def fake_write_file(path: str = "", content: str = "") -> str:
        calls.append((path, content))
        return f"Wrote {len(content)} bytes to {path}"

    result = await classify_turn(
        turn,
        msg,
        [msg],
        ["write_file", "append_to_file"],
        write_file_handler=fake_write_file,
    )

    assert result is not None
    assert result.pattern == DegeneratePattern.TRUNCATED_WRITE_FILE
    assert "/tmp/recovered.md" in result.message
    assert "append_to_file" in result.message
    assert len(calls) == 1
    assert calls[0][0] == "/tmp/recovered.md"
    assert "# Part 1" in calls[0][1]


@pytest.mark.asyncio
async def test_truncated_append_to_file_is_detected_and_recovered(session: Session) -> None:
    """A truncated append_to_file XML reuses the recovery helper."""
    turn = _make_turn()
    body = (
        '<tool_call>\n<function=append_to_file>\n<parameter=arguments>\n'
        '{"path": "/tmp/recovered.md", "content": "## Section 2\n'
        + "b" * 1600
    )
    msg = Message(role="assistant", content=body)
    calls: list[tuple[str, str]] = []

    async def fake_append_to_file(path: str = "", content: str = "") -> str:
        calls.append((path, content))
        return f"Appended {len(content)} bytes to {path}"

    result = await classify_turn(
        turn,
        msg,
        [msg],
        ["write_file", "append_to_file"],
        append_to_file_handler=fake_append_to_file,
    )

    assert result is not None
    assert result.pattern == DegeneratePattern.TRUNCATED_WRITE_FILE
    assert "/tmp/recovered.md" in result.message
    assert "append_to_file" in result.message
    assert len(calls) == 1
    assert calls[0][0] == "/tmp/recovered.md"
    assert "## Section 2" in calls[0][1]


@pytest.mark.asyncio
async def test_truncated_write_file_falls_back_when_write_fails(session: Session) -> None:
    """If the recovered write fails, the correction falls back to the generic message."""
    turn = _make_turn()
    body = (
        '<tool_call>\n<function=write_file>\n<parameter=arguments>\n'
        '{"path": "/tmp/recovered.md", "content": "# Part 1\n'
        + "a" * 1600
    )
    msg = Message(role="assistant", content=body)

    async def failing_write_file(path: str = "", content: str = "") -> str:
        return "Error: access denied"

    result = await classify_turn(
        turn,
        msg,
        [msg],
        ["write_file", "append_to_file"],
        write_file_handler=failing_write_file,
    )

    assert result is not None
    assert result.pattern == DegeneratePattern.TRUNCATED_WRITE_FILE
    assert "shorter than 2000 characters" in result.message


@pytest.mark.asyncio
async def test_truncated_write_file_recovery_resumes_at_line_boundary(session: Session) -> None:
    """Recovery drops an incomplete trailing line so append can continue seamlessly."""
    padding = "x" * 200
    original_lines = [f"Line {i:03d}: {padding}" for i in range(1, 21)]
    original_content = "\n".join(original_lines) + "\n"
    # Truncate mid-way through "Line 015\n" so the trailing fragment is incomplete.
    truncation_point = original_content.index("Line 015:") + len("Line 015: ") + len(padding) + 1
    partial = original_content[:truncation_point - 3]

    tmp_path = Path("/tmp/recovered-seam-test.md")
    tmp_path.unlink(missing_ok=True)

    body = (
        '<tool_call>\n<function=write_file>\n<parameter=arguments>\n'
        f'{{"path": "{tmp_path}", "content": "{partial}'
    )
    msg = Message(role="assistant", content=body)

    async def fake_write_file(path: str = "", content: str = "") -> str:
        Path(path).write_text(content, encoding="utf-8")
        return f"Wrote {len(content)} bytes to {path}"

    async def fake_append_to_file(path: str = "", content: str = "") -> str:
        with open(path, "a", encoding="utf-8") as f:
            f.write(content)
        return f"Appended {len(content)} bytes to {path}"

    result = await classify_turn(
        _make_turn(),
        msg,
        [msg],
        ["write_file", "append_to_file"],
        write_file_handler=fake_write_file,
        append_to_file_handler=fake_append_to_file,
    )

    assert result is not None
    assert result.pattern == DegeneratePattern.TRUNCATED_WRITE_FILE

    # The correction must name the exact last complete line so the model can resume.
    assert "Line 014" in result.message
    assert "append_to_file" in result.message

    # Simulate the model obeying the correction: append the rest of the original
    # content starting right after the last complete line.
    written = tmp_path.read_text(encoding="utf-8")
    remaining = original_content[len(written):]
    await fake_append_to_file(path=str(tmp_path), content=remaining)

    assert tmp_path.read_text(encoding="utf-8") == original_content
