"""Tests for TurnAssembly memory epoch injection."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from hestia.core.types import Message, Session, SessionState, SessionTemperature
from hestia.orchestrator.assembly import TurnAssembly, _is_greeting_or_smalltalk
from hestia.orchestrator.types import TurnContext
from hestia.policy.default import DefaultPolicyEngine


def _make_session() -> Session:
    return Session(
        id="test-session",
        platform="cli",
        platform_user="user",
        started_at=datetime.now(),
        last_active_at=datetime.now(),
        slot_id=None,
        slot_saved_path=None,
        state=SessionState.ACTIVE,
        temperature=SessionTemperature.HOT,
    )


def _make_turn_context(session: Session | None = None) -> TurnContext:
    from hestia.orchestrator.types import Turn

    session = session or _make_session()
    turn = Turn(
        id="turn-1",
        session_id=session.id,
        state="received",
        user_message=Message(role="user", content="hello"),
        started_at=datetime.now(),
        completed_at=None,
        iterations=0,
        tool_calls_made=0,
        final_response=None,
        error=None,
        transitions=[],
    )
    return TurnContext(
        turn=turn,
        user_message=Message(role="user", content="hello"),
        system_prompt="You are helpful.",
        respond_callback=AsyncMock(),
        session=session,
    )


@pytest.mark.asyncio
async def test_prepare_builds_context_and_acquires_slot():
    """TurnAssembly prepares context, tools, and history for execution."""
    mock_builder = MagicMock()
    mock_builder.build = AsyncMock(
        return_value=MagicMock(
            messages=[], tokens_used=0, tokens_budget=1000,
            truncated_count=0, kept_first_user=False,
        )
    )

    mock_tools = MagicMock()
    mock_tools.list_names.return_value = []
    mock_tools.meta_tool_schemas.return_value = []

    policy = DefaultPolicyEngine(ctx_window=4096)

    mock_message_store = MagicMock()
    mock_message_store.get_messages = AsyncMock(return_value=[])
    mock_message_store.append_message = AsyncMock()

    assembly = TurnAssembly(
        context_builder=mock_builder,
        tool_registry=mock_tools,
        policy=policy,
        session_store=MagicMock(),
        message_store=mock_message_store,
    )

    session = _make_session()
    ctx = _make_turn_context(session)
    transition = AsyncMock()

    await assembly.prepare(session, ctx, transition)

    mock_builder.build.assert_awaited_once()
    assert ctx.build_result is not None


@pytest.mark.parametrize(
    "text,expected",
    [
        ("hey", True),
        ("Hey!", True),
        ("hi there", False),  # not a pure greeting pattern
        ("hello", True),
        ("what's up?", True),
        ("how are you", True),
        ("run job search", False),
        ("", False),
        ("hello, please search indeed", False),
    ],
)
def test_is_greeting_or_smalltalk(text: str, expected: bool) -> None:
    assert _is_greeting_or_smalltalk(text) is expected


@pytest.mark.asyncio
async def test_prepare_strips_tools_for_first_turn_greeting():
    """A first-turn greeting should not be offered tools."""
    mock_builder = MagicMock()
    mock_builder.build = AsyncMock(
        return_value=MagicMock(
            messages=[], tokens_used=0, tokens_budget=1000,
            truncated_count=0, kept_first_user=False,
        )
    )

    mock_tools = MagicMock()
    mock_tools.list_names.return_value = []
    mock_tools.meta_tool_schemas.return_value = ["schema"]

    policy = DefaultPolicyEngine(ctx_window=4096)

    mock_message_store = MagicMock()
    mock_message_store.get_messages = AsyncMock(return_value=[])
    mock_message_store.append_message = AsyncMock()

    assembly = TurnAssembly(
        context_builder=mock_builder,
        tool_registry=mock_tools,
        policy=policy,
        session_store=MagicMock(),
        message_store=mock_message_store,
    )

    session = _make_session()
    ctx = _make_turn_context(session)
    ctx.user_message = Message(role="user", content="hey")
    ctx.turn.user_message = ctx.user_message

    await assembly.prepare(session, ctx, AsyncMock())

    assert ctx.tools == []
    built_tools = mock_builder.build.await_args.kwargs["tools"]
    assert built_tools == []


@pytest.mark.asyncio
async def test_prepare_keeps_tools_for_non_greeting_first_turn():
    """A task-oriented first turn should still be offered tools."""
    mock_builder = MagicMock()
    mock_builder.build = AsyncMock(
        return_value=MagicMock(
            messages=[], tokens_used=0, tokens_budget=1000,
            truncated_count=0, kept_first_user=False,
        )
    )

    schemas = ["schema"]
    mock_tools = MagicMock()
    mock_tools.list_names.return_value = []
    mock_tools.meta_tool_schemas.return_value = schemas

    policy = DefaultPolicyEngine(ctx_window=4096)

    mock_message_store = MagicMock()
    mock_message_store.get_messages = AsyncMock(return_value=[])
    mock_message_store.append_message = AsyncMock()

    assembly = TurnAssembly(
        context_builder=mock_builder,
        tool_registry=mock_tools,
        policy=policy,
        session_store=MagicMock(),
        message_store=mock_message_store,
    )

    session = _make_session()
    ctx = _make_turn_context(session)
    ctx.user_message = Message(role="user", content="search indeed for jobs")
    ctx.turn.user_message = ctx.user_message

    await assembly.prepare(session, ctx, AsyncMock())

    assert ctx.tools == schemas
    built_tools = mock_builder.build.await_args.kwargs["tools"]
    assert built_tools == schemas


def _make_assembly(mock_builder, mock_tools) -> TurnAssembly:
    policy = DefaultPolicyEngine(ctx_window=4096)
    mock_message_store = MagicMock()
    mock_message_store.get_messages = AsyncMock(return_value=[])
    mock_message_store.append_message = AsyncMock()
    return TurnAssembly(
        context_builder=mock_builder,
        tool_registry=mock_tools,
        policy=policy,
        session_store=MagicMock(),
        message_store=mock_message_store,
    )


def _make_mock_builder():
    mock_builder = MagicMock()
    mock_builder.build = AsyncMock(
        return_value=MagicMock(
            messages=[], tokens_used=0, tokens_budget=1000,
            truncated_count=0, kept_first_user=False,
        )
    )
    return mock_builder


@pytest.mark.asyncio
async def test_prepare_exposes_save_memory_first_class():
    """save_memory is visible alongside the meta-tools so rule 6 is actionable
    during casual conversation (card #60)."""
    from hestia.core.types import FunctionSchema, ToolSchema

    save_schema = ToolSchema(
        type="function",
        function=FunctionSchema(
            name="save_memory",
            description="Persist a durable fact.",
            parameters={"type": "object", "properties": {}},
        ),
    )
    mock_tools = MagicMock()
    mock_tools.list_names.return_value = []
    mock_tools.meta_tool_schemas.return_value = ["meta"]
    mock_tools.direct_schema.return_value = save_schema

    assembly = _make_assembly(_make_mock_builder(), mock_tools)
    session = _make_session()
    ctx = _make_turn_context(session)
    ctx.user_message = Message(role="user", content="my parents live 2 houses down from me")
    ctx.turn.user_message = ctx.user_message

    await assembly.prepare(session, ctx, AsyncMock())

    assert ctx.tools == ["meta", save_schema]
    built_tools = assembly._builder.build.await_args.kwargs["tools"]
    assert built_tools == ["meta", save_schema]


@pytest.mark.asyncio
async def test_prepare_first_class_save_memory_missing_from_registry():
    """If save_memory is not registered, only the meta-tools are exposed."""
    mock_tools = MagicMock()
    mock_tools.list_names.return_value = []
    mock_tools.meta_tool_schemas.return_value = ["meta"]
    mock_tools.direct_schema.return_value = None

    assembly = _make_assembly(_make_mock_builder(), mock_tools)
    session = _make_session()
    ctx = _make_turn_context(session)
    ctx.user_message = Message(role="user", content="my parents live 2 houses down from me")
    ctx.turn.user_message = ctx.user_message

    await assembly.prepare(session, ctx, AsyncMock())

    assert ctx.tools == ["meta"]


@pytest.mark.asyncio
async def test_prepare_greeting_strips_first_class_save_memory_too():
    """The first-turn greeting fast path removes ALL tools, including the
    first-class save_memory schema."""
    from hestia.core.types import FunctionSchema, ToolSchema

    save_schema = ToolSchema(
        type="function",
        function=FunctionSchema(
            name="save_memory",
            description="Persist a durable fact.",
            parameters={"type": "object", "properties": {}},
        ),
    )
    mock_tools = MagicMock()
    mock_tools.list_names.return_value = []
    mock_tools.meta_tool_schemas.return_value = ["meta"]
    mock_tools.direct_schema.return_value = save_schema

    assembly = _make_assembly(_make_mock_builder(), mock_tools)
    session = _make_session()
    ctx = _make_turn_context(session)
    ctx.user_message = Message(role="user", content="hey")
    ctx.turn.user_message = ctx.user_message

    await assembly.prepare(session, ctx, AsyncMock())

    assert ctx.tools == []
