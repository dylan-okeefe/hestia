"""Integration test for session handoff summary flow."""

from datetime import datetime

import pytest

from hestia.core.types import ChatResponse, Message, Session, SessionState, SessionTemperature
from hestia.memory.handoff import SessionHandoffSummarizer
from hestia.memory.store import MemoryStore
from hestia.orchestrator.engine import Orchestrator
from hestia.persistence.db import Database
from hestia.persistence.sessions import SessionStore


class FakeInferenceClient:
    """Fake inference client for testing."""

    model_name = "fake-model"

    async def tokenize(self, text: str) -> list[int]:
        return [0] * (len(text) // 4 + 1)

    async def count_request(self, messages, tools):
        total = 0
        for msg in messages:
            total += 10 + len(msg.content) // 4
        for _tool in tools:
            total += 50
        return total

    async def chat(self, messages, tools=None, slot_id=None, **kwargs):
        return ChatResponse(
            content="Discussed project planning and decided on Python.",
            reasoning_content=None,
            tool_calls=[],
            finish_reason="stop",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        )

    async def close(self):
        pass


class FakePolicyEngine:
    def should_delegate(
        self, session, task_description, tool_chain_length=0, projected_tool_calls=0
    ):
        return False

    def should_compress(self, session, tokens_used, tokens_budget):
        return False

    def should_evict_slot(self, slot_id, pressure):
        return False

    def retry_after_error(self, error, attempt):
        from hestia.policy.engine import RetryAction, RetryDecision
        return RetryDecision(action=RetryAction.FAIL)

    def filter_tools(self, session, tool_names, registry):
        return tool_names

    def turn_token_budget(self, session):
        return 4000

    def tool_result_max_chars(self, tool_name):
        return 4000

    def reasoning_budget(self, session, iteration):
        return 2048

    def auto_approve(self, tool_name, session):
        return False


@pytest.fixture
async def db(tmp_path):
    db_url = f"sqlite+aiosqlite:///{tmp_path}/test.db"
    database = Database(db_url)
    await database.connect()
    await database.create_tables()
    yield database
    await database.close()


@pytest.fixture
async def session_store(db):
    store = SessionStore(db)
    yield store


@pytest.fixture
async def memory_store(db):
    store = MemoryStore(db)
    await store.create_table()
    yield store


@pytest.mark.asyncio
async def test_full_handoff_cycle(session_store, memory_store):
    """Full cycle: start session, record turns, close, assert handoff memory."""
    from pathlib import Path

    from hestia.artifacts.store import ArtifactStore
    from hestia.context.builder import ContextBuilder
    from hestia.tools.registry import ToolRegistry

    inference = FakeInferenceClient()
    policy = FakePolicyEngine()
    builder = ContextBuilder(inference, policy, body_factor=1.0)
    artifact_store = ArtifactStore(Path("/tmp/artifacts"))
    registry = ToolRegistry(artifact_store)

    summarizer = SessionHandoffSummarizer(
        inference=inference,
        memory_store=memory_store,
        min_messages=4,
    )

    orchestrator = Orchestrator(
        inference=inference,
        session_store=session_store,
        context_builder=builder,
        tool_registry=registry,
        policy=policy,
        handoff_summarizer=summarizer,
    )

    test_session = Session(
        id="handoff_test_session",
        platform="test",
        platform_user="user1",
        started_at=datetime.now(),
        last_active_at=datetime.now(),
        slot_id=None,
        slot_saved_path=None,
        state=SessionState.ACTIVE,
        temperature=SessionTemperature.COLD,
    )

    # Create a session directly
    created = await session_store.create_session("test", "user1")

    # Record enough turns to meet min_messages
    for i in range(4):
        await session_store.append_message(
            created.id, Message(role="user", content=f"Message {i}")
        )
        await session_store.append_message(
            created.id, Message(role="assistant", content=f"Reply {i}")
        )

    # Close the session
    await orchestrator.close_session(created.id)

    # Assert handoff memory exists
    memories = await memory_store.list_memories(tag="handoff")
    assert len(memories) == 1
    assert "Python" in memories[0].content or "project" in memories[0].content
    assert memories[0].session_id == created.id

    # Assert session is archived
    archived = await session_store.get_session(created.id)
    assert archived.state == SessionState.ARCHIVED
