"""Tests for subagent delegation tool and policy-driven orchestrator path."""

from datetime import datetime

import pytest

from hestia.artifacts.store import ArtifactStore
from hestia.context.builder import ContextBuilder
from hestia.core.types import ChatResponse, Message, ToolCall
from hestia.orchestrator import Orchestrator, TurnState
from hestia.orchestrator.types import Turn
from hestia.persistence.db import Database
from hestia.persistence.sessions import SessionStore
from hestia.policy.default import DefaultPolicyEngine
from hestia.tools.builtin.current_time import current_time
from hestia.tools.builtin.delegate_task import make_delegate_task_tool
from hestia.tools.registry import ToolRegistry
from tests.integration.test_orchestrator import FakeInferenceClient


class AlwaysDelegatePolicy(DefaultPolicyEngine):
    """Force policy delegation for parent sessions only."""

    def should_delegate(
        self,
        session,
        task_description,
        tool_chain_length: int = 0,
        projected_tool_calls: int = 0,
    ) -> bool:
        return session.platform != "subagent"


@pytest.fixture
async def store(tmp_path):
    db_url = f"sqlite+aiosqlite:///{tmp_path}/subagent.db"
    db = Database(db_url)
    await db.connect()
    await db.create_tables()
    st = SessionStore(db)
    yield st
    await db.close()


@pytest.mark.asyncio
async def test_delegate_task_invokes_factory_orchestrator(store, tmp_path):
    """delegate_task creates a session, runs factory orchestrator, archives subagent."""
    from unittest.mock import AsyncMock, MagicMock

    sub_turn = Turn(
        id="sub-turn",
        session_id="placeholder",
        state=TurnState.DONE,
        user_message=None,
        started_at=datetime.now(),
        completed_at=datetime.now(),
        iterations=1,
        tool_calls_made=0,
        final_response="Subagent finished",
        error=None,
        transitions=[],
    )

    mock_orch = MagicMock()
    mock_orch.process_turn = AsyncMock(return_value=sub_turn)

    def factory():
        return mock_orch

    tool = make_delegate_task_tool(store, factory)
    text = await tool("Summarize the logs", context="none", timeout_seconds=30.0)

    assert "complete" in text.lower()
    assert "Subagent finished" in text
    assert mock_orch.process_turn.await_count == 1
    sub_sess = mock_orch.process_turn.await_args.kwargs["session"]
    archived = await store.get_session(sub_sess.id)
    assert archived is not None
    assert archived.state.value == "archived"


@pytest.mark.asyncio
async def test_orchestrator_policy_delegation_replaces_tool_batch(store, tmp_path):
    """When policy delegates, delegate_task runs and tool results map to each tool_call id."""
    artifact_store = ArtifactStore(tmp_path / "art")

    parent_inf = FakeInferenceClient(
        [
            ChatResponse(
                content="",
                reasoning_content=None,
                tool_calls=[ToolCall(id="tc1", name="current_time", arguments={})],
                finish_reason="tool_calls",
                prompt_tokens=1,
                completion_tokens=1,
                total_tokens=2,
            ),
            ChatResponse(
                content="Parent synthesis",
                reasoning_content=None,
                tool_calls=[],
                finish_reason="stop",
                prompt_tokens=1,
                completion_tokens=1,
                total_tokens=2,
            ),
        ]
    )

    child_inf = FakeInferenceClient(
        [
            ChatResponse(
                content="From subagent model",
                reasoning_content=None,
                tool_calls=[],
                finish_reason="stop",
                prompt_tokens=1,
                completion_tokens=1,
                total_tokens=2,
            ),
        ]
    )

    tool_registry = ToolRegistry(artifact_store)
    tool_registry.register(current_time)

    policy = AlwaysDelegatePolicy()

    def orchestrator_factory():
        cb = ContextBuilder(child_inf, DefaultPolicyEngine(), body_factor=1.0)
        return Orchestrator(
            inference=child_inf,
            session_store=store,
            context_builder=cb,
            tool_registry=tool_registry,
            policy=DefaultPolicyEngine(),
            confirm_callback=None,
            max_iterations=10,
            slot_manager=None,
        )

    tool_registry.register(make_delegate_task_tool(store, orchestrator_factory))

    parent_cb = ContextBuilder(parent_inf, policy, body_factor=1.0)
    orchestrator = Orchestrator(
        inference=parent_inf,
        session_store=store,
        context_builder=parent_cb,
        tool_registry=tool_registry,
        policy=policy,
        confirm_callback=None,
        max_iterations=10,
        slot_manager=None,
    )

    session = await store.create_session("test", "deleg_parent")

    responses: list[str] = []

    async def respond(text: str) -> None:
        responses.append(text)

    turn = await orchestrator.process_turn(
        session=session,
        user_message=Message(role="user", content="Please run tools"),
        respond_callback=respond,
    )

    assert turn.state == TurnState.DONE
    assert parent_inf.call_count == 2
    assert child_inf.call_count == 1
    assert "Parent synthesis" in responses[-1]
    msgs = await store.get_messages(session.id)
    tool_msgs = [m for m in msgs if m.role == "tool" and m.tool_call_id == "tc1"]
    assert tool_msgs
    assert "Subagent result" in tool_msgs[0].content or "complete" in tool_msgs[0].content.lower()
