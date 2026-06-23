"""Integration test for session handoff summary flow."""

import pytest

from hestia.core.types import ChatResponse, Message, SessionState
from hestia.memory.store import MemoryStore
from hestia.orchestrator.engine import Orchestrator
from hestia.orchestrator.handoff_service import HandoffService
from hestia.orchestrator.mappers import message_domain_to_dto
from hestia.persistence.db import Database
from hestia.persistence.message_store import MessageStore
from hestia.persistence.session_store import SessionStore


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

    def auto_approve(self, tool_name, session, registry=None):
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
async def session_store(db, message_store, memory_store):
    store = SessionStore(
        db,
        message_store=message_store,
        memory_store=memory_store,
        inference_factory=lambda: FakeInferenceClient(),
    )
    yield store


@pytest.fixture
async def memory_store(db):
    store = MemoryStore(db)
    await store.create_table()
    yield store


@pytest.fixture
async def message_store(db):
    return MessageStore(db)


@pytest.mark.asyncio
async def test_full_handoff_cycle(session_store, message_store, memory_store):
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

    handoff_service = HandoffService(session_store, message_store)

    orchestrator = Orchestrator(
        inference=inference,
        session_store=session_store,
        context_builder=builder,
        tool_registry=registry,
        policy=policy,
        handoff_service=handoff_service,
    )

    # Create a session directly
    created = await session_store.create_session("test", "user1")

    # Record enough turns to meet min_messages
    for i in range(4):
        await message_store.append_message(
            created.id,
            message_domain_to_dto(Message(role="user", content=f"Message {i}"), created.id, idx=0),
        )
        await message_store.append_message(
            created.id,
            message_domain_to_dto(
                Message(role="assistant", content=f"Reply {i}"), created.id, idx=0
            ),
        )

    # Close the session
    await orchestrator.close_session(created.id)

    # Assert structured archive memory exists
    memories = await memory_store.list_memories(tag="task-state")
    assert len(memories) == 1
    assert "project" in memories[0].content.lower() or "python" in memories[0].content.lower()
    assert memories[0].session_id == created.id

    # Assert handoff message exists
    handoffs = await message_store.get_handoff_messages(created.id)
    assert len(handoffs) == 1
    assert "project" in handoffs[0].content.lower() or "python" in handoffs[0].content.lower()

    # Assert session is archived
    archived = await session_store.get_session(created.id)
    assert archived.state == SessionState.ARCHIVED
